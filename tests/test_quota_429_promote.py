"""A long 429 block reaches the health strip, and stderr stays quiet until QUOTA_429_LOG_AFTER_S.

⚠Regression guard for 536dccf: gating the whole warn_once call (not just its print) starved the
soft count, so the strip never got the quota-429 entry. Fake clock; no live files, no sleeping."""
import contextlib
import io
import threading
import unittest

from tests._load import sidereus

ql = sidereus("quota_loop")
warn = sidereus("warn")

T0 = 1_800_000_000.0


class Long429Block(unittest.TestCase):
    def setUp(self):
        self.clock = [T0]
        clock = self.clock

        class T:
            @staticmethod
            def time():
                return clock[0]

            @staticmethod
            def sleep(s):
                clock[0] += s

        class R:
            @staticmethod
            def random():
                return 0.0

        self.q = {"data": {"five_hour": {"pct": 50}}, "at": int(T0), "err": "HTTP 429", "src": "api"}
        self.ql_saved = {k: getattr(ql, k) for k in ("time", "random", "_quota", "_quota_lock",
                                                     "_omc_cache_write")}
        ql.time, ql.random, ql._quota = T, R, self.q
        ql._quota_lock = threading.Lock()
        ql._omc_cache_write = lambda data, hold=False: None
        self.warn_saved = (warn.time, dict(warn._SOFT), list(warn._WARN_LOG), set(warn._warned),
                           dict(warn._wmute))
        warn.time = T
        warn._SOFT.clear()
        warn._WARN_LOG[:] = []
        warn._warned.clear()
        warn._wmute.clear()

    def tearDown(self):
        for k, v in self.ql_saved.items():
            setattr(ql, k, v)
        t, soft, log, warned, mute = self.warn_saved
        warn.time = t
        warn._SOFT.clear(); warn._SOFT.update(soft)
        warn._WARN_LOG[:] = log
        warn._warned.clear(); warn._warned.update(warned)
        warn._wmute.clear(); warn._wmute.update(mute)

    def _strip(self):
        return [w for w in warn._WARN_LOG if w.get("key") == "quota-429"]

    def test_strip_entry_and_quiet_stderr_before_600s(self):
        st = [0]
        err_ages = []                  # last-success age at each stderr line
        strip_at = None
        while self.clock[0] - T0 < 2 * 3600:
            age = int(self.clock[0] - T0)
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                ql._quota_backoff(st)
            if buf.getvalue():
                err_ages.append(age)
            if strip_at is None and self._strip():
                strip_at = age
        self.assertIsNotNone(strip_at, "long 429 block never reached the health strip")
        self.assertTrue(err_ages, "no stderr line at all during a 2h block")
        self.assertGreaterEqual(min(err_ages), ql.QUOTA_429_LOG_AFTER_S)
        # the entry stays fresh while the block goes on (age refresh via `_alive`)
        self.assertLess(self.clock[0] - self._strip()[-1]["at"], warn.WARN_TTL_S)

    def test_short_block_logs_nothing(self):
        st = [0]
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            while self.clock[0] - T0 < ql.QUOTA_429_LOG_AFTER_S - 200:
                ql._quota_backoff(st)
        self.assertEqual(buf.getvalue(), "")
        self.assertEqual(self._strip(), [])


if __name__ == "__main__":
    unittest.main()
