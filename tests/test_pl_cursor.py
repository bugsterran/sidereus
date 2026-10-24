"""Cursor CLI events in hooks/pl_mark.py and hooks/pl_flow.py: camelCase names, Shell tool, cwd from workspace_roots. Tmp dirs only."""
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

_HOOKS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks")


def _load(name):
    spec = importlib.util.spec_from_file_location(name + "_cursor_t", os.path.join(_HOOKS, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


M = _load("pl_mark")
F = _load("pl_flow")
SID = "c0ffee00-1234-5678-9abc-def012345678"
PIPE = {"stages": [{"title": "Plan", "agent": "main"}, {"title": "Build", "agent": "main"}]}


class Cursor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(os.path.join(self.proj, ".claude", "pipelines"))
        with open(os.path.join(self.proj, ".claude", "pipelines", "x.json"), "w", encoding="utf-8") as f:
            json.dump(PIPE, f)
        self.marks = os.path.join(self.tmp, "plmark")
        cfg = os.path.join(self.tmp, "config.local.json")
        common = (("MARK_DIR", self.marks), ("CONFIG_PATH", cfg), ("HOME_DIR", self.tmp), ("DATA_DIR", self.tmp),
                  ("DIRS_DIR", os.path.join(self.tmp, "plbrief")))
        flow = (("_now", lambda: 1000.0), ("CLAUDE_DIR", os.path.join(self.tmp, "uc")), ("_spawn", lambda argv: None),
                ("CLAUDE_JSON", os.path.join(self.tmp, ".claude.json")), ("PROJ_STORE", os.path.join(self.tmp, "pp.json")))
        for mod, pairs in ((M, common), (F, common + flow)):
            for k, v in pairs:
                if hasattr(mod, k):
                    p = mock.patch.object(mod, k, v)
                    p.start()
                    self.addCleanup(p.stop)

    def _run(self, mod, event, cmd):
        ev = {"hook_event_name": event, "conversation_id": SID, "session_id": SID, "cwd": "",
              "workspace_roots": [self.proj], "tool_name": "Shell",
              "tool_input": {"command": cmd, "cwd": "", "timeout": 30000}}
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", out):
            mod.main(["--platform", "cursor"])
        return out.getvalue()

    def _json(self, name):
        with open(os.path.join(self.marks, name), encoding="utf-8") as f:
            return json.load(f)

    def test_mark_sets_hold_and_root_cwd(self):
        self.assertEqual(self._run(M, "preToolUse", 'echo "[pl:x/Plan] secret"'), "")
        rec = self._json(SID + ".json")
        self.assertEqual((rec["name"], rec["title"], rec["hold"], rec["cwd"]), ("x", "Plan", 1, self.proj))
        self.assertNotIn("secret", json.dumps(rec))
        before = dict(rec)
        for ev in ("postToolUse", "postToolUseFailure"):
            self.assertEqual(self._run(M, ev, 'echo "[pl:x/Build]"'), "")
        self.assertEqual(self._json(SID + ".json"), before)   # Post never rewrites the mark

    def test_flow_opens_and_ends_run(self):
        self.assertEqual(self._run(F, "preToolUse", 'echo "[pl:x/Plan] secret"'), "")
        r = self._json(SID + ".runs.json")["runs"]["x"]
        self.assertEqual((r["proj"], r["st"]["Plan"]["s"]), (self.proj, "run"))
        self.assertEqual(self._run(F, "postToolUse", "echo '[pl-end:x/Plan]'"), "")   # cursor gets no hand-off text
        r = self._json(SID + ".runs.json")["runs"]["x"]
        self.assertEqual(r["st"]["Plan"]["s"], "done")
        self.assertEqual(self._run(F, "preToolUse", 'echo "[pl:x/Build]"'), "")
        self.assertEqual(self._run(F, "postToolUseFailure", "echo '[pl-end:x/Build]'"), "")
        self.assertTrue(self._json(SID + ".runs.json")["runs"]["x"].get("end"))
        with open(os.path.join(self.marks, SID + ".runs.json"), encoding="utf-8") as f:
            self.assertNotIn("secret", f.read())

    def test_cc_untouched(self):
        ev = {"hook_event_name": "preToolUse", "session_id": SID, "cwd": "", "workspace_roots": [self.proj],
              "tool_name": "Shell", "tool_input": {"command": 'echo "[pl:x/Plan]"'}}
        for mod in (M, F):
            out = io.StringIO()
            with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", out):
                mod.main([])
            self.assertEqual(out.getvalue(), "")
        self.assertFalse(os.path.exists(self.marks))


if __name__ == "__main__":
    unittest.main()
