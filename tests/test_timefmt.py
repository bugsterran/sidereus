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

    def test_pre_epoch_when_localtime_raises(self):
        # Windows localtime raises Errno 22 for negative values (e.g. a 100-year cut-off); simulate it
        import types
        from unittest import mock

        def lt(ts):
            if ts < 0:
                raise OSError(22, "Invalid argument")
            return time.localtime(ts)
        fake = types.SimpleNamespace(localtime=lt, strftime=time.strftime, gmtime=time.gmtime)
        with mock.patch.object(self.tf, "time", fake):
            self.assertEqual(self.tf.ymd(-86400 * 365), "1969-01-01")
            self.assertEqual(self.tf.iso_local(-1), "1969-12-31T23:59:59")
            self.assertEqual(self.tf.ymd(T), time.strftime("%Y-%m-%d", time.localtime(T)))

    def test_callers_bound(self):
        self.assertIs(sidereus("retro")._rt_day, self.tf.ymd)
        self.assertIs(sidereus("usage_index")._uidx_isoz, self.tf.iso_z)


if __name__ == "__main__":
    unittest.main()
