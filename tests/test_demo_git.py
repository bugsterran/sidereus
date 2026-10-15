"""sidereus/demo_git.py (`_WorldGit`): per demo repo, branches/git_links/git_rail are deterministic, keyed, synthetic-only."""
import json
import os
import unittest

from tests._load import sidereus

BRANCH_KEYS = {"ok", "remote", "fetchStaleH", "cwd", "repo", "head", "detached", "branches", "commits", "flow",
               "worktrees", "wtSig", "wtTok", "wtStaleDays", "truncated", "ms", "wtOrder"}
LINK_KEYS = {"ok", "busy", "links", "n", "ms"}
RAIL_KEYS = {"ok", "cwd", "view", "hasUp", "n", "add", "del", "files", "untracked", "commits", "branch", "upstream",
             "ahead", "behind", "base", "baseKind", "baseRef", "baseMode", "noRemote", "since", "nCommits",
             "commitsCut", "dirty"}


class DemoGit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo = sidereus("demo")
        cls.dd = sidereus("demo_data")
        a = 1_790_000_000
        cls.w = cls.demo.World(anchor=a, page_build="abc123def456", now=a)
        # ⚠Real paths that must never leak into a demo payload.
        cls.real = (os.path.expanduser("~"), os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "/Users/")

    def _calls(self, repo, cwd):
        cm = self.w.graph[repo]["commits"]
        code, br = self.w.branches(cwd)
        return {"code": code, "branches": br, "links": self.w.git_links(cwd, {c["sha"] for c in cm}),
                "rail": {m: self.w.git_rail(cwd, m) for m in ("auto", "head", "start", "remote", "upstream")}}

    def test_repos(self):
        for repo, (main, wts) in self.dd.REPOS.items():
            for cwd in [main] + [p for p, _ in wts]:
                with self.subTest(cwd=cwd):
                    one, two = self._calls(repo, cwd), self._calls(repo, cwd)
                    self.assertEqual(json.dumps(one, sort_keys=True), json.dumps(two, sort_keys=True))
                    self.assertEqual(one["code"], 200)
                    self.assertEqual(set(one["branches"]), BRANCH_KEYS)
                    self.assertEqual(one["branches"]["repo"], repo)
                    self.assertEqual(set(one["links"]), LINK_KEYS)
                    for m, r in one["rail"].items():
                        self.assertEqual(set(r), RAIL_KEYS, m)
                        self.assertEqual(r["cwd"], cwd)
                    blob = json.dumps(one)
                    for p in self.real:
                        self.assertNotIn(p, blob)

    def test_rail_upstream(self):
        # upstream mode must resolve to the branch's own origin/<br>, never be rewritten to remote (origin/main).
        main = self.dd.REPOS["acme-web"][0]
        r = self.w.git_rail(main, "upstream")
        self.assertEqual(r["baseMode"], "upstream")
        self.assertEqual((r["baseKind"], r["baseRef"]), ("remote", "origin/feature/checkout-redesign"))
        cm = {c["sha"]: c for c in self.w.graph["acme-web"]["commits"]}
        self.assertIn("origin/feature/checkout-redesign", cm[r["base"]]["refs"])
        self.assertNotEqual(r["base"], self.w.git_rail(main, "remote")["base"])
        self.assertFalse(r["noRemote"])

    def test_unknown_repo(self):
        self.assertEqual(self.w.branches("/nope")[0], 400)
        self.assertEqual(self.w.git_links("/nope", set())["links"], {})
        self.assertFalse(self.w.git_rail("/nope")["ok"])


if __name__ == "__main__":
    unittest.main()
