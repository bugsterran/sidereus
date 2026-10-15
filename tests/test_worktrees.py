"""`_worktrees` porcelain parsing: prunable (dead) worktrees are not work units. No live git."""
import types
import unittest

from tests._load import sidereus

gi = sidereus("gitinfo")

PORCELAIN = """worktree /repo/main
HEAD ecf954a4aaaaaaaa
branch refs/heads/main

worktree /tmp/gone/bl-fold
HEAD 3b2f23a4bbbbbbbb
detached
prunable gitdir file points to non-existent location

worktree /repo/wt-live
HEAD 1234567ccccccccc
branch refs/heads/fix/x

"""


def _run(args):
    return types.SimpleNamespace(returncode=0, stdout=PORCELAIN)


class Worktrees(unittest.TestCase):
    def test_prunable_dropped(self):
        ws = gi._worktrees(_run)
        self.assertEqual([w["branch"] for w in ws], ["main", "fix/x"])
        self.assertTrue(ws[0]["main"])
        self.assertFalse(ws[1]["main"])


if __name__ == "__main__":
    unittest.main()
