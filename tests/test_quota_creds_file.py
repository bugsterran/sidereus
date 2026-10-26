"""Off macOS the primary's OAuth token comes from `<config dir>/.credentials.json` (guarded); macOS keeps the keychain."""
import builtins
import json
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

q = sidereus("quota")
qf = sidereus("quota_fetch")
FAKE = "fake-token-for-tests"


class CredsFile(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="sidereus-creds-")
        self.saved = (q.IS_MAC, q.claude_home, q._quota_lookup_on, q.subprocess.run, builtins.open)
        q.IS_MAC = False
        q.claude_home = lambda: self.d
        q._quota_lookup_on = lambda: True
        q.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(AssertionError("keychain read off macOS"))

    def tearDown(self):
        q.IS_MAC, q.claude_home, q._quota_lookup_on, q.subprocess.run, builtins.open = self.saved
        shutil.rmtree(self.d, ignore_errors=True)

    def _write(self, body, name=".credentials.json"):
        p = os.path.join(self.d, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)
        return p

    def test_valid_file_gives_token(self):
        self._write(json.dumps({"claudeAiOauth": {"accessToken": FAKE}}))
        self.assertEqual(q._oauth_token(), FAKE)

    def test_flat_access_token(self):
        self._write(json.dumps({"accessToken": FAKE}))
        self.assertEqual(q._oauth_token(), FAKE)

    def test_symlink_refused(self):
        real = self._write(json.dumps({"claudeAiOauth": {"accessToken": FAKE}}), "real.json")
        os.symlink(real, os.path.join(self.d, ".credentials.json"))
        self.assertIsNone(q._oauth_token())

    def test_directory_refused(self):
        os.mkdir(os.path.join(self.d, ".credentials.json"))
        self.assertIsNone(q._oauth_token())

    def test_oversize_refused(self):
        self._write(json.dumps({"claudeAiOauth": {"accessToken": FAKE}, "pad": "x" * (q.CREDS_MAX_BYTES + 1)}))
        self.assertIsNone(q._oauth_token())

    def test_malformed_refused(self):
        for body in ("{not json", "[1, 2]", json.dumps({"claudeAiOauth": {"accessToken": 7}})):
            self._write(body)
            self.assertIsNone(q._oauth_token(), body)

    def test_missing_file(self):
        self.assertIsNone(q._oauth_token())

    def test_lookup_off_reads_nothing(self):
        self._write(json.dumps({"claudeAiOauth": {"accessToken": FAKE}}))
        q._quota_lookup_on = lambda: False
        calls = []
        builtins.open = lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(AssertionError("open called"))
        try:
            self.assertIsNone(q._oauth_token())
        finally:
            builtins.open = self.saved[4]
        self.assertEqual(calls, [])

    def test_no_login_reason_off_mac(self):
        saved = (qf.IS_MAC, qf._oauth_token, qf._quota_lookup_on, qf._quota.get("err"))
        qf.IS_MAC, qf._oauth_token, qf._quota_lookup_on = False, lambda: None, lambda: True
        try:
            self.assertFalse(qf._quota_fetch())
            self.assertEqual(qf._quota["err"], "No Claude Code login found")
            qf.IS_MAC = True
            qf._quota_fetch()
            self.assertEqual(qf._quota["err"], qf.QF_ERR_KEYS[1])     # macOS reason unchanged
        finally:
            qf.IS_MAC, qf._oauth_token, qf._quota_lookup_on, qf._quota["err"] = saved


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ErrText(unittest.TestCase):
    def test_reasons(self):
        import subprocess
        from tests._load import js_fn
        from tests._node import node_e
        from tests.test_saver_quota_js import i18n
        src = "var document = {getElementById: () => null};\n" + i18n() + "\n" + js_fn("qErrText") + "\nprocess.stdout.write(JSON.stringify(" \
            "['URLError', 'timeout', 'HTTPError 429', 'No Claude Code login found', null].map(qErrText)));"
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), ["사용량 API 에 연결하지 못했습니다", "사용량 API 에 연결하지 못했습니다",
                                                "HTTPError 429", "Claude Code 로그인 정보를 찾지 못했습니다", ""])


if __name__ == "__main__":
    unittest.main()
