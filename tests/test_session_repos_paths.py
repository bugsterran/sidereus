"""session_repos (sidereus/gitinfo.py) folds `~/...` paths and `cd <dir>` targets into git roots, not only absolute paths.
Temp dirs only: _HOME and _PATH_RE are patched to point inside a temp "home"."""
import json
import os
import re
import shutil
import tempfile
import unittest

from tests._load import sidereus

gi = sidereus("gitinfo")


def tu(**inp):
    return json.dumps({"message": {"content": [{"type": "tool_use", "name": "Bash", "input": inp}]}})


class SessionReposPaths(unittest.TestCase):
    def setUp(self):
        self.home = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-home-"))
        self.saved = (gi._HOME, gi._PATH_RE)
        gi._HOME = self.home
        gi._PATH_RE = gi._path_re(self.home)       # the product builder: `\` separators on Windows
        gi._REPO_CACHE.clear()
        gi._GITROOT.clear()
        self.launch = self.mk("launch", git=False)

    def tearDown(self):
        gi._HOME, gi._PATH_RE = self.saved
        gi._REPO_CACHE.clear()
        gi._GITROOT.clear()
        shutil.rmtree(self.home, ignore_errors=True)

    def mk(self, name, git=True):
        d = os.path.join(self.home, name)
        os.makedirs(os.path.join(d, "src"))
        if git:
            os.makedirs(os.path.join(d, ".git"))
        return d

    def repos(self, lines):
        fp = os.path.join(self.home, "t.jsonl")
        with open(fp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return gi.session_repos(fp, os.path.getmtime(fp), self.launch)

    def test_tilde_path_resolves(self):
        a = self.mk("agent")
        self.assertEqual(self.repos([tu(file_path="~/agent/src/x.py")]), [a])

    def test_cd_relative_to_cwd(self):
        sub = os.path.join(self.launch, "inner")
        os.makedirs(os.path.join(sub, ".git"))
        self.assertEqual(self.repos([tu(command="cd inner && make")]), [sub])

    def test_absolute_path(self):
        a = self.mk("abs")
        self.assertEqual(self.repos([tu(file_path=a + "/src/y.py")]), [a])

    def test_non_git_and_missing_ignored(self):
        self.mk("plain", git=False)
        got = self.repos([tu(command="cd plain; cd nowhere; ls ~/plain/src ~/gone/z")])
        self.assertEqual(got, [])

    def test_windows_path_re(self):
        """Windows transcripts carry `C:\\Users\\me\\repo\\a.py` (or `/`, mixed, any case); POSIX pattern unchanged."""
        w = gi._path_re("C:\\Users", win=True)
        for s in ("C:\\Users\\me\\repo\\src\\a.py", "C:/Users/me/repo/a.py", "c:\\users\\me\\repo/a.py"):
            self.assertEqual([m.group(0) for m in w.finditer("x " + s + " y")], [s])
        self.assertEqual(w.findall("D:\\Users\\me\\a.py"), [])
        self.assertEqual(gi._path_re("/home", win=False).pattern, r"/home/[A-Za-z0-9_.-]+/[A-Za-z0-9_.\-/]+")

    def test_cd_outside_home_ignored(self):
        self.assertEqual(self.repos([tu(command="cd /")]), [])


if __name__ == "__main__":
    unittest.main()
