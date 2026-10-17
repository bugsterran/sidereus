"""Session row project = git root of the cwd (a shell cd into a repo subfolder is the same project). Temp dirs only."""
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

from unittest import mock

from tests import test_history_units as HU

sessions = sidereus("sessions")
gitinfo = sidereus("gitinfo")
ident = sidereus("ident")
H = HU.H


class ProjRoot(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        old = dict(ident._PROJ_ROOT)
        ident._PROJ_ROOT.clear()
        self.addCleanup(lambda: (ident._PROJ_ROOT.clear(), ident._PROJ_ROOT.update(old)))

    def mk(self, *parts):
        p = os.path.join(self.tmp, *parts)
        os.makedirs(p, exist_ok=True)
        return p

    def proj(self, cwd):
        r = sessions._proj_root(cwd)
        return sessions._proj_name(r), r

    def test_subfolder_is_repo_root(self):
        root = self.mk("repo-a")
        self.mk("repo-a", ".git")
        deep = self.mk("repo-a", "backup", "x", "y")
        self.assertEqual(self.proj(deep), ("repo-a", root))
        self.assertEqual(self.proj(root), ("repo-a", root))

    def test_worktree_git_file(self):
        wt = self.mk("repo-b", ".claude", "worktrees", "agent-1")
        with open(os.path.join(wt, ".git"), "w", encoding="utf-8") as f:
            f.write("gitdir: /nowhere\n")
        self.assertEqual(self.proj(self.mk("repo-b", ".claude", "worktrees", "agent-1", "sub")), ("repo-b", wt))

    def test_git_root_at_home_ignored(self):
        self.mk(".git")
        d = self.mk("dot", "proj")
        with mock.patch.object(ident, "_real_home", lambda: self.tmp):
            self.assertEqual(self.proj(d), ("proj", d))

    def test_windows_name_is_basename(self):
        import ntpath
        import types
        with mock.patch.object(ident, "os", types.SimpleNamespace(path=ntpath, sep="\\")), \
                mock.patch.object(ident, "_proj_root", lambda c: c):
            self.assertEqual(ident._proj_name("C:\\w\\repo-a"), "repo-a")
            self.assertEqual(ident._proj_name("C:\\w\\proj-C\\admin\\.claude\\worktrees\\agent-x"), "proj-C/admin")

    def test_outside_git_unchanged(self):
        d = self.mk("plain", "backup")
        self.assertEqual(self.proj(d), ("backup", d))
        self.assertEqual(sessions._proj_root(""), "")
        self.assertEqual(sessions._proj_root(None), "")



class HistorySubdir(unittest.TestCase):
    """History: a session whose cwd is a repo subfolder is listed under the repo."""
    setUp, tearDown = HU.HistoryUnitsTest.setUp, HU.HistoryUnitsTest.tearDown

    def test_units_project_is_repo(self):
        repo = os.path.join(self.root, "repo-h")
        sub = os.path.join(repo, "backup")
        os.makedirs(os.path.join(repo, ".git"))
        os.makedirs(sub)
        ident._PROJ_ROOT.clear()
        H._hist_cwd.clear()
        with mock.patch.object(H, "_cwd_from_slug", lambda s: sub):
            out = H.history_units(HU.SID)
        self.assertEqual((out["cwd"], out["project"]), (sub, "repo-h"))


if __name__ == "__main__":
    unittest.main()
