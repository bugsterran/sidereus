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


if __name__ == "__main__":
    unittest.main()
