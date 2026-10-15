"""Golden trace for `_quota_loop` (guards the behaviour-preserving phase split).

Every dependency is a recording stub: clock/sleep, random, fetchers, writers, the lock and the
`_quota` slot. The loop runs until the sleep stub raises a BaseException sentinel after N sleeps.
The golden holds, per case, the ordered call trace and the final state. No network, no live file.
Regenerate only for an intended change:
    GOLDEN_UPDATE=1 /usr/bin/python3 -m unittest tests.test_golden_quota_loop
"""
import json
import os
import unittest

from tests._load import sidereus

ql = sidereus("quota_loop")

GOLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden", "quota_loop.json")
NOW = 1_790_000_000.0


class _Stop(BaseException):
    pass


def _j(x):
    return json.loads(json.dumps(x, default=repr))


class _Lock:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        self.log.append(["enter"])

    def __exit__(self, *a):
        self.log.append(["exit"])
        return False


class _Slot(dict):
    def __init__(self, log, init):
        super().__init__(init)
        self.log = log

    def __setitem__(self, k, v):
        self.log.append(["q_set", k, _j(v)])
        super().__setitem__(k, v)


class _LogList(list):
    def __init__(self, log, name, init):
        super().__init__(init)
        self.log, self.name = log, name

    def __setitem__(self, k, v):
        self.log.append([self.name + "_set", k, v])
        super().__setitem__(k, v)


class _ErrMap(dict):
    def __init__(self, log):
        super().__init__()
        self.log = log

    def pop(self, k, *d):
        self.log.append(["loop_err_pop", k])
        return super().pop(k, *d)

    def __setitem__(self, k, v):
        self.log.append(["loop_err_set", k, _j(v)])
        super().__setitem__(k, v)


def _take(seq, default=None):
    if not seq:
        return default
    v = seq.pop(0)
    if isinstance(v, BaseException):
        raise v
    return v


DATA = {"five_hour": {"pct": 30}, "extra": {"limit": 5000, "pct": 10, "used": 500}}
OMC_NEW = {"at": int(NOW) + 5, "data": {"five_hour": {"pct": 33}}}
OMC_OLD = {"at": 1, "data": {"five_hour": {"pct": 1}}}

# name: (sleeps, script, initial state)
#   script keys: fetch, hdr, omc, owrite, warn, calib, rand, err (value of _quota["err"] after each fetch)
CASES = {
    "ok_normal": (9, {"fetch": [True, True]}, {}),
    "ok_hold_short_interval": (6, {"fetch": [True, True, True], "interval": [3.2, 0.2, 25]}, {}),
    "fail_hdr_omc_new": (3, {"fetch": [False, False], "hdr": [{"pct": 40}, {"pct": 41}],
                             "omc": [OMC_NEW, OMC_NEW]}, {}),
    "fail_hdr_not_due_omc_old": (2, {"fetch": [False, False], "omc": [OMC_OLD, OMC_OLD]},
                                 {"hdr_at": NOW - 5}),
    "hdr_no_limit_at_zero": (2, {"fetch": [False], "hdr": [{"pct": 12}], "omc": [OMC_OLD]},
                             {"data": {"extra": {"pct": 1}}, "at": 0}),
    "hdr_none_data_none": (2, {"fetch": [False], "hdr": [None], "omc": [None]},
                           {"data": None, "at": 0}),
    "blocked_429_backoff": (30, {"fetch": [False] * 6, "err": ["HTTP 429"] * 6,
                                 "rand": [0.0, 0.5, 0.99, 0.1, 0.2, 0.3]}, {}),
    "blocked_no_last": (12, {"fetch": [False] * 4, "err": ["timeout"] * 4}, {"data": None, "at": 0}),
    "fetch_raises_then_ok": (5, {"fetch": [RuntimeError("boom"), True]}, {}),
    "raise_mid_ok_keeps_fail": (25, {"fetch": [False, True, False, True],
                                     "owrite": [None] * 7 + [OSError("disk")],
                                     "err": ["429 x", None, "429 y", None]}, {}),
    "raise_after_fail_inc": (12, {"fetch": [False, False], "err": ["429"] * 2,
                                  "warn": [ValueError("w"), None]}, {}),
    "calib_raises_after_omc": (3, {"fetch": [False, False], "omc": [OMC_NEW, None],
                                   "calib": [KeyError("c")]}, {"hdr_at": NOW}),
    "fail_then_omc_resets": (16, {"fetch": [False, False, False, False],
                                  "omc": [None, None, OMC_NEW, None], "err": ["429"] * 4},
                             {"hdr_at": NOW}),
}


def _run_case(name):
    n_sleep, script, init = CASES[name]
    script = {k: list(v) for k, v in script.items()}
    log = []
    clock = [NOW]
    sleeps = [0]

    class T:
        @staticmethod
        def time():
            log.append(["time", clock[0]])
            return clock[0]

        @staticmethod
        def sleep(s):
            log.append(["sleep", round(s, 6)])
            clock[0] += s
            sleeps[0] += 1
            if sleeps[0] >= n_sleep:
                raise _Stop()

    class R:
        @staticmethod
        def random():
            v = _take(script.setdefault("rand", []), 0.25)
            log.append(["random", v])
            return v

    q = _Slot(log, {"data": _j(init.get("data", DATA)), "at": init.get("at", int(NOW) - 100),
                    "err": None, "src": "api"})
    loop_err = _ErrMap(log)
    hdr_at = _LogList(log, "hdr_at", [init.get("hdr_at", 0.0)])
    retry = _LogList(log, "retry", [7])

    def fetch():
        log.append(["fetch"])
        v = _take(script.setdefault("fetch", []), False)
        errs = script.setdefault("err", [])
        if errs:
            dict.__setitem__(q, "err", errs.pop(0))
        return v

    def owrite(data, hold=False):
        log.append(["omc_write", _j(data), hold])
        _take(script.setdefault("owrite", []))

    def probe():
        v = _take(script.setdefault("hdr", []))
        log.append(["probe_hdr", v])
        return v

    def from_omc(fresh_s):
        v = _take(script.setdefault("omc", []))
        log.append(["from_omc", fresh_s, v])
        return _j(v) if v else v

    def interval():
        v = _take(script.setdefault("interval", []), 60)
        log.append(["interval", v])
        return v

    def wait_hint(f):
        v = min(240, 30 * (2 ** max(0, f - 1)))
        log.append(["wait_hint", f, v])
        return v

    def warn(key, msg, **kw):
        log.append(["warn", key, msg, sorted(kw.items())])
        _take(script.setdefault("warn", []))

    def calib():
        log.append(["calibrate"])
        _take(script.setdefault("calib", []))

    patches = {
        "time": T, "random": R, "_quota_load": lambda: log.append(["load"]),
        "_quota_fetch": fetch, "_quota_save": lambda: log.append(["save"]),
        "_quota_lock": _Lock(log), "_quota": q, "_omc_cache_write": owrite,
        "_quota_calibrate": calib, "_quota_interval": interval, "_hdr_at": hdr_at,
        "_quota_probe_hdr": probe, "_quota_from_omc": from_omc, "_wait_hint": wait_hint,
        "warn_once": warn, "_LOOP_ERR": loop_err, "_quota_retry_after": retry,
        "QUOTA_HDR_EVERY_S": 300, "QUOTA_HOLD_EVERY_S": 10, "OMC_FRESH_S": 90,
        "_acc_tick": lambda: None,      # quota_roots.tick: extra roots are covered by tests/test_quota_roots.py
    }
    saved = {k: getattr(ql, k) for k in patches}
    try:
        for k, v in patches.items():
            setattr(ql, k, v)
        try:
            ql._quota_loop()
            end = "returned"
        except _Stop:
            end = "stopped"
    finally:
        for k, v in saved.items():
            setattr(ql, k, v)
    return {"trace": log, "end": end, "clock": clock[0], "quota": _j(dict(q)),
            "loop_err": _j(dict(loop_err)), "hdr_at": list(hdr_at), "retry": list(retry)}


def capture():
    out = {name: _run_case(name) for name in CASES}
    return json.dumps(out, sort_keys=True, ensure_ascii=False, indent=1) + "\n"


class TestGoldenQuotaLoop(unittest.TestCase):
    def test_trace(self):
        text = capture()
        if os.environ.get("GOLDEN_UPDATE") == "1":
            os.makedirs(os.path.dirname(GOLD), exist_ok=True)
            with open(GOLD, "w", encoding="utf-8") as f:
                f.write(text)
        with open(GOLD, encoding="utf-8") as f:
            self.assertEqual(text, f.read())

    def test_stable(self):
        self.assertEqual(capture(), capture())


if __name__ == "__main__":
    unittest.main()
