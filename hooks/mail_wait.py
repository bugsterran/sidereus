#!/usr/bin/env python3
"""Shared mail waiter for hooks: one waiter per session, waits on bus.jsonl, calls `check` when the bus changes (and every retry_s if given).

Used by hooks/mailbox_wake.py (Claude, asyncRewake), ext-hooks/gemini_mail_stop.py --wait (sync Stop wait) and
ext-hooks/codex_wake.py (Codex, app-server turn).
Rules:
- WAKE is the adapter table: how each CLI's idle session is woken. A new CLI = one row here + its contract test
  (tests/test_mail_wake_table.py checks every EXT_PLAT key has a row).
- Same code on every OS: the only signal is os.stat(bus.jsonl) (st_mtime_ns, st_size) every POLL_S seconds.
  ⚠No sys.platform / os.name branch here (tests/test_mail_wait.test_R5_no_platform_branch).
- One waiter per session: a newer waiter for the same session id exits at once while the older one's
  heartbeat is fresh. ⚠Liveness is the lock file mtime, not os.kill — os.kill(pid, 0) terminates on Windows.
- Waiting costs no model call: the CLI only sees our output when check() finds mail or the lifetime ends.
"""
import os
import time

# async-rewake: background Stop hook, exit 2 wakes the idle session (Claude Code asyncRewake).
# stop-wait: the sync Stop hook itself waits; a block reason continues the turn (Codex `--wait`).
#   ⚠Opt-in (`--wait`): it also holds every interactive turn, so typed input queues; the example ships it off.
# app-server-turn: the Stop hook spawns a detached waiter that starts a turn through the Codex app-server daemon
#   (ext-hooks/codex_wake.py, opt-in `--wake`; the example ships turn-end delivery); typed input never queues behind it.
# turn-end: mail only at the next turn end (Gemini AfterAgent; worker mode is the opt-in idle wait).
# none: not measured; turn-end hook from generic-hooks-example.json at best.
WAKE = {"claude": "async-rewake", "codex": "app-server-turn", "gemini": "turn-end",
        "copilot": "none", "cursor": "none", "cline": "none", "windsurf": "none", "warp": "none",
        "trae": "none", "zed": "none", "grok": "none", "deepseek": "none", "qwen": "none", "kimi": "none",
        "mistral": "none", "ollama": "none", "perplexity": "none", "huggingface": "none", "meta": "none",
        "openrouter": "none"}
METHODS = ("async-rewake", "stop-wait", "app-server-turn", "turn-end", "none")

POLL_S = 2.0
RETRY_S = 30.0             # ⚠Claude's plan() also reads non-bus inputs (time budget, cursor, rooms, pending): retry without a bus change
STALE_S = 15.0             # heartbeat older than this = the owning waiter is gone


def wake_method(plat):
    return WAKE.get(plat, "none") if isinstance(plat, str) else "none"


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


def slot_free(store, sid, now):
    """True when no live waiter holds the session's slot (lock missing or its heartbeat is stale)."""
    try:
        return now - os.path.getmtime(lock_path(store, sid)) >= STALE_S
    except OSError:
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


def bus_sig(store):
    try:
        st = os.stat(os.path.join(store, "bus.jsonl"))
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def wait(store, sid, me, check, life_s, poll_s=POLL_S, first_s=0.0, sleep=time.sleep, clock=time.monotonic,
         retry_s=None):
    """("hit", value) when check() returns something truthy, ("timeout", None) after life_s,
    ("busy", None) when another live waiter owns the session, ("lost", None) when a newer one took it over."""
    lp = lock_path(store, sid)
    if not take_lock(lp, time.time()):
        return "busy", None
    end = clock() + life_s
    sleep(first_s)
    seen = object()                # never equal: the first poll always checks
    last = clock()
    try:
        while clock() < end:
            if not owns(lp):
                return "lost", None
            os.utime(lp, None)
            beat(store, me)
            sig = bus_sig(store)
            if sig != seen or (retry_s is not None and clock() - last >= retry_s):
                seen, last = sig, clock()
                got = check()
                if got:
                    return "hit", got
            sleep(poll_s)
        return "timeout", None
    finally:
        try:
            if owns(lp):
                os.remove(lp)
        except OSError:
            pass
