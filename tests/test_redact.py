"""Work-popup secret redaction + structure allowed-roots denial of ~ and / (security audit 2026-09-25)."""
import os
import pwd
import unittest
from unittest import mock

from tests._load import sidereus

R = sidereus("redact")
W = sidereus("work")
S = sidereus("structure")
ST = sidereus("steps")
M = R.MASK


class RedactPatterns(unittest.TestCase):
    def assertMasked(self, raw, keep, secret):
        out = R.redact(raw)
        self.assertNotIn(secret, out, out)
        self.assertIn(keep, out)
        self.assertIn(M, out)

    def test_anthropic(self):
        self.assertMasked("k sk-ant-api03-AbCdEf123456_xyz", "sk-ant-", "AbCdEf123456")

    def test_openai(self):
        self.assertMasked("sk-proj-ZZZZyyyyXXXX1234", "sk-", "ZZZZyyyyXXXX1234")
        self.assertMasked("sk-abcdefghij1234567890", "sk-", "abcdefghij1234567890")

    def test_bearer(self):
        self.assertMasked("Authorization: Bearer abc.def-ghi123", "Bearer ", "abc.def-ghi123")

    def test_jwt(self):
        self.assertMasked("t=eyJhbGciOi.eyJzdWIiOiIx.SflKxwRJSMeKKF2", "eyJ", "SflKxwRJSMeKKF2")

    def test_aws(self):
        self.assertMasked("AKIAIOSFODNN7EXAMPLE", "AKIA", "IOSFODNN7EXAMPLE")

    def test_url_userinfo(self):
        self.assertMasked("psql postgresql://admin:FakeSecret99@db.example:5432/app", "postgresql://admin:", "FakeSecret99")
        self.assertMasked("mongodb+srv://u:p4ssXyz@c.example/x", "@c.example/x", "p4ssXyz")
        # no password part, or a port after the host: unchanged
        for s in ("https://user@host.example/x", "http://127.0.0.1:8799/api", "ssh git@github.com:org/repo"):
            self.assertEqual(R.redact(s), s)

    def test_github(self):
        for p in ("ghp_", "gho_", "github_pat_"):
            self.assertMasked(p + "A1b2C3d4E5f6G7h8", p, "A1b2C3d4E5f6G7h8")

    def test_slack(self):
        self.assertMasked("xoxb-1234567890-abcdef", "xoxb-", "1234567890-abcdef")

    def test_pem_multiline(self):
        # Headers built from halves so secret scanners do not flag a key literal.
        begin, end = "-----BEGIN RSA " + "PRIVATE KEY-----", "-----END RSA " + "PRIVATE KEY-----"
        lines = ["x", begin, "MIIEowIBAAKCAQEA", "zzzz", end, "y"]
        out = "\n".join(R.redact_lines(lines))
        self.assertNotIn("MIIEowIBAAKCAQEA", out)
        self.assertIn(begin + M + end, out)
        self.assertTrue(out.startswith("x\n") and out.endswith("\ny"))

    def test_env_and_json(self):
        self.assertMasked("DB_PASSWORD=hunter2", "DB_PASSWORD=", "hunter2")
        self.assertMasked("export API_KEY='abc 123'", "API_KEY=", "abc 123")
        self.assertMasked('{"client_secret": "s3cr3t", "x": 1}', '"client_secret": "', "s3cr3t")
        self.assertMasked("auth_token = zzz", "auth_token = ", "zzz")

    def test_normal_untouched(self):
        for s in ("def f(x):\n    return x + 1", "ls -la /tmp", "task done in 3s", "", "keyboard layout", None, 5):
            self.assertEqual(R.redact(s), s)


class WorkPayload(unittest.TestCase):
    def test_session_work_redacted(self):
        steps = [{"t": "", "tool": "Bash", "targ": "", "arg": "cat .env", "id": "a",
                  "edit": {"path": ".env", "old": "", "new": "TOKEN=zzz9", "cut": False}}]
        results = {"a": {"lines": ["OPENAI_API_KEY=sk-live1234567890", "plain"], "more": 0, "err": False}}  # gitleaks:allow
        says = [{"t": "", "text": "use Bearer tok_abcdef123"}]
        sc = (steps, says, results, "", "", "", "my password=pw1")
        with mock.patch.object(W, "_allowed_cwds", lambda: {"/w/proj": {"project": "proj"}}), \
                mock.patch.object(W, "_past_row", lambda c, s: None), \
                mock.patch.object(W, "_sid_path", lambda c, s: "/nonexistent.jsonl"), \
                mock.patch.object(W, "_open_or_tail", lambda fp, tail=None, at=None: None), \
                mock.patch.object(W, "_work_scan", lambda f, c: (sc, None)), \
                mock.patch.object(W.os, "listdir", lambda d: ["x.jsonl"]), \
                mock.patch.object(W.os.path, "getmtime", lambda p: 0):
            out = W.session_work("/w/proj", "")
        self.assertTrue(out.get("ok"), out)
        blob = repr(out)
        for secret in ("sk-live1234567890", "tok_abcdef123", "pw1", "zzz9"):
            self.assertNotIn(secret, blob)
        self.assertEqual(out["steps"][0]["res"]["lines"][1], "plain")

    def _scan(self, blocks):
        steps, says, results = [], [], {}
        ST._scan_blocks(blocks, steps, results, "", says, "")
        for st in steps:                  # same join as session_work, then the second pass
            if st.get("id") in results:
                st["res"] = results[st["id"]]
        return repr(R.redact_work({"ok": True, "steps": steps, "says": says}))

    def test_secret_straddling_cut_masked(self):
        # Fake secrets cut mid-way by the caps must not leak a fragment (redact before cut).
        dsn = "x" * (ST.AGENT_SAY_MAX - 25) + " postgresql://u:FakePw123456@h/db"
        js = "y" * (ST.AGENT_SAY_MAX - 20) + ' {"api_key": "FakeVal0987654321abcdefgh"}'
        ed = "z" * (ST.AGENT_EDIT_MAX - 22) + ' {"secret": "FakeTok123456789abcdef"}'
        res = "r" * (ST.AGENT_ARG_MAX - 20) + " mysql://u:FakeRes123456@h/db"
        blob = self._scan([{"type": "text", "text": dsn}, {"type": "text", "text": js},
                           {"type": "tool_use", "name": "Edit", "id": "e",
                            "input": {"file_path": "/a.py", "old_string": "", "new_string": ed}},
                           {"type": "tool_result", "tool_use_id": "e", "content": res}])
        self.assertEqual([f for f in ("FakePw", "FakeVa", "FakeTok", "FakeRes") if f in blob], [])
        self.assertIn("postgresql://u:", blob)


class StructRoots(unittest.TestCase):
    def test_home_and_root_denied(self):
        home = os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir)
        repo = os.path.join(home, "some", "repo")
        with mock.patch.object(S, "_struct_warm_targets", lambda: []), \
                mock.patch.object(S, "sessions_snapshot", lambda: [{"cwd": home, "repos": ["/", repo]}]):
            got = S._struct_allowed_roots()
        self.assertNotIn(home, got)
        self.assertNotIn("/", got)
        self.assertIn(os.path.realpath(repo), got)


if __name__ == "__main__":
    unittest.main()
