"""`quota()` publishes resets_at rounded to the whole minute, so every view prints the same HH:MM.

⚠The API's resets_at jitters by under a second around the minute; truncating views flipped 10:59 <-> 11:00.
No live files, no network, no real clock."""
import threading
import unittest

from tests._load import sidereus

qm = sidereus("quota")
tr = sidereus("transcript")

T0 = 1_800_000_000          # whole minute (divisible by 60)


class ResetRoundsToMinute(unittest.TestCase):
    def setUp(self):
        self.saved = {k: getattr(qm, k) for k in ("_quota", "_quota_lock", "_quota_from_omc", "time",
                                                  "_cc_plan", "_cc_seat")}

        class T:
            @staticmethod
            def time():
                return T0 - 3600

        qm.time = T
        qm._quota_lock = threading.Lock()
        qm._quota_from_omc = lambda fresh_s=None: None
        qm._cc_plan = lambda: None
        qm._cc_seat = lambda: None

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(qm, k, v)

    def run_with(self, five, seven):
        qm._quota = {"data": {"five_hour": {"pct": 74.0, "resets_at": five},
                              "seven_day": {"pct": 15.0, "resets_at": seven}},
                     "at": T0 - 3660, "err": None, "next": 0}
        return qm.quota()

    def test_jitter_both_sides_gives_one_value(self):
        a = self.run_with("2026-12-30T01:59:59.599995+00:00", "2026-12-30T09:59:59.600014+00:00")
        b = self.run_with("2026-12-30T02:00:00.008214+00:00", "2026-12-30T10:00:00.008234+00:00")
        self.assertEqual(a["five_hour"]["resets_at"], b["five_hour"]["resets_at"])
        self.assertEqual(a["seven_day"]["resets_at"], b["seven_day"]["resets_at"])
        self.assertEqual(tr._iso_ts(a["five_hour"]["resets_at"]) % 60, 0)
        self.assertEqual(a["five_hour"]["leftSec"], b["five_hour"]["leftSec"])

    def test_left_sec_matches_rounded_reset(self):
        r = self.run_with("2026-12-30T01:59:59.6+00:00", None)
        self.assertEqual(r["five_hour"]["leftSec"], int(tr._iso_ts(r["five_hour"]["resets_at"]) - (T0 - 3600)))

    def test_missing_reset_stays_none(self):
        r = self.run_with(None, None)
        self.assertIsNone(r["five_hour"]["resets_at"])
        self.assertIsNone(r["five_hour"]["leftSec"])


if __name__ == "__main__":
    unittest.main()
