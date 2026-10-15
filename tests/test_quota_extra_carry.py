"""Adopting OMC's cache keeps our credit (`extra`) slot, with its own age; header-path URLError is soft.

⚠OMC's cache has no credit slot — replacing `_quota["data"]` wholesale wiped the credit row (2026-09-25).
No live files, no network, no sleeping."""
import threading
import unittest
import urllib.error

from tests._load import sidereus

ql = sidereus("quota_loop")
qm = sidereus("quota")
warn = sidereus("warn")

T0 = 1_800_000_000


class OmcKeepsExtra(unittest.TestCase):
    def setUp(self):
        self.saved = {k: getattr(ql, k) for k in ("_quota", "_quota_lock", "_quota_from_omc",
                                                  "_quota_save", "_quota_calibrate", "_quota_interval",
                                                  "time", "_cc_account")}
        ql._cc_account = lambda: None

        class T:
            @staticmethod
            def time():
                return T0

            @staticmethod
            def sleep(s):
                pass

        ql.time = T
        ql._quota_lock = threading.Lock()
        ql._quota_save = lambda: None
        ql._quota_calibrate = lambda: None
        ql._quota_interval = lambda: 60
        ql._quota_from_omc = lambda fresh_s=0: {
            "at": T0, "data": {"five_hour": {"pct": 7}, "seven_day": {"pct": 80}}}

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(ql, k, v)

    def test_extra_carried_with_its_age(self):
        ex = {"pct": 24.0, "used": 4800, "limit": 20000, "cur": "USD", "at": T0 - 900}
        ql._quota = {"data": {"five_hour": {"pct": 5}, "extra": ex}, "at": T0 - 300, "err": "HTTP 429"}
        self.assertTrue(ql._quota_try_omc([0]))
        d = ql._quota["data"]
        self.assertEqual(d["five_hour"]["pct"], 7)
        self.assertEqual(d["extra"]["pct"], 24.0)
        self.assertEqual(d["extra"]["at"], T0 - 900)       # not bumped to the OMC time

    def test_extra_without_at_gets_previous_payload_time(self):
        ql._quota = {"data": {"extra": {"pct": 10}}, "at": T0 - 300, "err": None}
        ql._quota_try_omc([0])
        self.assertEqual(ql._quota["data"]["extra"]["at"], T0 - 300)

    def test_same_account_carries(self):
        ql._cc_account = lambda: "acct-a"
        ql._quota = {"data": {"extra": {"pct": 10, "at": T0 - 900}}, "at": T0 - 300, "err": None,
                     "acct": "acct-a"}
        ql._quota_try_omc([0])
        self.assertEqual(ql._quota["data"]["extra"]["pct"], 10)

    def test_other_account_drops(self):
        # ⚠After an account switch, the previous account's credits must not show under the new one.
        ql._cc_account = lambda: "acct-b"
        ql._quota = {"data": {"extra": {"pct": 10, "at": T0 - 900}}, "at": T0 - 300, "err": None,
                     "acct": "acct-a"}
        ql._quota_try_omc([0])
        self.assertNotIn("extra", ql._quota["data"])

    def test_no_extra_stays_absent(self):
        ql._quota = {"data": {"five_hour": {"pct": 5}}, "at": T0 - 300, "err": None}
        ql._quota_try_omc([0])
        self.assertNotIn("extra", ql._quota["data"])


class HdrUrlErrorIsSoft(unittest.TestCase):
    def setUp(self):
        self.saved = {k: getattr(qm, k) for k in ("_quota_probe_on", "_oauth_token", "warn_once")}
        self.calls = []
        qm._quota_probe_on = lambda: True
        qm._oauth_token = lambda: "x"
        qm.warn_once = lambda key, msg, **kw: self.calls.append((key, kw))
        import urllib.request
        self.urlopen = urllib.request.urlopen

        def boom(*a, **k):
            raise urllib.error.URLError("offline")
        urllib.request.urlopen = boom

    def tearDown(self):
        import urllib.request
        urllib.request.urlopen = self.urlopen
        for k, v in self.saved.items():
            setattr(qm, k, v)

    def test_soft(self):
        self.assertIsNone(qm._quota_probe_hdr())
        self.assertEqual(self.calls[0][0], "quota-hdr")
        self.assertTrue(self.calls[0][1].get("soft"))


if __name__ == "__main__":
    unittest.main()
