"""Persisted per-day OTel tool tally (sidereus/otel.py `_otel_tday*`, `_otel_tool_rank`).

File path and module state are swapped per test; timestamps are fixed — no live file, clock or network.
"""
import json
import os
import shutil
import tempfile
import time
import unittest

from tests import _load

o = _load.sidereus("otel")


def _ts(d, h=12):
    return time.mktime(time.strptime("%s %02d" % (d, h), "%Y-%m-%d %H"))


class ToolDaysCase(unittest.TestCase):
    def setUp(self):
        self.saved = (o._otel_tday, o._otel_tday_meta, o.OTEL_TDAY_FILE, o.OTEL_TDAY_CAP,
                      o._otel_tools, o._otel_tools_all, o._otel_stat)
        o._otel_stat = {"kept": 0}
        self.tmp = tempfile.mkdtemp()
        o.OTEL_TDAY_FILE = os.path.join(self.tmp, "otel-tools.json")
        o._otel_tools, o._otel_tools_all = {}, {}
        self._reset()

    def tearDown(self):
        (o._otel_tday, o._otel_tday_meta, o.OTEL_TDAY_FILE, o.OTEL_TDAY_CAP,
         o._otel_tools, o._otel_tools_all, o._otel_stat) = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _reset(self):
        # simulates a restart: empty memory, not yet loaded
        o._otel_tday = {}
        o._otel_tday_meta = {"loaded": False, "savedAt": 0.0, "dirty": False}

    def _count(self, name, success, ms=None, d="2026-10-01", h=12):
        with o._otel_lock:
            o._otel_tool_count("s", name, success, ms, _ts(d, h))

    def test_day_bucketing(self):
        self._count("Bash", True, d="2026-10-01", h=1)
        self._count("Bash", True, d="2026-10-01", h=23)
        self._count("Bash", True, d="2026-10-02", h=0)
        self.assertEqual(sorted(o._otel_tday), ["2026-10-01", "2026-10-02"])
        self.assertEqual(o._otel_tday["2026-10-01"]["Bash"][0], 2)
        self.assertEqual(o._otel_tday["2026-10-02"]["Bash"][0], 1)

    def test_fail_only_on_explicit_false(self):
        for v in (False, "false", None, "weird", True, "true"):
            self._count("Read", v)
        self.assertEqual(o._otel_tday["2026-10-01"]["Read"][:2], [6, 2])

    def test_cap_merges_into_gita(self):
        o.OTEL_TDAY_CAP = 2
        for n in ("A", "B", "C", "D"):
            self._count(n, True)
        self._count("A", True)
        row = o._otel_tday["2026-10-01"]
        self.assertEqual(set(row), {"A", "B", "기타"})
        self.assertEqual((row["A"][0], row["기타"][0]), (2, 2))

    def test_save_load_round_trip_is_additive(self):
        self._count("Bash", True, 100)
        self._count("Bash", False, 300)
        self.assertTrue(o._otel_tday_save(now=_ts("2026-10-01", 13)))
        with open(o.OTEL_TDAY_FILE, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["d"]["2026-10-01"]["Bash"], [2, 1, 400.0, 2, 300.0])
        self._reset()
        self._count("Bash", True, 50)               # ingested after restart, before the load
        o._otel_tday_load()
        self.assertEqual(o._otel_tday["2026-10-01"]["Bash"], [3, 1, 450.0, 3, 300.0])

    def test_second_load_does_not_double_count(self):
        self._count("Bash", True, 100)
        self.assertTrue(o._otel_tday_save(now=_ts("2026-10-01", 13)))
        self._reset()
        o._otel_tday_load()
        o._otel_tday_load()
        self.assertEqual(o._otel_tday["2026-10-01"]["Bash"], [1, 0, 100.0, 1, 0.0])

    def test_save_throttled_and_only_when_dirty(self):
        now = _ts("2026-10-01", 13)
        self._count("Bash", True)
        self.assertTrue(o._otel_tday_save(now=now))
        self._count("Bash", True)
        self.assertFalse(o._otel_tday_save(now=now + 10))
        self.assertTrue(o._otel_tday_save(now=now + 61))
        self.assertFalse(o._otel_tday_save(now=now + 200))

    def test_prune_older_than_keep(self):
        self._count("Bash", True, d="2026-08-20")
        self._count("Bash", True, d="2026-09-20")
        self.assertTrue(o._otel_tday_save(now=_ts("2026-10-05")))
        self.assertEqual(list(o._otel_tday), ["2026-09-20"])

    def test_rank_order_top_rest_and_percent(self):
        for i, n in enumerate(("A", "B", "C", "D")):
            for _ in range(10 - i):
                self._count(n, True, 100, d="2026-10-02")
        self._count("A", False, 400, d="2026-10-02")    # A: 11 calls, 1 fail, avg 1400/11
        self._count("Z", True, d="2026-09-01")          # before since — excluded; "from" clamps to the range start
        r = o._otel_tool_rank("2026-10-01", top=2, rest=1)
        self.assertEqual([x["n"] for x in r["top"]], ["A", "B"])
        self.assertEqual(r["top"][0], {"n": "A", "calls": 11, "ok": 90.9, "ms": 127, "tms": 1400, "fms": 29})
        self.assertEqual([x["n"] for x in r["rest"]], ["C"])
        self.assertEqual((r["restN"], r["calls"], r["from"]), (2, 11 + 9 + 8 + 7, "2026-10-01"))

    def test_rank_from_is_collection_start_inside_range(self):
        self._count("Bash", True, d="2026-10-03")
        self.assertEqual(o._otel_tool_rank("2026-10-01")["from"], "2026-10-03")

    def test_rank_live_flag_from_kept_events(self):
        self.assertFalse(o._otel_tool_rank("2026-10-01")["live"])
        o._otel_stat = {"kept": 3}
        self.assertTrue(o._otel_tool_rank("2026-10-01")["live"])

    def test_rank_rest_default_cap_sends_all_tools(self):
        for i in range(40):
            self._count("T%02d" % i, True)
        r = o._otel_tool_rank("2026-10-01")
        self.assertEqual((len(r["rest"]), r["restN"]), (35, 35))

    def test_rank_ms_none_without_durations(self):
        self._count("Bash", True)
        self.assertEqual(o._otel_tool_rank("2026-10-01")["top"][0]["ms"], None)

    def test_rank_empty(self):
        self.assertEqual(o._otel_tool_rank("2026-10-01"),
                         {"top": [], "rest": [], "restN": 0, "calls": 0, "from": None, "live": False,
                          "time": {"rows": [], "restN": 0}})

    def test_r1_load_pads_4_element_rows(self):
        # R1: files written before failDurMs hold 4-element rows; they load with failDurMs=0
        with open(o.OTEL_TDAY_FILE, "w", encoding="utf-8") as f:
            json.dump({"v": 1, "d": {"2026-10-01": {"Old": [3, 1, 90.0, 3], "New": [2, 1, 50.0, 2, 30.0],
                                                     "Bad": [1, 2, 3]}}}, f)
        o._otel_tday_load()
        row = o._otel_tday["2026-10-01"]
        self.assertEqual(row["Old"], [3, 1, 90.0, 3, 0.0])
        self.assertEqual(row["New"], [2, 1, 50.0, 2, 30.0])
        self.assertNotIn("Bad", row)

    def test_r1_fail_duration_only_on_failed_timed_calls(self):
        self._count("Bash", True, 100)
        self._count("Bash", False, None)     # failed but no duration
        self._count("Bash", None, 70)        # unknown success is not a failure
        self.assertEqual(o._otel_tday["2026-10-01"]["Bash"][4], 0.0)
        self._count("Bash", False, 40)
        self.assertEqual(o._otel_tday["2026-10-01"]["Bash"][4], 40.0)

    def test_r1_time_ranks_by_total_duration(self):
        # R1: tms = calls x mean; a call without a duration counts at the mean
        for _ in range(10):
            self._count("Read", True, 10)              # 100 ms total
        self._count("Bash", True, 300)
        self._count("Bash", False, 100)
        self._count("Bash", True)                      # 3 calls, mean 200 -> 600
        self._count("Grep", True)                      # no duration -> not in `time`
        r = o._otel_tool_rank("2026-10-01", top=1)
        bash = [x for x in r["top"] + r["rest"] if x["n"] == "Bash"][0]
        self.assertEqual((bash["tms"], bash["fms"]), (600, 25))
        self.assertEqual([x["n"] for x in r["time"]["rows"]], ["Bash"])
        self.assertEqual(r["time"]["restN"], 1)


if __name__ == "__main__":
    unittest.main()
