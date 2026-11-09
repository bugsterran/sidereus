"""Session wt: a non-git cwd falls back to repos[0] only when that is a linked worktree. Synthetic data only."""
import unittest

from tests._load import sidereus

s = sidereus("sessions")

WTS = {
    "/w/app": {"root": "/w/app", "main": "", "name": "app"},
    "/w/app-wt-fix": {"root": "/w/app-wt-fix", "main": "/w/app", "name": "app-wt-fix"},
}


class WtRepoFallback(unittest.TestCase):
    def setUp(self):
        self._old = s._wt_of
        s._wt_of = lambda d: WTS.get(d)

    def tearDown(self):
        s._wt_of = self._old

    def test_non_git_cwd_linked_worktree(self):
        out = s._row_repos_wt("/w/bot", ["/w/app-wt-fix", "/w/app"])
        self.assertEqual(out["wt"], WTS["/w/app-wt-fix"])
        self.assertEqual(out["repos"], ["/w/app-wt-fix", "/w/app"])

    def test_non_git_cwd_plain_repo(self):
        self.assertIsNone(s._row_repos_wt("/w/bot", ["/w/app", "/w/app-wt-fix"])["wt"])

    def test_non_git_cwd_no_repos(self):
        self.assertIsNone(s._row_repos_wt("/w/bot", [])["wt"])

    def test_git_cwd_unchanged(self):
        self.assertEqual(s._row_repos_wt("/w/app", ["/w/app-wt-fix"])["wt"], WTS["/w/app"])


if __name__ == "__main__":
    unittest.main()
