"""gitinfo._wt_split: worktree gitdir -> main repo on both POSIX and Windows separators (pure string, no fs)."""
import ntpath
import posixpath
import unittest

from tests._load import sidereus

gi = sidereus("gitinfo")


class WtSplitSep(unittest.TestCase):
    def test_posix(self):
        self.assertEqual(gi._wt_split("/r/app/.git/worktrees/x", posixpath), "/r/app")
        self.assertEqual(gi._wt_split("/r/app/.git/worktrees/", posixpath), "")
        self.assertEqual(gi._wt_split("/r/app/.git/modules/x", posixpath), "")

    def test_windows_backslash(self):
        # ⚠realpath on Windows returns backslashes; the old literal "/.git/worktrees/" search gave "" here.
        self.assertEqual(gi._wt_split(r"C:\r\app\.git\worktrees\x", ntpath), r"C:\r\app")
        self.assertEqual(gi._wt_split(r"C:\r\app\.git\worktrees" + "\\", ntpath), "")
        self.assertEqual(gi._wt_split(r"C:\r\app\.git\modules\x", ntpath), "")


if __name__ == "__main__":
    unittest.main()
