"""Untracked files count as uncommitted: _wt_git dirty and wt_files rows use `status -unormal` (dir = one entry).
No live git: _git_run / run_in faked, paths in a temp dir."""
import os
import subprocess
import tempfile
import unittest

from tests._load import sidereus

g = sidereus("git")
gw = sidereus("git_wt")


class _R(object):
    def __init__(self, out, rc=0):
        self.stdout, self.returncode = out, rc


# porcelain -z output of a worktree holding only new files: one file and one untracked dir folded to "new/"
OUT = "?? a.txt\0?? new/\0"


class Untracked(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.calls = []
        self._saved = (g._git_run, g._branch_ok)
        g._branch_ok = lambda cwd: True

    def tearDown(self):
        g._git_run, g._branch_ok = self._saved
        self.td.cleanup()

    def test_wt_git_counts_untracked(self):
        def run_in(p, args):
            self.calls.append(args)
            return _R(OUT)
        h = gw._wt_git(self.td.name, "", True, run_in)
        self.assertEqual(h["dirty"], 2)
        self.assertIn("-unormal", self.calls[0])
        self.assertNotIn("-uno", self.calls[0])

    def test_wt_files_keeps_question_marks(self):
        def fake(cwd, args, timeout, **kw):
            self.calls.append(args)
            return _R(OUT + " M b.py\0")
        g._git_run = fake
        code, out = g.wt_files(self.td.name)
        self.assertEqual(code, 200)
        self.assertEqual(out["n"], 3)
        self.assertEqual(out["files"][:2], [{"st": "??", "path": "a.txt"}, {"st": "??", "path": "new/"}])
        self.assertEqual(out["files"][2], {"st": "M", "path": "b.py"})
        self.assertIn("-unormal", self.calls[0])

    def test_wt_files_timeout_unchanged(self):
        def slow(cwd, args, timeout, **kw):
            raise subprocess.TimeoutExpired(args, timeout)
        g._git_run = slow
        self.assertEqual(g.wt_files(self.td.name), (504, {"ok": False, "err": "timeout"}))


class SecretUntracked(unittest.TestCase):
    """An untracked `.env` shows its name but never its body, in both the diff window and the full-file view."""
    def setUp(self):
        self.gv = gv = sidereus("git_view")
        self.td = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.td.name)
        os.mkdir(os.path.join(self.root, ".git"))
        for n, b in ((".env", "API_KEY=xyz-secret\n"), (".env.example", "API_KEY=placeholder\n")):
            with open(os.path.join(self.root, n), "w", encoding="utf-8") as fh:
                fh.write(b)

        def fake(cwd, args, timeout, wait=None, **kw):
            if args[0] == "ls-files" and "--others" in args:
                return _R(".env\0.env.example\0")
            if args[0] == "ls-files":
                return _R("", 1)                               # --error-unmatch: not tracked
            if args[0] == "status":
                return _R("? .env\0? .env.example\0")
            return _R("")
        self._saved = (gv._git_run, gv._git_run_capped, gv.sessions_rows)
        gv._git_run = fake
        gv._git_run_capped = lambda cwd, args, timeout, cap: ("", 0)
        gv.sessions_rows = lambda **k: [{"cwd": self.root, "repos": []}]

    def tearDown(self):
        self.gv._git_run, self.gv._git_run_capped, self.gv.sessions_rows = self._saved
        self.td.cleanup()

    def test_env_hidden(self):
        d = self.gv.git_diff(self.root, scope="work", untr="1")
        self.assertIn("b/.env\n", d["diff"])
        self.assertNotIn("xyz-secret", d["diff"])
        self.assertIn("+API_KEY=placeholder", d["diff"])     # shared template still readable
        f = self.gv.git_file_diff(self.root, ".env", "work")
        self.assertIn(".env", f["diff"])
        self.assertNotIn("xyz-secret", f["diff"])
        self.assertIn("+++ b/.env\n@@ -0,0 +1,1 @@\n+(contents hidden: secret file)\n", f["diff"])
        self.assertIn("placeholder", self.gv.git_file_diff(self.root, ".env.example", "work")["diff"])

    def test_names(self):
        s = self.gv._secret_name
        for n in (".env", "a/.env.local", "k.pem", "x.KEY", "id_ed25519", ".netrc", "credentials.json"):
            self.assertTrue(s(n), n)
        for n in (".env.example", ".env.sample", ".env.template", "id_rsa.pub", "env.py", "a.txt"):
            self.assertFalse(s(n), n)


if __name__ == "__main__":
    unittest.main()
