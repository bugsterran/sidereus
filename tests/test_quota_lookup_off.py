"""quota_lookup off: no keychain read, no quota call (SECURITY.md)."""
import os
import unittest

from tests._load import sidereus

q = sidereus("quota")
qf = sidereus("quota_fetch")


class LookupOff(unittest.TestCase):
    def setUp(self):
        self.saved = (q.CFG.get("quota_lookup"), os.environ.pop(q.QUOTA_LOOKUP_ENV, None), q.subprocess.run, qf._qf_request)
        self.calls = []
        q.subprocess.run = lambda *a, **k: self.calls.append("security") or (_ for _ in ()).throw(AssertionError("keychain read"))
        qf._qf_request = lambda tok: self.calls.append("http") or (False, None)

    def tearDown(self):
        cfg, env, run, req = self.saved
        if cfg is None:
            q.CFG.pop("quota_lookup", None)
        else:
            q.CFG["quota_lookup"] = cfg
        if env is not None:
            os.environ[q.QUOTA_LOOKUP_ENV] = env
        q.subprocess.run, qf._qf_request = run, req

    def test_config_off_reads_nothing(self):
        q.CFG["quota_lookup"] = False
        self.assertIsNone(q._oauth_token())
        self.assertFalse(qf._quota_fetch())
        self.assertEqual(self.calls, [])

    def test_env_beats_config(self):
        q.CFG["quota_lookup"] = True
        os.environ[q.QUOTA_LOOKUP_ENV] = "0"
        try:
            self.assertFalse(q._quota_lookup_on())
        finally:
            os.environ.pop(q.QUOTA_LOOKUP_ENV, None)
        self.assertTrue(q._quota_lookup_on())


if __name__ == "__main__":
    unittest.main()
