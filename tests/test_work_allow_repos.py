"""_allowed_cwds keeps one row per cwd but unions the repos of every row in that cwd (repos are per session)."""
import unittest

from tests._load import sidereus

wk = sidereus("work")


class AllowReposUnion(unittest.TestCase):
    def setUp(self):
        self._sess, self._allow = wk.sessions_rows, list(wk._ALLOW)
        self.addCleanup(setattr, wk, "sessions_rows", self._sess)
        self.addCleanup(wk._ALLOW.__setitem__, slice(None), self._allow)
        wk._ALLOW[:] = [0.0, {}]
        self.rows = [{"cwd": "/w/cwd", "plat": "cc", "sid": "a", "repos": ["/w/x", "/w/y"]},
                     {"cwd": "/w/cwd", "plat": "cc", "sid": "b", "repos": ["/w/y", "/w/z"]},
                     {"cwd": "/w/cwd", "plat": "gemini", "sid": "g", "repos": []}]
        wk.sessions_rows = lambda **k: self.rows

    def test_repos_of_every_row_kept_in_order(self):
        got = wk._allowed_cwds()
        self.assertEqual(got["/w/cwd"]["repos"], ["/w/x", "/w/y", "/w/z"])
        self.assertEqual(got["/w/cwd"]["sid"], "b")   # later Claude row still wins; Gemini row never replaces it

    def test_snapshot_rows_not_mutated(self):
        wk._allowed_cwds()
        self.assertEqual(self.rows[1]["repos"], ["/w/y", "/w/z"])


if __name__ == "__main__":
    unittest.main()
