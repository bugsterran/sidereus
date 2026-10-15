"""History rows: a session crossing local midnight carries its run (runFrom/runTo); rows sort by start, newest first."""
import time
import types
import unittest

from tests._load import sidereus

hi = sidereus("history")


def _at(y, mo, d, h):
    return int(time.mktime((y, mo, d, h, 0, 0, 0, 0, -1)))


def _h(*hours):
    return {str(k): {"claude-opus-5": [1, 1, 0, 0]} for k in hours}


class HistSpan(unittest.TestCase):
    def setUp(self):
        self.now = _at(2026, 9, 21, 12)
        # A: 22:00-01:00 across 09-19/09-20 · B: 09:00 on 09-20 · C: 00:00-23:00 on 09-20 (continues both ways)
        files = {
            "/p/-x/a.jsonl": {"sl": "-x", "h": _h(_at(2026, 9, 19, 22), _at(2026, 9, 19, 23), _at(2026, 9, 20, 0))},
            "/p/-x/b.jsonl": {"sl": "-x", "h": _h(_at(2026, 9, 20, 9))},
            "/p/-x/c.jsonl": {"sl": "-x", "h": _h(*([_at(2026, 9, 19, 23)] + [_at(2026, 9, 20, k) for k in range(24)]
                                                  + [_at(2026, 9, 21, 0), _at(2026, 9, 21, 1)]))},
        }
        self.saved = {k: getattr(hi, k) for k in ("_uidx", "_uidx_refresh", "time", "PLAT_MODS", "_cwd_from_slug")}
        hi._uidx = {"files": files}
        hi._uidx_refresh = lambda: None
        hi.time = types.SimpleNamespace(time=lambda: self.now, mktime=time.mktime, strptime=time.strptime)
        hi.PLAT_MODS = {}
        hi._cwd_from_slug = lambda s: "/w/x"
        hi._hist_cache.clear()

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(hi, k, v)
        hi._hist_cache.clear()

    def _day(self, out, d):
        return next(x for x in out["list"] if x["date"] == d)["rows"]

    def test_midnight_run_and_order(self):
        out = hi.history(7)
        d20 = self._day(out, "2026-09-20")
        self.assertEqual([r["sid"] for r in d20], ["b", "c", "a"])   # 09:00, then two 00:00 starts (later end first)
        b, c, a = d20
        self.assertEqual((b["runFrom"], b["runTo"]), (None, None))
        self.assertEqual((a["from"], a["runFrom"], a["runTo"]), (_at(2026, 9, 20, 0), _at(2026, 9, 19, 22), None))
        self.assertEqual((c["runFrom"], c["runTo"], c["to"]),
                         (_at(2026, 9, 19, 23), _at(2026, 9, 21, 2), _at(2026, 9, 21, 0)))
        a19 = next(r for r in self._day(out, "2026-09-19") if r["sid"] == "a")
        self.assertEqual((a19["runFrom"], a19["runTo"]), (None, _at(2026, 9, 20, 1)))

    def test_cross_gap_is_not_a_run(self):
        hs = {_at(2026, 9, 19, 22), _at(2026, 9, 20, 0)}   # 23:00 missing
        self.assertEqual(hi._cross(hs, _at(2026, 9, 20, 0), _at(2026, 9, 20, 0)), (None, None))


if __name__ == "__main__":
    unittest.main()
