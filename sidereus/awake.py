"""Keep the machine awake while sessions run (caffeinate on Mac, SetThreadExecutionState on Windows)."""
import os
import subprocess
import time
from sidereus.config import CFG, IS_MAC, IS_WIN
from sidereus.warn import _LOOP_ERR, warn_once
from sidereus.sessions import sessions


# ── when the Mac sleeps, sessions stop too ─────────────────────────────────────
# ★Measured 2026-09-17 (work had been running during the gap): in the 1-minute histogram, after
#   184,868 tokens at 15:08, 15:09~15:11 is **completely empty** and it resumed at 15:12. `pmset -g log`
#   15:08:08 `Entering Sleep state due to 'Idle Sleep'` → 15:12:23 `Wake from Deep Idle`.
#   matches to the minute ⇒ collection did not drop out; **the Mac actually slept and no requests went out.**
# ⇒ While any session is running, the viewer holds `caffeinate` to block idle sleep. Released when none.
AWAKE_HOLD = bool(CFG.get("keep_awake", True))   # off switch: config `keep_awake: false` (SECURITY.md)
AWAKE_EVERY_S = 40         # check interval — re-calls `sessions()` but polling keeps the cache warm, so it is cheap
AWAKE_GRACE_S = 180        # hold this long after the last "working" (so it does not flicker between turns)
AWAKE_BUSY = ("tool", "think")   # only `_sess_state` states where **the ball is on the model side**

_awake = {"on": False, "since": 0.0, "n": 0, "last": 0.0}
_awake_proc = [None]                 # live caffeinate child (None if none)
_win_held = [False]                  # Windows: execution state currently set by the awake thread
ES_HOLD, ES_RELEASE = 0x80000001, 0x80000000   # ES_CONTINUOUS|ES_SYSTEM_REQUIRED · ES_CONTINUOUS alone


def _win_hold(want):
    """Windows hold/release. ⚠The state is per thread — only call from the `_awake_loop` thread, or release misses it."""
    if bool(want) == _win_held[0]:
        return
    try:
        import ctypes                # ⚠lazy: `ctypes.windll` exists on Windows only
        ok = ctypes.windll.kernel32.SetThreadExecutionState(ES_HOLD if want else ES_RELEASE)
    except Exception as e:
        warn_once("awake-win", "keep-awake failed ({err})", vars={"err": f"{type(e).__name__}: {e}"}, soft=True)
        ok = 0
    _win_held[0] = bool(want and ok)   # 0 = call failed -> reads as off


def _awake_held():
    """Whether the hold is actually in effect (drives `_awake["on"]`)."""
    if IS_WIN:
        return _win_held[0]
    p = _awake_proc[0]
    return p is not None and p.poll() is None


def _awake_busy():
    """Number of sessions that «must not sleep». ⚠Input wait (wait/ask) is not counted —
    the person is away, and that state may sleep. Hold only while a tool runs or the model is processing."""
    try:
        return sum(1 for s in sessions(max_age_h=2, cap=24)
                   if (s.get("state") or "") in AWAKE_BUSY)
    except Exception as e:
        warn_once("awake-busy", "session state lookup failed ({err}) — keep-awake released",
                  vars={"err": f"{type(e).__name__}: {e}"}, soft=True)
        return 0


def _awake_apply(want):
    """Turn caffeinate on or off (no-op if already in that state)."""
    if IS_WIN:
        return _win_hold(want)
    if not IS_MAC:
        return          # ⚠Linux — no hold. With no child, `_awake` reads as off
    p = _awake_proc[0]
    alive = p is not None and p.poll() is None
    if p is not None and not alive:
        _awake_proc[0] = None        # reap a child that died on its own (avoid zombies)
    if want and not alive:
        # -i idle sleep · -s system sleep (effective on AC only). ⚠`-d` (display) is not held — the display may turn off.
        # ⚠`-w <server pid>`: caffeinate ends when the server dies. Without it an orphan remains and the Mac never sleeps.
        _awake_proc[0] = subprocess.Popen(
            ["/usr/bin/caffeinate", "-i", "-s", "-w", str(os.getpid())],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif alive and not want:
        try:
            p.terminate()
            p.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            pass                     # already gone, or `-w` ends it when the server exits
        _awake_proc[0] = None


def _awake_loop():
    while True:
        try:
            if not AWAKE_HOLD:
                _awake_apply(False)
                _awake.update({"on": False, "n": 0})
                time.sleep(AWAKE_EVERY_S)
                continue
            now, n = time.time(), _awake_busy()
            if n:
                _awake["last"] = now
            want = bool(n) or (0 < now - _awake["last"] < AWAKE_GRACE_S)
            was = _awake["on"]
            _awake_apply(want)
            on = _awake_held()
            if on and not was:
                _awake["since"] = now
            _awake.update({"on": on, "n": n})
            _LOOP_ERR.pop("awake", None)
            time.sleep(AWAKE_EVERY_S)
        except Exception as e:
            warn_once("loop:awake", "Sleep prevention stopped — {err}", vars={"err": f"{type(e).__name__}: {e}"[:140]})
            _LOOP_ERR["awake"] = {"at": time.time(), "err": f"{type(e).__name__}: {e}"[:160]}
            time.sleep(120)        # ⚠the exception path must sleep too
            continue
