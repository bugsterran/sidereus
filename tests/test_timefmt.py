"""sidereus.timefmt: each helper matches the strftime call it replaced (fixed epochs, no real clock)."""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from _load import sidereus  # noqa: E402

T = 1790000000.75          # fractional on purpose: localtime/gmtime truncate


class TimefmtTest(unittest.TestCase):
    def setUp(self):
        self.tf = sidereus("timefmt")

    def test_ymd_local(self):
        self.assertEqual(self.tf.ymd(T), time.strftime("%Y-%m-%d", time.localtime(T)))
        self.assertEqual(self.tf.ymd(int(T)), self.tf.ymd(T))

    def test_iso_local(self):
        self.assertEqual(self.tf.iso_local(T), time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(T)))

    def test_iso_z_is_utc(self):
        self.assertEqual(self.tf.iso_z(0), "1970-01-01T00:00:00.000Z")
        self.assertEqual(self.tf.iso_z(T), time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(T)))

    def test_callers_bound(self):
        self.assertIs(sidereus("retro")._rt_day, self.tf.ymd)
        self.assertIs(sidereus("usage_index")._uidx_isoz, self.tf.iso_z)


if __name__ == "__main__":
    unittest.main()
