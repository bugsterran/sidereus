#!/usr/bin/env python3
"""Turn-end mailbox hook for non-Claude CLIs: hand unread mail to the agent before its turn ends.

Wired in ext-hooks/*-example.json: Gemini AfterAgent (default), Codex Stop (`--platform codex`), other CLIs' Stop
(`--platform <key>`, unverified). `--platform` only changes the id namespace below (`<key>:` / `-<key>`) and drops
the Gemini-only tool-name prefix; worker mode is Gemini-only, `--wait` acts only where hooks/mail_wait.WAKE says stop-wait or app-server-turn, `--wake` only on app-server-turn. ⚠Must match the mailbox MCP launcher's id (gemini_mailbox_mcp.sh <key>).
Codex 0.156.1 Stop takes the same {"decision": "block", "reason"} shape (binary strings: "hook returned
decision:block without a non-empty reason", "Stop hook requested continuation without a prompt").

Contract (Gemini CLI 0.61.0, bundle/docs/hooks/reference.md "AfterAgent"; bundle/chunk-5FZXKDXH.js
isBlockingDecision() -> sendMessageStream([{text: reason}], ..., stopHookActive=true)):
stdout {"decision": "block", "reason": ...} with exit 0 rejects the response and sends `reason` to the
agent as a new prompt. Same shape as the Claude Code Stop hook, so the scan reuses hooks/mailbox_stop.py.

Identity (must match the mailbox MCP server in ~/.gemini/settings.json):
- The MCP server keys identity.json by CLAUDE_PROJECT_DIR. Gemini's mcpServers.mailbox entry starts it with
  CLAUDE_PROJECT_DIR="gemini:<physical cwd>" and MAILBOX_ME="<cwd basename>-gemini", so
  id = identity.json["gemini:<realpath(cwd)>"] (set by mailbox_login in the Gemini session) or else
  "<basename>-gemini". gemini_id() here computes exactly that.
- ⚠ Never identity.json[cwd]: that key belongs to the Claude session in the same folder. Taking it would
  surface (and, via mailbox_inbox, consume) Claude's mail.
- ⚠ If the resolved id equals any Claude identity (a non-"gemini:" key's value), stay silent: someone logged
  the Gemini session in under a Claude name, and the hook must not help it read that mail.
⚠ Never traps the agent: any error -> exit 0 with empty stdout. Never exit 2 (Gemini retries with stderr).

Mail worker mode (opt-in; docs/HOOKS.md "Mail worker mode"): with no pending mail at turn end, block with an
instruction to call mailbox_wait, do the task that arrives, reply with mailbox_send, and end the turn.
- On if env SIDEREUS_MAIL_WORKER=1 or a `.mail-worker` file sits in the session cwd. The marker is the main
  switch because the worker folder is also what the agent can read, so the choice belongs to that folder;
  the env var is for one-off runs.
- Runaway guard: a wait round is "empty" when the read cursor did not move since the last worker block.
  After SIDEREUS_MAIL_WORKER_MAX_IDLE (default 3, ~3 h at timeout_s=3540) consecutive empty rounds the hook stops
  blocking and shows a systemMessage. A new human prompt in the transcript resets the count.
  ⚠ Not stop_hook_active: Gemini 0.61.0 sends false whenever the turn ended after a tool response
  (the UI re-enters sendMessageStream without it), so it reset every round (live 2026-09-24: «0/12» x5).
- ⚠ Each block passes a fresh `round` to mailbox_wait. Gemini's loop detector (TOOL_CALL_LOOP_THRESHOLD=5
  identical name+args per prompt_id, and the whole worker chain is one prompt_id) otherwise injects
  "Potential loop detected" at the 5th wait and hard-aborts the turn (no AfterAgent) at the next one.

Idle wake on Codex (`--platform codex --wait`, hooks/mail_wait.py "stop-wait"): with no pending mail the sync Stop
hook itself waits on bus.jsonl; mail -> {"decision": "block", "reason"} exit 0, lifetime end -> exit 0, no output.
★Measured on Codex 0.163.0 (2026-10-20): a sync Stop wait has no timeout cap (default 600 s, 3600 accepted); a hook
timeout ends the turn cleanly; a block continues the same turn; an empty exit 0 makes no model call; the TUI shows
«Working · Running hook» while waiting; typed input queues until the wait ends; Esc aborts the wait.
- Runaway guard: `wake_n` counts wait-blocks since the last human prompt (human_key); at SIDEREUS_MAIL_WAIT_MAX
  (default 20) it prints a systemMessage and stops waiting until a human prompt.
  ⚠Codex wraps our block reason in `<hook_prompt ...>` and logs environment context as a user row: human_key()
  skips both, or the injected rows would reset the count every round.
- Lock key = plain session_id (.wake/<sid>.lock, same slot rule as hooks/mailbox_wake.py).
- `--wake` (app-server-turn): instead of waiting in the Stop hook, spawn ext-hooks/codex_wake.py detached and end the
  turn at once; the waiter starts a «[mailbox]» turn through the app-server daemon, so typed input never queues.
- ⚠No wait under `codex exec` (a script would hang up to 59 min). The Stop input has no exec field (0.163.0 schema:
  cwd, hook_event_name, last_assistant_message, model, permission_mode, session_id, stop_hook_active,
  transcript_path, turn_id), so the signal is the rollout's first row: session_meta originator "codex_exec" /
  source "exec" (★0.163.0 rollouts: exec 6/6, TUI 0/4 had it). Unreadable rollout = no wait (fail safe).
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks"))
import mailbox_stop as ms  # noqa: E402
import mail_wait as mw  # noqa: E402

T0 = time.monotonic()
PLATFORM = "gemini"
KEY_PREFIX = "gemini:"
ID_SUFFIX = "-gemini"
TOOL_PREFIX = "mcp_mailbox_"   # Gemini's MCP tool naming; other CLIs get the bare tool name
WORKER_MARK = ".mail-worker"
WORKER_MAX_IDLE = 3
WORKER_WAIT_S = 3540     # one round per hour; needs mcpServers.mailbox.timeout > 3540 s in Gemini
WAIT_S = 3540            # Stop-hook wait; below the example's 3600 s hook timeout
WAIT_MAX = 20
WAKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "codex_wake.py")
Popen = subprocess.Popen   # module attribute so tests can replace the spawn


def set_platform(plat):
    """Select the CLI namespace; False (stay silent) for a malformed key or `claude`, whose id is identity.json[cwd]."""
    global PLATFORM, KEY_PREFIX, ID_SUFFIX, TOOL_PREFIX
    if not isinstance(plat, str) or not plat.isalnum() or not plat.islower() or plat == "claude":
        return False
    PLATFORM, KEY_PREFIX, ID_SUFFIX = plat, plat + ":", "-" + plat
    TOOL_PREFIX = "mcp_mailbox_" if plat == "gemini" else ""
    return True


def gemini_id(cwd, ident):
    """Mailbox id of the Gemini session in cwd, or None if it would collide with a Claude identity."""
    real = os.path.realpath(cwd)
    me = ident.get(KEY_PREFIX + real) if isinstance(ident, dict) else None
    if not isinstance(me, str) or not me:
        me = os.path.basename(real.rstrip("/")) + ID_SUFFIX
    claude_ids = {v for k, v in ident.items() if not str(k).startswith(KEY_PREFIX)} if isinstance(ident, dict) else set()
    return None if me in claude_ids else me


def decide(inp, store=None, now_ns=None, hold=None):
    """Return the block reason string, or None to let the turn end.

    hold (dict): do not mark the mail as surfaced; fill hold["newest"] for mark_surfaced() once it was delivered."""
    store = store or ms.data_dir()
    now_ns = now_ns or time.time_ns()
    sid = str(inp.get("session_id") or "")
    cwd = inp.get("cwd") or ""
    if not sid or not cwd:
        return None
    me = gemini_id(cwd, ms.load(os.path.join(store, "identity.json"), {}))
    if not me or ms.watch_alive(store, me):
        return None

    sp = ms.state_path(store, KEY_PREFIX + sid)
    st = ms.load(sp, {})
    last = int(st.get("last_t") or 0) if isinstance(st, dict) else 0
    floor = max(ms.read_int(os.path.join(store, f"read-{me}.cursor")),
                last, now_ns - ms.LOOKBACK_S * 10 ** 9)

    rooms = ms.load(os.path.join(store, "rooms.json"), {})
    mine = {n for n, r in rooms.items()
            if isinstance(r, dict) and me in (r.get("members") or [])} if isinstance(rooms, dict) else set()

    cand = []
    for m in ms.tail_rows(os.path.join(store, "bus.jsonl"), ms.BUS_TAIL):
        try:
            t = int(m.get("t") or 0)
        except Exception:
            continue
        if t <= floor or m.get("from") == me:
            continue
        room = m.get("room")
        if (room and room in mine) or (not room and m.get("to") == me):
            cand.append(m)
    if not cand:
        return None
    acked = {a.get("id") for a in ms.tail_rows(os.path.join(store, "acks.jsonl"), ms.ACK_TAIL)
             if a.get("kind") == "ack" and a.get("who") == me}
    cand = [m for m in cand if m.get("id") not in acked]
    if not cand or time.monotonic() - T0 > ms.BUDGET_S:
        return None

    newest = max(int(m.get("t") or 0) for m in cand)
    if isinstance(hold, dict):
        hold.update(newest=newest, me=me, at=now_ns)
    else:
        mark_surfaced(sp, newest, me, now_ns)

    names = []
    for m in cand:
        who = str(m.get("from") or "?")
        tag = f"{who}(room {m['room']})" if m.get("room") else f"{who}(DM)"
        if tag not in names:
            names.append(tag)
    more = f" and {len(names) - ms.MAX_NAMES} more" if len(names) > ms.MAX_NAMES else ""
    return (f"[mailbox] {len(cand)} new mail for `{me}` — from: {', '.join(names[:ms.MAX_NAMES])}{more}. "
            f"Before ending, read it with {TOOL_PREFIX}mailbox_inbox and reply, or {TOOL_PREFIX}mailbox_ack it. "
            "(The same mail will not block again.)")


def mark_surfaced(sp, newest, me, now_ns):
    st = ms.load(sp, {})
    # Keep other fields (wake_n, worker counters): the wait's runaway guard lives in the same state file.
    ms.save_state(sp, dict(st if isinstance(st, dict) else {}, last_t=newest, me=me, at=now_ns))
    ms.prune_states(os.path.dirname(sp), time.time())


def worker_on(cwd):
    # Gemini only: Codex idles through the Stop-hook wait (`--wait`), which costs no model call per round.
    if PLATFORM != "gemini":
        return False
    if os.environ.get("SIDEREUS_MAIL_WORKER") == "1":
        return True
    return bool(cwd) and os.path.isfile(os.path.join(cwd, WORKER_MARK))


def worker_max_idle():
    try:
        return max(0, int(os.environ.get("SIDEREUS_MAIL_WORKER_MAX_IDLE", WORKER_MAX_IDLE)))
    except (TypeError, ValueError):
        return WORKER_MAX_IDLE


# ⚠Keep the old Korean prefixes: transcripts written before the English switch still hold them.
MACHINE_PROMPTS = ("[mail worker]", "[mailbox]", "[메일 일꾼]", "[메일박스]", "System: ")
# Codex 0.163.0 user rows that no human typed: hook block reasons (`<hook_prompt hook_run_id=...>`), the
# environment context, and AGENTS.md / user instructions that older builds logged as user rows.
CODEX_INJECTED = ("<hook_prompt", "<environment_context", "<user_instructions", "<turn_aborted",
                  "# AGENTS.md instructions")
TRANSCRIPT_TAIL = 256 * 1024


def _row_user_text(r):
    """(id, text) of a user prompt row in a Gemini or Codex transcript, else None."""
    if r.get("type") == "user":                                  # Gemini chat jsonl
        rid, c = r.get("id") or r.get("timestamp"), r.get("content")
    elif r.get("type") == "response_item":                       # Codex rollout jsonl
        p = r.get("payload")
        if not isinstance(p, dict) or p.get("type") != "message" or p.get("role") != "user":
            return None
        meta = p.get("internal_chat_message_metadata_passthrough")
        kinds = meta.get("content_item_kinds") if isinstance(meta, dict) else None
        if isinstance(kinds, list) and "user.text" not in kinds:  # environment context, hook prompt ("unknown")
            return None
        rid, c = p.get("id") or r.get("timestamp"), p.get("content")
    else:
        return None
    text = c if isinstance(c, str) else "".join(
        str(x.get("text") or "") for x in (c or []) if isinstance(x, dict))
    return rid, text.strip()


def human_key(inp):
    """Id of the newest human-typed prompt, or None if not found.

    Gemini's transcript (transcript_path, jsonl) logs prompts as type "user" rows; tool responses are
    user rows with no text, and our block reasons / loop-detector feedback start with MACHINE_PROMPTS.
    Codex's rollout logs them as response_item / message / role "user"; injected rows are skipped by
    content_item_kinds and by the CODEX_INJECTED prefixes.
    Falls back to the AfterAgent `prompt` field (the chain's original request) when there is no transcript."""
    rows = ms.tail_rows(str(inp.get("transcript_path") or ""), TRANSCRIPT_TAIL)
    if not rows:
        p = inp.get("prompt")
        return ("p:" + _h(p)) if p else None
    for r in reversed(rows):
        got = _row_user_text(r) if isinstance(r, dict) else None
        if not got:
            continue
        rid, text = got
        if text and not text.startswith(MACHINE_PROMPTS + CODEX_INJECTED):
            return str(rid or _h(text))
    return None


def _h(s):
    # ⚠The key is persisted in the worker state file: store a hash, never prompt text.
    import hashlib
    return hashlib.sha256(str(s).encode("utf-8")).hexdigest()[:16]


def worker(inp, store=None, now_ns=None):
    """Worker-mode hook output (dict) for a turn with no pending mail, or None when worker mode is off."""
    store = store or ms.data_dir()
    now_ns = now_ns or time.time_ns()
    sid = str(inp.get("session_id") or "")
    cwd = inp.get("cwd") or ""
    if not sid or not cwd or not worker_on(cwd):
        return None
    me = gemini_id(cwd, ms.load(os.path.join(store, "identity.json"), {}))
    if not me or ms.watch_alive(store, me):
        return None
    sp = ms.state_path(store, KEY_PREFIX + sid)
    st = ms.load(sp, {})
    st = st if isinstance(st, dict) else {}
    cur = ms.read_int(os.path.join(store, f"read-{me}.cursor"))
    human = human_key(inp)
    if (human is not None and human != st.get("w_human")) or cur > int(st.get("w_cur") or 0):
        idle = 0                                   # new human prompt, or mail was read in the last round
    else:
        idle = int(st.get("idle_n") or 0) + 1
    rnd = int(st.get("w_round") or 0) + 1
    ms.save_state(sp, dict(st, idle_n=idle, w_cur=cur, w_round=rnd, me=me, at=now_ns,
                           w_human=human if human is not None else st.get("w_human")))
    k = worker_max_idle()
    if idle >= k:
        return {"systemMessage": f"[mail worker] {idle} empty waits in a row — stopping the loop. "
                                 "Type any prompt to start again."}
    return {"decision": "block", "reason": (
        f"[mail worker] No pending mail for `{me}`. "
        f"Call {TOOL_PREFIX}mailbox_wait with timeout_s={WORKER_WAIT_S}, round={rnd}. "
        f"If a task mail arrives, do that task and reply to the sender with {TOOL_PREFIX}mailbox_send "
        "(to=sender, same thread, subject prefixed with the server's reply tag [답]). Then end the turn. "
        # ⚠mailbox_wait returns the Korean line "(메일 없음 — N초 대기)" on timeout; quote it verbatim.
        f"If it returns '(메일 없음' (no mail), do nothing and end the turn at once. (empty waits {idle}/{k})")}


def _env_int(name, default, lo, hi):
    try:
        return min(hi, max(lo, int(os.environ.get(name, default))))
    except (TypeError, ValueError):
        return default


def interactive(inp):
    """True only when the rollout's session_meta row is readable and not a `codex exec` run."""
    try:
        with open(str(inp.get("transcript_path") or ""), "rb") as f:
            first = f.readline(4 * 1024 * 1024)
        row = json.loads(first.decode("utf-8"))
        meta = row.get("payload") if row.get("type") == "session_meta" else None
        if not isinstance(meta, dict):
            return False
        return meta.get("originator") != "codex_exec" and meta.get("source") != "exec"
    except Exception:
        return False


def wait_mail(inp, store=None, sleep=time.sleep, clock=time.monotonic):
    """Stop-hook wait (stop-wait CLIs): hook output dict on mail or at the runaway cap, None on timeout or busy slot."""
    store = store or ms.data_dir()
    sid = str(inp.get("session_id") or "")
    cwd = inp.get("cwd") or ""
    if not sid or not cwd or mw.wake_method(PLATFORM) not in ("stop-wait", "app-server-turn"):
        return None
    me = gemini_id(cwd, ms.load(os.path.join(store, "identity.json"), {}))
    if not me or ms.watch_alive(store, me) or not interactive(inp):
        return None
    n, cap, human = wake_count(inp, store)
    if n >= cap:
        return {"systemMessage": f"[mailbox] {n} mail wakes in a row without a human prompt — stopped waiting. "
                                 "Type any prompt to start again."}

    def check():
        global T0
        T0 = time.monotonic()      # ⚠decide() gives up after BUDGET_S from T0; each bus check gets a fresh budget
        return decide(inp, store=store)
    got, reason = mw.wait(store, sid, me, check, _env_int("SIDEREUS_MAIL_WAIT_S", WAIT_S, 60, WAIT_S),
                          sleep=sleep, clock=clock)
    if got != "hit":
        return None
    bump_wake(inp, store, n, human)
    return {"decision": "block", "reason": reason}


def wake_count(inp, store):
    """(wakes since the last human prompt, cap, human key): the runaway guard shared by --wait and codex_wake."""
    st = ms.load(ms.state_path(store, KEY_PREFIX + str(inp.get("session_id") or "")), {})
    st = st if isinstance(st, dict) else {}
    human = human_key(inp)
    n = 0 if (human is not None and human != st.get("wake_human")) else int(st.get("wake_n") or 0)
    return n, _env_int("SIDEREUS_MAIL_WAIT_MAX", WAIT_MAX, 0, 10 ** 6), human


def bump_wake(inp, store, n, human):
    sp = ms.state_path(store, KEY_PREFIX + str(inp.get("session_id") or ""))
    st = ms.load(sp, {})
    st = st if isinstance(st, dict) else {}
    ms.save_state(sp, dict(st, wake_n=n + 1, wake_human=human if human is not None else st.get("wake_human")))


def spawn_wake(inp, store=None):
    """`--wake`: start the detached app-server waiter; True when spawned (the hook then ends the turn at once)."""
    store = store or ms.data_dir()
    sid = str(inp.get("session_id") or "")
    cwd = inp.get("cwd") or ""
    tp = str(inp.get("transcript_path") or "")
    if not sid or not cwd or not tp or mw.wake_method(PLATFORM) != "app-server-turn":
        return False
    me = gemini_id(cwd, ms.load(os.path.join(store, "identity.json"), {}))
    if os.name == "nt" or not me or ms.watch_alive(store, me) or not interactive(inp):
        return False      # no daemon socket on Windows
    n, cap, _ = wake_count(inp, store)
    if n >= cap or not mw.slot_free(store, sid, time.time()):
        return False
    # ⚠Ids and paths only: the waiter rebuilds its prompt from decide(), never from hook input text.
    Popen([sys.executable, WAKER, sid, cwd, tp, me], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
          stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
    return True


def main():
    try:
        raw = sys.stdin.read()
        inp = json.loads(raw) if raw.strip() else {}
        if not isinstance(inp, dict):
            return
        argv = sys.argv[1:]
        if "--platform" in argv:
            i = argv.index("--platform") + 1
            if not set_platform(argv[i] if i < len(argv) else ""):
                return
        reason = decide(inp)
        if reason:
            sys.stdout.write(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
            return
        if "--wake" in argv and spawn_wake(inp):
            return
        out = wait_mail(inp) if "--wait" in argv else None
        out = out or worker(inp)
        if out:
            sys.stdout.write(json.dumps(out, ensure_ascii=False))
    except Exception:
        pass


if __name__ == "__main__":
    for _s in (sys.stdin, sys.stdout):   # ⚠Windows pipes default to the ANSI codepage; hook JSON is UTF-8
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    main()
    sys.exit(0)
