"""Background task tracking: open/finished/dropped bg tasks read from transcripts.
State and per-line handlers live in bgtasks_parse (split 2026-09-24); this module reads, locks, expires, revives and builds rows."""
import json
import os
import re
import threading
import time
from sidereus.warn import warn_once
from sidereus.memo import MISS, BoundedMemo
from sidereus.transcript import _tail_bytes
from sidereus.agents import _agent_busy, _agent_ended, _agent_last, _agent_meta, boot_time
from sidereus.perm_marks import note_sub_log
# ⚠Re-exported for importers (chat_server, sessions, notes, tests). Patch BG_DROP/warn_once/_atomic_write/_agent_meta
#   for the drop list and line handlers on bgtasks_parse — their functions read that module's globals.
from sidereus.bgtasks_parse import (_bg_open, _bg_open_at, _bg_seeded, _bg_finished, _bg_dropped, _bg_drop_save,
                                 _bg_popped, _bg_resume, _bg_sent, _sub_label, _bg_pop, _bg_on_notice, _bg_on_line,
                                 _alive_beat)
from sidereus.bgtasks_open import _bg_open_restore, _bg_open_save

RUN_STALE_S = 7200        # agents launched over 2 hours ago are not counted (a completion notice may have been missed)
SUB_LIVE_S = 120           # if the subagent log was updated within this, **treat it as running** (comment below)
REVIVE_GRACE_S = 30        # updates within this after a completion notice are treated as the 'last flush' and not revived
SUB_DONE_QUIET_S = 300     # a subagent whose last message is `end_turn` and quiet this long counts as done (see _retired)
_ENDED_TAIL = 262_144      # bytes read from the end of a subagent log to find its last message record
_ended_cache = BoundedMemo(500)   # agent log path → (mtime, bool)


def _ended_turn(f, mt):
    """True if the last user/assistant record in log `f` is an assistant turn with stop_reason end_turn,
    or a user tool_result answering a successful SubagentHandback (judged by `agents._agent_ended`)."""
    hit = _ended_cache.get(f, MISS, stamp=mt)
    if hit is not MISS:
        return hit
    res = False
    try:
        lines = _tail_bytes(f, _ENDED_TAIL)[0].decode("utf-8", "replace").splitlines()
        for l in reversed(lines):
            try:
                d = json.loads(l)
            except Exception:
                continue
            if d.get("type") not in ("user", "assistant"):
                continue                     # attachments (hooks·reminders) and system lines are not turns
            res = d["type"] == "assistant" and (d.get("message") or {}).get("stop_reason") == "end_turn"
            c = (d.get("message") or {}).get("content")
            if d["type"] == "user" and isinstance(c, list) and any(
                    isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                # ⚠A handback run ends on the tool_result, not end_turn — without this it was revived and never retired by (3).
                #   Only on a tool_result: a plain user prompt (resume) must stay open, though _agent_ended skips it.
                res = _agent_ended(f)
            break
    except OSError:
        res = False
    _ended_cache.put(f, res, stamp=mt)
    return res


_TUID_BYTES = re.compile(rb"<tool-use-id>([^<]+)</tool-use-id>")
_bg_skips = {}                 # fp → skip count (kept so it can be checked on screen)
_bg_skipped_mb = {}            # fp → cumulative MB skipped
_bg_gap_tids = []              # completion tids picked up in skipped spans — removed at the next decision

BG_SEED_BYTES = 20_000_000     # how far back to read on first sight
BG_MAX_READ = 24_000_000       # cap per read (runaway guard) — must exceed the seeding window (20MB) to avoid truncation
_bg_offset = {}                # fp → byte offset to start the next read


def _bg_lines(fp):
    """**From after the last read to end of file** — looking through a window (tail) misses things.

    ★Measured 2026-08-20: a completion notice was clearly at **1.9MB** from the end of the file, yet the agent stayed on screen.
      Polling looked only at the 400KB tail, and this session (771MB) wrote so fast that much passed between two polls.
      **Enlarging the window is not the answer** — whatever the size, faster writing misses again. Remembering the read position leaves no hole."""
    try:
        size = os.path.getsize(fp)
    except OSError:
        return []
    off = _bg_offset.get(fp)
    if off is None:
        off = max(0, size - BG_SEED_BYTES)      # first time seeing the file — look back at recent content only
    if off > size:
        off = 0                                  # the file was recreated (truncated)
    start = off
    if size - start > BG_MAX_READ:
        start = size - BG_MAX_READ
        # ★In a skipped span, **completion notices must still be picked up** (measured 2026-09-01).
        #   It used to just skip with a warning, so notices inside were never seen and finished agents
        #   stayed on screen (`repo-B-be` did this on a server up for 57 min — a restart fixed it).
        #   No JSON parsing. One regex over bytes suffices, and this path runs only when skipping.
        _bg_skips[fp] = _bg_skips.get(fp, 0) + 1
        _bg_skipped_mb[fp] = _bg_skipped_mb.get(fp, 0.0) + (size - off - BG_MAX_READ) / 1e6
        try:
            with open(fp, "rb") as f2:
                f2.seek(off)
                left = start - off
                while left > 0:
                    chunk = f2.read(min(8_000_000, left))
                    if not chunk:
                        break
                    left -= len(chunk)
                    for mm in _TUID_BYTES.finditer(chunk):
                        _bg_gap_tids.append(mm.group(1).decode("ascii", "ignore"))
        except OSError:
            pass                      # transcript vanished mid-read; the skip itself is warned just below
        warn_once("bgskip:" + os.path.basename(fp)[:8], "Background check skips {mb}MB — scanning notices only",
                  vars={"mb": f"{(size - off) / 1e6:.0f}"})
    # ⚠Line by line, never read()+decode()+splitlines() at once: ★that kept ~20MB raw + 26MB str + the list alive
    #   together in state() (tracemalloc peak 140MB on a 20MB seed), and CPython does not hand freed memory back.
    #   Same result: b"\n" never sits inside a UTF-8 sequence, so per-line "replace" decoding matches the whole-buffer
    #   decode; str.splitlines() still splits the other separators; a truncated first line survives only if it
    #   starts with "{", exactly as the old drop-then-filter did. Lines without b"{" cannot yield a kept piece.
    # ⚠Advance only past the last b"\n": a line still being written is left for the next read. Consuming it
    #   parsed a broken half now and dropped the tail next time (no leading "{") — a lost completion notice
    #   kept the agent «Running» forever. Same streaming rule as `_tail_incr`.
    out = []
    end = start
    try:
        with open(fp, "rb") as f:
            f.seek(start)
            for raw in f:
                if not raw.endswith(b"\n"):
                    break                        # trailing partial line — only possible as the last one
                end += len(raw)
                if b"{" not in raw:
                    continue
                for l in raw.decode("utf-8", "replace").splitlines():
                    if l.lstrip().startswith("{"):
                        out.append(l)
    except OSError:
        return []
    _bg_offset[fp] = end
    return out


# ★`_running_bg` mutates **module globals** (_bg_open · _bg_seeded · _bg_offset). But this server is
#   ThreadingHTTPServer, so `sessions()` is called concurrently from multiple threads (2.5s poll + timeline +
#   work history + failure tab). With no lock there was **an alert bomb right after startup** (measured 2026-09-02):
#     (a) thread A: `seeding = fp not in _bg_seeded` → True, then `_bg_seeded.add(fp)`
#     (b) thread B: same check right after → **False**. But A has not advanced `_bg_offset` yet, so
#        B also reads the whole seeding window (20MB) → every old completion notice in it
#        is processed with `seeding=False` and **48 completion cards flooded out at once**.
#   Repro: 48 cards 15s after restart (repo-E·repo-B-fe … ones finished days earlier).
_bg_lock = threading.Lock()


def _running_bg(fp, rows=None):
    with _bg_lock:
        return _running_bg_locked(fp, rows)


def bg_dismiss(cwd, tid, cwd_of):
    """Drop open sub/bg entries (one tid, or all for cwd); returns count removed."""
    # ⚠Under _bg_lock: the poll thread iterates _bg_open values in _running_bg_locked (RuntimeError/KeyError otherwise).
    gone, dropped = 0, []
    with _bg_lock:
        for fp, opened in list(_bg_open.items()):
            for k, v in list(opened.items()):
                if tid and k != tid:
                    continue
                if v[0] in ("sub", "bg") and (tid or not cwd or cwd_of(fp) == cwd):
                    opened.pop(k, None)
                    dropped.append(k)
                    gone += 1
        if dropped:
            _bg_drop_save(dropped)        # ★Persisted to file — does not come back after a restart
    return gone


def _sub_transcripts(fp, now, max_age=6 * 3600):
    """Subagent transcripts of the session `fp` touched within `max_age` seconds (newest work only)."""
    d = os.path.join(fp[:-len(".jsonl")] if fp.endswith(".jsonl") else fp, "subagents")
    try:
        names = os.listdir(d)
    except OSError:
        return []
    out = []
    for n in names:
        if n.endswith(".jsonl"):
            p = os.path.join(d, n)
            try:
                mt = os.path.getmtime(p)
            except OSError:
                continue                  # removed between listdir and stat: nothing to scan
            if now - mt <= max_age:
                out.append(p)
    return out


def _running_bg_locked(fp, rows=None):
    """Currently running subagents·background commands. Lines are supplied **without gaps** by `_bg_lines()`.

    ★There are two completion signals and **they differ by kind** (got it wrong twice by measurement):
      · `<tool-use-id>` in `<task-notification>` — the real end of a background task. **Both end here.**
      · `tool_result` — Agent also ends with this, but `Bash(run_in_background)` returns a task id **immediately on launch**,
        so counting it as completion makes it 0 the whole time it runs. So bg only accepts the notification.
    ⚠Every step below runs under `_bg_lock` (held by `_running_bg`) — call them only from here.
    """
    open_now = _bg_open.setdefault(fp, {})
    _bg_open_at[fp] = time.time()       # ★touch — the eviction (LRU) below looks only at this time
    seeding = fp not in _bg_seeded      # the first scan makes no 'completion cards' (old ones would flood out at once)
    _bg_seeded.add(fp)
    now = time.time()
    if seeding:
        _bg_open_restore(fp, open_now, boot_time())   # before the lines, so a notice read now still closes the row
    # ⚠A subagent's own Bash shells (background, or a foreground call moved to the background at its timeout) are
    #   recorded only in that agent's transcript, while their completion notices land in this parent transcript.
    #   Read the agents' Bash lines first so a launch and its notice in the same tick open then close in order.
    for sfp in _sub_transcripts(fp, now):
        for line in _bg_lines(sfp):
            # ⚠A receipt line carries no '"Bash"'; without the third test its output path was never stored.
            # ⚠A hook-denied launch gets only an is_error tool_result (no receipt, no notice) — forward it or the row never closes.
            if ('"Bash"' in line or "moved to the background" in line or "running in background with ID" in line
                    or '"is_error":true' in line or '"is_error": true' in line):
                _bg_on_line(line, open_now, fp, seeding, now)
    rows = _bg_lines(fp)
    for line in rows:
        if "<task-notification>" in line:
            _bg_on_notice(line, open_now, fp, seeding, now)
        else:
            _bg_on_line(line, open_now, fp, seeding, now)
    _bg_gap_flush(open_now, fp, seeding)
    # ⚠Stamp after the scan so the saved alive time covers every line read; force it when a card is due,
    #   else a restart within 30 s re-announces that completion.
    _bg_open_at[fp] = time.time()
    _alive_beat(force=bool(_bg_finished.get(fp)))
    _bg_evict()
    _bg_expire(open_now, now)
    _bg_revive(fp, open_now, now)
    _bg_open_save(fp, open_now)
    return _bg_result(fp, open_now)


def _bg_gap_flush(open_now, fp, seeding):
    # ★Remove completion tids picked up in skipped spans here — those lines did not go through the parse path.
    if _bg_gap_tids:
        for _gt in _bg_gap_tids:
            _bg_pop(open_now, _gt, fp, seeding)
        _bg_gap_tids.clear()


def _bg_evict():
    if len(_bg_open) > 200:
        # ★Evict **the least recently touched first** (LRU) — the old code was `list(_bg_open)[:100]`, i.e. dict insertion order,
        #   picking «files registered first». But what registers first right after startup is the newest·most active session
        #   (`_recent_transcripts` is newest first), so **the currently running session's records were evicted first**. That made the session's
        #   agent·background rows vanish from the screen and revive on the next deep scan — a flicker.
        #   ⚠Eviction creates an «unknown state» — never pick an active one.
        #   Measured 2026-09-07: `_bg_open` at this server's start had 4 (4 transcripts within 12 hours) and
        #   there are 99 transcript files overall, so the cap of 200 is rarely reached — a latent defect, but
        #   the moment it is reached it becomes the worst choice of «dropping the most important first», so it is fixed.
        for k in sorted(_bg_open, key=lambda x: _bg_open_at.get(x, 0))[:100]:
            _bg_open.pop(k, None)
            _bg_open_at.pop(k, None)


def _bg_expire(open_now, now):
    for key, v in list(open_now.items()):
        # ★Watchers (task) are **not expired by time** (measured 2026-08-24 · a live monitor was not shown).
        #   Claude Code itself showed `1 monitor` alive in the footer while the viewer showed 0. The last
        #   event was 808 min ago, so the 2-hour limit caught it. **Being quiet when there is nothing to watch is normal** for a watcher,
        #   so liveness must not be measured by event gaps — raising 30 min to 2 hours still repeated the same failure.
        #   When the session dies the rows themselves are emptied (dead in _bg_show), and wrongly remaining ones can be dismissed with ✕.
        #   The principle stands: **saying what exists does not is worse.**
        # Background shells (bg) are exempt too: dev servers outlive 2h; they close on their notice, error receipt, session death or ✕.
        if v[0] in ("task", "bg"):
            continue
        if now - v[2] > RUN_STALE_S:
            open_now.pop(key, None)  # drop old ones — do not decide whether finished or quiet (unknown is not counted)


BG_IDLE_S = 900            # an open bg shell whose output file has not grown for this long counts as idle


def bg_idle(fp, now):
    """{"n": open bg shells, "idle": idle count, "max": longest idle seconds} for session `fp`, or None when none is idle.
    ⚠stat only (never opens the output file); called per poll — the parse cache would freeze the elapsed time."""
    with _bg_lock:
        paths = [v[3] if len(v) > 3 else "" for v in (_bg_open.get(fp) or {}).values() if v[0] == "bg"]
    bt = boot_time()
    k, mx = 0, 0
    for p in paths:
        if not p:
            continue
        try:
            mt = os.stat(p).st_mtime
        except OSError:
            continue
        if bt and mt < bt:
            continue                  # written before the reboot: the shell cannot still be running
        if now - mt > BG_IDLE_S:
            k += 1
            mx = max(mx, int(now - mt))
    return {"n": len(paths), "idle": k, "max": mx} if k else None


def _bg_revive(fp, open_now, now):
    """Re-add agents whose own log shows fresh activity, and the ancestors of any open agent."""
    # ★Revive resumed agents (measured 2026-08-26). `<task-notification>` is **not a completion notice** —
    #   the notification body itself says so:
    #     "A task-notification fires each time this agent stops with no live background children of its
    #      own. The user can send it another message and resume it, so the same task-id may notify more
    #      than once."
    #   An agent was actually notified as `status:failed` (the computer slept and the response broke off), then a person spoke
    #   to it again and it resumed, but the viewer treated that one notice as completion and removed it, so **the agent running now
    #   vanished from the screen** (its log had been updating until 9s before).
    #   Proof of life is not the notice but **the update time of that agent's own log file**. Trust only that.
    #   ⚠A finished agent also lingers up to SUB_LIVE_S — a short error of saying what is gone exists, but
    #     it follows this file's principle that saying what exists does not is worse.
    try:
        _sd = fp[:-len(".jsonl")] if fp.endswith(".jsonl") else fp
        # ★**Do not re-add an agent already shown as a resume row** (measured 2026-09-07). A resume row's key is
        #   the SendMessage's tool_use id and the key here is the first Agent tool_use id, so comparing keys alone shows
        #   the same agent as **two rows** (the number the user counts goes wrong). Reverse-index via `_bg_resume`.
        #   ⚠Same for resume rows a person dismissed with ✕ — reviving a dismissed one under the old key is wrong (the recurrence
        #     path of the failure caught on 2026-08-19 as "a dismissed agent reappeared").
        _live_aids = set()
        for _k9, _a9 in _bg_resume.items():
            if _k9 in open_now or _k9 in _bg_dropped:
                _live_aids.add(_a9)
        for _tid, _mm in _agent_meta(_sd).items():
            if _tid in _bg_dropped or _tid in open_now:
                continue
            if (_mm.get("_id") or "") in _live_aids:
                continue
            _f2 = _mm.get("_file") or ""
            _mt = os.path.getmtime(_f2) if _f2 and os.path.exists(_f2) else 0
            _bt = boot_time()
            if _bt and _mt and _mt < _bt:
                continue                      # do not revive ones that stopped before the reboot
            # ★Do not revive ones whose completion notice was already consumed — revert **only if there is new activity after it**
            #   (the case where a person spoke to it again and it resumed). Without this, finished ones stayed forever.
            # ★Keep a generous grace. The agent's log is updated once more **after** the completion notice too
            #   (measured 2026-09-01: the last record landed at notice +283s — the harness's last flush).
            #   At 5s that was read as 'new activity' and revived, and since no notice comes again it stayed forever.
            #   A person resuming by speaking again produces activity much later than that.
            # ★2026-09-24: a resumed agent (log grew after the notice with a turn that has not ended) is live again at once,
            #   and stays live up to SUB_DONE_QUIET_S of quiet (a long tool_use) — stale duplicate notices re-pop it.
            _pt = _bg_popped.get(_tid)
            _open_turn = bool(_mt) and now - _mt <= SUB_DONE_QUIET_S and not _ended_turn(_f2, _mt)
            # ⚠Open turn alone is not a resume: a killed/failed agent's trailing flush (no end_turn) lands within grace too.
            #   Bypass grace only when a SendMessage to it came around/after the notice.
            _resumed = (_bg_sent.get(_mm.get("_id") or "") or 0) >= (_pt or 0) - REVIVE_GRACE_S
            if _pt and _mt <= _pt + REVIVE_GRACE_S and not (_open_turn and _mt > _pt and _resumed):
                continue
            if _mt and (now - _mt <= SUB_LIVE_S or (_open_turn and now - _mt <= SUB_DONE_QUIET_S)):
                open_now[_tid] = ("sub", _sub_label(_mm, _mt), _mt)
        # ★**If a live descendant exists, the ancestor is alive too** (measured 2026-09-02).
        #   The screen showed only a depth-2 `claude`, and the depth-1 `repo-B-bugfix` that launched it was
        #   missing — the parent was quiet waiting for the child, so SUB_LIVE_S (120s) dropped it, and its completion notice
        #   had already been consumed once. That leaves **an orphan** on screen and the lineage becomes false.
        #   The basis for ignoring the completion notice is in the notice body itself: a notice goes out "when it has no background
        #   children of its own", and on resume goes out again with the same task-id. A parent cannot have
        #   finished while a descendant runs — this is not a guess but an ordering the harness guarantees.
        _byid = {}
        for _t2, _m2 in _agent_meta(_sd).items():
            if _m2.get("_id"):
                _byid[_m2["_id"]] = (_t2, _m2)
        for _t2 in list(open_now):
            _m2 = _agent_meta(_sd).get(_t2)
            _guard = 0
            while _m2 and _m2.get("parentAgentId") and _guard < 8:
                _guard += 1
                _par = _byid.get(_m2["parentAgentId"])
                if not _par:
                    break
                _pt2, _pm2 = _par
                if _pt2 in _bg_dropped:
                    break                     # do not revive what a person dismissed
                if (_pm2.get("_id") or "") in _live_aids:
                    _m2 = _pm2                # that parent is already shown as **a resume row** — do not make it two rows
                    continue
                if _pt2 not in open_now:
                    _pf = _pm2.get("_file") or ""
                    try:
                        _pmt = os.path.getmtime(_pf) if _pf else 0
                    except OSError:
                        _pmt = 0
                    open_now[_pt2] = ("sub", _sub_label(_pm2, _pmt or now), _pmt or now)
                _m2 = _pm2
    except OSError:
        pass                                  # race: an agent log vanished mid-scan
    except Exception as e:
        warn_once("bgrevive", "Agent revive scan failed ({err}) — some agent rows may be missing",
                  vars={"err": type(e).__name__})


def _bg_result(fp, open_now):
    """Assemble (subs, bgs, watchers) rows for the screen."""
    # Split into three — **calling a watcher (Monitor) an 'agent' is wrong** (different nature).
    # ★Include elapsed time — completion notices **get lost** (the harness said so itself once:
    #   "No completion record was found for background agent …"). Then something finished stays 'running' forever.
    #   Alive or dead cannot be known from files (subagent conversations are not in the transcript), so **do not decide;
    #   show how long it has been** — 95 min in a room where 6 finished in 5~25 min lets a person judge.
    # ★Elapsed is **not computed here.** Parse results freeze in the cache, so while the file does not change
    #   the number stays still (measured 2026-08-20: screen 49 min · actual 52 min, 108 vs 111 — always ~3 min behind).
    #   Pass only raw timestamps and count against the current time **when drawing the row**.
    # ★Subagents take what they are doing now from **their own transcript** (see _agent_meta comment above).
    #   open_now's key is the parent's tool_use id and equals meta's toolUseId, so they link without guessing.
    sess_dir = fp[:-len(".jsonl")] if fp.endswith(".jsonl") else fp
    meta = _agent_meta(sess_dir)

    def _meta_of(key):
        """Find meta by row key. ★A resume row's key is «the SendMessage's tool_use id», so it is not in `meta`
        (the meta index is «first Agent tool_use id → meta»). Left as-is, `_lab` returns the short 2-slot form and
        **lineage (own id · parent id)·depth·current task·quiet time are all missing** — the screen tree
        cannot link that row, and before/after resume look like different kinds of rows (measured 2026-09-07: revived rows
        showed as `aid=?`). Get the agent id via `_bg_resume` and map back."""
        if not key:
            return None
        m = meta.get(key)
        if m:
            return m
        _aid = _bg_resume.get(key)
        if _aid:
            for _mm in meta.values():
                if (_mm.get("_id") or "") == _aid:
                    return _mm
        return None

    def _lab(v, key=None):
        m = _meta_of(key)
        if m:
            f = m.get("_file") or ""
            now_doing = _agent_last(f)
            try:
                idle = int(time.time() - os.path.getmtime(f))
            except OSError:
                idle = -1
            note_sub_log(m.get("_id") or "", f)   # perm_marks stats it per poll: `idle` is frozen until the next refresh
            # ★Also pass lineage (own id · parent id) — a depth number alone is not enough for the screen
            #   to build a tree (with several at the same depth it cannot tell whose child it is).
            return [v[1], v[2], now_doing, int(m.get("spawnDepth") or 1), key, idle,
                    m.get("_id") or "", m.get("parentAgentId") or "", _agent_busy(f)]
        return [v[1], v[2]]

    def _notice_consumed(key, aid):
        """True if a completion notice for this agent (any of its row keys) was consumed and no SendMessage came after it."""
        keys = {key} | {k for k, mm in meta.items() if aid and (mm.get("_id") or "") == aid}
        keys |= {k for k, a in list(_bg_resume.items()) if aid and a == aid}
        pts = [t for t in (_bg_popped.get(k) for k in keys) if t]
        if not pts:
            return False
        return (_bg_sent.get(aid) or 0) < max(pts) - REVIVE_GRACE_S   # same resume test as _bg_revive

    def _retired(key):
        """Is this agent no longer running. Two grounds:
        (1) **stopped before boot** — orphaned by a reboot (certain).
        (2) its own log **ended with a final report** and has been quiet since — finished even without a completion notice.
        ★Resume rows are also mapped back via `_meta_of` for the same decision — otherwise resume rows orphaned by
          a reboot miss (1) and remain."""
        m = _meta_of(key)
        f = (m or {}).get("_file") or ""
        if not f:
            return False
        try:
            mt = os.path.getmtime(f)
        except OSError:
            return False
        bt = boot_time()
        if bt and mt < bt:
            return True                       # stopped before the reboot — that process does not exist
        # ★The "last line is a final report + quiet" rule was **removed** (measured 2026-08-28, pointed out via user screenshot).
        #   `migration-legacy-analyst` was 18m39s into writing a large document and vanished from the list.
        #   **While generating a long response no lines are appended to the transcript** — exactly the same look as 'finished and quiet'.
        #   From outside the two states cannot be told apart.
        #   ⇒ Do not declare death from quiet (this file's principle). There are only two real grounds:
        #     (1) before boot (above) (2) a **completion notice** the parent received (handled by _bg_pop) — plus the 2-hour backstop.
        # ★(3) added 2026-09-24: the last *message* record is an assistant turn with `stop_reason == "end_turn"` and the log
        #   has been quiet for SUB_DONE_QUIET_S. Unlike the removed rule this is not «looks like text»: streamed blocks carry
        #   stop_reason None (thinking/text mid-message) or "tool_use", so a long generation or a long tool never matches.
        #   Needed because the parent can move to a new transcript (session fork: repo-S cc33cc33 → dd44dd44) and the notice
        #   lands only in the new file, leaving the old file's row open forever.
        #   ⚠Not retired while an open row is its child — an agent that ended its turn waiting on a child is woken again.
        _aid = (m or {}).get("_id") or ""
        # (4) its completion notice was consumed, nothing resumed it since, and its own log stayed quiet for
        #   SUB_DONE_QUIET_S — done whatever its last record is. ⚠A finished agent whose log ends on a `user` record
        #   (or a mid-stream assistant one) never matches (3); once a revive re-opened its row it stayed «running»
        #   until the RUN_STALE_S backstop. A resumed agent is excluded by `_bg_sent`, and its fresh log lines reset the quiet window.
        _quiet = time.time() - mt >= SUB_DONE_QUIET_S
        if not _quiet or not (_ended_turn(f, mt) or _notice_consumed(key, _aid)):
            return False
        for _k6 in open_now:
            if _k6 != key and _aid and ((_meta_of(_k6) or {}).get("parentAgentId") or "") == _aid:
                return False
        return True
    subs = [v for v in open_now.values() if v[0] == "sub"]
    bgls = [v for v in open_now.values() if v[0] == "bg"]
    # ★Elapsed is counted **per kind** — merging and taking the max attaches an old *command*'s time to the *agent* label
    #   (2026-08-19: a 5-minute-old agent showed as 107 min). And with several, the max must not be presented
    #   as that one item's age — the screen labels it `Longest`.
    # ★Watchers too as [label, time] — previously only labels were sent, so "how long quiet" could not be counted on screen.
    #   Watchers are not expired (comment above), so showing the silent duration is the only basis for judgment.
    sub_keys = [k for k, v in open_now.items() if v[0] == "sub" and not _retired(k)]
    return ([_lab(open_now[k], k) for k in sub_keys], [_lab(v) for v in bgls],
            [_lab(v) for v in open_now.values() if v[0] == "task"])
