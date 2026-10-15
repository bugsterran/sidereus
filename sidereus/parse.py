"""Session transcript parser."""
import json
import os
from sidereus.transcript import (_human_text, _line_ts, _noise_user, _reply_summary, _tail_lines,
    _tool_target)
from sidereus.ident import _cwd_from_slug
from sidereus.bgtasks import _running_bg


# ★**Records that are not activity** — things that touch the transcript even when the session is not working.
#   Measured 2026-09-02 (an idle advocate-repo session sat mid-list):
#   that session's last real turn was 07:04:56, but an `away_summary` was appended at 07:08:07 and the file mtime
#   updated. `ageSec` was measured from mtime so it showed **0 min ago**, and `Awaiting input` rows are sorted by recency,
#   so it rose above a session finished 89 min ago. 14-day measurement: 1,276 cases — common noise.
#   ⚠`turn_duration`·`stop_hook_summary` are **not excluded**: they are written at the very moment a turn ends,
#     so effectively equal to activity time. Only records that land late on their own are excluded.
_NOT_ACT = {"away_summary"}


def _turn_break(d):
    """True for a record that starts a new turn: queue-operation, or a user record that is not only tool_results."""
    if d.get("type") == "queue-operation":
        return True
    if d.get("type") != "user":
        return False
    c = (d.get("message") or {}).get("content")
    if d.get("isMeta") or isinstance(c, str):
        return True
    return isinstance(c, list) and any(not (isinstance(x, dict) and x.get("type") == "tool_result") for x in c)


def _tail_rep(rows):
    """Consecutive identical tool calls at the tail -> {n, tool}. Loop signal for attention.
    ⚠Key is (tool, hash of the full input) — stricter than the display target, so Read with other offsets is not a loop.
    ⛔Only the count and tool name leave here; inputs are hashed, never stored."""
    key, tool, n, seen = None, "", 0, set()
    for line in reversed(rows):
        # Count within one turn only: a cron or /loop re-issuing the same command each turn is not a stuck loop.
        if '"queue-operation"' in line or '"user"' in line:
            try:
                u = json.loads(line)
            except Exception:
                u = None
            if isinstance(u, dict) and _turn_break(u):
                break
        if '"tool_use"' not in line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        c = (d.get("message") or {}).get("content") if d.get("type") == "assistant" else None
        if not isinstance(c, list):
            continue
        for x in reversed(c):
            if not (isinstance(x, dict) and x.get("type") == "tool_use") or x.get("id") in seen:
                continue
            seen.add(x.get("id"))
            k = (x.get("name"), hash(json.dumps(x.get("input"), sort_keys=True, default=str)))
            if key is None:
                key, tool = k, x.get("name") or ""
            elif k != key:
                return {"n": n, "tool": tool}
            n += 1
    return {"n": n, "tool": tool}


def _tail_pmode(rows):
    """Latest `permissionMode` in the tail ("" = unknown). Metadata only (see live_probe._NO_PROMPT_MODES)."""
    for line in reversed(rows):
        if '"permissionMode"' not in line:
            continue
        try:
            m = json.loads(line).get("permissionMode")
        except Exception:
            continue
        if isinstance(m, str) and m:
            return m
    return ""


def _pending_ask_sibling(rows, mid):
    """True if a line of message `mid` holds an AskUserQuestion/ExitPlanMode tool_use with no tool_result yet."""
    asks, done = set(), set()
    for line in rows:
        if '"tool_use' not in line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        msg = d.get("message") or {}
        c = msg.get("content")
        if not isinstance(c, list):
            continue
        for x in c:
            if not isinstance(x, dict):
                continue
            if d.get("type") == "assistant" and msg.get("id") == mid and x.get("type") == "tool_use" \
                    and x.get("name") in ("AskUserQuestion", "ExitPlanMode"):
                asks.add(x.get("id"))
            elif d.get("type") == "user" and x.get("type") == "tool_result":
                done.add(x.get("tool_use_id"))
    return bool(asks - done)


def _turn_shape(d, msg, turn_end):
    """Shape of the newest non-noise assistant/user line -> {shape, askTool, mid, ask, reply, abort, err}.
    Called at most once per scan (the first such line from the tail)."""
    asking = ask_tool = aborted = errored = False
    reply = ""
    last_mid = None
    c0 = msg.get("content")
    if d.get("type") == "assistant":
        has_tool = isinstance(c0, list) and any(
            isinstance(x, dict) and x.get("type") == "tool_use" for x in c0)
        # ★Only **presence** of `thinking` · `text` is checked (body is not read or kept — same level as the ⛔ below).
        has_think = isinstance(c0, list) and any(
            isinstance(x, dict) and x.get("type") == "thinking" for x in c0)
        has_text = isinstance(c0, list) and any(
            isinstance(x, dict) and x.get("type") == "text" for x in c0)
        # ★Separate "done" from "waiting on question" — the next action differs.
        #   Two signals: (a) the last turn was AskUserQuestion·ExitPlanMode (b) the last sentence ends with a question mark
        #   ⛔Bodies are not stored·sent — **booleans only** (other sessions' responses belong to that user).
        if isinstance(c0, list):
            for x in c0:
                if not isinstance(x, dict):
                    continue
                if x.get("type") == "tool_use" and x.get("name") in ("AskUserQuestion", "ExitPlanMode"):
                    asking = True
                if x.get("type") == "text":
                    tl = (x.get("text") or "").strip()
                    if tl.endswith(("?", "?", "까요", "할까", "될까")):
                        asking = True
        reply = _reply_summary(c0)
        # ★Split shape into three (measured 2026-09-07: the triage bot showed as input-wait
        #   while still working).
        #   Previously no `tool_use` always meant `text` (= `_sess_state` reads it as **input wait**).
        #   But lines where the model only thinks are also `type=assistant` with `content` just `[{"type":"thinking"}]`,
        #   so all of them were stamped input wait — in session ee55ee55's 1200-line tail,
        #   **132 thinking-only assistant lines · 99 lines carrying text**. 231 spots were wait candidates.
        #   ⚠`thinking` is **the opposite evidence** of waiting: the model is writing its own turn right now, so
        #   there is nothing for the person to do. Sessions with long thinking·prose between tools (22 min of continuous work)
        #   kept falling into this stretch and flipped to "input wait".
        #   So even `text` is read as **in progress** unless a turn-end marker (turn_end above) has been seen.
        if has_tool:
            shape = "tool"                    # a tool is running (same as before)
            # ★2026-09-24: a pending AskUserQuestion/ExitPlanMode is the user's turn, not a running tool.
            ask_tool = any(isinstance(x, dict) and x.get("type") == "tool_use"
                           and x.get("name") in ("AskUserQuestion", "ExitPlanMode") for x in c0)
            last_mid = msg.get("id")
        elif has_think and not has_text:
            shape = "result"                  # thinking — `_sess_state` reads it as think
        elif has_text:
            # ⚠A resumed/ended turn may carry no turn_duration/stop_hook_summary — the line's own stop_reason
            #   (or a "<synthetic>" harness reply) also closes it, else it stays «thinking» with nothing to expire it.
            closed = turn_end or msg.get("model") == "<synthetic>" \
                or msg.get("stop_reason") in ("end_turn", "stop_sequence")
            shape = "text" if closed else "result"   # has the turn closed · still speaking?
        else:
            shape = "text"                    # content is not a list or is empty = unknown, keep previous behavior
    else:
        shape = "result"      # a tool result just arrived = the model received it and is thinking
        # ★Interrupted·error are states entirely different from "running" — a person must act for it to move.
        if isinstance(c0, str) and c0.strip().startswith("[Request interrupted"):
            aborted = True
        elif isinstance(c0, list):
            for x in c0:
                if not isinstance(x, dict):
                    continue
                if x.get("type") == "tool_result" and x.get("is_error"):
                    errored = True
                if x.get("type") == "text" and (x.get("text") or "").strip().startswith("[Request interrupted"):
                    aborted = True
    return {"shape": shape, "askTool": ask_tool, "mid": last_mid, "ask": asking, "reply": reply,
            "abort": aborted, "err": errored}


def _scan_tail(rows):
    """Newest-first pass over the tail: identity, last tool, context, task, turn shape and usage samples."""
    cwd = branch = sid = None
    tool = None
    targ = ""                  # target of the last tool (file name·description·pattern …) — "current task" on screen
    kind = None
    ctx = 0
    model = None
    task = ""
    # shp = _turn_shape() of the newest assistant/user line: shape 'tool' (tool running) · 'text' (response end · input wait)
    #   · 'result' (thinking); reply = last response summary (card body); ask = question·approval wait signal;
    #   askTool = unanswered AskUserQuestion/ExitPlanMode; abort = user interrupt (esc); err = last tool result was an error
    shp = None
    turn_end = False           # was there a turn-end marker **after** the last assistant line (see below)
    act_at = 0                 # last record time **that counts as activity** (see _NOT_ACT comment above)
    # ★Per-request context samples (2026-09-03). Measured: 97.9% of cost was **cache reads** —
    #   i.e. each request re-reading the whole context is the entire cost. Measuring its size and frequency gives
    #   "how much this session burns per minute", the basis for deciding when to start a new session.
    #   ⚠Tail only — not a whole-session average but the burn rate of **the recent span** (the value to use for current decisions).
    use = []                   # [(time, cache read+cache create, cache read)]
    for line in reversed(rows):
        try:
            d = json.loads(line)
        except Exception:
            continue
        cwd = cwd or d.get("cwd")
        branch = branch or d.get("gitBranch")
        sid = sid or d.get("sessionId")
        if len(use) < 40 and '"cache_read' in line:
            u = ((d.get("message") or {}).get("usage")) or {}
            cr = int(u.get("cache_read_input_tokens") or 0)
            cc = int(u.get("cache_creation_input_tokens") or 0)
            ts0 = int(_line_ts(d, 0) or 0)
            if ts0 and (cr or cc):
                use.append((ts0, cr + cc, cr))
        # ★Noise `user` lines (lines written by slash commands, etc.) are **not activity** either — unfiltered, the last activity time
        #   gets caught there and `ageSec` measures from the slash command, not the real last work
        #   (measured 2026-09-08: 01:29:57Z caught instead of 21:15:22Z = off by 4+ hours).
        #   ⚠If the whole tail is noise, `act_at` stays 0 — then **the same fallback as before**
        #     uses the file mtime (at the `ageSec` computation: `p.get("actAt") or mt`). The screen does not go blank.
        # ⚠`queue-operation` is not activity: a line queued (typed by the person or a background notification) while a
        #   permission prompt is open lands after the prompt marker and hid it (sidereus/perm_marks._mark_t needs marker > actAt).
        # ⚠Same for an `attachment` of type `queued_command` (the queued line echoed into the transcript).
        if not act_at and d.get("type") != "queue-operation" \
                and not (d.get("type") == "attachment" and isinstance(d.get("attachment"), dict)
                         and d["attachment"].get("type") == "queued_command") \
                and not (d.get("type") == "system" and d.get("subtype") in _NOT_ACT) \
                and not (d.get("type") == "user" and _noise_user((d.get("message") or {}).get("content"))):
            act_at = int(_line_ts(d, 0) or 0)
        if kind is None:
            kind = d.get("type")
        msg = d.get("message") or {}
        # ★Turn-end markers — `turn_duration` of `type=system` (carries durationMs·messageCount) and
        #   `stop_hook_summary` are stamped **only at the moment a turn ends**. i.e. the only proof of "now it is the human's turn".
        #   Measured 2026-09-07 (session ee55ee55, 1200-line tail): turn_duration 10 · stop_hook_summary 9 —
        #   far fewer than the 99 assistant lines carrying `text`. So **most `text` is mid-turn**.
        #   ⚠Only those met **before** `shp` is set count: the loop is `reversed(rows)`, so
        #   a flag set here means «a marker after the last assistant line».
        if shp is None and d.get("type") == "system" and \
                d.get("subtype") in ("turn_duration", "stop_hook_summary"):
            turn_end = True
        # ★Noise `user` lines are **skipped without setting shape** (see `_noise_user` comment above).
        #   The loop then keeps going back, meets `stop_hook_summary`/`turn_duration` (turn_end) → `assistant` (text),
        #   and `last_shape="text"` = `wait`. Noise lines never carry `aborted`·`errored` signals,
        #   so those checks are skipped too.
        #   ⚠A `user` line containing `[Request interrupted` is not in `_NOT_HUMAN_STATE` ⇒ not caught here.
        #     The existing `aborted` path must stay alive (interruption is a state).
        # ⚠An auto-compact summary is a `user` line written by the harness: neither turn shape nor task label (metadata only).
        summary = d.get("type") == "user" and bool(d.get("isCompactSummary"))
        if shp is None and d.get("type") in ("assistant", "user") and not summary \
                and not (d.get("type") == "user" and _noise_user(msg.get("content"))):
            shp = _turn_shape(d, msg, turn_end)
        if d.get("type") == "assistant":
            c = msg.get("content")
            if tool is None and isinstance(c, list):
                for x in c:
                    if isinstance(x, dict) and x.get("type") == "tool_use":
                        tool = x.get("name")
                        targ = _tool_target(x)      # **what** that tool is running against
                        break
            u = msg.get("usage") or {}
            if not ctx and u:
                # ★Context size = cache read + cache create + new input. This is "how full it is"
                #   (output tokens are that one response, not cumulative, so they cannot drive the gauge).
                ctx = int(u.get("cache_read_input_tokens") or 0) + int(u.get("cache_creation_input_tokens") or 0) + int(u.get("input_tokens") or 0)
                model = msg.get("model") or model
        if not task and d.get("type") == "user" and not summary:
            task = _human_text(msg.get("content"))
        if cwd and sid and tool and ctx and task:
            break
    shp = shp or {"shape": None, "askTool": False, "mid": None, "ask": False, "reply": "",
                  "abort": False, "err": False}
    return {"cwd": cwd, "branch": branch, "sid": sid, "tool": tool, "targ": targ, "kind": kind, "ctx": ctx,
            "model": model, "task": task, "actAt": act_at, "use": use, "shp": shp}


def _ask_pending(rows, shp):
    """askTool after checking sibling lines of the newest tool_use message."""
    # ⚠Parallel tool_use blocks of one message are written as separate lines (same message.id) — check all of them.
    if shp["shape"] == "tool" and not shp["askTool"] and shp["mid"]:
        return _pending_ask_sibling(rows, shp["mid"])
    return shp["askTool"]


def _session_cwd(fp, cwd):
    """Session cwd from the transcript folder slug; the transcript's own cwd only when restoration fails."""
    # ★A session's identity is **the folder slug**. Using the `cwd` of the transcript's last line makes the name change constantly —
    #   tools running in subagents·subdirectories leave their own cwd (measured 2026-08-20:
    #   repo-A changed from `template` → `js`. The 400KB tail had two kinds of cwd:
    #   `…/webapp/template` 41 times · `…/webapp/template/js` 12 times — the last line won).
    #   The slug is where the session started so it does not change, and matches the `claude` process cwd too (liveness gets accurate as well).
    #   Path restoration costs isdir calls, so it is done **once here** (per poll it would add syscalls per session).
    base = _cwd_from_slug(os.path.basename(os.path.dirname(fp)))
    return base or cwd          # the slug is the source of truth · the transcript value only when restoration fails (folder renamed, etc.)


def _use_rate(use):
    """(creq, burn, rpm): context per request (median) · burn per minute · requests per minute.
    Not emitted (all 0) with fewer than 2 samples (no guessing)."""
    # ⚠The name `ctx` is **already taken** (context size of the last response — used in the window % calculation).
    #   Reusing that name at first silently changed the window % to a different value — hence `creq`.
    creq = burn = rpm = 0
    if len(use) >= 2:
        use = sorted(use)                           # oldest first
        span = max(1.0, (use[-1][0] - use[0][0]) / 60.0)      # minutes
        crs = sorted(x[2] for x in use)
        creq = crs[len(crs) // 2]
        burn = int(sum(x[1] for x in use) / span)
        rpm = round(len(use) / span, 1)
    return creq, burn, rpm


def _parse_transcript(fp):
    """Extract **metadata only** from the transcript tail (conversation is not copied). This result is the unit stored in the cache.

    ★Why split (2026-08-19): previously the cache path and the parse path **each assembled the screen row**. So fixing only one
      silently diverged, and it did — the cache path called `_ctx_window(None, …)`, so
      **only cache-hit sessions got no %.** Now the cache holds this parse result, and row assembly happens
      in **one place**, `_session_row()` (no spot left for the same bug to recur)."""
    rows = _tail_lines(fp, nbytes=400_000, limit=600)   # background decisions share this tail (no duplicate reads)
    # ★What is **running now** — tools called whose results have not arrived yet
    #   (running background tasks and subagent counts).
    #   Match `tool_use.id` against `tool_result.tool_use_id` — unmatched means still running.
    #   Why this works well: subagents and background commands are both caught by **one rule**.
    #   ⚠Only the last 300 lines are checked — things launched earlier cannot be counted (we do not invent what we do not know).
    #   ⛔`~/.claude/tasks/<session>/*.json` is **a to-do list** (TaskCreate), not running work — do not use it.
    sub, bgs, mon = _running_bg(fp)
    t = _scan_tail(rows)
    shp = t["shp"]
    ask_tool = _ask_pending(rows, shp)
    cwd = _session_cwd(fp, t["cwd"])
    creq, burn, rpm = _use_rate(t["use"])
    return {"actAt": t["actAt"], "creq": int(creq), "burn": int(burn), "rpm": rpm,
            "sid": t["sid"], "cwd": cwd, "branch": t["branch"], "tool": t["tool"], "targ": t["targ"],
            "kind": t["kind"], "ctx": t["ctx"],
            "sub": sub, "bgs": bgs, "mon": mon,
            "model": t["model"], "task": t["task"], "reply": shp["reply"],
            "shape": shp["shape"], "ask": shp["ask"], "askTool": ask_tool, "abort": shp["abort"], "err": shp["err"],
            "rep": _tail_rep(rows), "pmode": _tail_pmode(rows)}
