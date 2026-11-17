"""session_repos (sidereus/gitinfo.py): an idle session whose cwd becomes a repo later gets it after the miss TTL,
not only after its transcript is written again. Fake clock and fake walk; no live files."""
import unittest
from unittest import mock

from tests._load import sidereus

gi = sidereus("gitinfo")

CWD = "/nonexistent-sidereus/proj/r/sub"
ROOT = "/nonexistent-sidereus/proj/r"


class SessionReposLateInit(unittest.TestCase):
    def setUp(self):
        self.now = [1000.0]
        self.repo = [False]
        self.walks = []

        def walk(d):
            self.walks.append(d)
            return ROOT if self.repo[0] and d.startswith(ROOT) else ""

        for name, val in (("_REPO_CACHE", {}), ("_GITROOT", {}), ("_GITROOT_MISS", gi.BoundedMemo(gi.GITROOT_MAX)),
                          ("_mono", lambda: self.now[0]), ("_git_walk", walk),
                          ("_tool_inputs", lambda fp, off: ([], off, False))):
            p = mock.patch.object(gi, name, val)
            p.start()
            self.addCleanup(p.stop)

    def test_git_init_reaches_idle_row_after_miss_ttl(self):
        fp = "/nonexistent-sidereus/t.jsonl"
        self.assertEqual(gi.session_repos(fp, 1.0, CWD), [])
        self.repo[0] = True                       # `git init proj/r` from outside; transcript mtime unchanged
        self.assertEqual(gi.session_repos(fp, 1.0, CWD), [])   # still inside the miss window
        self.now[0] += gi.GITROOT_MISS_TTL
        self.assertEqual(gi.session_repos(fp, 1.0, CWD), [ROOT])
        self.assertEqual(gi._REPO_CACHE[fp][1], [ROOT])

    def test_hit_with_own_root_does_not_walk(self):
        self.repo[0] = True
        fp = "/nonexistent-sidereus/u.jsonl"
        self.assertEqual(gi.session_repos(fp, 1.0, CWD), [ROOT])
        self.walks.clear()
        gi._GITROOT.clear()                       # a re-ask would have to walk again
        for _ in range(5):
            self.assertEqual(gi.session_repos(fp, 1.0, CWD), [ROOT])
        self.assertEqual(self.walks, [])

    def test_late_root_goes_first_and_cap_holds(self):
        fp = "/nonexistent-sidereus/v.jsonl"
        others = ["/nonexistent-sidereus/o%d" % i for i in range(8)]
        gi._REPO_CACHE[fp] = (1.0, list(others), 0, list(others), "")
        self.repo[0] = True
        out = gi.session_repos(fp, 1.0, CWD)
        self.assertEqual(out, [ROOT] + others[:7])


if __name__ == "__main__":
    unittest.main()
