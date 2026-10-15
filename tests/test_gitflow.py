"""git-flow awareness in sidereus/git.py: config parsing, base/PR target per branch type. Synthetic data only."""
import unittest

from tests._load import sidereus

g = sidereus("git")
gw = sidereus("git_wt")

CFG = ("gitflow.branch.master production\ngitflow.branch.develop dev\n"
       "gitflow.prefix.feature feat/\ngitflow.prefix.hotfix hf/\ngitflow.prefix.versiontag v\n")


class FlowParse(unittest.TestCase):
    def test_configured(self):
        f = g.flow_parse(CFG, ["production", "dev"])
        self.assertEqual((f["develop"], f["master"], f["src"]), ("dev", "production", "gitflow-config"))
        self.assertEqual(f["prefix"]["feature"], "feat/")
        self.assertEqual(f["prefix"]["bugfix"], "bugfix/")              # unconfigured key keeps the default
        self.assertNotIn("versiontag", f["prefix"])

    def test_default(self):
        f = g.flow_parse("", ["master", "main", "develop"])
        self.assertEqual((f["develop"], f["master"], f["src"]), ("develop", "main", "default"))
        self.assertEqual(f["prefix"], {t: t + "/" for t in sidereus("git_flow").FLOW_TYPES})

    def test_no_develop(self):
        f = g.flow_parse("", ["master", "feature/x"])
        self.assertEqual((f["develop"], f["master"]), (None, "master"))
        self.assertEqual(g.flow_parse("", [])["master"], None)


class FlowBase(unittest.TestCase):
    F = g.flow_parse("", ["main", "develop"])

    def test_base_and_pr_per_type(self):
        cases = {"feature/a": ("develop", ["develop"]), "bugfix/b": ("develop", ["develop"]),
                 "release/1.4.0": ("main", ["main", "develop"]), "hotfix/c": ("main", ["main", "develop"]),
                 "worktree-x": ("main", [])}
        for br, want in cases.items():
            self.assertEqual(g.flow_base(br, self.F, "main"), want, br)

    def test_no_develop_feature_goes_to_master(self):
        f = g.flow_parse("", ["master"])
        self.assertEqual(g.flow_base("feature/a", f, "master"), ("master", ["master"]))
        self.assertEqual(g.flow_base("hotfix/a", f, "master"), ("master", ["master"]))

    def test_card_base(self):
        loc = {"main": 1, "develop": 1}
        self.assertEqual(gw.wt_base("feature/a", self.F, "main", loc), ("develop", ["develop"]))
        self.assertEqual(gw.wt_base("fix-x", self.F, "main", loc), ("main", []))
        self.assertEqual(gw.wt_base("main", self.F, "main", loc), ("", []))
        # flow base not a local branch (only origin/develop) -> current rule, no PR hint
        self.assertEqual(gw.wt_base("feature/a", self.F, "main", {"main": 1}), ("main", []))


class R:
    def __init__(self, out, rc=0):
        self.stdout, self.returncode = out, rc


class FlowRemoteDevelop(unittest.TestCase):
    """develop only as <remote>/develop (fresh clone, no gitflow config). Fake git runner, no repo."""

    def run_with(self, refs, cfg=("", 1)):
        calls = []

        def run(args):
            calls.append(args)
            if args[0] == "config":
                return R(*cfg)
            if args[0] == "for-each-ref":
                return R("".join(r + "\n" for r in refs))
            raise AssertionError(args)
        return calls, run

    def test_origin_preferred(self):
        calls, run = self.run_with(["upstream/develop", "origin/develop"])
        f = g.flow_info(run, ["main"])
        self.assertEqual((f["develop"], f["devRemote"], f["devName"]), ("origin/develop", "origin", "develop"))
        self.assertEqual(calls[1], ["for-each-ref", "--format=%(refname:short)", "refs/remotes/*/develop"])
        self.assertEqual(g.flow_base("feature/a", f, "main"), ("origin/develop", ["develop"]))
        self.assertEqual(g.flow_base("release/1", f, "main"), ("main", ["main", "develop"]))
        # card base: the remote ref counts even though it is not a local branch
        self.assertEqual(gw.wt_base("feature/a", f, "main", {"main": 1}), ("origin/develop", ["develop"]))

    def test_other_remote_and_configured_name(self):
        _, run = self.run_with(["fork/dev"], cfg=("gitflow.branch.develop dev\n", 0))
        f = g.flow_info(run, ["main"])
        self.assertEqual((f["develop"], f["devName"]), ("fork/dev", "dev"))

    def test_local_develop_skips_lookup(self):
        calls, run = self.run_with(["origin/develop"])
        f = g.flow_info(run, ["main", "develop"])
        self.assertEqual((f["develop"], f.get("devRemote")), ("develop", None))
        self.assertEqual(len(calls), 1)

    def test_remote_only_main(self):
        calls, run = self.run_with(["upstream/main", "origin/master", "origin/develop"])
        f = g.flow_info(run, ["feature/x"])
        self.assertEqual(calls[2], ["for-each-ref", "--format=%(refname:short)", "refs/remotes/*/main", "refs/remotes/*/master"])
        self.assertEqual((f["master"], f["mstRemote"], f["mstName"]), ("upstream/main", "upstream", "main"))  # main before master
        self.assertEqual(g.flow_base("hotfix/a", f, ""), ("upstream/main", ["main", "develop"]))
        self.assertEqual(gw.wt_base("release/1", f, "", {"feature/x": 1}), ("upstream/main", ["main", "develop"]))

    def test_configured_master_remote_only(self):
        _, run = self.run_with(["origin/production"], cfg=("gitflow.branch.master production\n", 0))
        f = g.flow_info(run, ["develop"])
        self.assertEqual((f["master"], f["mstName"]), ("origin/production", "production"))

    def test_no_remote_master(self):
        _, run = self.run_with([])
        f = g.flow_info(run, ["develop"])
        self.assertEqual((f["master"], f.get("mstRemote")), (None, None))

    def test_no_remote_develop(self):
        _, run = self.run_with(["origin/main"])
        f = g.flow_info(run, ["main"])
        self.assertEqual(f["develop"], None)
        self.assertEqual(g.flow_base("feature/a", f, "main"), ("main", ["main"]))


if __name__ == "__main__":
    unittest.main()
