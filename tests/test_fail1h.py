"""Tests for the header «최근 1시간 실패» summary (sidereus/failures.py: _fail_1h_fold / _fail_1h_build / fail1h).

No live files, no clock: `_fail_events` and `time.time` are monkeypatched on the failures module.
"""
import unittest
from unittest import mock

from tests._load import sidereus

F = sidereus("failures")
NOW = 1_800_000_000.0


class Fold1hTests(unittest.TestCase):
    def test_buckets_are_oldest_first_and_window_is_exclusive(self):
        evs = [{"at": NOW - 5, "kind": "tool"},          # newest bucket
               {"at": NOW - 601, "kind": "hook"},        # second newest
               {"at": NOW - 3599, "kind": "api"},        # oldest bucket
               {"at": NOW - 3600, "kind": "api"},        # exactly one hour old -> out
               {"at": NOW - 9000, "kind": "tool"}]       # far out
        r = F._fail_1h_fold(evs, NOW)
        self.assertEqual(r["bins"], [1, 0, 0, 0, 1, 1])
        self.assertEqual(r["n"], 3)
        self.assertEqual(r["kinds"], {"tool": 1, "hook": 1, "api": 1})
        self.assertEqual(r["bk"][0], {"api": 1})
        self.assertEqual(r["step"], 600)
        self.assertEqual(r["at"], int(NOW))

    def test_future_timestamp_lands_in_newest_bucket_and_missing_kind_is_question_mark(self):
        r = F._fail_1h_fold([{"at": NOW + 30}], NOW)
        self.assertEqual(r["bins"], [0, 0, 0, 0, 0, 1])
        self.assertEqual(r["kinds"], {"?": 1})

    def test_empty(self):
        r = F._fail_1h_fold([], NOW)
        self.assertEqual((r["n"], r["bins"], r["kinds"]), (0, [0] * 6, {}))
        self.assertEqual(r["last"], [])

    def test_last_is_newest_first_metadata_only_capped_at_8(self):
        evs = [{"at": NOW - 10 * i, "kind": "tool", "proj": "p", "sid": "s", "text": "secret", "sig": "x"} for i in range(12)]
        evs.append({"at": NOW - 4000, "kind": "api"})      # outside the hour
        r = F._fail_1h_fold(evs, NOW)
        self.assertEqual(len(r["last"]), 8)
        self.assertEqual(r["last"][0], {"at": int(NOW), "kind": "tool", "proj": "p", "sid": "s"})
        self.assertTrue(all(a["at"] >= b["at"] for a, b in zip(r["last"], r["last"][1:])))


class Build1hTests(unittest.TestCase):
    def test_build_reads_one_hour_of_events_and_fail1h_serves_the_cache(self):
        seen = {}

        def fake_events(hours, capped=True):
            seen["h"] = hours
            return [{"at": NOW - 10, "kind": "deny"}], 3, hours

        old = F._FAIL_1H
        try:
            with mock.patch.object(F, "_fail_events", fake_events), \
                 mock.patch.object(F.time, "time", return_value=NOW):
                F._fail_1h_build()
            self.assertEqual(seen["h"], 1.0)
            got = F.fail1h()
            self.assertEqual(got["n"], 1)
            self.assertEqual(got["kinds"], {"deny": 1})
        finally:
            F._FAIL_1H = old


if __name__ == "__main__":
    unittest.main()
