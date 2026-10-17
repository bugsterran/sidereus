"""Changes rail baseline: merge-base with the default branch, HEAD at the session start, or HEAD (real git, temp repos)."""
import os
import shutil
import subprocess
import tempfile
import unittest

from tests._load import sidereus

gv = sidereus("git_view")
gr = sidereus("git_rail")   # rail internals live here (split 2026-09-25)

T0, T2 = 1790000000, 1790007200          # two commit times; the session starts between them


class RailBase(unittest.TestCase):
    def setUp(self):
        self.d = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d)
        self._sess = gv.sessions_rows
        gv.sessions_rows = lambda **k: [{"cwd": self.d, "repos": []}]
        self.addCleanup(setattr, gv, "sessions_rows", self._sess)

    def git(self, *a, at=None):
        env = dict(os.environ)
        if at:
            env["GIT_COMMITTER_DATE"] = env["GIT_AUTHOR_DATE"] = "%d +0000" % at
        return subprocess.run(["git", "-C", self.d, "-c", "user.name=t", "-c", "user.email=t@t",
                               "-c", "commit.gpgsign=false"] + list(a),
                              check=True, capture_output=True, text=True, env=env, encoding="utf-8").stdout.strip()

    def put(self, p, b):
        with open(os.path.join(self.d, p), "w", encoding="utf-8") as fh:
            fh.write(b)

    def commit(self, p, b, at=None):
        self.put(p, b)
        self.git("add", p)
        self.git("commit", "-qm", p, at=at)
        return self.git("rev-parse", "HEAD")

    def rail(self, since=0, mode="head", calls=None):
        def run(a):
            if calls is not None:
                calls.append(a[0])
            return gv._git_run(self.d, a, gv.DIFF_TIMEOUT).stdout
        return gr._git_rail(self.d, run, None, since, mode)

    def test_default_mode_is_head(self):
        self.git("init", "-q", "-b", "main")
        self.commit("a.txt", "1\n", at=T0)
        self.git("checkout", "-qb", "feat")
        self.commit("b.txt", "x\n")
        self.put("a.txt", "2\n")
        calls = []
        d = self.rail(since=T0 + 60, calls=calls)             # a start time is known but not used
        self.assertEqual((d["baseKind"], d["base"], d["baseMode"], d["nCommits"]), ("head", "", "head", 0))
        self.assertEqual([x["path"] for x in d["files"]], ["a.txt"])
        self.assertEqual(calls, ["status", "diff", "log"])    # the old 3-call budget, no base lookup
        self.assertEqual(len(d["commits"]), 2)               # recent commits, as before

    def test_auto_without_remote_is_head(self):
        self.git("init", "-q", "-b", "main")
        self.commit("a.txt", "1\n")
        calls = []
        d = self.rail(mode="auto", calls=calls)
        self.assertEqual((d["baseMode"], d["baseKind"]), ("head", "head"))
        self.assertEqual(calls, ["status", "diff", "log"])
        self.assertEqual(gv.git_diff(self.d, view="rail")["baseMode"], "head")   # "" = auto

    def test_auto_with_remote_is_remote(self):
        bare = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, bare)
        subprocess.run(["git", "init", "-q", "--bare", bare], check=True, capture_output=True)
        self.git("init", "-q", "-b", "main")
        pushed = self.commit("a.txt", "1\n")
        self.git("remote", "add", "origin", bare)
        self.git("push", "-q", "origin", "main")              # no upstream set: origin/main ref alone decides
        self.commit("b.txt", "2\n")
        d = self.rail(mode="auto")
        self.assertEqual((d["baseMode"], d["baseKind"], d["baseRef"], d["base"]), ("remote", "remote", "origin/main", pushed))
        self.git("checkout", "-qb", "feat")                   # no-upstream feature branch: merge-base with default
        d = self.rail(mode="auto")
        self.assertEqual((d["baseMode"], d["baseKind"], d["baseRef"]), ("remote", "branch", "main"))

    def test_invalid_mode_refused(self):
        self.git("init", "-q", "-b", "main")
        self.commit("a.txt", "1\n")
        d = gv.git_diff(self.d, view="rail", base_mode="HEAD~3")
        self.assertEqual(d, {"ok": False, "msg": "Unknown base."})
        self.assertEqual(gv.git_diff(self.d, view="rail")["baseKind"], "head")

    def test_remote_mode_feature_branch_vs_merge_base(self):
        self.git("init", "-q", "-b", "main")
        base = self.commit("a.txt", "1\n")
        self.git("checkout", "-qb", "feat")
        self.commit("b.txt", "x\ny\n")
        self.put("a.txt", "1\n2\n")                          # uncommitted edit
        self.put("c.txt", "new\n")                           # untracked
        d = self.rail(mode="remote")
        self.assertEqual((d["baseKind"], d["baseRef"], d["base"]), ("branch", "main", base))
        f = {x["path"]: x["st"] for x in d["files"]}
        self.assertEqual(f, {"b.txt": "A", "a.txt": "M", "c.txt": "A"})
        self.assertEqual((d["nCommits"], d["dirty"]), (1, 2))
        self.git("commit", "-qam", "edit a")                 # committed files stay listed
        d = self.rail(mode="remote")
        self.assertEqual({x["path"] for x in d["files"]}, {"a.txt", "b.txt", "c.txt"})
        self.assertEqual((d["nCommits"], d["dirty"]), (2, 1))

    def test_remote_mode_upstream_bare_repo(self):
        bare = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, bare)
        subprocess.run(["git", "init", "-q", "--bare", bare], check=True, capture_output=True)
        self.git("init", "-q", "-b", "main")
        pushed = self.commit("a.txt", "1\n")
        self.git("remote", "add", "origin", bare)
        self.git("push", "-q", "-u", "origin", "main")
        self.commit("b.txt", "unpushed\n")
        self.put("c.txt", "new\n")
        d = self.rail(since=T0, mode="remote")
        self.assertEqual((d["baseKind"], d["baseRef"], d["base"], d["noRemote"]), ("remote", "origin/main", pushed, False))
        self.assertEqual({x["path"] for x in d["files"]}, {"b.txt", "c.txt"})
        self.assertEqual((d["nCommits"], d["dirty"]), (1, 1))

    def test_remote_mode_without_remote_uses_session_start(self):
        self.git("init", "-q", "-b", "main")
        c1 = self.commit("a.txt", "1\n", at=T0)
        self.commit("b.txt", "2\n", at=T2)
        d = self.rail(since=T0 + 60, mode="remote")
        self.assertEqual((d["baseKind"], d["base"], d["noRemote"]), ("start", c1, True))

    def test_start_mode(self):
        self.git("init", "-q", "-b", "master")
        c1 = self.commit("a.txt", "1\n", at=T0)
        self.commit("b.txt", "2\n", at=T2)
        d = self.rail(since=T0 + 60, mode="start")
        self.assertEqual((d["baseKind"], d["base"], d["since"], d["nCommits"]), ("start", c1, T0 + 60, 1))
        self.assertEqual([x["path"] for x in d["files"]], ["b.txt"])
        self.assertEqual(self.rail(since=0, mode="start")["baseKind"], "head")   # no start time -> HEAD

    def test_origin_head_wins(self):
        self.git("init", "-q", "-b", "main")
        self.commit("a.txt", "1\n")
        self.git("branch", "trunk")
        self.git("update-ref", "refs/remotes/origin/trunk", "HEAD")
        self.git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
        self.assertEqual(gr._default_branch(self.d), "trunk")
        self.git("branch", "-D", "trunk")
        self.assertEqual(gr._default_branch(self.d), "origin/trunk")

    def test_base_scope_guard(self):
        self.git("init", "-q", "-b", "main")
        c1 = self.commit("a.txt", "1\n")
        self.git("checkout", "-qb", "side")
        side = self.commit("s.txt", "s\n")
        self.git("checkout", "-q", "main")
        self.commit("b.txt", "2\n")
        self.assertEqual(gv._base_scope(self.d, "b:" + c1), c1)
        self.assertIsNone(gv._base_scope(self.d, "b:" + side))          # not an ancestor of HEAD
        self.assertIsNone(gv._base_scope(self.d, "b:HEAD~1"))           # not hex
        self.assertEqual(gv._base_scope(self.d, "work"), "")
        d = gv.git_diff(self.d, scope="b:" + c1)
        self.assertTrue(d["ok"])
        self.assertIn("+++ b/b.txt", d["diff"])
        self.assertFalse(gv.git_diff(self.d, scope="b:" + side)["ok"])
        f = gv.git_file_diff(self.d, "b.txt", "b:" + c1)
        self.assertTrue(f["ok"])
        self.assertIn("+2", f["diff"])

    def test_session_start_from_transcript(self):
        fp = os.path.join(self.d, "t.jsonl")
        with open(fp, "w", encoding="utf-8") as fh:
            fh.write('{"type":"mode"}\n{"type":"x","timestamp":"2026-09-23T18:53:09.336Z"}\n')
        real = gr._sid_path
        gr._sid_path = lambda cwd, sid: fp if sid == "abc" else ""
        self.addCleanup(setattr, gr, "_sid_path", real)
        gr._start_cache.clear()
        self.assertEqual(gr._session_start(self.d, "abc"), 1790189589)
        self.assertEqual(gr._session_start(self.d, "zzz"), 0)
        self.assertEqual(gr._session_start(self.d, ""), 0)


if __name__ == "__main__":
    unittest.main()


class RailUpstreamMode(unittest.TestCase):
    """«vs this branch's remote»: merge-base with the branch's own upstream only, never the default branch."""
    SHA = "a" * 40

    def base(self, upstream, mb=SHA):
        calls = []

        def run(a):
            calls.append(a)
            if a[0] == "merge-base":
                return mb
            if a[0] == "rev-list":
                return "b" * 40
            return ""
        return gr._rail_base("/nonexistent", run, "feat", T0, mode="upstream", upstream=upstream), calls

    def test_uses_branch_upstream(self):
        (rev, kind, ref, no_remote), calls = self.base("origin/feat")
        self.assertEqual((rev, kind, ref, no_remote), (self.SHA, "remote", "origin/feat", False))
        self.assertEqual(calls[0][:3], ["merge-base", "HEAD", "origin/feat"])

    def test_no_upstream_falls_back_to_session_start(self):
        (rev, kind, _, no_remote), calls = self.base("")
        self.assertEqual((kind, no_remote), ("start", True))
        self.assertFalse(any(c[0] == "merge-base" for c in calls))   # the default branch is not consulted

    def test_bad_ref_is_refused(self):
        (_, kind, _, no_remote), calls = self.base("origin/x..y")
        self.assertEqual((kind, no_remote), ("start", True))
        self.assertIn("upstream", gr.RAIL_MODES)


class RailHeadAhead(RailBase):
    """head mode: a clean branch with unpushed commits diffs against its upstream so the repo chip does not fold."""

    def test_clean_ahead_with_upstream_lists_unpushed_files(self):
        self.git("init", "-q", "-b", "main")
        self.commit("a.txt", "1\n", at=T0)
        self.git("checkout", "-qb", "feat")
        self.git("branch", "-q", "-u", "main")                # local upstream: no remote, no network
        self.commit("b.txt", "x\n")
        d = self.rail(mode="head")
        self.assertEqual((d["baseKind"], d["baseRef"], d["ahead"], d["noRemote"]), ("remote", "main", 1, False))
        self.assertEqual([x["path"] for x in d["files"]], ["b.txt"])
        self.assertNotIn("main", d)                            # plain repo: no main-repo label

    def test_ahead_without_upstream_keeps_head(self):
        self.git("init", "-q", "-b", "main")
        self.commit("a.txt", "1\n", at=T0)
        self.commit("b.txt", "x\n")
        d = self.rail(mode="head")
        self.assertEqual((d["baseKind"], d["base"], d["files"]), ("head", "", []))

    def test_worktree_reply_names_main_repo(self):
        self.git("init", "-q", "-b", "main")
        self.commit("a.txt", "1\n", at=T0)
        wt = os.path.join(self.d, "wt1")
        self.git("worktree", "add", "-q", "-b", "side", wt)
        main = self.d
        self.d = wt
        try:
            d = self.rail(mode="head")
        finally:
            self.d = main
        self.assertEqual((d["main"], d["branch"]), (os.path.basename(main), "side"))
