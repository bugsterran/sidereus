"""ident._git_walk / gitinfo._git_root: a non-absolute cwd never resolves against the server's own cwd."""
import os
import tempfile
import unittest

from tests._load import sidereus


class GitWalkAbs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ident = sidereus("ident")
        cls.gi = sidereus("gitinfo")

    def setUp(self):
        self.gi._GITROOT.clear()

    def test_relative_dir_is_none(self):
        self.assertEqual(self.ident._git_walk("rel/dir"), "")
        self.assertEqual(self.gi._git_root("rel/dir"), "")
        self.assertEqual(self.gi._git_root("."), "")

    @unittest.skipIf(os.name == "nt", "a drive path is absolute on Windows")
    def test_foreign_windows_cwd_is_none(self):
        self.assertEqual(self.gi._git_root("C:\\Users\\demo\\app"), "")

    def test_absolute_dirs_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            td = os.path.realpath(td)
            bare = os.path.join(td, "plain")
            repo = os.path.join(td, "repo")
            sub = os.path.join(repo, "a", "b")
            os.makedirs(bare)
            os.makedirs(sub)
            os.makedirs(os.path.join(repo, ".git"))
            self.assertEqual(self.gi._git_root(sub), repo)
            self.assertEqual(self.ident._git_walk(repo), repo)
            # a git-less temp dir walks up to whatever is above it (normally ""), same as before
            self.assertNotEqual(self.ident._git_walk(bare), bare)


if __name__ == "__main__":
    unittest.main()
