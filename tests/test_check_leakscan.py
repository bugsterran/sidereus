"""scripts/leakscan.py matcher: identifiers, home paths, UUIDs, secrets, allow marker, binary skip, .distignore."""
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

from tests._fs import rmtree_force

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("leakscan", os.path.join(ROOT, "scripts", "leakscan.py"))
L = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(L)

IDS = L.identifiers("Kim Tester/Platform Team/CL", "kim.tester@acmecorp.example", "kimt")
UID = "12345678-9abc-4def-8123-456789abcdef"


def kinds(rel, text):
    return [h[2] for h in L.scan_text(rel, text, IDS)]


class Matcher(unittest.TestCase):
    def test_identifiers(self):
        self.assertEqual(kinds("a.py", "by Kim Tester\n"), ["ident"])
        self.assertEqual(kinds("a.py", "mail KIM.TESTER@x\n"), ["ident"])
        self.assertEqual(kinds("a.py", "host acmecorp.io\n"), ["ident"])
        self.assertEqual(kinds("a.py", "who: kimt\n"), ["ident"])
        self.assertEqual(kinds("a.py", "kimtx acmecorpish CL\n"), [])   # word-bounded; short parts ignored

    def _idents(self, glob, local):
        """git_idents() in a temp repo with the given global/local (name, email); never reads live config."""
        d = tempfile.mkdtemp()
        try:
            g = os.path.join(d, "global.cfg")
            with open(g, "w", encoding="utf-8") as f:
                f.write("[user]\n\tname = %s\n\temail = %s\n" % glob if glob else "")
            subprocess.run(["git", "init", "-q", d], check=True)
            if local:
                subprocess.run(["git", "-C", d, "config", "user.name", local[0]], check=True)
                subprocess.run(["git", "-C", d, "config", "user.email", local[1]], check=True)
            env = {"GIT_CONFIG_GLOBAL": g, "GIT_CONFIG_NOSYSTEM": "1", "USER": "kimt"}
            old = {k: os.environ.get(k) for k in env}
            os.environ.update(env)
            try:
                ids = L.git_idents(d)
            finally:
                for k, v in old.items():
                    os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
            return lambda t: [h[2] for h in L.scan_text("a.py", t, ids)]
        finally:
            rmtree_force(d)

    PRIV = ("Kim Tester/Platform Team/CL", "kim.tester@acmecorp.example")
    PUB = ("nickpub", "nickpub@mailhost.example")

    def test_local_public_identity_not_a_leak(self):
        hit = self._idents(self.PRIV, self.PUB)
        self.assertEqual(hit("by Kim Tester\n"), ["ident"])        # private global identity still caught
        self.assertEqual(hit("Copyright nickpub\n"), [])            # public repo-local author allowed

    def test_no_global_identity_keeps_local_private(self):
        hit = self._idents(None, self.PRIV)
        self.assertEqual(hit("by Kim Tester\n"), ["ident"])

    def test_same_identity_local_and_global_stays_private(self):
        hit = self._idents(self.PRIV, self.PRIV)
        self.assertEqual(hit("by Kim Tester\n"), ["ident"])
        self.assertEqual(hit("host acmecorp.io\n"), ["ident"])

    def test_homedir(self):
        self.assertEqual(kinds("a.py", 'p = "/Users/zed/x"\n'), ["homedir"])  # leakscan: allow
        self.assertEqual(kinds("a.py", 'p = "/Users/x/proj" or "/Users/demo"\n'), [])

    def test_uuid_outside_fixtures(self):
        self.assertEqual(kinds("sidereus/x.py", "sid=" + UID + "\n"), ["uuid"])
        self.assertEqual(kinds("tests/test_x.py", "sid=" + UID + "\n"), [])
        self.assertEqual(kinds("sidereus/demo_data.py", UID + "\n"), [])

    def test_secrets(self):
        self.assertEqual(kinds("a.py", "k = 'ghp_" + "A" * 20 + "'\n"), ["token"])
        self.assertEqual(kinds("a.py", "-----BEGIN RSA PRIVATE KEY-----\n"), ["private-key"])
        self.assertEqual(kinds("a.py", "API_TOKEN=" + "a1B2" * 8 + "\n"), ["named-secret"])
        self.assertEqual(kinds("a.py", "task-notification token = get_token()\n"), [])
        self.assertEqual(kinds("tests/test_r.py", "sk-ant-" + "x" * 20 + "\n"), [])   # fixture secret

    def test_allow_marker(self):
        self.assertEqual(kinds("a.py", "Kim Tester  # leakscan: allow\n"), [])

    def test_line_numbers(self):
        hits = L.scan_text("a.md", "ok\nok\n/Users/zed\n", IDS)  # leakscan: allow
        self.assertEqual([(h[0], h[1]) for h in hits], [("a.md", 3)])


class Files(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="leakscan-")
        self.addCleanup(rmtree_force, self.d)

    def w(self, rel, data):
        p = os.path.join(self.d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)

    def test_binary_skipped(self):
        self.w("img.bin", b"\x89PNG\0\0 Kim Tester")
        self.w("t.txt", b"Kim Tester\n")
        self.assertEqual(L.scan_file(self.d, "img.bin", IDS), [])
        self.assertEqual(len(L.scan_file(self.d, "t.txt", IDS)), 1)

    def test_shipped_honours_distignore(self):
        if shutil.which("git") is None:
            self.skipTest("no git")
        self.w(".distignore", b"secret/\n*.log\nNOTES-*\n")
        for rel in ("a.py", "secret/b.py", "x.log", "NOTES-1.md", "docs/c.md"):
            self.w(rel, b"x\n")
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
        subprocess.run(["git", "init", "-q", self.d], check=True, env=env)
        subprocess.run(["git", "-C", self.d, "add", "-A"], check=True, env=env)
        self.assertEqual(sorted(L.shipped(self.d)), [".distignore", "a.py", "docs/c.md"])


if __name__ == "__main__":
    unittest.main()
