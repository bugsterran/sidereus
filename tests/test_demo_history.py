"""Demo /api/history rows obey the real per-local-day split (sidereus/history.py): from/to inside the row's own
date, runFrom/runTo only where a run really continues across midnight. Fixed anchors — no live clock."""
import time
import unittest

from tests._load import sidereus

demo = sidereus("demo")
H = 3600


def _at(y, mo, d, h, mi=0):
    return int(time.mktime((y, mo, d, h, mi, 0, 0, 0, -1)))


def _ymd(ts):
    return time.strftime("%Y-%m-%d", time.localtime(ts))


class DemoHistory(unittest.TestCase):
    ANCHORS = (_at(2026, 9, 27, 14, 20), _at(2026, 9, 27, 0, 40), _at(2026, 9, 27, 23, 50))

    def rows(self, a, days=7):
        h = demo.World(anchor=a, now=a).history(days)
        return h, [(day, x) for day in h["list"] for x in day["rows"] + day.get("gm", {}).get("rows", [])]

    def test_rows_stay_inside_their_day(self):
        for a in self.ANCHORS:
            for days in (1, 2, 7, 14):
                h, rows = self.rows(a, days)
                self.assertEqual([d["date"] for d in h["list"]], [_ymd(_at(2026, 9, 27 - i, 12)) for i in range(days)])
                for day, x in rows:
                    self.assertEqual(x["date"], day["date"])
                    self.assertEqual(_ymd(x["from"]), x["date"], (a, x))
                    self.assertEqual(_ymd(x["to"] - 1), x["date"], (a, x))
                    self.assertLess(x["from"], x["to"])
                    self.assertLessEqual(x["hours"] * H, x["to"] - x["from"])
                for day in h["list"]:
                    keys = [(-x["from"], -x["to"]) for x in day["rows"]]
                    self.assertEqual(keys, sorted(keys))

    def test_run_links_pair_up_across_midnight(self):
        for a in self.ANCHORS:
            _h, rows = self.rows(a, 14)
            by = {(x["date"], x["sid"]): x for _d, x in rows}
            for _d, x in rows:
                nxt = by.get((_ymd(x["to"]), x["sid"]))
                if x["runTo"]:
                    self.assertTrue(nxt and nxt["from"] == x["to"] and nxt["runFrom"], (a, x))
                    self.assertGreater(x["runTo"], x["to"])
                elif nxt and nxt["from"] == x["to"]:
                    self.fail("continuing run without runTo: %r" % (x,))
                if x["runFrom"]:
                    self.assertLess(x["runFrom"], x["from"])
                    self.assertIn((_ymd(x["from"] - 1), x["sid"]), by)

    def test_order_ignores_wall_clock(self):
        # screen_check keeps one baseline: row order and run markers must not depend on the hour or the day.
        def shape(a):
            h = demo.World(anchor=a, now=a).history(7)
            return [[(x["sid"], x["plat"], bool(x["runFrom"]), bool(x["runTo"])) for x in d["rows"]]
                    for d in h["list"]]
        ref = shape(self.ANCHORS[0])
        for a in self.ANCHORS[1:] + (_at(2026, 9, 27, 3, 10), _at(2026, 9, 27, 12, 55),
                                     _at(2026, 9, 28, 8, 5), _at(2026, 10, 3, 19, 45)):
            self.assertEqual(shape(a), ref, a)

    def test_one_realistic_crossing_2200_to_0100(self):
        a = self.ANCHORS[0]
        w = demo.World(anchor=a, now=a)
        _h, rows = self.rows(a)
        sid = w.by["docs"]["sid"]
        d2 = next(x for _d, x in rows if x["sid"] == sid and x["date"] == "2026-09-25")
        d1 = next(x for _d, x in rows if x["sid"] == sid and x["date"] == "2026-09-26")
        self.assertEqual((d2["from"], d2["to"], d2["runTo"]),
                         (_at(2026, 9, 25, 22), _at(2026, 9, 26, 0), _at(2026, 9, 26, 1)))
        self.assertEqual((d1["from"], d1["to"], d1["runFrom"]),
                         (_at(2026, 9, 26, 0), _at(2026, 9, 26, 1), _at(2026, 9, 25, 22)))


if __name__ == "__main__":
    unittest.main()
