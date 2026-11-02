"""macOS: a missing keychain item (`security` rc 44) reads as «not signed in»; any other failure keeps the keychain message."""
import subprocess
import unittest

from tests._load import sidereus

q = sidereus("quota")
qf = sidereus("quota_fetch")


class _R:
    def __init__(self, rc, out=""):
        self.returncode, self.stdout = rc, out


class KeychainRc(unittest.TestCase):
    def setUp(self):
        self.saved = (q.IS_MAC, q._quota_lookup_on, q.subprocess.run,
                      qf.IS_MAC, qf._oauth_token, qf._quota_lookup_on, qf._quota.get("err"))
        q.IS_MAC = qf.IS_MAC = True
        q._quota_lookup_on = qf._quota_lookup_on = lambda: True
        qf._oauth_token = q._oauth_token     # real reader, fake subprocess

    def tearDown(self):
        (q.IS_MAC, q._quota_lookup_on, q.subprocess.run,
         qf.IS_MAC, qf._oauth_token, qf._quota_lookup_on, qf._quota["err"]) = self.saved
        q._oauth_miss["no_login"] = False

    def _fetch(self, rc):
        q.subprocess.run = lambda *a, **k: _R(rc)
        self.assertFalse(qf._quota_fetch())
        return qf._quota["err"]

    def test_rc44_is_no_login(self):
        self.assertEqual(self._fetch(44), qf.QF_ERR_KEYS[2])
        self.assertEqual(qf.QF_ERR_KEYS[2], "No Claude Code login found")

    def test_other_rc_is_keychain(self):
        for rc in (51, 128, 1):
            self.assertEqual(self._fetch(rc), qf.QF_ERR_KEYS[1], rc)

    def test_timeout_is_keychain(self):
        def boom(*a, **k):
            raise subprocess.TimeoutExpired("security", 10)
        q.subprocess.run = lambda *a, **k: _R(44)
        q._oauth_token()
        q.subprocess.run = boom     # a later failure must not keep the stale «not signed in»
        self.assertFalse(qf._quota_fetch())
        self.assertEqual(qf._quota["err"], qf.QF_ERR_KEYS[1])


if __name__ == "__main__":
    unittest.main()
