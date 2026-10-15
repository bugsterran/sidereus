"""`_wk_daily` per-day `top` (2 largest projects) — fake clock and P, no live files."""
import time as _rt
import unittest
from datetime import date, timedelta

from tests._load import sidereus

bu = sidereus("burn_usage")
NOW = 1_790_000_000.0   # 2026-09-21 UTC


class _T:
    @staticmethod
    def time():
        return NOW

    @staticmethod
    def localtime(t):
        return _rt.gmtime(t)

    strftime = staticmethod(_rt.strftime)


def _d(k, tok, cost=0.0):
    return {"date": k, "totalTokens": tok, "totalCost": cost}


class WkDailyTop(unittest.TestCase):
    def setUp(self):
        self._old = (bu.time, bu._slug_name, bu._WK_NAMES)
        bu.time = _T
        bu._slug_name = lambda s: "n" + s
        bu._WK_NAMES = {}

    def tearDown(self):
        bu.time, bu._slug_name, bu._WK_NAMES = self._old

    def test_top2_order_and_empty_days(self):
        D0, D2 = "2026-09-21", "2026-09-19"
        P = {"a": [_d(D0, 100, 1.0), _d(D2, 5)],
             "b": [_d(D0, 300, 2.0)],
             "c": {"daily": [_d(D0, 200, 0.5)]},
             "z": [_d(D0, 0)]}
        daily, keys = bu._wk_daily(P, 7)
        self.assertEqual(len(daily), 7)
        self.assertEqual(keys, [x["d"] for x in daily])
        ds = [date.fromisoformat(x["d"]) for x in daily]
        self.assertTrue(all(b - a == timedelta(days=1) for a, b in zip(ds, ds[1:])))  # no gaps
        today = daily[-1]
        self.assertEqual(today["d"], D0)
        self.assertEqual(today["tok"], 600)
        self.assertEqual(today["top"], [{"name": "nb", "slug": "b", "tok": 300},
                                        {"name": "nc", "slug": "c", "tok": 200}])
        by = {x["d"]: x for x in daily}
        self.assertEqual(by[D2]["top"], [{"name": "na", "slug": "a", "tok": 5}])
        empty = by["2026-09-20"]
        self.assertEqual((empty["tok"], empty["cost"], empty["top"]), (0, 0, []))

    def test_name_resolved_once_per_slug(self):
        calls = []
        bu._slug_name = lambda s: calls.append(s) or s
        P = {"a": [_d("2026-09-%02d" % n, 10) for n in range(1, 22)]}
        bu._wk_daily(P, 30)
        self.assertEqual(calls, ["a"])

    def test_same_name_across_ranges(self):
        # Cold session snapshot during the 7-day fetch (path fallback), warm during the 30-day one (session match).
        P = {"-w--repo": [_d("2026-09-21", 50)], "-w-x": [_d("2026-09-21", 10)]}
        bu._slug_name = lambda s: s
        out7 = {"rows": bu._wk_rows(P), "daily": bu._wk_daily(P, 7)[0]}
        bu._slug_name = lambda s: {"-w--repo": ".repo"}.get(s, s)
        out30 = {"rows": bu._wk_rows(P), "daily": bu._wk_daily(P, 30)[0]}
        bu._slug_name = lambda s: s     # the session left again: the learned name must hold
        out7b = {"rows": bu._wk_rows(P), "daily": bu._wk_daily(P, 7)[0]}
        tops = [[t["name"] for t in bu._wk_rename(o)["daily"][-1]["top"]] for o in (out7, out30, out7b)]
        self.assertEqual(tops, [[".repo", "-w-x"]] * 3)
        for o in (out7, out30, out7b):
            self.assertEqual({r["slug"]: r["name"] for r in o["rows"]}, {"-w--repo": ".repo", "-w-x": "-w-x"})

    def test_all_empty(self):
        daily, _ = bu._wk_daily({}, 30)
        self.assertEqual(len(daily), 30)
        self.assertTrue(all(x["top"] == [] and x["tok"] == 0 for x in daily))


if __name__ == "__main__":
    unittest.main()
