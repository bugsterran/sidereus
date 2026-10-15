"""Golden trace for `_wkuse_fetch` (guards the behaviour-preserving phase split).

Every dependency is replaced by a recording stub: clock, subprocess, bin_path/rich_env, _uidx_projects,
_slug_group/_slug_name, both locks and the period slot. The golden holds, per case, the ordered call
trace (incl. lock enter/exit and each slot write), the final slot and the return value.
No network, no live file, no real clock. Regenerate only for an intended change:
    GOLDEN_UPDATE=1 /usr/bin/python3 -m unittest tests.test_golden_wkuse_fetch
"""
import json
import os
import time as _rt
import unittest

from tests._load import sidereus

bu = sidereus("burn_usage")

GOLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden", "wkuse_fetch.json")
NOW = 1_790_000_000.0


def _day(date, tot, cost=0.0, inp=0, out=0, cc=0, cr=0, models=None):
    d = {"date": date, "totalTokens": tot, "totalCost": cost, "inputTokens": inp,
         "outputTokens": out, "cacheCreationTokens": cc, "cacheReadTokens": cr}
    if models is not None:
        d["modelBreakdowns"] = models
    return d


def _m(name, i, o, c, r, cost):
    return {"modelName": name, "inputTokens": i, "outputTokens": o,
            "cacheCreationTokens": c, "cacheReadTokens": r, "cost": cost}


D0, D1, D2, D3 = "2026-09-21", "2026-09-20", "2026-09-19", "2026-09-15"
P_RICH = {
    "-Users-a": [_day(D0, 1000, 1.234, 10, 20, 300, 670, [_m("opus", 10, 20, 300, 670, 1.234)]),
                 _day(D1, 500, 0.5, 5, 5, 90, 400, [_m("sonnet", 5, 5, 90, 400, 0.5)]),
                 {"totalTokens": 99}],
    "-tmp-scratchpad-x": [_day(D0, 40, 0.04, 1, 1, 8, 30)],
    "-tmp-scratchpad-y": {"daily": [_day(D0, 60, 0.06, 2, 2, 6, 50, [_m(None, 1, 1, 1, 1, None)])]},
    "-Users-b": {"daily": [_day(D2, 700, 0.7, 7, 7, 0, 686), _day(D3, 50, None, None, 1, 2, 3)]},
    "-Users-c": [_day(D1, 300, 0.3, 3, 3, 3, 291)],
    "-Users-d": [_day(D0, 0, 0.0)],
    "-Users-e": [_day(D2, 20, 0.02, 1, 1, 1, 17), _day(D2, 5, 0.01, 0, 0, 0, 5)],
    "-Users-f": {"daily": None},
}
P_ZERO_REST = {
    "-Users-a": [_day(D0, 10, 0.1)], "-Users-b": [_day(D0, 9, 0.1)],
    "-Users-c": [_day(D0, 8, 0.1)], "-Users-z": [_day(D0, 0, 0.0)],
}


class _R:
    def __init__(self, rc, out, err):
        self.returncode, self.stdout, self.stderr = rc, out, err


# (name, days, USAGE_LOCAL, uidx result or exception, subprocess result or exception)
CASES = [
    ("local_rich_7", 7, True, P_RICH, None),
    ("local_rich_none_days", None, True, P_RICH, None),
    ("local_rich_30str", "30", True, P_RICH, None),
    ("local_rich_1", 1, True, P_RICH, None),
    ("local_empty", 7, True, {}, None),
    ("local_zero_rest", 3, True, P_ZERO_REST, None),
    ("local_raises", 7, True, OSError("boom"), None),
    ("local_bad_shape", 7, True, {"-Users-a": [None]}, None),
    ("cc_ok", 7, False, None, _R(0, json.dumps({"projects": P_RICH}), "")),
    ("cc_null", 7, False, None, _R(0, "null", "")),
    ("cc_rc", 7, False, None, _R(2, "x", "E" * 200)),
    ("cc_rc_none_err", 7, False, None, _R(1, "", None)),
    ("cc_empty_out", 30, False, None, _R(0, "  \n", "warn")),
    ("cc_none_out", 7, False, None, _R(0, None, None)),
    ("cc_badjson", 7, False, None, _R(0, "{not json", "")),
    ("cc_timeout", 7, False, None, TimeoutError("t")),
]


class _Lock:
    def __init__(self, log, name):
        self.log, self.name = log, name

    def __enter__(self):
        self.log.append(["enter", self.name])

    def __exit__(self, *a):
        self.log.append(["exit", self.name])
        return False


class _Slot(dict):
    def __init__(self, log, init):
        super().__init__(init)
        self.log = log

    def __setitem__(self, k, v):
        self.log.append(["slot_set", k, v])
        super().__setitem__(k, v)

    def update(self, *a, **kw):
        self.log.append(["slot_update", dict(*a, **kw)])
        super().update(*a, **kw)


def _run_case(case):
    name, days, local, uidx, sub = case
    log = []

    class T:
        @staticmethod
        def time():
            log.append(["time"])
            return NOW

        @staticmethod
        def localtime(t):
            log.append(["localtime", t])
            return _rt.gmtime(t)

        @staticmethod
        def strftime(f, tt):
            r = _rt.strftime(f, tt)
            log.append(["strftime", f, r])
            return r

    class S:
        @staticmethod
        def run(argv, **kw):
            log.append(["run", argv, sorted(kw.items(), key=lambda x: x[0])])
            if isinstance(sub, BaseException):
                raise sub
            return sub

    def fake_uidx(nd):
        log.append(["uidx", nd])
        if isinstance(uidx, BaseException):
            raise uidx
        return json.loads(json.dumps(uidx))

    slots = {}

    def fake_slot(d):
        log.append(["wk_slot", d])
        return slots.setdefault(int(d), _Slot(log, {"at": 0.0, "rows": [], "total": 0,
                                                     "days": int(d), "err": ""}))

    def group(sl):
        r = _REAL_GROUP(sl)
        log.append(["group", sl, r])
        return r

    def sname(sl):
        log.append(["name", sl])
        return "N:" + sl

    def bin_path(n):
        log.append(["bin_path", n])
        return "/bin/" + n

    def rich_env():
        log.append(["rich_env"])
        return {"ENV": "1"}

    patches = {"time": T, "subprocess": S, "_uidx_projects": fake_uidx, "_wk_slot": fake_slot,
               "_slug_group": group, "_slug_name": sname, "bin_path": bin_path,
               "rich_env": rich_env, "USAGE_LOCAL": local, "_WK_NAMES": {},
               "_wkuse_lock": _Lock(log, "wkuse"), "_ccusage_lock": _Lock(log, "ccusage")}
    saved = {k: getattr(bu, k) for k in patches}
    try:
        for k, v in patches.items():
            setattr(bu, k, v)
        try:
            ret = ["ret", bu._wkuse_fetch(days)]
        except Exception as e:
            ret = ["raise", type(e).__name__, str(e)]
    finally:
        for k, v in saved.items():
            setattr(bu, k, v)
    return {"trace": log, "ret": ret, "slots": {str(k): dict(v) for k, v in slots.items()}}


_REAL_GROUP = bu._slug_group


def capture():
    out = {c[0]: _run_case(c) for c in CASES}
    return json.dumps(out, sort_keys=True, ensure_ascii=False, indent=1) + "\n"


class TestGoldenWkuseFetch(unittest.TestCase):
    def test_trace(self):
        text = capture()
        if os.environ.get("GOLDEN_UPDATE") == "1":
            os.makedirs(os.path.dirname(GOLD), exist_ok=True)
            with open(GOLD, "w", encoding="utf-8") as f:
                f.write(text)
        with open(GOLD, encoding="utf-8") as f:
            self.assertEqual(text, f.read())

    def test_no_live_state_touched(self):
        before = json.dumps(bu._wkuse_by, sort_keys=True, default=str)
        capture()
        self.assertEqual(before, json.dumps(bu._wkuse_by, sort_keys=True, default=str))


if __name__ == "__main__":
    unittest.main()
