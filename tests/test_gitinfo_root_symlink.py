"""gitinfo: a git-root miss is not cached, session repos dedupe by realpath, pi relative paths outside home resolve.
Temp dirs only: _HOME and _PATH_RE are patched to point inside a temp "home"."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

gi = sidereus("gitinfo")


def tu(**inp):
    return json.dumps({"message": {"content": [{"type": "tool_use", "name": "Edit", "input": inp}]}})


class GitRootMissNotCached(unittest.TestCase):
    def setUp(self):
        self.saved = dict(gi._GITROOT)
        gi._GITROOT.clear()
        self.d = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-gr-"))

    def tearDown(self):
        gi._GITROOT.clear()
        gi._GITROOT.update(self.saved)
        shutil.rmtree(self.d, ignore_errors=True)

    def test_git_init_after_miss_is_seen(self):
        self.assertEqual(gi._git_root(self.d), "")
        os.makedirs(os.path.join(self.d, ".git"))
        self.assertEqual(gi._git_root(self.d), self.d)


class SessionReposSymlink(unittest.TestCase):
    def setUp(self):
        self.home = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-home-"))
        self.saved = (gi._HOME, gi._PATH_RE)
        gi._HOME = self.home
        gi._PATH_RE = gi._path_re(self.home)
        gi._REPO_CACHE.clear()
        gi._GITROOT.clear()
        self.real = os.path.join(self.home, "real")
        os.makedirs(os.path.join(self.real, ".git"))
        os.makedirs(os.path.join(self.real, "src"))
        self.link = os.path.join(self.home, "link")
        os.symlink(self.real, self.link)
        self.launch = os.path.join(self.home, "launch")
        os.makedirs(self.launch)

    def tearDown(self):
        gi._HOME, gi._PATH_RE = self.saved
        gi._REPO_CACHE.clear()
        gi._GITROOT.clear()
        shutil.rmtree(self.home, ignore_errors=True)

    def repos(self, lines, cwd):
        fp = os.path.join(self.home, "t.jsonl")
        with open(fp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return gi.session_repos(fp, os.path.getmtime(fp), cwd)

    def test_link_and_real_listed_once(self):
        got = self.repos([tu(file_path=self.real + "/src/a.py"), tu(file_path=self.link + "/src/b.py")], self.launch)
        self.assertEqual(len(got), 1)
        self.assertIn(got[0], (self.real, self.link))

    def test_cwd_form_kept_first(self):
        # the cwd's root keeps the cwd's own spelling so it still matches the row's cwd
        got = self.repos([tu(file_path=self.real + "/src/a.py")], self.link)
        self.assertEqual(got, [self.link])


class PiAbsPath(unittest.TestCase):
    def test_relative_outside_home(self):
        self.assertEqual(gi.pi_abs_path("a.py", "/opt/x"), "/opt/x/a.py")

    def test_relative_without_cwd(self):
        self.assertEqual(gi.pi_abs_path("a.py", ""), "")
        self.assertEqual(gi.pi_abs_path("a.py", "rel"), "")


if __name__ == "__main__":
    unittest.main()
