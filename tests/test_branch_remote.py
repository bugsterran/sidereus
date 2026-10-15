"""Remote freshness for the Branches tab (sidereus/git.py remote_info): FETCH_HEAD age, common-dir, URL host. Temp files only."""
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

g = sidereus("git_flow")

CFG = """[core]
\tbare = false
[remote "origin"]
\turl = https://alice:ghp_SECRET123@github.example.com/infra/repo-j.git
\tfetch = +refs/heads/*:refs/remotes/origin/*
[branch "main"]
\tremote = origin
[remote "up"]
\turl = git@github.com:someone/repo.git
[remote "disk"]
\turl = /Users/x/mirror.git
"""


class RemoteInfo(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.main = os.path.join(self.d, "app")
        self.gd = os.path.join(self.main, ".git")
        os.makedirs(os.path.join(self.gd, "worktrees", "fix"))
        with open(os.path.join(self.gd, "config"), "w") as f:
            f.write(CFG)
        # Worktree layout as git writes it: <wt>/.git file -> <main>/.git/worktrees/fix, commondir = ../..
        self.wt = os.path.join(self.d, "wt-fix")
        os.makedirs(os.path.join(self.wt, "sub"))
        with open(os.path.join(self.wt, ".git"), "w") as f:
            f.write("gitdir: " + os.path.join(self.gd, "worktrees", "fix") + "\n")
        with open(os.path.join(self.gd, "worktrees", "fix", "commondir"), "w") as f:
            f.write("../..\n")

    def tearDown(self):
        shutil.rmtree(self.d)

    def touch(self, p, t):
        open(p, "w").close()
        os.utime(p, (t, t))

    def test_never_fetched(self):
        rs = g.remote_info(self.main)
        self.assertEqual([r["name"] for r in rs], ["origin", "up", "disk"])
        self.assertTrue(all(r["fetchAt"] is None for r in rs))

    def test_fetch_head_present(self):
        self.touch(os.path.join(self.gd, "FETCH_HEAD"), 1_700_000_000)
        self.assertEqual(g.remote_info(self.main)[0]["fetchAt"], 1_700_000_000)

    def test_worktree_resolves_common_dir(self):
        self.assertEqual(os.path.realpath(g._git_common_dir(os.path.join(self.wt, "sub"))), os.path.realpath(self.gd))
        self.assertEqual(g.remote_info(self.wt)[0]["host"], "github.example.com")

    def test_newest_fetch_head_wins_incl_worktree(self):
        # FETCH_HEAD is per-worktree; a fetch run in the worktree still refreshes the shared remote refs.
        self.touch(os.path.join(self.gd, "FETCH_HEAD"), 1_700_000_000)
        self.touch(os.path.join(self.gd, "worktrees", "fix", "FETCH_HEAD"), 1_700_050_000)
        self.assertEqual(g.remote_info(self.main)[0]["fetchAt"], 1_700_050_000)

    def test_no_repo(self):
        self.assertEqual(g.remote_info(os.path.join(self.d)), [])

    def test_hosts_never_leak_credentials(self):
        rs = {r["name"]: r for r in g.remote_info(self.main)}
        self.assertEqual((rs["origin"]["host"], rs["origin"]["local"]), ("github.example.com", False))
        self.assertEqual((rs["up"]["host"], rs["up"]["local"]), ("github.com", False))
        self.assertEqual((rs["disk"]["host"], rs["disk"]["local"]), ("", True))
        self.assertNotIn("SECRET", repr(rs))
        self.assertNotIn("alice", repr(rs))


class UrlHost(unittest.TestCase):
    def test_forms(self):
        for url, want in [
            ("https://user:tok@github.example.com:8443/a/b.git", ("github.example.com", False)),
            ("https://github.com/a/b", ("github.com", False)),
            ("ssh://git@host.example:2222/a.git", ("host.example", False)),
            ("git@github.example.com:org/repo.git", ("github.example.com", False)),
            ("host.local:repo.git", ("host.local", False)),
            ("file:///srv/git/r.git", ("", True)),
            ("/srv/git/r.git", ("", True)),
            ("../sibling", ("", True)),
            ("", ("", True)),
        ]:
            self.assertEqual(g._url_host(url), want, url)


if __name__ == "__main__":
    unittest.main()
