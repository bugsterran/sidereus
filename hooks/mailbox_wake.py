#!/usr/bin/env python3
"""Async Stop hook: waits in the background for new mail and wakes the idle session when it arrives.

Why: the sync Stop hook (mailbox_stop.py) only runs while the session is ending a turn; an idle session
saw new mail only through a watcher process (Monitor + watch.sh). This waiter needs neither: Claude Code
runs it with `asyncRewake: true`, so exit code 2 wakes the model and shows stderr to it.
Other CLIs without an async wake still get mail from mailbox_stop.py at the next turn end.

Rules:
- Same candidate rules, state file and receipts as mailbox_stop.plan() — the two hooks share the cursor,
  so a post surfaced by one is never surfaced again by the other.
- Fires only on mail newer than max(confirmed, pending) — a staged block is the sync hook's to settle; when it
  fires it plans from the confirmed cursor, so the staged set is re-shown, and the save clears `pending`.
- One waiter per session: a newer waiter for the same session id exits at once while the older one's
  heartbeat is fresh. ⚠Liveness is the lock file mtime, not os.kill — os.kill(pid, 0) terminates on Windows.
- ⚠Exit 2 only for new mail or the lifetime renewal; any error -> exit 0 (an exit-2 loop would wake the
  session every turn). Every turn end starts a new waiter, so a renewal re-arms the watch.
- Metadata only (from · room · count); bodies only for Sidereus relays, exactly as mailbox_stop.py.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mailbox_stop as MS  # noqa: E402

POLL_S = 2.0
FIRST_DELAY_S = 3.0        # the sync Stop hook commits first at the same turn end; avoids a double surface
LIFE_S = 6 * 3600          # below the hook timeout in hooks.json; renewal re-arms through the next turn end
STALE_S = 15.0             # heartbeat older than this = the owning waiter is gone
RENEW = ("[mailbox] watch renewed — no new mail. Nothing to do: call no tools and end the turn without a reply.")


def lock_path(store, sid):
    return os.path.join(store, ".wake", "%s.lock" % "".join(c for c in sid if c.isalnum() or c in "-_")[:64])


def take_lock(path, now):
    """True when this process owns the session's waiter slot."""
    try:
        if now - os.path.getmtime(path) < STALE_S:
            with open(path, encoding="utf-8") as f:
                if f.read().strip() != str(os.getpid()):
                    return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    return True


def owns(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip() == str(os.getpid())
    except OSError:
        return False


def beat(store, me):
    """Same presence heartbeat watch.sh writes (mailbox_core.touch_presence «watch»): peers see this id as watching."""
    try:
        name = "".join(c for c in str(me) if c.isalnum() or c in "-_")[:64]
        if not name:
            return
        with open(os.path.join(store, "presence-%s.watch" % name), "w", encoding="utf-8") as f:
            f.write(str(int(time.time())))
    except OSError:
        pass


def deliver(p, err):
    """mailbox_stop.commit() order (cursor -> output -> receipts), output to stderr for the rewake."""
    # mailbox_stop's notice says the watch is off; here the waiter itself is the watch.
    # ⚠Must equal the closing sentence of mailbox_stop.notice() byte for byte, or the swap silently does nothing.
    p["reason"] = p["reason"].replace(
        "(No mailbox watch is running, so this is reported at turn end. The same mail will not block again.)",
        "(The wait hook woke you. The same mail will not wake you again.)")
    MS.save_state(p["sp"], p["state"])     # plan() state has no `pending`: committed past everything
    MS.prune_states(os.path.dirname(p["sp"]), time.time())
    err.write(p["reason"] + "\n")
    err.flush()
    MS.append_receipts(p["acks"], p["receipts"])


def run(inp, store=None, life_s=LIFE_S, poll_s=POLL_S, first_s=FIRST_DELAY_S, err=None, sleep=time.sleep):
    """Returns the exit code: 2 = wake (stderr written), 0 = nothing to do."""
    err = err or sys.stderr
    store = store or MS.data_dir()
    sid = str(inp.get("session_id") or "")
    cwd = inp.get("cwd") or ""
    ident = MS.load(os.path.join(store, "identity.json"), {})
    if not sid or not cwd or not isinstance(ident, dict) or not isinstance(ident.get(cwd), str):
        return 0
    lp = lock_path(store, sid)
    if not take_lock(lp, time.time()):
        return 0
    end = time.monotonic() + life_s
    sleep(first_s)
    try:
        while time.monotonic() < end:
            if not owns(lp):
                return 0           # a newer waiter took the slot
            os.utime(lp, None)
            beat(store, ident[cwd])
            p = MS.plan(inp, store=store, t0=time.monotonic(), over_pending=True)   # sync-hook budget per poll
            if p:
                deliver(p, err)
                return 2
            sleep(poll_s)
        err.write(RENEW + "\n")
        err.flush()
        return 2
    finally:
        try:
            if owns(lp):
                os.remove(lp)
        except OSError:
            pass


def headless(env=None):
    """True under `claude -p` / SDK: Claude Code sets CLAUDE_CODE_ENTRYPOINT=sdk-* there, `cli` interactively."""
    return str((env if env is not None else os.environ).get("CLAUDE_CODE_ENTRYPOINT") or "").startswith("sdk")


def main():
    try:
        # ⚠ headless runs await every Stop hook (asyncRewake included) before acting on a block,
        # so a waiting waiter holds the run until the hook timeout; nothing idles there to wake anyway.
        if headless():
            return 0
        raw = sys.stdin.read()
        inp = json.loads(raw) if raw.strip() else {}
        return run(inp) if isinstance(inp, dict) else 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
