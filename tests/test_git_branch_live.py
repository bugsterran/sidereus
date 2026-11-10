"""Session row branch comes from live `git status --branch`, not the stale transcript gitBranch.
No live git: gitinfo._git_run faked, caches saved/restored, cwd is a temp dir."""
import subprocess
import tempfile
import unittest

from tests._load import sidereus

gi = sidereus("gitinfo")


class LiveBranch(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self._saved = (gi._git_run, dict(gi._git_cache), dict(gi._git_branch_cache))
        gi._git_cache.clear()
        gi._git_branch_cache.clear()
        self.out = ""
        self.rc = 0
        gi._git_run = lambda cwd, args, t, wait=0: subprocess.CompletedProcess(args, self.rc, self.out, "")

    def tearDown(self):
        gi._git_run = self._saved[0]
        gi._git_cache.clear(); gi._git_cache.update(self._saved[1])
        gi._git_branch_cache.clear(); gi._git_branch_cache.update(self._saved[2])
        self.td.cleanup()

    def test_live_branch_beats_stale_transcript(self):
        self.out = "## main...origin/main [ahead 1]\n M a.py\n"
        self.assertEqual(gi.git_branch(self.td.name, "worktree-agent-a1c1c277a3f0ac754"), "main")
        self.assertEqual(gi._git_state(self.td.name), "↑1 ~1")    # same call, marker unchanged

    def test_slash_branch_with_ahead_behind(self):
        self.out = "## fix/d160...origin/fix/d160 [ahead 2, behind 1]\n"
        self.assertEqual(gi.git_branch(self.td.name, "x"), "fix/d160")

    def test_no_upstream_and_unborn(self):
        self.out = "## feat/x\n"
        self.assertEqual(gi.git_branch(self.td.name), "feat/x")
        gi._git_cache.clear(); gi._git_branch_cache.clear()
        self.out = "## No commits yet on dev\n"
        self.assertEqual(gi.git_branch(self.td.name), "dev")

    def test_detached_is_empty_not_transcript(self):
        self.out = "## HEAD (no branch)\n"
        self.assertEqual(gi.git_branch(self.td.name, "worktree-agent-x"), "")

    def test_not_a_repo_falls_back_to_transcript(self):
        self.rc = 128
        self.assertEqual(gi.git_branch(self.td.name, "dev"), "dev")
        self.assertEqual(gi.git_branch("", "dev"), "dev")


if __name__ == "__main__":
    unittest.main()
