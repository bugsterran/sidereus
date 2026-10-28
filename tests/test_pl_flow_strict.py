"""hooks/pl_flow.py strict mode (_policy.json {"enforce": "writes"}): edits / main commits denied every time with no
open run (R1); [pl-none:explore] only, other categories refused (R2); missing/unknown switch keeps deny-once.
Tmp dirs only, fixed clock."""
import json
import os
import unittest

from tests import test_pl_flow_none as N   # ⚠not `from … import PlNone`: its tests would run again here

H = N.H
SID = N.SID


# Reuse PlNone's fixture without re-running its tests: borrow its helpers onto a fresh TestCase.
class Strict(unittest.TestCase):
    _ev = N.PlNone._ev
    edit = N.PlNone.edit
    bash = N.PlNone.bash
    denied = N.PlNone.denied

    def policy(self, d):
        with open(os.path.join(self.proj, ".claude", "pipelines", "_policy.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)

    def setUp(self):
        N.PlNone.setUp(self)
        with open(os.path.join(self.proj, ".claude", "pipelines", "alpha.json"), "w", encoding="utf-8") as f:
            json.dump({"v": 1, "name": "alpha", "use": "Alpha work " + "x" * 200,
                       "stages": [{"title": "s1", "agent": "general-purpose"}]}, f)
        self.policy({"enforce": "writes"})

    def tool(self, name):
        fp = os.path.join(self.proj, "src", "a.py")
        ti = {"notebook_path": fp} if name == "NotebookEdit" else {"file_path": fp, "content": "y"}
        return self._ev(name, ti)

    def open_run(self, t1=990.0):
        os.makedirs(self.marks, exist_ok=True)
        with open(os.path.join(self.marks, SID + ".runs.json"), "w", encoding="utf-8") as f:
            json.dump({"v": 1, "runs": {"alpha": {"cur": "s1", "end": 0, "t1": t1}}}, f)

    def test_r1_edits_denied_every_time(self):
        for name in H.EDITS:
            for _ in range(2):
                o = self.tool(name)
                self.assertTrue(self.denied(o), name)
                why = o["permissionDecisionReason"]
                self.assertIn("alpha: Alpha work", why)
                self.assertIn("beta", why)
                self.assertIn("quick-fix", why)
                self.assertNotIn("retrying proceeds", why)
                self.assertNotIn("x" * 80, why)   # use text clipped to 80
        self.assertFalse(os.path.exists(self.nf))   # no nudge stamp

    def test_r1_main_commit_denied_every_time(self):
        self.assertTrue(self.denied(self.bash("git commit -m x", "commit")))
        self.assertTrue(self.denied(self.bash("git commit -m x", "commit")))

    def test_r1_tagged_commit_without_run_denied(self):
        for desc in ("[pl:-] commit", "[pl:nonexistent/x] c", "[pl-skip:a/b] c", "[pl] c"):
            self.assertTrue(self.denied(self.bash("git commit -m x", desc)), desc)

    def test_r1_commit_grace_after_run_ended(self):
        os.makedirs(self.marks, exist_ok=True)
        with open(os.path.join(self.marks, SID + ".runs.json"), "w", encoding="utf-8") as f:
            json.dump({"v": 1, "runs": {"alpha": {"cur": "s1", "end": 900.0, "t1": 900.0}}}, f)
        self.assertFalse(self.denied(self.bash("git commit -m x", "commit")))   # 100 s after end
        self.t = 900.0 + H.STRICT_GRACE_S + 1
        self.assertTrue(self.denied(self.bash("git commit -m x", "commit")))
        self.assertTrue(self.denied(self.edit()))

    def test_r1_reads_bash_agent_dry_run_pass(self):
        self.assertIsNone(self._ev("Read", {"file_path": os.path.join(self.proj, "a.py")}))
        self.assertFalse(self.denied(self.bash("ls", "list")))
        self.assertFalse(self.denied(self.bash("git commit --dry-run -m x", "dry")))
        self.assertFalse(self.denied(self._ev("Agent", {"description": "look around", "subagent_type": "Explore"})))

    def test_r1_open_run_passes(self):
        self.open_run()
        self.assertFalse(self.denied(self.edit()))
        self.assertFalse(self.denied(self.bash("git commit -m x", "commit")))

    def test_r2_explore_accepted_but_edits_stay_denied(self):
        self.assertFalse(self.denied(self.bash("ls", "[pl-none:explore]")))
        self.assertEqual(H._none_load(self.nf).get("cat"), "explore")
        self.assertTrue(self.denied(self.edit()))
        self.assertTrue(self.denied(self.bash("git commit -m x", "[pl-none:explore] commit")))

    def test_r2_other_categories_refused(self):
        for c in ("small-fix", "no-fit", "other"):
            o = self.bash("ls", "[pl-none:%s] x" % c)
            self.assertTrue(self.denied(o), c)
            self.assertIn("quick-fix", o["permissionDecisionReason"])
        self.assertFalse(os.path.exists(self.nf))

    def test_r1_subagent_denied_without_run_passes_with_stale_open_run(self):
        self.assertTrue(self.denied(self.edit(agent="agent-1")))
        self.assertTrue(self.denied(self.bash("git commit -m x", "commit", agent="agent-1")))
        self.open_run(t1=1000.0 - H.IDLE_S - 10)   # un-ended but idle: a long stage still counts
        self.assertFalse(self.denied(self.edit(agent="agent-1")))
        self.assertFalse(self.denied(self.bash("git commit -m x", "commit", agent="agent-1")))

    def test_nongoal_unknown_or_missing_switch_denies_once(self):
        for pol in ({"enforce": "all"}, None, ["writes"]):
            if os.path.exists(self.nf):
                os.remove(self.nf)
            path = os.path.join(self.proj, ".claude", "pipelines", "_policy.json")
            if pol is None:
                os.remove(path)
            else:
                self.policy(pol)
            o = self.edit()
            self.assertTrue(self.denied(o))
            self.assertIn("retrying proceeds", o["permissionDecisionReason"])
            self.assertFalse(self.denied(self.edit()))
            self.assertFalse(self.denied(self.edit(agent="agent-1")))
        self.assertFalse(self.denied(self.bash("ls", "[pl-none:small-fix]")))

    def test_apply_off_bypasses(self):
        with open(H.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"pipeline_apply": {"mode": "off"}}, f)
        self.assertFalse(self.denied(self.edit()))
        self.assertFalse(self.denied(self.bash("git commit -m x", "commit")))
        self.assertFalse(self.denied(self.bash("ls", "[pl-none:small-fix]")))

    def test_strict_helper(self):
        self.assertTrue(H._strict(self.proj))
        self.assertFalse(H._strict(self.bare))


if __name__ == "__main__":
    unittest.main()
