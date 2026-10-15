"""Surface silent failures: warn_once, soft (tier-2) fallbacks, the dead-thread excepthook and per-loop last errors."""
import os
import re
import sys
import threading
import time
import traceback
from time import localtime as _localtime, strftime as _strftime


# ── Surface silent failures ────────────────────────────────────────────────
#   Why (measured 2026-08-13): the viewer's `presence()` did `except: return {}`, so a broken import
#   left presence **silently blank**. Nothing flagged it.
#   ★Logging on every poll (2.5 s) would make the log useless → **one line per reason.**
_warned = set()
# ★Warnings go **up to the screen** (2026-09-07). launchd only piles stderr into `viewer.err`
#   and nobody reads it — in fact it held 71 warning lines + 3 stack traces, and among them
#   `_wkuse_loop`'s `TypeError: unsupported operand type(s) for -: 'list' and 'int'`
#   (chat_server.py:3259) silently killed a background thread and froze the screen.
#   It was found only once the frozen screen was noticed — **a person was the detector.**
#   So the same text also goes into a ring buffer and out via `/api/state.health`.
#   ⚠Recency matters here — on overflow drop **the oldest first**.
_WARN_MAX = 60
# ★Warnings must **disappear once resolved** (measured 2026-09-07; user saw one warning that never went away).
#   An entry sat in the strip for an hour after the 429 had cleared — the same trap as the watch list's
#   "list without expiry". On recurrence `warn_once` below refreshes `at`, so **ongoing problems stay visible**.
#   ⚠Too short hides live problems of slow loops (WK_RETRY_S=120, QUOTA_SLOW_S=300) → 30 min.
WARN_TTL_S = 1800
# ★A warning dismissed with ✕ **stays quiet this long** (2026-09-09; user: dismissed warnings kept coming back).
#   Previously dismiss only removed it from `_WARN_LOG` and cleared `_warned`, so with the condition unchanged
#   the same line came back on **the next poll (2.5 s)** — dismiss was effectively a no-op.
#   ⚠This **defers**, not disables: if it persists after 10 min it shows again (ongoing problems are not hidden).
WARN_MUTE_S = 600
_wmute = {}                        # warning key -> keep off the strip until this time
_WARN_LOG = []
_warn_lock = threading.Lock()      # called from several threads — held only briefly for append/trim
# ★viewer.err lines carried no time (2026-09-25), so a warning could not be told apart from one that predates a fix.
#   ⚠Local time, header line only. `_clock=None` reads `time.time()` at call time, so tests that swap
#   `warn.time` for a virtual clock keep working; strftime/localtime are bound separately for that reason.
_clock = None


def exc_name(e) -> str:
    """Exception class name, with every timeout as "timeout".
    ⚠3.10+ made socket.timeout an alias of TimeoutError, so type(e).__name__ differs between 3.9 and 3.10+."""
    import socket
    return "timeout" if isinstance(e, (socket.timeout, TimeoutError)) else type(e).__name__


def log_ts() -> str:
    """`YYYY-MM-DD HH:MM:SS ` (local time, trailing space) prefix for lines written to stderr / viewer.err."""
    return _strftime("%Y-%m-%d %H:%M:%S ", _localtime((_clock or time.time)()))

# ── Separate tier 1 (covered) from tier 2 (fell to "unknown") ─────────────
#   ★Why (2026-09-07; the user saw a warning that kept showing and had no action they could take):
#     failure paths in this file already have two tiers.
#       tier 1 `live-slow`·`mon-slow`·`busy-slow`·`quota-429` = the query failed but **was covered by the last value**
#            ⇒ the screen was right. There is **by definition no action** for the user.
#       tier 2 `live`·`mon`·`busy`·thread death·loop stall = fallbacks exhausted too ⇒ **the screen is wrong**.
#     Yet both went into `_WARN_LOG` and onto the strip, sitting there for `WARN_TTL_S` (30 min).
#     Measured at that moment: one `live-slow` in the strip with **`at` frozen** (live `/api/state`
#     6 times at 5 s intervals — age only grew 520.6→547.4 s ⇒ not recurring, **a one-off that ended**).
#     So the user watched a finished, non-actionable warning for 30 min.
#   ⚠Conversely **just deleting them** is wrong: a machine that stays slow, with every poll covered by
#     fallback (= a real problem), would show nowhere. So **count them and promote on repetition**.
#
#   ★Constant rationale (all measured 2026-09-07):
#     · normal cost — `ps -eo pid=,ppid=,command=` 26~41ms (median 32ms) · `lsof -a -d cwd -Fpn` 17~27ms
#       (median 19ms). 24 samples over 60 s, even at **load average 11.7 / 15.2 / 14.1**, **0** over 4 s.
#       The 4 s timeout is 100~150x normal ⇒ a timeout means **a pathological stall**, not "high load".
#     · size of a one-off — **1 occurrence** per the live observation above (not a burst). In all of `viewer.err`
#       this family logs first occurrences only: live-slow 10 · mon-slow 1 · busy-slow 0 · quota-429 7 lines.
#     · interval in a persistent state — `live_cwds(ttl=2)`·`tool_busy(ttl=2)` every poll (2.5 s) · `mailbox_watches`
#       every `MON_TTL`=5 s · `quota-429` at backoff 30·60·120·240 s (effective cap 240 — see `_wait_hint` comment).
#   ⇒ `SOFT_PROMOTE_N`=6 · `SOFT_WIN_S`=900:
#       live/busy 6 times = 15 s straight (with 24+ s lost to timeouts in between) · mon 6 times = 30 s
#       · the 6th quota-429 at 30+60+120+240 = 690 s + jitter = **about 740 s** (< 900 s window) ⇒ a persistently blocked 429
#       promotes at about 12.5 min (the case that really hurt was "last success 1510 s ago" — this catches it).
#     Requiring 6x a one-off means normal state never promotes, and persistent state promotes within minutes.
#   ⚠The window is **tumbling, not sliding** (anchored at first). So after promotion `_n` resets to 1 in the next window —
#     a slow key (`quota-429`, interval ≈260 s) fits only 4 times in 900 s and **never reaches 6 again.**
#     ⇒ Chained by "if an unexpired strip entry exists, don't require the count again" (`_alive` below,
#     measured 2026-09-09). Once quiet, the `WARN_TTL_S` (30 min) rule drops it.
SOFT_PROMOTE_N = 6
SOFT_WIN_S = 900
_SOFT_MAX = 20                     # only 4 keys exist, but a safety cap (on overflow evict oldest last-seen)
_SOFT = {}                         # key -> {"n":count, "first":first, "last":last, "msg":text}


def _fill(tpl, vars):
    """`{k}` slots -> values, same rule as the page's TV() (unknown slots stay as written)."""
    if not vars:
        return tpl
    return re.sub(r"\{(\w+)\}", lambda m: str(vars[m.group(1)]) if m.group(1) in vars else m.group(0), tpl)


def warn_once(key: str, msg: str, soft: bool = False, en: str = None, log: bool = True, vars: dict = None,
              more: list = None) -> None:
    """`soft=True` = tier 1 (covered by the last value). Still logged to stderr, but not put on the strip right away.

    `msg` is the English text, a fixed template with `{k}` slots filled from `vars` (values never translated).
    The health item carries `msg`/`msgEn` = the filled English and `tv` = [{msg, vars}, ...] parts the page
    joins with ' · ' after TV() (Korean from I18N.ko by template); `more` = extra such parts (load suffix).
    `en` = older call form (Korean `msg` + English `en`): only `en` is kept. ⚠`tests/test_warn_en.py` requires English at every call site.

    `log=False` = count and promote as usual, but print nothing to stderr for this call.
    ⚠Callers that want a quieter log must pass this, not skip the call: skipping also skips the soft
    count, and a slow key (quota-429) then never reaches `SOFT_PROMOTE_N` (536dccf regression).

    ⚠**Counting must come before the `_warned` early return below.** From the second call on, that return
      fires before reaching here, so counting after it leaves the count at 1 forever and promotion dies."""
    tpl = en if en else msg        # ⚠legacy (msg Korean, en English): the screen text is the English one
    # ⚠vars go out in /api/state JSON: exceptions and other objects become their str()
    vars = {k: v if isinstance(v, (int, float, str)) else str(v) for k, v in (vars or {}).items()}
    parts = [dict({"msg": tpl}, **({"vars": dict(vars)} if vars else {}))] + list(more or [])
    msg = " · ".join(_fill(p["msg"], p.get("vars")) for p in parts)
    if soft:
        _now = time.time()
        with _warn_lock:            # called from several threads — held only briefly for dict updates
            _s = _SOFT.get(key)
            if not _s or _now - (_s.get("first") or 0) > SOFT_WIN_S:
                _s = {"n": 0, "first": _now}      # window elapsed — start a new one
                _SOFT[key] = _s
            _s["n"] += 1
            _s["last"], _s["msg"] = _now, msg
            _n = _s["n"]
            if len(_SOFT) > _SOFT_MAX:
                for _dk, _dv in sorted(_SOFT.items(), key=lambda kv: kv[1].get("last") or 0)[
                        :len(_SOFT) - _SOFT_MAX]:
                    _SOFT.pop(_dk, None)
            # ⚠One line per window, on the first call that allows logging (not only `_n == 1`):
            #   with `log=False` early calls, `_n == 1` alone would drop the window's line entirely.
            _say = log and not _s.get("logged")
            if _say:
                _s["logged"] = True
        if _say:
            # ★`viewer.err` is the diagnostic record — keep it. One line per window (worst case 1 per 15 min), no flood.
            print(f"{log_ts()}⚠ {msg}", file=sys.stderr, flush=True)
        # ★**A reason already on the strip does not need the count again** (measured 2026-09-09).
        #   Why: with tumbling windows `_n` resets to 1 in the next window after promotion. `quota-429`'s
        #   steady-state interval is the backoff cap (_wait_hint max **240 s** + jitter ≈ 260 s), so only
        #   **4 fit in a 900 s window** ⇒ it never reaches 6 again. It then never re-enters the `_warned` path
        #   (age refresh) below, and even with 429 **blocked for 4 hours** the strip entry's `at` froze at
        #   the first promotion and vanished after 30 min (`WARN_TTL_S`)
        #   (virtual clock, 60 `_quota_loop` runs: promoted once at t=739 s, then `at` fixed at 738.6).
        #   That is the opposite of `WARN_TTL_S`'s promise that "ongoing problems stay visible".
        #   ⇒ **If an unexpired strip entry exists**, inherit the promoted state and refresh the age only.
        #   ⚠Do not decide by `_warned` — that set is cleared only when the user dismisses with ✕ and otherwise
        #     lives for the process lifetime. A **one-off** much later would go straight to the strip,
        #     breaking tier 1's purpose ("one-offs stay off the strip"). After expiry (30 min) 6 are required again.
        _alive = False
        with _warn_lock:
            _cut = _now - WARN_TTL_S
            for _w in reversed(_WARN_LOG):
                if _w.get("key") == key:
                    _alive = (_w.get("at") or 0) >= _cut
                    break
        if _n < SOFT_PROMOTE_N and not _alive:
            return
        # ★Promotion — from here it takes the tier-2 path. The text carries **the repeat count** so the
        #   user can tell "briefly slow" from "still slow" at a glance.
        #   (An inherited state whose count is not yet full omits the count and says only "still" — "1 in the new window" would be false.)
        parts.append({"msg": "repeated {n}× in {min} min — still slow", "vars": {"n": _n, "min": SOFT_WIN_S // 60}}
                     if _n >= SOFT_PROMOTE_N else {"msg": "still slow"})
        msg = msg + " · " + _fill(parts[-1]["msg"], parts[-1].get("vars"))
    if _wmute.get(key, 0) > time.time():
        return                     # user just dismissed it (WARN_MUTE_S above) — keep off the strip meanwhile
    if key in _warned:
        # ★On recurrence **refresh the age only**. Previously the first-seen time froze, the screen said "1 hour ago",
        #   and you could not tell a fresh recurrence from one long over — the age lied.
        #   stderr still gets one line only (logging every 2.5 s poll would make the log useless).
        with _warn_lock:
            for _w in reversed(_WARN_LOG):
                if _w.get("key") == key:
                    _w["at"], _w["msg"], _w["msgEn"], _w["tv"] = time.time(), msg, msg, parts
                    break
        return
    _warned.add(key)               # one line per reason (logging every 2.5 s poll would make the log useless)
    # ⚠stderr keeps the "⚠ " marker after the time; nothing parses these lines (checked 2026-09-24, 09-25).
    if log:                        # ⚠the strip entry below is added regardless — `log` gates stderr only
        print(f"{log_ts()}⚠ {msg}", file=sys.stderr, flush=True)
    with _warn_lock:
        _WARN_LOG.append({"at": time.time(), "key": key, "msg": msg, "msgEn": msg, "tv": parts})
        if len(_WARN_LOG) > _WARN_MAX:
            del _WARN_LOG[:len(_WARN_LOG) - _WARN_MAX]


# ── Catch-all net for silently dead threads ───────────────────
#   ★Why try inside loops is not enough: threads also start in places we don't track
#     (e.g. `wkuse_refresh`'s ad-hoc thread). The moment an exception escapes the loop
#     the thread ends there, and with no code left running it **cannot report itself.**
#     `threading.excepthook` (3.8+; this server runs 3.9.6) is called just before Python folds the thread.
#   ⚠An exception on any line of the handler **erases the diagnosis itself** — swallow everything.
_THREAD_DEAD_MAX = 20
_THREAD_DEAD = {}
_thread_hook_prev = threading.excepthook


def _thread_died(args):
    try:
        th = getattr(args, "thread", None)
        nm = getattr(th, "name", None) or "?"
        et, ev = getattr(args, "exc_type", None), getattr(args, "exc_value", None)
        exc = f"{getattr(et, '__name__', None) or et}: {ev}"[:160]
        where = ""
        try:
            fr = traceback.extract_tb(getattr(args, "exc_traceback", None))
            if fr:
                last = fr[-1]      # ★last frame = where it actually blew up (like 3259 in the trace above)
                where = f"{os.path.basename(last.filename)}:{last.lineno} in {last.name}"
        except Exception:
            where = ""
        with _warn_lock:
            _THREAD_DEAD[nm] = {"at": time.time(), "thread": nm, "exc": exc, "where": where}
            if len(_THREAD_DEAD) > _THREAD_DEAD_MAX:
                _drop = sorted(_THREAD_DEAD.items(), key=lambda kv: kv[1].get("at") or 0)
                for _k, _v in _drop[:len(_THREAD_DEAD) - _THREAD_DEAD_MAX]:
                    _THREAD_DEAD.pop(_k, None)
        # ⚠call after releasing `_warn_lock` — `warn_once` takes the same lock again (it is not reentrant)
        warn_once("thread:" + nm, "Background thread {name} stopped — {exc}" + (" ({where})" if where else ""),
                  vars={"name": nm, "exc": exc, "where": where})
    except Exception:
        pass                       # an excepthook must never raise; the default hook below still logs
    try:
        _thread_hook_prev(args)    # keep the default behavior (traceback to stderr) — the log is the only raw record
    except Exception:
        pass                       # nothing left to report to


threading.excepthook = _thread_died

# ── Last error each periodic loop hit ─────────────────────────
#   loop name -> {"at":…, "err":…}. Cleared after one successful round.
_LOOP_ERR = {}
