"""«To-do» hooks (R1): pipelines_brief TODO line at SessionStart only (cc and codex, with no pipelines), silent with
config `features.todo` false; pl_flow strict mode lets `<git root>/.claude/todo.md` edits through. Tmp dirs only."""
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests import test_pipelines_brief as B
from tests import test_pl_flow_strict as S   # ⚠not `from … import Strict`: its tests would run again here

H = B.H
SID = "abcdef12-3456"


class Brief(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.repo, ".git"))
        self.cfg = os.path.join(self.tmp, "config.local.json")
        for k, v in (("CONFIG_PATH", self.cfg), ("BRIEF_DIR", os.path.join(self.tmp, "plbrief")),
                     ("DIRS_DIR", os.path.join(self.tmp, "plbrief")), ("CLAUDE_DIR", os.path.join(self.tmp, "uc")),
                     ("HOME_DIR", os.path.join(self.tmp, "home"))):
            p = mock.patch.object(H, k, v)
            p.start()
            self.addCleanup(p.stop)

    def run_hook(self, event, plat=None):
        ev = {"hook_event_name": event, "session_id": SID, "cwd": self.repo}
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", out):
            H.main(["--platform", plat] if plat else [])
        v = out.getvalue()
        return json.loads(v)["hookSpecificOutput"]["additionalContext"] if v else ""

    def test_session_start_cc_and_codex_without_pipelines(self):
        for plat in (None, "codex"):
            t = self.run_hook("SessionStart", plat)
            self.assertIn(os.path.join(self.repo, ".claude", "todo.md"), t, plat)
            self.assertIn("- [~]", t)
            self.assertNotIn("Pipelines", t)

    def test_not_on_prompt(self):
        self.run_hook("SessionStart")
        self.assertEqual(self.run_hook("UserPromptSubmit"), "")

    def test_silent_when_feature_off_and_apply_off_keeps_it(self):
        with open(self.cfg, "w", encoding="utf-8") as f:
            json.dump({"features": {"todo": False}}, f)
        self.assertEqual(self.run_hook("SessionStart"), "")
        with open(self.cfg, "w", encoding="utf-8") as f:
            json.dump({"pipeline_apply": {"mode": "off"}}, f)
        self.assertIn("todo.md", self.run_hook("SessionStart"))

    def test_off_switch_read_like_viewer(self):
        with open(self.cfg, "w", encoding="utf-8-sig") as f:   # BOM: the viewer still reads features.todo false
            json.dump({"features": {"todo": False}}, f)
        self.assertEqual(self.run_hook("SessionStart"), "")
        with open(self.cfg, "w", encoding="utf-8") as f:   # invalid dict: the viewer ignores it (all on)
            json.dump({"features": {"todo": False, "x": "no"}}, f)
        self.assertIn("todo.md", self.run_hook("SessionStart"))

    def test_apply_mode_read_with_bom(self):
        with open(self.cfg, "w", encoding="utf-8-sig") as f:
            json.dump({"pipeline_apply": {"mode": "ask"}}, f)
        self.assertEqual(H._mode(self.repo), "ask")

    def test_no_repo_or_home_repo_silent(self):
        self.assertEqual(H._todo_line(self.tmp), "")
        with mock.patch.object(H, "HOME_DIR", self.repo):
            self.assertEqual(H._todo_line(self.repo), "")


class StrictTodo(unittest.TestCase):
    setUp = S.Strict.setUp
    policy = S.Strict.policy
    _ev = S.Strict._ev
    denied = S.Strict.denied

    def test_todo_edit_passes_strict(self):
        fp = os.path.join(self.proj, ".claude", "todo.md")
        for name in ("Edit", "Write"):
            self.assertFalse(self.denied(self._ev(name, {"file_path": fp, "content": "- [ ] a\n"})), name)
        other = os.path.join(self.proj, ".claude", "notes.md")
        self.assertTrue(self.denied(self._ev("Write", {"file_path": other, "content": "x"})))
        nested = os.path.join(self.proj, "src", ".claude", "todo.md")   # not at the git root
        self.assertTrue(self.denied(self._ev("Write", {"file_path": nested, "content": "x"})))


if __name__ == "__main__":
    unittest.main()
