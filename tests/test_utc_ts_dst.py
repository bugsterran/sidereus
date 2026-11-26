"""Transcript UTC stamps must map to the same epoch in every time zone, DST or not."""
import os
import time
import unittest

from tests._load import sidereus

tr = sidereus("transcript")
tsc = sidereus("timeline_scan")
pm = sidereus("perm_marks")

# calendar.timegm of the same UTC wall times, computed by hand (independent of the code under test)
CASES = [("2026-01-15T12:00:00.000Z", 1768478400.0), ("2026-07-15T12:00:00.000Z", 1784116800.0)]


@unittest.skipUnless(hasattr(time, "tzset"), "time.tzset is POSIX only")
class UtcStampsAcrossZones(unittest.TestCase):
    def setUp(self):
        self._tz = os.environ.get("TZ")

    def tearDown(self):
        if self._tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self._tz
        time.tzset()

    def test_same_epoch_in_dst_and_fixed_zones(self):
        # ⚠A fixed offset taken at import (the old `_TZ_OFF`) passes in UTC/Asia/Seoul and fails in the DST zones.
        for tz in ("UTC", "Asia/Seoul", "America/New_York", "Europe/Berlin"):
            os.environ["TZ"] = tz
            time.tzset()
            tsc._HOUR_TS.clear()
            for s, want in CASES:
                got = (tr._line_ts({"timestamp": s}, 0), tsc._fast_ts(s), pm._iso_s(s))
                self.assertEqual(got, (want, want, want), (tz, s))


if __name__ == "__main__":
    unittest.main()
