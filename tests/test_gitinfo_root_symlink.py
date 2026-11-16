"""gitinfo: a git-root miss is cached only for GITROOT_MISS_TTL, session repos dedupe by realpath, pi relative paths outside home resolve.
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


class GitRootMissTtl(unittest.TestCase):
    def setUp(self):
        self.saved = (dict(gi._GITROOT), dict(gi._GITROOT_MISS), gi._mono)
        gi._GITROOT.clear()
        gi._GITROOT_MISS.clear()
        self.now = [1000.0]
        gi._mono = lambda: self.now[0]
        self.d = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-gr-"))

    def tearDown(self):
        gi._GITROOT.clear()
        gi._GITROOT.update(self.saved[0])
        gi._GITROOT_MISS.clear()
        gi._GITROOT_MISS.update(self.saved[1])
        gi._mono = self.saved[2]
        shutil.rmtree(self.d, ignore_errors=True)

    def test_git_init_after_miss_is_seen_after_ttl(self):
        self.assertEqual(gi._git_root(self.d), "")
        os.makedirs(os.path.join(self.d, ".git"))
        self.now[0] += gi.GITROOT_MISS_TTL
        self.assertEqual(gi._git_root(self.d), self.d)

    def test_miss_is_cached_inside_the_window(self):
        # a miss must not walk the fs again on every poll (cwd_git runs per external row)
        self.assertEqual(gi._git_root(self.d), "")
        walks = []
        real = gi._git_walk
        gi._git_walk = lambda d: walks.append(d) or real(d)
        try:
            self.assertEqual(gi._git_root(self.d), "")
        finally:
            gi._git_walk = real
        self.assertEqual(walks, [])


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
        # ⚠Expected value goes through normpath: on Windows the result is native (`\opt\x\a.py`), not POSIX.
        self.assertEqual(gi.pi_abs_path("a.py", "/opt/x"), os.path.normpath("/opt/x/a.py"))

    def test_relative_without_cwd(self):
        self.assertEqual(gi.pi_abs_path("a.py", ""), "")
        self.assertEqual(gi.pi_abs_path("a.py", "rel"), "")


if __name__ == "__main__":
    unittest.main()
