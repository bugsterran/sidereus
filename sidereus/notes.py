"""Card triggers: bg-task done, context warnings and session state transitions."""
import json
import os
import re
import time
from datetime import datetime
from sidereus.transcript import _tail_lines, iso_epoch
from sidereus.live import sid_alive, sid_alive_stale
from sidereus.cards import CARDS, _card_add, _card_bump, _prev_state
from sidereus.agents import _agent_meta
from sidereus.bgtasks import _bg_finished


_ENDED = {"wait", "ask", "abort"}
_WORKING = {"tool", "think"}
# ★Context-near-full card — shown only in the top bar, it is **missed while not looking at the tab.**
#   Compaction loses context, and this project runs on handover docs ⇒ **a window to intervene before compaction** is the value.
#   ⚠Noise judgment: idle alerts were removed but this is kept, for different reasons —
#     (a) **once per session** (idle repeats as long as the condition holds) (b) **it demands action** (leave a handover).
#   When compaction actually happens the value drops sharply ⇒ below 60% the mark is released to warn **again next cycle**.
CTX_WARN = 0.85
CTX_REARM = 0.60
CTX_CARD_EVERY_S = 4 * 3600   # if already alerted for the same session within this, do not alert again (a criterion that survives restarts)
_ctx_warned = set()


START_AT = time.time()
CARD_GRACE_S = 60          # no completion cards for this long right after startup


def _note_bg_done(fp, info):
    """Announce that an agent·background task **finished** (agent completion was not tracked before).
    Launch and walk away and you do not know it finished — that is why the bell exists.
    Noise judgment: completion happens **once** and means a result arrived, so it is worth seeing (unlike idle alerts)."""
    got = _bg_finished.pop(fp, [])
    # ★The first 60s after startup are **discarded** (safety net). In that window 'just finished' and 'old completion
    #   already inside the window' cannot be told apart — the lock above prevents the race, but the seeding boundary is inherently ambiguous.
    #   The cost of missing is a few cards; the opposite cost is the bell buried in old completions (measured 48).
    #   Catch-up items (after the saved alive time, bgtasks_parse `_catchup_ok`) pass, capped and deduped by the card file.
    grace = time.time() - START_AT < CARD_GRACE_S
    seen = None
    for it in got:
        catchup = len(it) > 5 and it[5]
        if grace and not catchup:
            continue
        kind, label = it[0], it[1]
        aid = it[2] if len(it) > 2 else ""
        extra = None
        if catchup:
            tid, done_at = it[3], it[4]
            if seen is None:
                seen = _catchup_seen()
            if _catchup_n[0] >= CATCHUP_MAX or tid in seen[0] or (aid and seen[1].get(aid, -1.0) >= int(done_at)):
                continue
            _catchup_n[0] += 1
            seen[0].add(tid)
            extra = {"tid": tid, "done_at": datetime.fromtimestamp(done_at).isoformat(timespec="seconds")}
            if aid:
                extra["aid"] = aid
        if kind == "sub":
            _note_agent_done(fp, info, label, aid, extra)
            continue
        _card_add("bgdone", info.get("project", ""), "Background done", label, info.get("cwd", ""), extra)


CATCHUP_MAX = 20           # catch-up cards per process — a long downtime must not bury the bell
_catchup_n = [0]           # catch-up cards written so far (mutated in place)


def _catchup_seen():
    """(tids, {aid: newest card epoch}) from the last 24 h of cards — a catch-up already shown must not repeat."""
    cut, tids, aids = time.time() - 86400, set(), {}
    for line in _tail_lines(CARDS, nbytes=400000, limit=2000):
        try:
            c = json.loads(line)
        except ValueError:
            continue
        t = iso_epoch(c.get("at"), None)
        if t is None or t < cut or c.get("kind") not in ("bgdone", "agent"):
            continue
        if c.get("tid"):
            tids.add(c["tid"])
        if c.get("kind") == "agent" and c.get("aid"):
            aids[c["aid"]] = max(t, aids.get(c["aid"], -1.0))
    return tids, aids


def _agent_of(fp, label):
    """(agent id, real type) for a completion label `"<type>: <description>"`, from the session's agent meta files.
    ⚠An `Agent` launch without `subagent_type` is labelled «agent» (bgtasks `_bg_on_launch`), while its resume
      label comes from meta («general-purpose») — so the same agent showed under two names (2026-09-24)."""
    desc = label.split(": ", 1)[1] if ": " in label else label
    sd = fp[:-len(".jsonl")] if fp.endswith(".jsonl") else fp
    best, best_mt = None, -1.0
    for m in _agent_meta(sd).values():
        if (m.get("description") or "")[:40] != desc:
            continue
        try:
            mt = os.path.getmtime(m.get("_file") or "")
        except OSError:
            mt = 0.0
        if mt > best_mt:
            best, best_mt = m, mt
    return (best.get("_id") or "", best.get("agentType") or "") if best else ("", "")


def _note_agent_done(fp, info, label, aid="", extra=None):
    """One card per agent: a resumed agent's completion bumps its earlier card (time, `resumes` +1) instead of adding one.
    `aid` comes from bgtasks `_sub_identity`; the description lookup is only a fallback when it could not be resolved."""
    desc = label.split(": ", 1)[1] if ": " in label else label
    if not aid:
        aid, atype = _agent_of(fp, label)
        if atype:
            label = atype + ": " + desc
    cwd = info.get("cwd", "")

    def same(c):
        # ⚠With an id, match by id only — a relaunch with the same brief is a different agent and keeps its own card.
        if aid:
            return c.get("aid") == aid
        t = c.get("text") or ""
        return not c.get("aid") and (t.split(": ", 1)[1] if ": " in t else t) == desc   # cards written before `aid` existed

    more = dict(extra or {}, **({"aid": aid} if aid else {}))
    bumped = _card_bump("agent", cwd, same, lambda c: {"resumes": int(c.get("resumes") or 0) + 1,
                                                       "text": label, **more})
    if bumped is None:
        _card_add("agent", info.get("project", ""), "Subagent done", label, cwd, more or None)


def _recent_card(kind, cwd, within_s):
    """Was there a recent card of the same kind·same session — dedup whose **memory survives restarts**.
    ★Using only an in-memory set (`_ctx_warned`) re-alerts on every server restart (measured 2026-08-19:
      24 `Context nearly full` cards piled up over ten viewer restarts).
      The card file itself is already the source of truth, so **decide from it** (no new state file)."""
    cut = datetime.now().timestamp() - within_s
    for line in _tail_lines(CARDS, nbytes=60000, limit=200):
        try:
            c = json.loads(line)
        except Exception:
            continue
        if c.get("kind") != kind or c.get("cwd") != cwd:
            continue
        t = iso_epoch(c.get("at"), None)
        if t is not None and t >= cut:
            return True
    return False


def _note_ctx(info):
    # ★Context-near-full is also not alerted by default.
    #   The top bar already has a `Context 85%+ N` cell, and it is **a static indicator**, so not noise.
    #   The bell keeps only "things demanding action": waiting on question · interrupted · agent done.
    #   To revive: `MAILBOX_CARD_CTX=1`.
    if os.environ.get("MAILBOX_CARD_CTX") != "1":
        return
    win, ctx = info.get("win") or 0, info.get("ctx") or 0
    if not win or not ctx or info.get("state") == "done":
        return
    key = info.get("sid") or info.get("cwd") or info.get("id")   # per session, same reason as _note_transition
    r = ctx / win
    if r < CTX_REARM:
        _ctx_warned.discard(key)              # compacted — release so it can alert again next cycle
        return
    if r < CTX_WARN or key in _ctx_warned:
        return
    if _recent_card("ctx", info.get("cwd", ""), CTX_CARD_EVERY_S):
        _ctx_warned.add(key)          # already alerted — just fill the memory and pass quietly
        return
    _ctx_warned.add(key)
    pct = int(r * 100)
    _card_add("ctx", info.get("project", ""), "Context nearly full",
              f"{pct}% ({ctx // 1000}k / {win // 1000}k) — leave a handover before auto-compaction",
              info.get("cwd", ""), {"pct": pct, "used": ctx // 1000, "win": win // 1000})   # numbers let the page translate


def _note_transition(info):
    """Leave a card on a state transition — **only the moment a turn ends** (not start·middle; that would be noise again)."""
    # ⚠Key by session, not cwd — two live sessions in one folder (abort + think) alternated in one cwd slot and
    #   raised a «Aborted» card every poll (2026-09-24: 437 cards in ~5 min).
    key = info.get("sid") or info.get("cwd") or info.get("id")
    now_st, prev = info.get("state"), _prev_state.get(key)
    _prev_state.put(key, now_st)                  # sid keys grow over days — LRU keeps the live ones
    if prev is None or prev == now_st:
        return
    if prev in _WORKING and now_st in _ENDED:
        # ★`Awaiting input` is not alerted by default.
        #   The original intent was "task complete alerts" (replacing external messenger notifications), but measured: of 196 cards **wait was 128 (68%)**.
        #   `Awaiting input` **demands no action** — if you are in front of that session you already know. Same reason external messenger notifications were removed.
        #   Kept are only those that demand action: `Awaiting answer`·`Aborted`·context near full·agent done.
        #   To revive, launch with `MAILBOX_CARD_WAIT=1` (EnvironmentVariables in the plist).
        if now_st == "wait" and os.environ.get("MAILBOX_CARD_WAIT") != "1":
            return
        # `task` is read server-side only to spot end commands — it never reaches the card.
        task = _task_line(info.get("task") or "")
        # ⚠/exit · /clear · /quit is the user ending the session on purpose, not an abort to act on.
        if task in _END_CMDS:
            return
        label = {"wait": "Awaiting input", "ask": "Awaiting answer", "abort": "Aborted"}[now_st]
        # ⚠Empty body: no reply summary or instruction on cards (AGENTS.md rule 1) —
        #   project · cwd · time · kind are the card; the session id rides in `extra`.
        _card_add(now_st, info.get("project", ""), label, "", info.get("cwd", ""),
                  {"sid": info.get("sid") or ""} if info.get("sid") else None)


_END_CMDS = {"/exit", "/clear", "/quit"}
_CMD_RE = re.compile(r"<command-name>\s*(/?[^<\s]+)\s*</command-name>")
TASK_MAX = 60


def _task_line(task):
    """Card-sized instruction line: slash-command markup -> the command name; otherwise one line cut at a word boundary."""
    # ⚠Slicing the raw text at 60 cut mid-tag (`<command-message>exit</co`, 2026-09-24).
    m = _CMD_RE.search(task)
    if m:
        name = m.group(1)
        return name if name.startswith("/") else "/" + name
    t = " ".join(task.split())
    if len(t) <= TASK_MAX:
        return t
    cut = t[:TASK_MAX]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > TASK_MAX // 2 else cut).rstrip() + "…"


def _sess_state(cwd, last_shape, live, asking=False, aborted=False, errored=False, sid=None, ask_tool=False):
    """run (working) · wait (input wait) · done (ended) · unknown (process unreadable).
    ★What separates "working" from "waiting" is **the shape of the last event** — if it ended with a tool call or a tool
      result just arrived, the ball is on the model side; if it ended with assistant text, the ball is on the human side."""
    # ⚠Unknown liveness keeps a pending question: attention must not drop a request it cannot prove unanswerable.
    pend = not aborted and (ask_tool if last_shape == "tool" else (asking and last_shape != "result"))
    if live is None:
        return "ask" if pend else "unknown"
    # ★Even if not in the path, **alive if confirmed by id** (when `--resume` was run from another directory).
    if not (cwd and cwd in live) and not sid_alive(sid):
        if sid_alive_stale(sid):
            if pend:
                return "ask"
            # ★The evidence is merely stale (2026-09-07) — it **was** in the last seen set. Declaring something that hit
            #   the cap `done` erases a working session. The two extremes this file repeatedly failed on were
            #   "quiet means dead" (erases the living) and "wait for a notification" (ghosts remain).
            #   ⇒ Push neither way; drop to **the same place** (unknown) as `live is None` above.
            return "unknown"
        return "done"
    if aborted:
        return "abort"                 # user cut it off with esc — moves only when instructed again
    if last_shape == "tool":
        # ⚠Only the pending tool's own name decides — `asking` alone (a '?' in text beside a Bash call) must not.
        return "ask" if ask_tool else "tool"   # a tool is running (its name is shown alongside)
    if last_shape == "result":
        return "think"                 # model is processing a received tool result
    return "ask" if asking else "wait"
