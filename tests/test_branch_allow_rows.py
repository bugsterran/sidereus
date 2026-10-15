"""_branch_ok reads repos from every session row, not one row per cwd (picker and gate share the same rows)."""
import unittest

from tests._load import sidereus

gv = sidereus("git_view")


class BranchAllowRows(unittest.TestCase):
    def setUp(self):
        self._sess = gv.sessions_rows
        self.addCleanup(setattr, gv, "sessions_rows", self._sess)
        gv.sessions_rows = lambda **k: [{"cwd": "/w/cwd", "repos": ["/w/repo-x"]},
                                        {"cwd": "/w/cwd", "repos": []}]

    def test_repo_of_earlier_row_same_cwd_allowed(self):
        self.assertTrue(gv._branch_ok("/w/repo-x"))
        self.assertTrue(gv._branch_ok("/w/cwd"))

    def test_path_in_no_row_refused(self):
        self.assertFalse(gv._branch_ok("/w/other"))
        self.assertFalse(gv._branch_ok(""))


if __name__ == "__main__":
    unittest.main()
