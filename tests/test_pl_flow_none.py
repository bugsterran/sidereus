"""hooks/pl_flow.py [pl-none:<category>] declaration (R1) and the once-per-session first-edit / commit deny (R2, R3).
Tmp dirs only, fixed clock."""
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests import test_pl_flow as F   # ⚠not `from … import Flow`: its tests would run again here

H = F.H
SID = F.SID


class PlNone(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(os.path.join(self.proj, ".claude", "pipelines"))
        for n in ("alpha", "beta"):
            with open(os.path.join(self.proj, ".claude", "pipelines", n + ".json"), "w", encoding="utf-8") as f:
                json.dump({"v": 1, "name": n, "stages": [{"title": "s1", "agent": "general-purpose"}]}, f)
        self.bare = os.path.join(self.tmp, "bare")
        for d in (self.proj, self.bare):   # git roots bound the walk up from an edited file
            os.makedirs(os.path.join(d, ".git"), exist_ok=True)
        self.marks = os.path.join(self.tmp, "plmark")
        self.t = 1000.0
        for k, v in (("MARK_DIR", self.marks), ("CONFIG_PATH", os.path.join(self.tmp, "config.local.json")),
                     ("_now", lambda: self.t), ("CLAUDE_DIR", os.path.join(self.tmp, "user-claude")),
                     ("HOME_DIR", self.tmp), ("DIRS_DIR", os.path.join(self.tmp, "plbrief")),
                     ("DATA_DIR", self.tmp), ("_spawn", lambda argv: None)):
            p = mock.patch.object(H, k, v)
            p.start()
            self.addCleanup(p.stop)
        self.nf = os.path.join(self.marks, SID + ".none.json")

    def _ev(self, tool, ti, cwd=None, plat=None, agent=None, tp=None):
        ev = {"hook_event_name": "PreToolUse", "tool_name": tool, "session_id": SID, "cwd": cwd or self.proj,
              "tool_input": ti}
        if tp:
            ev["transcript_path"] = tp
        if agent:
            ev["agent_id"] = agent
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", out), \
                mock.patch.object(H, "_nudge", lambda *a: None):
            H.main(["--platform", plat] if plat else [])
        v = out.getvalue()
        return json.loads(v)["hookSpecificOutput"] if v else None

    def edit(self, root=None, **kw):
        fp = os.path.join(root or self.proj, "src", "a.py")
        return self._ev("Edit", {"file_path": fp, "old_string": "x", "new_string": "y"}, **kw)

    def bash(self, cmd, desc, **kw):
        return self._ev("Bash", {"command": cmd, "description": desc}, **kw)

    def denied(self, o):
        return bool(o) and o.get("permissionDecision") == "deny"

    def test_r1_valid_category_stores_only_cat_and_time(self):
        self.assertFalse(self.denied(self.bash("ls", "[pl-none:small-fix] secret reason text")))
        with open(self.nf, encoding="utf-8") as f:
            raw = f.read()
        self.assertNotIn("secret", raw)
        self.assertEqual(json.loads(raw), {"v": 1, "cat": "small-fix", "t": 1000.0})
        self.assertFalse(os.path.exists(os.path.join(self.marks, SID + ".json")))   # ⚠plm_of's file untouched

    def test_r1_unknown_category_denied_with_allowed_list(self):
        o = self.bash("ls", "[pl-none:bogus] why")
        self.assertTrue(self.denied(o))
        for c in H.NONE_CATS:
            self.assertIn(c, o["permissionDecisionReason"])
        self.assertFalse(os.path.exists(self.nf))

    def test_r2_first_edit_denied_once_then_commit_passes(self):
        o = self.edit()
        self.assertTrue(self.denied(o))
        why = o["permissionDecisionReason"]
        self.assertIn("alpha", why)
        self.assertIn("beta", why)
        self.assertIn("[pl-none:", why)
        self.assertFalse(self.denied(self.edit()))
        self.assertFalse(self.denied(self.bash("git commit -m x", "commit")))

    def test_r2_first_commit_denied(self):
        self.assertTrue(self.denied(self.bash("git commit -m x", "commit")))
        self.assertFalse(self.denied(self.bash("git commit -m x", "commit")))

    def test_r2_no_deny_after_declaration(self):
        self.bash("ls", "[pl-none:explore]")
        self.assertFalse(self.denied(self.edit()))
        self.assertFalse(self.denied(self.bash("git commit -m x", "commit")))

    def test_r2_no_deny_while_run_open(self):
        os.makedirs(self.marks)
        with open(os.path.join(self.marks, SID + ".runs.json"), "w", encoding="utf-8") as f:
            json.dump({"v": 1, "runs": {"alpha": {"cur": "s1", "end": 0, "t1": 990.0}}}, f)
        self.assertFalse(self.denied(self.edit()))
        self.assertFalse(os.path.exists(self.nf))

    def test_r2_subagent_and_other_platform_never_denied(self):
        self.assertFalse(self.denied(self.edit(agent="agent-1")))
        self.assertFalse(self.denied(self.bash("git commit -m x", "commit", agent="agent-1")))
        self.assertFalse(self.denied(self.edit(plat="codex")))
        self.assertFalse(self.denied(self.bash("git commit -m x", "commit", plat="codex")))
        self.assertFalse(os.path.exists(self.nf))

    def test_r4_run_open_drops_nudge(self):
        self.assertTrue(self.denied(self.edit()))   # nudged
        self.assertIn("nudge", H._none_load(self.nf))
        self.assertIsNone(self._ev("Agent", {"description": "[pl:alpha/s1] work", "subagent_type": "general-purpose"}))
        self.assertFalse(os.path.exists(self.nf))   # nothing else left: file removed

    def test_r4_run_open_keeps_category(self):
        self.edit()
        H._none_save(self.nf, {"v": 1, "cat": "explore", "t": 1.0, "nudge": 1000.0})
        self._ev("Agent", {"description": "[pl:alpha/s1] work", "subagent_type": "general-purpose"})
        self.assertEqual(H._none_load(self.nf), {"v": 1, "cat": "explore", "t": 1.0})

    def test_r3_transcript_repo_with_pipelines_does_not_lend_them(self):
        # cwd repo A (no pipelines); the transcript cd'd into repo B (pipelines): an edit in A is never denied
        tp = os.path.join(self.tmp, "t.jsonl")
        with open(tp, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "input": {"command": "cd %s && ls" % self.proj}}]}}) + "\n")
        ev = {"session_id": SID, "cwd": self.bare, "transcript_path": tp}
        self.assertIn(self.proj, H.session_dirs(ev))   # precondition: session dirs do see repo B
        self.assertFalse(self.denied(self.edit(root=self.bare, cwd=self.bare, tp=tp)))
        self.assertFalse(self.denied(self.bash("git commit -m x", "commit", cwd=self.bare, tp=tp)))
        self.assertFalse(os.path.exists(self.nf))

    def test_r2_edited_file_in_pipeline_repo_denied_from_other_cwd(self):
        o = self.edit(cwd=self.bare)   # file under repo B, session cwd in repo A
        self.assertTrue(self.denied(o))
        self.assertIn("alpha", o["permissionDecisionReason"])

    def test_r3_project_without_pipelines_never_denied(self):
        self.assertFalse(self.denied(self.edit(root=self.bare, cwd=self.bare)))
        self.assertFalse(self.denied(self.bash("git commit -m x", "commit", cwd=self.bare)))
        self.assertFalse(os.path.exists(self.nf))


if __name__ == "__main__":
    unittest.main()
