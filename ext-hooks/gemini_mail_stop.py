#!/usr/bin/env python3
"""Turn-end mailbox hook for non-Claude CLIs: hand unread mail to the agent before its turn ends.

Wired in ext-hooks/*-example.json: Gemini AfterAgent (default), Codex Stop (`--platform codex`), other CLIs' Stop
(`--platform <key>`, unverified). `--platform` only changes the id namespace below (`<key>:` / `-<key>`) and drops
the Gemini-only tool-name prefix and worker mode. ⚠Must match the mailbox MCP launcher's id (gemini_mailbox_mcp.sh <key>).
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
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks"))
import mailbox_stop as ms  # noqa: E402

T0 = time.monotonic()
PLATFORM = "gemini"
KEY_PREFIX = "gemini:"
ID_SUFFIX = "-gemini"
TOOL_PREFIX = "mcp_mailbox_"   # Gemini's MCP tool naming; other CLIs get the bare tool name
WORKER_MARK = ".mail-worker"
WORKER_MAX_IDLE = 3
WORKER_WAIT_S = 3540     # one round per hour; needs mcpServers.mailbox.timeout > 3540 s in Gemini


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


def decide(inp, store=None, now_ns=None):
    """Return the block reason string, or None to let the turn end."""
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
    ms.save_state(sp, {"last_t": newest, "me": me, "at": now_ns})
    ms.prune_states(os.path.dirname(sp), time.time())

    names = []
    for m in cand:
        who = str(m.get("from") or "?")
        tag = f"{who}(방 {m['room']})" if m.get("room") else f"{who}(DM)"
        if tag not in names:
            names.append(tag)
    more = f" 외 {len(names) - ms.MAX_NAMES}" if len(names) > ms.MAX_NAMES else ""
    return (f"[메일박스] `{me}` 앞으로 새 메일 {len(cand)}건 — 보낸이: {', '.join(names[:ms.MAX_NAMES])}{more}. "
            f"끝내기 전에 {TOOL_PREFIX}mailbox_inbox 로 읽고 답하거나 {TOOL_PREFIX}mailbox_ack 하십시오. "
            "(같은 글로 다시 막지 않습니다.)")


def worker_on(cwd):
    if PLATFORM != "gemini":       # ⚠the round/loop guards are tuned to Gemini 0.61.0 only
        return False
    if os.environ.get("SIDEREUS_MAIL_WORKER") == "1":
        return True
    return bool(cwd) and os.path.isfile(os.path.join(cwd, WORKER_MARK))


def worker_max_idle():
    try:
        return max(0, int(os.environ.get("SIDEREUS_MAIL_WORKER_MAX_IDLE", WORKER_MAX_IDLE)))
    except (TypeError, ValueError):
        return WORKER_MAX_IDLE


MACHINE_PROMPTS = ("[메일 일꾼]", "[메일박스]", "System: ")
TRANSCRIPT_TAIL = 256 * 1024


def human_key(inp):
    """Id of the newest human-typed prompt, or None if not found.

    Gemini's transcript (transcript_path, jsonl) logs prompts as type "user" rows; tool responses are
    user rows with no text, and our block reasons / loop-detector feedback start with MACHINE_PROMPTS.
    Falls back to the AfterAgent `prompt` field (the chain's original request) when there is no transcript."""
    rows = ms.tail_rows(str(inp.get("transcript_path") or ""), TRANSCRIPT_TAIL)
    if not rows:
        p = inp.get("prompt")
        return ("p:" + _h(p)) if p else None
    for r in reversed(rows):
        if r.get("type") != "user":
            continue
        c = r.get("content")
        text = c if isinstance(c, str) else "".join(
            str(x.get("text") or "") for x in (c or []) if isinstance(x, dict))
        text = text.strip()
        if text and not text.startswith(MACHINE_PROMPTS):
            return str(r.get("id") or r.get("timestamp") or _h(text))
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
        return {"systemMessage": f"[메일 일꾼] 빈 대기 {idle}회 연속 — 루프를 멈추고 쉽니다. "
                                 "다시 시작하려면 아무 프롬프트나 입력하세요."}
    return {"decision": "block", "reason": (
        f"[메일 일꾼] `{me}` 앞으로 대기 중인 메일이 없습니다. "
        f"mcp_mailbox_mailbox_wait 를 timeout_s={WORKER_WAIT_S}, round={rnd} 로 부르십시오. "
        "작업 메일이 오면 그 일을 하고, 보낸이에게 mcp_mailbox_mailbox_send 로 답하십시오"
        "(to=보낸이, 같은 thread · subject 앞에 [답]). 그다음 턴을 끝내십시오. "
        f"'(메일 없음' 이면 아무것도 하지 말고 바로 턴을 끝내십시오. (빈 대기 {idle}/{k})")}


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
        out = worker(inp)
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
