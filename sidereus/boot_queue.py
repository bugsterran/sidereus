"""Boot warm-up queue: the one-shot startup warms run one at a time (TRAPS «boot warm-up threads»).

`with gate(name):` around a warm's heavy first pass. At most one holder; on release the waiter with the
lowest ORDER index goes next (unknown name = last). Re-entrant for the same thread. The queue drains
when every ORDER name finished once (or was never started: its thread is switched off), or
BQ_DRAIN_MAX seconds after the first gate — after that gate() is a no-op.
A warm with nothing to do calls done(name) instead, so the drain does not wait for the time cap.
⚠Never hold the gate across a wait for an outside event (e.g. the first quota sample): the rest of boot stalls.
"""
import contextlib
import threading
import time

from sidereus.features import thread_on as _thread_on

ORDER = ("today_loop", "usage_loop", "fail_loop", "qburn_warm", "win_loop", "tl_warm",
         "toolidx_warm", "br_boot_warm", "wkuse_loop", "struct_warm")
BQ_DRAIN_MAX = 600
_THREAD = {"qburn_warm": "qburn_warm_start", "br_boot_warm": "br_boot_warm_start"}   # main() thread names
_WAIT_S = 0.5   # real wait slice, so a drain by time is noticed while blocked
_cv = threading.Condition()


def _fresh():
    """Empty queue state (tests replace _BQ with one)."""
    return {"t0": None, "drained": False, "holder": None, "depth": 0, "name": None,
            "seq": 0, "wait": {}, "done": set(), "status": {}}


_BQ = _fresh()
_now = time.time


def _log(msg):
    print(msg, flush=True)


def _enabled(name):
    try:
        return bool(_thread_on(_THREAD.get(name, name)))
    except Exception:
        return True   # a broken feature check must not hide a warm from the queue


def _rank(name):
    return ORDER.index(name) if name in ORDER else len(ORDER)


def _check_drain(q):
    """Under _cv: flip to drained once every name is done or the time cap passed."""
    if q["drained"] or q["t0"] is None:
        return q["drained"]
    if all(n in q["done"] for n in ORDER) or _now() - q["t0"] >= BQ_DRAIN_MAX:
        q["drained"] = True
        _log("boot: drained %.1fs" % (_now() - q["t0"]))
        _cv.notify_all()
    return q["drained"]


def _first(q):
    """Under _cv: the first gate() marks switched-off warms as done (they never call gate)."""
    q["t0"] = _now()
    for n in ORDER:
        if not _enabled(n):
            q["done"].add(n)
            _log("boot: %s off" % n)


def _is_next(q, me):
    return min(q["wait"].items(), key=lambda kv: (_rank(kv[1][0]), kv[1][1]))[0] == me


@contextlib.contextmanager
def gate(name):
    me = threading.get_ident()
    q = _BQ
    with _cv:
        if q["t0"] is None:
            _first(q)
        if _check_drain(q):
            held = False
        elif q["holder"] == me:
            q["depth"] += 1
            held = None   # re-entry: the outer gate releases
        else:
            q["seq"] += 1
            q["wait"][me] = (name, q["seq"])
            while not _check_drain(q) and (q["holder"] is not None or not _is_next(q, me)):
                _cv.wait(_WAIT_S)
            q["wait"].pop(me, None)
            held = not q["drained"]
            if held:
                q["holder"], q["depth"], q["name"] = me, 1, name
            _cv.notify_all()
        if held is not None and name not in q["status"]:
            q["status"][name] = [_now(), None]   # also after the drain, so every warm's run stays visible
    try:
        yield
    finally:
        with _cv:
            if held is None:
                q["depth"] -= 1
            else:
                if held:
                    q["holder"], q["depth"], q["name"] = None, 0, None
                st = q["status"].get(name)
                if st is not None and st[1] is None:
                    st[1] = _now()
                    _log("boot: %s %.1fs" % (name, st[1] - st[0]))
                q["done"].add(name)
                _check_drain(q)
                _cv.notify_all()


def done(name):
    """Mark `name` finished without holding the gate (an early return). May drain; no-op after drain."""
    with _cv:
        q = _BQ
        if q["t0"] is None:
            _first(q)
        if _check_drain(q) or name in q["done"]:
            return
        q["done"].add(name)
        _log("boot: %s skip" % name)
        _check_drain(q)
        _cv.notify_all()


def others_done(name):
    """True once every ORDER name except `name` is done (or the queue drained)."""
    with _cv:
        q = _BQ
        return _check_drain(q) or all(n in q["done"] for n in ORDER if n != name)


def drained():
    with _cv:
        return _check_drain(_BQ)


def status():
    """{name: [t0, t1]} for each warm that entered the gate (t1 None while running)."""
    with _cv:
        return {n: list(v) for n, v in _BQ["status"].items()}
