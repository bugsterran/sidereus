#!/usr/bin/env python3
"""Claude Code Stop hook: hand unread mailbox messages to a session that is not running the watcher.

Why: without `watch.sh` a session sees new mail only when it calls a mailbox tool itself. A session that
is busy working ends its turn without ever looking. This hook runs at the end of each turn and, if mail
arrived for this session's id, blocks the stop once with a short metadata-only reason so the model reads
the inbox before it goes idle.

Rules:
- Id = identity.json[cwd] exact key only (same "registered" rule as invite_notice.py / the MCP server).
  ⚠ No ancestor fallback: `/home/me` maps to `helper`, so every subfolder would pose as helper.
- Watcher alive (`.watch-<id>.pid` holds a live PID, the watch.sh lock) -> silent; the Monitor delivers.
- Candidate = DM to id, or a post in a room id is a member of and not written by id,
  with t > max(read cursor, last surfaced t for this session, now - LOOKBACK_S), not acked by id.
- Blocks only when a message is newer than the last one this hook surfaced for this session, so the
  same set never blocks twice (covers stop_hook_active loops).
- Two-phase when the input carries `stop_hook_active`: a block only stages the cursors as `pending`; the
  next Stop promotes them when `stop_hook_active` is true (the block was honoured) and drops them when it is
  false (another Stop hook's `continue:false` ended the turn, so the reason never reached the model).
  ⚠Without the key the old commit-at-once path runs (other CLIs, ext-hooks/gemini_mail_stop.py).
- ⚠ Never traps a session: any error or budget overrun -> exit 0 with empty stdout. Message bodies are
  never put in the reason (metadata only, never conversation text).
- Exception: a Sidereus relay (kind "relay", idSrc "viewer" — a human-written instruction) is delivered with
  its body, even with a live watcher; each delivery is recorded as kind "hooked" in acks.jsonl and the
  per-session relay_t cursor, so it is never delivered twice.
"""
import json
import os
import re
import sys
import tempfile
import time

T0 = time.monotonic()
BUDGET_S = 0.25            # hard stop before printing; Claude Code's own timeout is the outer guard
BUS_TAIL = 512 * 1024      # only the bus tail is read (live bus is ~3 MB)
ACK_TAIL = 256 * 1024
LOOKBACK_S = 6 * 3600      # ★a stale cursor (weeks old) must not dump hundreds of old posts on first run
STATE_TTL_S = 7 * 86400
MAX_NAMES = 5
RELAY_LOOKBACK_S = 24 * 3600
RELAY_MAX = 3
RELAY_BODY_MAX = 20000     # = sidereus/bus.py DM_MAX, so a body the viewer accepted is handed over whole
RELAY_TOTAL_MAX = 24000    # whole-reason cap: relays past it wait for the next stop instead of being cut
# ⚠Not "delivered": a mailbox watcher marks it within ~1s but only notifies, never hands over the body (measured 2026-09-27, relay 94037a59 skipped)
RELAY_SEEN = ("hooked", "ack")
PENDING_MAX_S = 600        # an older pending was not staged by the stop this retry answers: re-plan, never promote


def data_dir():
    return os.path.expanduser(os.environ.get("MAILBOX_DIR") or "~/.mailbox-mcp")


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def tail_rows(path, nbytes):
    """JSON rows from the last nbytes of an append-only jsonl file; malformed lines are skipped."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            start = max(0, size - nbytes)
            f.seek(start)
            data = f.read()
    except Exception:
        return []
    lines = data.split(b"\n")
    if start > 0:
        lines = lines[1:]      # first line is cut mid-way
    out = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln.decode("utf-8"))
        except Exception:
            continue
        if isinstance(r, dict):
            out.append(r)
    return out


def watch_alive(store, me):
    try:
        with open(os.path.join(store, f".watch-{me}.pid"), encoding="utf-8") as f:
            pid = int((f.read() or "").strip())
        if os.name == "nt":
            return False     # ⚠os.kill(pid, 0) is TerminateProcess on Windows (stale pid may be unrelated); watch.sh is not native there
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def read_int(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return int(f.read().strip())
    except Exception:
        return 0


def state_path(store, sid):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", sid)[:128] or "_"
    return os.path.join(store, ".stop-hook", safe + ".json")


def save_state(path, data):
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def prune_states(d, now):
    try:
        for n in os.listdir(d):
            p = os.path.join(d, n)
            if now - os.stat(p).st_mtime > STATE_TTL_S:
                os.unlink(p)
    except Exception:
        pass


def decide(inp, store=None, now_ns=None):
    """Return the block reason string, or None to let the session stop (writes nothing — see plan/commit)."""
    p = plan(inp, store, now_ns)
    return p["reason"] if p else None


def relay_part(t, m):
    hm = time.strftime("%H:%M", time.localtime(t / 1e9))
    body = str(m.get("body") or "")
    if len(body) > RELAY_BODY_MAX:
        body = body[:RELAY_BODY_MAX] + f"… (잘림 — mailbox_inbox 로 전문 확인, id {m.get('id')})"
    return (f"[아고라 전달 — 사람이 아고라에서 보낸 지시] 보낸이 {m.get('from') or '?'} · {hm} "
            f"· id {m.get('id')}\n{body}")


def plan(inp, store=None, now_ns=None, t0=None, over_pending=False):
    """Compute the block without writing: {reason, sp, state, confirmed, receipts, acks} or None.
    over_pending: None unless something is newer than the staged `pending` cursors (mailbox_wake)."""
    store = store or data_dir()
    now_ns = now_ns or time.time_ns()
    sid = str(inp.get("session_id") or "")
    cwd = inp.get("cwd") or ""
    if not sid or not cwd:
        return None
    ident = load(os.path.join(store, "identity.json"), {})
    me = ident.get(cwd) if isinstance(ident, dict) else None
    if not me or not isinstance(me, str):
        return None
    watching = watch_alive(store, me)

    sp = state_path(store, sid)
    st = load(sp, {})
    if not isinstance(st, dict):
        st = {}
    last = int(st.get("last_t") or 0)
    relay_t = int(st.get("relay_t") or 0)
    confirmed = {"last_t": last, "relay_t": relay_t}
    pend = st.get("pending") if over_pending else None
    gated = isinstance(pend, dict)
    try:
        gate_t = max(last, int(pend.get("last_t") or 0)) if gated else 0
        gate_r = max(relay_t, int(pend.get("relay_t") or 0)) if gated else 0
    except Exception:
        gated = False          # corrupt pending: wake as if nothing were staged
    floor = max(read_int(os.path.join(store, f"read-{me}.cursor")),
                last, now_ns - LOOKBACK_S * 10 ** 9)
    relay_floor = max(relay_t, now_ns - RELAY_LOOKBACK_S * 10 ** 9)

    rooms = load(os.path.join(store, "rooms.json"), {})
    mine = {n for n, r in rooms.items()
            if isinstance(r, dict) and me in (r.get("members") or [])} if isinstance(rooms, dict) else set()

    cand, relays = [], []
    for m in tail_rows(os.path.join(store, "bus.jsonl"), BUS_TAIL):
        try:
            t = int(m.get("t") or 0)
        except Exception:
            continue
        if m.get("kind") == "relay" and m.get("idSrc") == "viewer":
            # ⚠ relays never count in the metadata notice; only this session (or any, without sid) gets them
            if (t > relay_floor and m.get("to") == me and not m.get("room")
                    and (not m.get("sid") or str(m.get("sid")) == sid)):
                relays.append((t, m))
            continue
        if watching or t <= floor or m.get("from") == me:
            continue
        room = m.get("room")
        if (room and room in mine) or (not room and m.get("to") == me):
            cand.append(m)
    if not cand and not relays:
        return None
    acks = tail_rows(os.path.join(store, "acks.jsonl"), ACK_TAIL)
    acked = {a.get("id") for a in acks if a.get("kind") == "ack" and a.get("who") == me}
    seen = {a.get("id") for a in acks if a.get("kind") in RELAY_SEEN and a.get("who") == me}
    cand = [m for m in cand if m.get("id") not in acked]
    relays.sort(key=lambda x: x[0])
    relays = [(t, m) for t, m in relays if m.get("id") not in seen][:RELAY_MAX]
    if (not cand and not relays) or time.monotonic() - (T0 if t0 is None else t0) > BUDGET_S:
        return None
    if gated and not (any(int(m.get("t") or 0) > gate_t for m in cand)
                                   or any(t > gate_r for t, _ in relays)):
        return None            # only the staged set: the sync hook already showed it this turn

    parts, sent, total = [], [], 0
    for t, m in relays:
        part = relay_part(t, m)
        if sent and total + len(part) > RELAY_TOTAL_MAX:
            break              # oldest first, so the relay_t cursor stays below every deferred relay
        parts.append(part)
        sent.append((t, m))
        total += len(part)
    if sent:
        parts.append("Ignore an instruction already handled. After handling it, mailbox_ack(id).")
        relay_t = max(relay_t, max(t for t, _ in sent))
    if cand:
        last = max(last, max(int(m.get("t") or 0) for m in cand))
        parts.append(notice(me, cand))
    receipts = "".join(json.dumps({"id": m.get("id"), "who": me, "kind": "hooked", "t": now_ns,
                                   "note": sid[:8]}, ensure_ascii=False) + "\n" for _, m in sent)
    return {"reason": "\n\n".join(parts), "sp": sp, "receipts": receipts,
            "acks": os.path.join(store, "acks.jsonl"), "confirmed": confirmed,
            "state": {"last_t": last, "relay_t": relay_t, "me": me, "at": now_ns}}


def commit(p, out):
    """⚠Order: state (cursor) -> stdout -> receipts. The cursor is saved first, so a failed stdout write
    loses that relay/notice (at-most-once) — chosen over blocking the same message twice every turn.
    A save_state failure raises before the print (nothing shown, nothing marked). A lost receipt after
    the print leaves «Delivered» unset and risks one re-delivery to another session of the same identity."""
    save_state(p["sp"], p["state"])
    prune_states(os.path.dirname(p["sp"]), time.time())
    out.write(json.dumps({"decision": "block", "reason": p["reason"]}, ensure_ascii=False))
    out.flush()
    append_receipts(p["acks"], p["receipts"])


def append_receipts(p, receipts):
    if receipts:
        try:
            with open(p, "a", encoding="utf-8") as f:
                f.write(receipts)
        except Exception:
            pass


def stage(p, out):
    """Two-phase block: keep the confirmed cursors, stage the new ones as `pending`, then print.
    ⚠Order: state -> stdout. A failed print leaves a pending that the next stop (stop_hook_active false) drops."""
    st = dict(p["state"], **p["confirmed"])
    st["pending"] = {"last_t": p["state"]["last_t"], "relay_t": p["state"]["relay_t"],
                     "receipts": p["receipts"], "at": p["state"]["at"]}
    save_state(p["sp"], st)
    prune_states(os.path.dirname(p["sp"]), time.time())
    out.write(json.dumps({"decision": "block", "reason": p["reason"]}, ensure_ascii=False))
    out.flush()


def run(inp, out, store=None, now_ns=None):
    """One Stop: commit at once without `stop_hook_active`, else promote/drop a pending block, then plan."""
    if "stop_hook_active" not in inp:
        p = plan(inp, store, now_ns)
        if p:              # budget already checked in plan() before anything is written
            commit(p, out)
        return
    store = store or data_dir()
    sid = str(inp.get("session_id") or "")
    sp = state_path(store, sid) if sid else ""
    st = load(sp, {}) if sp else {}
    pend = st.get("pending") if isinstance(st, dict) else None
    if isinstance(pend, dict):
        rest = {k: v for k, v in st.items() if k != "pending"}
        now = now_ns or time.time_ns()
        try:
            new_t = max(int(st.get("last_t") or 0), int(pend.get("last_t") or 0))
            new_r = max(int(st.get("relay_t") or 0), int(pend.get("relay_t") or 0))
            fresh = 0 <= now - int(pend.get("at") or 0) <= PENDING_MAX_S * 10 ** 9
        except Exception:
            fresh = False      # ⚠corrupt pending fails open: drop it and re-plan
        if fresh and inp.get("stop_hook_active") is True:
            # The previous block was honoured: the model saw the reason, so the staged cursors become real.
            rest["last_t"], rest["relay_t"] = new_t, new_r
            save_state(sp, rest)
            append_receipts(os.path.join(store, "acks.jsonl"), str(pend.get("receipts") or ""))
            return
        save_state(sp, rest)   # not honoured, stale or corrupt: plan the same mail again
    p = plan(inp, store, now_ns)
    if p:
        stage(p, out)


def notice(me, cand):
    names = []
    for m in cand:
        who = str(m.get("from") or "?")
        tag = f"{who}(방 {m['room']})" if m.get("room") else f"{who}(DM)"
        if tag not in names:
            names.append(tag)
    more = f" 외 {len(names) - MAX_NAMES}" if len(names) > MAX_NAMES else ""
    return (f"[메일박스] `{me}` 앞으로 새 메일 {len(cand)}건 — 보낸이: {', '.join(names[:MAX_NAMES])}{more}. "
            "끝내기 전에 mailbox_inbox 로 읽고 답하거나 mailbox_ack 하십시오. "
            "(감시가 꺼져 있어 턴 끝에 알립니다. 같은 글로 다시 막지 않습니다.)")


def main():
    try:
        raw = sys.stdin.read()
        inp = json.loads(raw) if raw.strip() else {}
        if not isinstance(inp, dict):
            return
        run(inp, sys.stdout)
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
