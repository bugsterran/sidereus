"""transcript.iso_epoch: Z, offsets and any fraction width parse on 3.9; garbage returns the caller's default."""
import time
import unittest
from datetime import datetime

from tests._load import sidereus

tr = sidereus("transcript")


class IsoEpoch(unittest.TestCase):
    def test_z_and_offset(self):
        self.assertEqual(tr.iso_epoch("1970-01-01T00:01:00Z"), 60.0)
        self.assertEqual(tr.iso_epoch("1970-01-01T00:01:00z"), 60.0)
        self.assertEqual(tr.iso_epoch("1970-01-01T09:01:00+09:00"), 60.0)
        self.assertEqual(tr.iso_epoch(" 1970-01-01T00:01:00+00:00\n"), 60.0)

    def test_fraction_widths(self):
        for frac, want in [(".5", 60.5), (".25", 60.25), (".123", 60.123), (".1234", 60.1234),
                           (".123456", 60.123456), (".123456789", 60.123456)]:
            self.assertAlmostEqual(tr.iso_epoch("1970-01-01T00:01:00%sZ" % frac), want, places=6, msg=frac)
            self.assertAlmostEqual(tr.iso_epoch("1970-01-01T00:01:00%s+00:00" % frac), want, places=6, msg=frac)

    def test_naive_is_local(self):
        s = "2026-09-25T06:21:08"
        self.assertEqual(tr.iso_epoch(s), time.mktime(datetime(2026, 9, 25, 6, 21, 8).timetuple()))

    def test_garbage_returns_default(self):
        for bad in [None, "", "Z", "not a date", "2026-13-01T00:00:00Z", "2026-09-25T25:00:00Z", 12345, b"x"]:
            self.assertEqual(tr.iso_epoch(bad), 0.0, bad)
            self.assertIsNone(tr.iso_epoch(bad, None), bad)
        self.assertIsNone(tr._iso_ts(""))
        self.assertIsNone(tr._iso_ts(None))


if __name__ == "__main__":
    unittest.main()
