"""Background task bookkeeping: open/finished/dismissed state and the per-line transcript handlers (notice, result, launch).
Split out of bgtasks (2026-09-24); bgtasks keeps reading, the lock, expiry/revival and the screen rows, and re-exports these names."""
import json
import os
import re
import time
from sidereus.config import DATA_DIR
from sidereus.warn import warn_once
from sidereus.bus import _atomic_write
from sidereus.memo import BoundedMemo
from sidereus.transcript import _TUID_RE, _line_ts
from sidereus.agents import _agent_meta
from sidereus.redact import redact

# ★Persistent tasks (Monitor etc.) — **the launch line is already outside the tail** and only notifications keep coming (measured: a watcher
#   launched at 09:40, and its `tool_use` is not within the current 20MB tail). So *the notifications themselves* are used as proof of life.
#   A notification with `<tool-use-id>` is **a completion notice**; one with only `<summary>` is **alive and emitting events**.
_TASKID_RE = re.compile(r"<task-id>([^<]+)</task-id>")
_SUMM_RE = re.compile(r"<summary>([^<]{1,70})")
# ★2026-10-06: a re-armed Monitor that had not emitted an event yet was invisible (rows came only
#   from heartbeats), and the 30-min expiry notice reuses the «Monitor event:» summary, so a dead watcher read as alive.
_MON_START_RE = re.compile(r"^Monitor started \(task ([A-Za-z0-9_-]+)")
_MON_EXPIRED = "[Monitor expired after"
_STOPPED_IDS_RE = re.compile(r"didn't finish before the previous session ended\. Task ids: ([A-Za-z0-9_, -]+)")
_mon_lab = BoundedMemo(200)    # Monitor tool_use id → (row label, line time), joined with its «Monitor started» result
# ⚠A foreground Bash that hits its timeout becomes a background task with no
#   `run_in_background` on its tool_use — only its result says so. Keep each foreground Bash's label until its result.
_fg_lab = BoundedMemo(400)     # foreground Bash tool_use id → (row label, line time)
# ⚠Anchored at the start of the result: a command whose OUTPUT merely contains these words (a grep of a transcript)
#   must not open a row.
#   Only the measured form (Bash timeout) is matched; a hand-backgrounded message was not seen in any transcript.
_FG_MOVED_RE = re.compile(r"^\s*Command did not complete within its \S+ timeout and was moved to the background")

# ★**Remember** running background tasks (cumulative). The tail alone misses them — measured 2026-08-19: the repo-A transcript
#   was **780MB**, so the 800KB tail was 209 lines and the running agent's *launch line* was pushed outside it, giving 0.
#   Widening the window is not the answer (the file keeps growing). Polling runs every 2.5s, so **seeing the launch moment once is enough**;
#   remember it then and remove it when the completion notice arrives.
#   ⚠A server restart empties the memory — things launched before it cannot be counted (we do not invent what we do not know).
_bg_open = {}          # transcript path → {tool_use_id: (kind, label)}
# ★`_bg_open` eviction uses **the last-touched time** (LRU) — evicting by insertion order picked exactly the wrong ones
#   (measured 2026-09-07 audit "cause 3"). `_recent_transcripts()` returns **newest first**, so right after startup
#   what enters `_bg_open` first is **the most active session now**. The old code was `list(_bg_open)[:100]`,
#   i.e. it evicted that active session first. Losing the record makes that session's agent rows flicker away and back.
#   ⚠An empty dict is also «seen» information — so the time is stamped on every scan of fp regardless of whether `_bg_open[fp]` exists.
_bg_open_at = {}       # transcript path → last scan time (eviction key. LRU)

# ⚠Seeding drops every completion, so one that finished while the viewer was down never rang the bell.
#   The per-fp scan clock is saved as «last alive time»; seeding announces only completions after it.
ALIVE_FILE = os.path.join(DATA_DIR, "bg-alive.json")
ALIVE_EVERY_S = 30
CATCHUP_MAX_AGE_S = 86400
_alive_last = [0.0]    # time of the last `_alive_beat` write (mutated in place)


def _alive_load(path):
    """{fp: epoch} from the alive file, or None when it is missing, unreadable, empty or holds future/non-number values."""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None                              # unknown alive time: seeding stays silent (startup grace only)
    if not isinstance(d, dict) or not d:
        return None
    lim, out = time.time() + 60, {}
    for k, v in d.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v > lim:
            return None                          # a future stamp would hide real completions; trust none of it
        out[k] = float(v)
    return out


_alive_prev = _alive_load(ALIVE_FILE)


def _alive_beat(now=None, force=False):
    """Persist `_bg_open_at` (merged over the previous run's entries, 24 h kept) at most every ALIVE_EVERY_S."""
    now = time.time() if now is None else now
    if not force and now - _alive_last[0] < ALIVE_EVERY_S:
        return
    _alive_last[0] = now
    cut = now - CATCHUP_MAX_AGE_S
    d = {k: v for k, v in (_alive_prev or {}).items() if v >= cut}   # fps not rescanned yet keep their old time
    d.update(_bg_open_at)
    try:
        _atomic_write(ALIVE_FILE, json.dumps({k: round(v, 3) for k, v in d.items()}).encode("utf-8"))
    except OSError as e:
        warn_once("bgalive", "Could not save the alive time ({err}) — completions while the viewer is down are not announced",
                  vars={"err": str(e)}, soft=True)


def _catchup_ok(fp, at, now):
    """Seeding: did this completion happen after the last alive time (and within 24 h)? ⚠Never true for at=0."""
    prev = _alive_prev
    if not at or prev is None:
        return False
    return at > prev.get(fp, max(prev.values())) and at > now - CATCHUP_MAX_AGE_S


_bg_seeded = set()      # marks that the **first-time** deep scan per session is done
_bg_finished = {}       # what **finished** in this scan (fp → [(kind, label)]) — announced via bell cards
# ★Manual dismissals are **kept in a file**. Memory-only means a restart's 20MB deep scan picks them up again
#   (measured 2026-08-19: a dismissed agent reappeared after two viewer restarts — the user caught it).
BG_DROP = os.path.join(DATA_DIR, "bg-dismissed.txt")
# ★A **dict**, not a set (tid → dismissal time). Order is needed — the old code cut a `set` with `list(...)[-500:]`,
#   but `list(set)` order is **undefined** (hash order). So not «the latest 500» but **an arbitrary 500**
#   were saved, and an item the user just dismissed with ✕ could be pushed out, leaving open the path where **a dismissed agent comes back
#   after restart** (measured 2026-09-07 audit "cause 3". The same symptom the user caught on 2026-08-19 —
#   "a dismissed agent reappeared after two restarts" — revives at the cap).
#   A dict preserves insertion order while membership (`in`) stays O(1) — this list is queried on the 2.5s polling path
#   (per tool_use inside `_running_bg`), so it must not become a list with O(n) scans.
#   ⚠**The in-memory side is not trimmed.** Removing a tid here «reverts a dismissal to undismissed» and
#     revives rows that must not be on screen. Entries grow only as often as a person presses ✕ (a few per day).
#     The cap was meant to «keep the file from growing forever», so it applies to file writes only.
_bg_dropped = {}


def _bg_drop_load():
    try:
        with open(BG_DROP, encoding="utf-8") as f:
            now = time.time()
            for x in f:                          # the file is written oldest → newest (load in that order)
                x = x.strip()
                if x:
                    _bg_dropped[x] = now
    except OSError:
        pass                                     # no drop list yet: nothing was dismissed


def _bg_drop_save(ids):
    for _i in ids:
        _bg_dropped.pop(_i, None)                # ★remove before inserting — reassigning an existing key in a dict
        _bg_dropped[_i] = time.time()            #   **does not move it to the end.** Otherwise it gets pushed out at the cap again
    try:
        keep = list(_bg_dropped)[-500:]          # cap — keeps the file from growing forever (now truly «the latest 500»)
        # ⚠Atomic swap: a crash mid-write used to leave a truncated list, and every lost tid revives a dismissed row.
        _atomic_write(BG_DROP, ("\n".join(keep) + "\n").encode("utf-8"))
    except OSError as e:
        warn_once("bgdrop", "Could not save the dismissed list ({err}) — items come back after a restart",
                  vars={"err": str(e)})


_bg_drop_load()


_bg_popped = BoundedMemo(4000)  # ⚠400 was evicted by one busy transcript, leaving rows to the 2h backstop. tid → time the completion notice was consumed. Revival checks this and does not revert it
# ★Map from a row **key → agent id** for rows relaunched by resume (`SendMessage`) (measured 2026-09-07:
#   2 origin subagents running but only 1 shown).
#   A resumed row's key is «that SendMessage's tool_use id» (so a later completion notice's `<tool-use-id>` removes it
#   exactly — reusing the old Agent tool_use id gets caught by `_bg_popped` and blocked again). But that key alone does not say
#   **who the row is** — `_agent_meta` is indexed only by «first Agent tool_use id → meta».
#   ⇒ Holding the reverse index here lets us (1) push out the same agent's old row to avoid duplicates (2) remove this row too when
#     removing by notice (3) keep revival from re-adding an agent already shown.
_bg_resume = BoundedMemo(400)  # resume tool_use id → agent id
_bg_sent = BoundedMemo(400)    # agent id → line time of the latest SendMessage to it (tells a resume from a trailing flush)
# ★2026-10-01: a resumed agent kept its spawn label (spawned with a bugfix task description,
#   resumed 04:32Z with summary "[pl:bugfix/<fix stage>] …") — the pipeline tab lit «Reproduce»/«Root cause»/«Fix» for finished work.
#   ⚠Only the SendMessage `summary` (a one-line label, same class as the Agent description) — never `message` (rule 1).
_bg_said = BoundedMemo(400)    # agent id → (line time, summary) of the latest SendMessage to it


def _sub_label(m, live_ts=None):
    """Row label "<agentType>: <label>": the latest SendMessage summary once the agent ran after it, else the description."""
    _said = _bg_said.get(m.get("_id") or "")
    _lab = m.get("description") or ""
    if _said and _said[1] and (live_ts is None or live_ts >= _said[0] - 30):
        _lab = _said[1]
    # ⚠Redact before the cut: a truncated `u:pw@host` loses its `@` and the userinfo pattern no longer matches.
    return (m.get("agentType") or "agent") + ": " + redact(_lab)[:40]
_RESUME_OK_RE = re.compile(r"Resuming agent|resumed from transcript|\"resumedAgentId\"")
# ★Resume success is judged from **the tool_result body**. The `SendMessage` result text was measured in three branches:
#     ① `{"success":true,"message":"Resuming agent a1b2c3d","resumedAgentId":"a1b2c3d4e5f6a7b8c",…}`
#        `{"success":true,"message":"Agent \"afb5…\" had no active task; resumed from transcript …"}`
#        ⇒ **a stopped agent relaunches.** The next completion notice carries this tool_use id.
#     ② `{"success":true,"message":"Message queued for delivery to a1b2c3d… at its next tool round."}`
#        ⇒ **already running.** Nothing new launches, and no notice comes with this tool_use id.
#     ③ `{"success":false,"message":"Agent … was stopped by the user and won't be resumed. …"}`
#        ⇒ nothing launches.
#   Only (1) keeps a row. Keeping a row in (2)(3) leaves no basis to ever remove it, so it sticks until the 2-hour backstop
#   (measured: in the same session a1b2c3d4 the SendMessage at 08:08:33 was (2) — row A was already shown then).


def _bg_pop(open_now, key, fp, seeding, done=True, at=0, line_at=0):
    """Remove from the open list. If what was removed is **an agent·command, record it as completed** (watchers come and go constantly, so excluded).
    ⚠Not recorded during seeding (old completions would flood out as cards right after server start) — except
      completions after the saved alive time (`_catchup_ok`).
    ★Record the removal time (measured 2026-08-28): a completion notice passes **only once**, and if revival below re-adds
      the same item afterwards there is no chance to ever remove it, so it stays until the 2-hour backstop. Three actually finished
      agents stuck on screen that way ("really 2 but 4 on screen")."""
    v = open_now.pop(key, None)
    # ★Record **whether removed or not** (measured 2026-08-31). Yesterday it was recorded only when `v` existed, so
    #   when the item was not yet in the list at notice time (during restart seeding the tool_use is outside the window, the notice inside)
    #   nothing was recorded, revival re-added it later, and it never went away.
    #   `svc-D-live` (2 completed, yet on screen for 20 min) was that case.
    #   This function is called **only when a completion signal is seen** — so recording unconditionally is right.
    # ⚠`at` = the notice line time: `_bg_sent` holds line times, so the read clock judged a late-read resume as consumed.
    #   +1s because `_line_ts` truncates to the second (else the agent's own pre-notice flush reads as «after»).
    _t = time.time()
    _bg_popped.put(key, min(at + 1, _t) if at else _t)
    # ★`done=False` means «removed **because it never ran**» (2026-09-08). The `_bg_popped` record
    #   that blocks revival is still made, but it is **not counted as completed** — turning a hook-blocked command into
    #   a "task complete" card would claim an execution that never happened.
    if v and done and v[0] in ("sub", "bg"):
        # `line_at` = line time for the catch-up check only; `_bg_popped` keeps its read-clock stamp on those paths
        at = at or line_at
        catchup = seeding and _catchup_ok(fp, at, _t)
        if seeding and not catchup:
            return
        label, aid = v[1], ""
        if v[0] == "sub":
            label, aid = _sub_identity(fp, key, label)
        # catch-up items carry (tid, completion time, True) so notes can dedup against the card file
        _bg_finished.setdefault(fp, []).append((v[0], label, aid, key, at, True) if catchup else (v[0], label, aid))


def _sub_identity(fp, key, label):
    """(label, agent id) for a finished agent row keyed by its Agent or resuming SendMessage tool_use id.
    ⚠The launch row may predate the meta file and fall back to «agent» — re-read the type here so the card carries
      the real one, and the agent id so a resume bumps that agent's card and never a same-brief relaunch (2026-09-24)."""
    sd = fp[:-len(".jsonl")] if fp.endswith(".jsonl") else fp
    try:
        meta = _agent_meta(sd)
    except Exception as e:                       # _agent_meta absorbs read errors itself — anything here is a fault
        warn_once("sub-ident", "agent type lookup failed ({err}) — launch label kept",
                  vars={"err": f"{type(e).__name__}: {e}"}, soft=True)
        return label, ""
    m = meta.get(key)
    if m is None and key in _bg_resume:
        m = next((x for x in meta.values() if (x.get("_id") or "") == _bg_resume[key]), None)
    if m is None:
        return label, ""
    desc = label.split(": ", 1)[1] if ": " in label else label
    return (m.get("agentType") or label.split(": ", 1)[0]) + ": " + desc, m.get("_id") or ""


def _mon_put(open_now, key, lab, ts):
    """Open a watcher row, pushing out older watchers with the same label (see the heartbeat comment below)."""
    for _ok, _ov in list(open_now.items()):
        if _ok != key and _ov[0] == "task" and _ov[1] == lab:
            open_now.pop(_ok, None)
    open_now[key] = ("task", lab, ts)


def _bg_on_notice(line, open_now, fp, seeding, now):
    """One `<task-notification>` line: watcher heartbeats, completion by tool-use-id, and by task-id (agent id)."""
    # ★A regex on the raw string **drags in JSON escapes too** (measured: labels had escapes mixed in, and
    #   in the proj-C session it picked up 21 task ids from someone else's body). Parse and look at **the body string**.
    if _is_replay(line):
        return                                   # replayed notice has no line time, so it would pop a resumed row
    try:
        d0 = json.loads(line)
    except ValueError:
        return                                   # half-written or non-JSON line: not a notification
    # ★Notifications come in two places. When the session is busy they sit in **the top-level `content` of a `queue-operation` line**
    #   (measured 2026-08-20: a completion notice clearly existed but the agent remained running —
    #    only `message.content` was checked, and that line was `type=queue-operation · content=<string>`).
    c0 = (d0.get("message") or {}).get("content") or d0.get("content")
    # ★Third place (measured 2026-09-24, repo-S dd44dd44 · CLI 2.1.281): `type=attachment` with
    #   `attachment={type: queued_command, commandMode: task-notification, prompt: "<task-notification>…"}`.
    #   The notice is in `attachment.prompt`, not message/content, so all 62 notices were skipped and 16 finished
    #   agents stayed «running». ⚠Keep the two older places — older transcripts still use them.
    if not c0 and isinstance(d0.get("attachment"), dict):
        c0 = d0["attachment"].get("prompt") or d0["attachment"].get("content")
    if isinstance(c0, str):
        txt = c0
    elif isinstance(c0, list):
        txt = " ".join((x.get("text") or "") for x in c0 if isinstance(x, dict))
    else:
        txt = ""
    if "<task-notification>" not in txt:
        return
    m = _SUMM_RE.search(txt)
    summ = (m.group(1).strip() if m else "")
    # ★The only proof of life is **the Monitor heartbeat**. Everything else (completed·stopped·no record) is finished —
    #   at first "no tool-use-id means alive" was used and counted `Agent … finished` as running.
    alive = summ.startswith("Monitor event:") and _MON_EXPIRED not in txt
    # a resumed session lists the previous run's unfinished tasks as stopped (ids in the summary, not in tags)
    _sm = _STOPPED_IDS_RE.search(txt)
    for tid in (_sm.group(1).replace(",", " ").split() if _sm else ()):
        open_now.pop("task:" + tid, None)
    for tid in _TASKID_RE.findall(txt):
        if alive:
            _lb = "감시 " + summ[14:].strip(' "')[:40]
            _k = "task:" + tid
            # ★★**Push out older watchers with the same label** (measured 2026-09-07: 2 still showing).
            #   Watchers are not expired by time (see `_bg_expire`), so a watcher that **never got
            #   its stop notice** stays in the list forever. It did — in the advocate session (b2c3d4e5)
            #   `beu8ozhfb` (last heartbeat 09-04 06:02) vanished without a stopped notice and
            #   `bo373wcua` (06:17) launched. The screen showed the same text as 2 rows for 70 hours.
            #   When a script is killed with `pkill` the harness **sometimes gives a stop notice and sometimes not**
            #   (the same file mixes `script failed (exit 143)` · `stopped` · no notice).
            #   ⇒ If a watcher with the same label **emitted a more recent heartbeat**, the old one handed its place
            #     to that successor. There is only one mailbox watcher per session (watch.sh launches with a single MAILBOX_ME).
            #   ⚠If both are truly alive and alternate heartbeats, only 1 shows — an error of showing one less of what exists.
            #     Less harmful than the current symptom (showing what is gone forever).
            _mon_put(open_now, _k, _lb, _line_ts(d0, now))
        else:
            open_now.pop("task:" + tid, None)
    # ★**Completion notices must also be handled here** — notice lines never reach `_bg_on_line`.
    #   Missing it left two already-finished agents as 'running' (measured 2026-08-19).
    # ⚠A notice written before the latest SendMessage to its agent is a late duplicate — it must not hide the resumed run.
    #   Compare line times (notice vs `_bg_sent`), never the arrival clock.
    _sd0 = fp[:-len(".jsonl")] if fp.endswith(".jsonl") else fp
    _nts = _line_ts(d0, 0)
    _keep = set()
    if _nts and not alive:
        _stale = {a for a in _TASKID_RE.findall(txt) if (_bg_sent.get(a) or 0) > _nts}
        if _stale:
            for _t7, _m7 in _agent_meta(_sd0).items():
                if (_m7.get("_id") or "") in _stale:
                    _keep.add(_t7)
            _keep.update(k for k, a in _bg_resume.items() if a in _stale)
    for tid in _TUID_RE.findall(txt):
        if tid not in _keep:
            _bg_pop(open_now, tid, fp, seeding, at=_nts)
    if not alive:
        # ★★A notification **sometimes lacks `<tool-use-id>`** (measured 2026-09-07 · a finished
        #   bugfix agent in repo-A was still shown). Of 56 non-Monitor notices in the same file,
        #   6 did, all from one agent — an agent that finished again after a resume (SendMessage).
        #   A `sub` row's key is **only the tool_use id**, so the removal target could not be found and it stayed
        #   'running' for 71 min. The else branch's `open_now.pop("task:"+tid)` above is
        #   **the watcher key space**, so it cannot remove subagents.
        #   ⇒ `<task-id>` is the agent id (= meta file name). Map back via meta's `toolUseId`.
        #   ⚠`alive` (Monitor heartbeats) also lacks tool-use-id, so it must be excluded —
        #     otherwise live watchers are removed on every heartbeat.
        # ★★**Removed** `"<tool-use-id>" not in txt` from the condition (measured 2026-09-07). Even with a tool-use-id,
        #   it **may not be that agent's current row key** — a resumed agent has a different
        #   tool-use-id per notice (session a1b2c3d4 · agent a1b2c3d4e5f6a7b8c:
        #     08:19:14Z tuid=toolu_01AAAA… (first Agent call)
        #     08:24:26Z tuid=toolu_01BBBB… (resuming SendMessage)
        #   same task-id, two tool-use-ids). So «find and remove all rows of that agent by task-id» is
        #   always done per notice — otherwise a row under an old key (added by revival)
        #   remains, the «show what is gone for 2 hours» failure.
        #   ⚠Normally (agents without resume) the meta `toolUseId` the task-id points to is **the same key** as the tuid
        #     already removed above, so the second `_bg_pop` has nothing to remove (harmless · no duplicate completion
        #     card either — `_bg_pop` leaves a card only when it actually removed something).
        _aids = set(_TASKID_RE.findall(txt))
        if _aids:
            for _t3, _m3 in _agent_meta(_sd0).items():
                if (_m3.get("_id") or "") in _aids and _t3 not in _keep:
                    _bg_pop(open_now, _t3, fp, seeding, at=_nts)
            # rows launched by resume (key is the SendMessage's tool_use id) are removed too if they are the same agent
            for _k3 in list(open_now):
                if _bg_resume.get(_k3) in _aids and _k3 not in _keep:
                    _bg_pop(open_now, _k3, fp, seeding, at=_nts)


def _json_ts(line):
    """Line time of a raw transcript line, 0 when unparsable."""
    try:
        d = json.loads(line)
    except ValueError:
        return 0
    return _line_ts(d, 0) if isinstance(d, dict) else 0


def _is_replay(line):
    """⚠`api-request-blob` lines replay earlier tool_use/notice blocks after their result, with no timestamp — not a turn."""
    return '"api-request-blob"' in line[:80]


def _bg_on_line(line, open_now, fp, seeding, now):
    """Any other line: stray completion ids, then tool_result / tool_use blocks."""
    if _is_replay(line):
        return
    if "tool-use-id" in line:
        _ats = _json_ts(line)
        for tid in _TUID_RE.findall(line):
            _bg_pop(open_now, tid, fp, seeding, line_at=_ats)   # completion notice — ended regardless of kind
    if '"tool_result"' not in line and '"tool_use"' not in line:
        return
    try:
        d = json.loads(line)
    except ValueError:
        return                                   # half-written or non-JSON line: nothing to track
    c = (d.get("message") or {}).get("content")
    if not isinstance(c, list):
        return
    for x in c:
        if not isinstance(x, dict):
            continue
        if x.get("type") == "tool_result":
            _bg_on_result(x, open_now, fp, seeding, _line_ts(d, 0))
        elif x.get("type") == "tool_use" and x.get("id"):
            _bg_on_launch(x, d, open_now, fp, now)


def _bg_on_result(x, open_now, fp, seeding, line_at=0):
    """A `tool_result` block: receipt (keep) vs synchronous end / failed launch (pop)."""
    tid = x.get("tool_use_id")
    if tid and tid in _mon_lab:
        cc0 = x.get("content")
        if isinstance(cc0, list):
            cc0 = " ".join((y.get("text") or "") for y in cc0 if isinstance(y, dict))
        ms = _MON_START_RE.match(cc0.strip()) if isinstance(cc0, str) else None
        if ms:
            _mon_put(open_now, "task:" + ms.group(1), *_mon_lab[tid])
        return
    if tid and tid in _fg_lab:
        cc1 = x.get("content")
        if isinstance(cc1, list):
            cc1 = " ".join((y.get("text") or "") for y in cc1 if isinstance(y, dict))
        if isinstance(cc1, str) and _FG_MOVED_RE.match(cc1):
            lab1, t1 = _fg_lab[tid]
            open_now.setdefault(tid, ("bg", lab1, t1))   # closed by its completion notice, like any background Bash
        return
    if tid and (open_now.get(tid) or ("",))[0] == "sub":
        # ★An Agent's tool_result is **a receipt, not completion** (measured 2026-08-19):
        #     "Async agent launched successfully. … agentId: …"
        #   counting it as completion made **running subagents look 'task complete'**.
        #   The real end is `<tool-use-id>` in `<task-notification>`. But synchronous calls (body is the report) may
        #   also exist, so keep it alive **only when it is a receipt**.
        cc = x.get("content")
        body = cc if isinstance(cc, str) else json.dumps(cc, ensure_ascii=False)
        # ★A resume (`SendMessage`) receipt is **not completion** either (measured 2026-09-07). Resume rows made by
        #   `_bg_on_launch` also have kind `sub` and go through this check — removing on the absence of "Async agent
        #   launched" would make **a resumed row vanish on the very next line**.
        #   ⇒ The resume success text (`_RESUME_OK_RE`, branch (1) of the three measured above) also counts as a receipt.
        #     (2) "Message queued …" · (3) "won't be resumed" drop out here — that is correct.
        if "Async agent launched" not in body and not _RESUME_OK_RE.search(body):
            # ⚠A SendMessage row that did not resume ((2) queued to a running agent · (3) refused) is not a
            #   completion: the agent is still running under its own row, or never restarted. done=True here
            #   put running agents into the bell's «N done» card.
            # ⚠line time passed: without it a foreground Agent that finished while the viewer was down got no card
            _bg_pop(open_now, tid, fp, seeding, done=not _bg_resume.get(tid), line_at=line_at)
        elif _bg_resume.get(tid):
            # resume confirmed ⇒ **push out the same agent's old row** (one agent = one row).
            # a row revival added under the old Agent tool_use id is cleaned up here.
            _aid4 = _bg_resume[tid]
            _sd4 = fp[:-len(".jsonl")] if fp.endswith(".jsonl") else fp
            for _k4, _m4 in _agent_meta(_sd4).items():
                if (_m4.get("_id") or "") == _aid4 and _k4 != tid:
                    open_now.pop(_k4, None)
            for _k4 in list(open_now):
                if _k4 != tid and _bg_resume.get(_k4) == _aid4:
                    open_now.pop(_k4, None)
    elif tid and (open_now.get(tid) or ("",))[0] == "bg":
        # ★★**A blocked·rejected background command never creates a task** (measured 2026-09-08:
        #   a docker command launch still shown as held). The two on-screen rows "command: Rebuild and start svc-D
        #   container" were that — calls blocked by the devil's-advocate hook, and scanning the full log for those three tool_use ids
        #   found **0 notices**, so waiting never removes them.
        #   The "bg only accepts the notification" rule above is itself right (counting receipts as completion makes it 0 the
        #   whole time it runs). What was missing is **a third case: a `tool_result` that is not a receipt**.
        #   Measured 7 days, 526: receipts 513 · hook blocked 9 · user rejected 2 · other errors 2 (model unavailable·permission).
        #   ⚠Do not remove on `is_error` alone — if a receipt ever carries that flag it would **erase a running
        #     command**. Check the absence of the receipt marker **as well** (pushes toward neither extreme).
        #   ⚠Do not go with a text whitelist — 4 causes appeared in 7 days and each new kind leaks again.
        #     `is_error` is a flag the harness sets regardless of kind (measured 13/13 all true).
        #   `done=False` — it never ran, so **it is not counted as completed**.
        if x.get("is_error"):
            cc2 = x.get("content")
            body2 = cc2 if isinstance(cc2, str) else json.dumps(cc2, ensure_ascii=False)
            if "running in background with ID" not in body2:
                _bg_pop(open_now, tid, fp, seeding, done=False)


def _bg_on_launch(x, d, open_now, fp, now):
    """A `tool_use` block that starts something: Agent, resuming SendMessage, or background Bash."""
    a = x.get("input") if isinstance(x.get("input"), dict) else {}
    if x.get("id") in _bg_dropped:
        return                            # already dismissed by a person — do not bring it back
    if _bg_popped.get(x.get("id")):
        return                            # ⚠already closed — a repeated tool_use must not re-open it (no result follows)
    if x.get("name") == "Agent":
        # ⚠No `subagent_type` = the harness default; take the real type from meta like the resume path (else «agent»,
        #   corrected again at completion by `_sub_identity`).
        _ty = a.get("subagent_type")
        if not _ty:
            _m8 = _agent_meta(fp[:-len(".jsonl")] if fp.endswith(".jsonl") else fp).get(x["id"]) or {}
            _ty = _m8.get("agentType")
        open_now.setdefault(x["id"], ("sub", (_ty or "agent") + ": "
                                      + redact(a.get("description") or "")[:40], _line_ts(d, now)))
    elif x.get("name") == "SendMessage":
        # ★★**A resume is also a «start»** (measured 2026-09-07: 2 origin subagents running
        #   but only 1 shown). The old parser made rows only from tool_use with `name == "Agent"`.
        #   But speaking to a finished agent again via `SendMessage` makes it work again —
        #   nothing triggers a row, and the original key (A) is caught by `_bg_popped` so revival does not
        #   bring it back either ⇒ **a working agent drops off the screen entirely.**
        #   Measured trace (session a1b2c3d4 · agent a1b2c3d4e5f6a7b8c):
        #     08:05:11Z Agent   tuid A=toolu_01AAAA…  → row A
        #     08:19:14Z notice(A) → row A removed · `_bg_popped[A]` recorded
        #     08:20:41Z SendMessage tuid B=toolu_01BBBB… "Resuming agent a1b2c3d"
        #               ⇒ **a row must exist here** (old code: none)
        #     08:24:26Z notice(B) → row B removed (hence the key is B — reusing A would be blocked again)
        # ⚠`SendMessage` **also sends to other sessions·teammates·cloud sessions.** Those are not this session's
        #   subagents, so no row must be made. Only when `input.to` is an agent id in this session's
        #   `agent-<id>.meta.json` — that guard is the distinction.
        # ★Whether the row really stays is decided by **the tool_result on the next line** ((1)/(2)/(3) of the `_RESUME_OK_RE`
        #   comment above). Create it here first; for (2)(3) `_bg_on_result` removes it. Reversing the order
        #   («create after seeing the result») makes it «not exist» for one round right after resume, and
        #   this file's principle is **saying what exists does not is worse**, so this order stays.
        _to = a.get("to")
        if isinstance(_to, str) and _to:
            _sd5 = fp[:-len(".jsonl")] if fp.endswith(".jsonl") else fp
            _m5 = None
            for _mm5 in _agent_meta(_sd5).values():
                if (_mm5.get("_id") or "") == _to:
                    _m5 = _mm5
                    break
            if _m5 is not None:
                _bg_resume.put(x["id"], _to)
                _bg_sent.put(_to, _line_ts(d, now))
                _sm = a.get("summary")
                _bg_said.put(_to, (_line_ts(d, now), " ".join(_sm.split()) if isinstance(_sm, str) else ""))
                # same "<agentType>: <label>" format as other `sub` rows; label = this SendMessage's summary if any.
                open_now.setdefault(x["id"], ("sub", _sub_label(_m5), _line_ts(d, now)))
    elif x.get("name") == "Monitor":
        # row opens on the «Monitor started (task <id>…)» result — notices key watchers by task id, not tool_use id.
        # ⚠Label = the one-line description only, never the command (rule 1); same «Watch » form as heartbeat rows.
        _mon_lab.put(x["id"], ("감시 " + redact(a.get("description") or "Monitor").strip(' "')[:40], _line_ts(d, now)))
    elif x.get("name") == "Bash" and a.get("run_in_background"):
        # ⚠Label = the one-line description only, never the command text (AGENTS.md rule 1, 2026-09-25).
        open_now.setdefault(x["id"], ("bg", redact(a.get("description") or "Bash")[:48], _line_ts(d, now)))
    elif x.get("name") == "Bash":
        _fg_lab.put(x["id"], (redact(a.get("description") or "Bash")[:48], _line_ts(d, now)))
