"""R1 «Activity by hour»: sidereus/otel.py `_otel_src_heat` folds bysrc 5-min buckets into a weekday x hour grid.

`_otel_src` is swapped per test; no file, clock or network is used (`now` is passed in).
"""
import json
import time
import unittest

from tests import _load

o = _load.sidereus("otel")


def _ts(d, h, m=0):
    return int(time.mktime(time.strptime("%s %02d:%02d" % (d, h, m), "%Y-%m-%d %H:%M")))


MON14 = _ts("2026-10-12", 14)          # a Monday, local time
NOW = _ts("2026-10-14", 20)


class HeatCase(unittest.TestCase):
    def setUp(self):
        self.saved = o._otel_src
        o._otel_src = {}

    def tearDown(self):
        o._otel_src = self.saved

    def test_r1_fold_weekday_hour_sums_one_hour(self):
        o._otel_src = {MON14: {"opus|repl_main_thread": [2, 100], "other": [1, 5]},
                       MON14 + 1500: {"haiku|agent:x": [3, 30]},          # 14:25, same hour
                       _ts("2026-10-14", 9): {"opus|repl_main_thread": [1, 7]}}   # Wednesday 09
        r = o._otel_src_heat(_ts("2026-10-12", 0), NOW)
        self.assertEqual(len(r["cells"]), 7)
        self.assertTrue(all(len(x) == 24 for x in r["cells"]))
        self.assertEqual(r["cells"][0][14], [6, 135])
        self.assertEqual(r["cells"][2][9], [1, 7])
        self.assertEqual(r["n"], 7)

    def test_r1_pre_start_excluded_since_is_oldest(self):
        old = _ts("2026-10-08", 10)
        o._otel_src = {old: {"a|b": [5, 50]}, MON14: {"a|b": [1, 1]}}
        r = o._otel_src_heat(_ts("2026-10-12", 0), NOW)
        self.assertEqual(r["n"], 1)
        self.assertEqual(r["since"], old)
        self.assertEqual(r["from"], _ts("2026-10-12", 0))
        self.assertEqual(sum(c[0] for row in r["cells"] for c in row), 1)

    def test_r3_empty(self):
        r = o._otel_src_heat(_ts("2026-10-12", 0), NOW)
        self.assertEqual(r["n"], 0)
        self.assertIsNone(r["since"])

    def test_metadata_only_no_key_strings(self):
        o._otel_src = {MON14: {"claude-opus|agent:secret": [1, 2]}}
        s = json.dumps(o._otel_src_heat(_ts("2026-10-12", 0), NOW))
        self.assertNotIn("opus", s)
        self.assertNotIn("agent", s)


if __name__ == "__main__":
    unittest.main()
