"""/api/git/file: user paths reach git only as `:(literal)` pathspecs; magic prefixes and NUL are refused (temp repo)."""
import os
import shutil
import subprocess
import tempfile
import unittest

from tests._load import sidereus

gv = sidereus("git_view")


class FilePathspec(unittest.TestCase):
    def setUp(self):
        self.d = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d)
        self._sess = gv.sessions_rows
        gv.sessions_rows = lambda **k: [{"cwd": self.d, "repos": []}]
        self.addCleanup(setattr, gv, "sessions_rows", self._sess)
        self.git("init", "-q", "-b", "main")
        for p in ("a.txt", "b.txt", "x*"):
            with open(os.path.join(self.d, p), "w") as fh:
                fh.write(p + "\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "init")
        for p in ("a.txt", "b.txt", "x*"):
            with open(os.path.join(self.d, p), "a") as fh:
                fh.write("more\n")

    def git(self, *a):
        return subprocess.run(["git", "-C", self.d, "-c", "user.name=t", "-c", "user.email=t@t",
                               "-c", "commit.gpgsign=false"] + list(a),
                              check=True, capture_output=True, text=True).stdout

    def test_magic_and_nul_refused(self):
        for p in (":(glob)**", ":/", ":!a.txt", "a.txt\0b", ":(literal)a.txt"):
            r = gv.git_file_diff(self.d, p, "work")
            self.assertFalse(r["ok"], p)
            self.assertNotIn("diff", r)

    def test_glob_chars_are_literal(self):
        r = gv.git_file_diff(self.d, "*.txt", "work")
        self.assertFalse(r["ok"])                     # no file named `*.txt`, and it must not match a.txt/b.txt
        r = gv.git_file_diff(self.d, "x*", "work")
        self.assertTrue(r["ok"])
        self.assertIn("b/x*", r["diff"])
        self.assertNotIn("a.txt", r["diff"])

    def test_plain_file_unchanged(self):
        r = gv.git_file_diff(self.d, "a.txt", "work")
        self.assertTrue(r["ok"])
        self.assertIn("+more", r["diff"])
        self.assertNotIn("b.txt", r["diff"])


if __name__ == "__main__":
    unittest.main()
