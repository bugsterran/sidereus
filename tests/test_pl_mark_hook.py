"""PreToolUse hook hooks/pl_mark.py: untagged Agent/Task in a pipeline project is denied every time until tagged. Tmp dirs only."""
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

_P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks", "pl_mark.py")
_spec = importlib.util.spec_from_file_location("pl_mark_hook", _P)
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)


class Nudge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(os.path.join(self.proj, ".claude", "pipelines"))
        with open(os.path.join(self.proj, ".claude", "pipelines", "db-migration.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        self.cfg = os.path.join(self.tmp, "config.local.json")
        for k, v in (("MARK_DIR", os.path.join(self.tmp, "plmark")),
                     ("CONFIG_PATH", self.cfg)):
            p = mock.patch.object(H, k, v)
            p.start()
            self.addCleanup(p.stop)

    def _run(self, desc, tool="Agent", cwd=None, sid="sess-0001"):
        ev = {"tool_name": tool, "session_id": sid, "cwd": cwd or self.proj,
              "tool_input": {"summary" if tool == "SendMessage" else "description": desc}}
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", out):
            H.main()
        v = out.getvalue()
        return json.loads(v)["hookSpecificOutput"] if v else None

    def test_deny_every_untagged(self):
        o = self._run("fix the thing")
        self.assertEqual(o["permissionDecision"], "deny")
        self.assertIn("db-migration", o["permissionDecisionReason"])
        self.assertNotIn("fix the thing", o["permissionDecisionReason"])   # metadata only
        self.assertIsNotNone(self._run("fix the thing"))   # not once per session: mixed tagging lit runs in part
        self.assertIsNotNone(self._run("other", tool="Task", sid="sess-0002"))

    def test_tagged_pass(self):
        self.assertIsNone(self._run("[pl:db-migration/구현] x"))
        self.assertIsNone(self._run("[pl:-] x"))
        self.assertIsNotNone(self._run("x"))

    def test_other_tools_and_projects_pass(self):
        self.assertIsNone(self._run("x", tool="SendMessage"))
        self.assertIsNone(self._run("x", tool="Bash"))
        self.assertIsNone(self._run("x", cwd=self.tmp))                    # no pipelines
        self.assertIsNone(self._run("x", cwd="relative"))
        with open(self.cfg, "w", encoding="utf-8") as f:
            json.dump({"pipeline_apply": {"mode": "off"}}, f)
        self.assertIsNone(self._run("x"))                                   # «적용» off: no nudge

    def test_no_platform_bytes_identical(self):
        ev = json.dumps({"tool_name": "Agent", "session_id": "sess-0001", "cwd": self.proj,
                         "tool_input": {"description": "x"}})
        want = json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                           "permissionDecisionReason": H.nudge({"cwd": self.proj}, "sess-0001", "x")}})
        for argv in ([], ["--platform", "cc"]):
            out = io.StringIO()
            with mock.patch("sys.stdin", io.StringIO(ev)), mock.patch("sys.stdout", out):
                H.main(argv)
            self.assertEqual(out.getvalue(), want)


class ShellMarker(unittest.TestCase):
    """--platform: a shell command that starts with a marker sets the mark; metadata only."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.marks = os.path.join(self.tmp, "plmark")
        p = mock.patch.object(H, "MARK_DIR", self.marks)
        p.start()
        self.addCleanup(p.stop)
        self.path = os.path.join(self.marks, "sess-0001.json")

    def _run(self, cmd, argv=("--platform", "gemini"), tool="run_shell_command", event="BeforeTool"):
        ev = {"hook_event_name": event, "tool_name": tool, "session_id": "sess-0001", "cwd": self.tmp,
              "tool_input": {"command": cmd}}
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", out):
            H.main(list(argv))
        return out.getvalue()

    def mark(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def test_gemini_marker_holds(self):
        self.assertEqual(self._run('echo "[pl:sidereus-change/구현] secret text"'), "")
        m = self.mark()
        self.assertEqual(sorted(m), ["cwd", "hold", "name", "t", "title"])   # never the command
        self.assertEqual((m["name"], m["title"], m["hold"]), ("sidereus-change", "구현", 1))
        self._run("[pl-end:sidereus-change/구현|fail]")
        self.assertNotIn("hold", self.mark())
        self._run("# [pl:-]")
        self.assertFalse(os.path.exists(self.path))

    def test_not_a_marker(self):
        self._run('grep "[pl:" -r .')
        self._run('ls; echo "[pl:sidereus-change/구현]"')
        self._run('echo "[pl:sidereus-change/구현]"', event="AfterTool")
        self._run('echo "[pl:sidereus-change/구현]"', argv=())                              # cc: command ignored
        self._run('echo "[pl:sidereus-change/구현]"', argv=("--platform", "cc"), tool="Bash")
        self._run('echo "[pl:sidereus-change/구현]"', argv=("--platform", "nope"))
        self.assertFalse(os.path.exists(self.path))

    def test_codex_bash_and_argv_list(self):
        self._run(["bash", "-lc", ": [pl:sidereus-change/검증]"], argv=("--platform", "codex"), tool="shell",
                  event="PreToolUse")
        self.assertEqual(self.mark()["title"], "검증")
        os.remove(self.path)
        self._run("echo [pl:sidereus-change/리뷰]", argv=("--platform", "codex"), tool="Bash", event="PreToolUse")
        self.assertEqual(self.mark()["title"], "리뷰")

    def test_platforms_match_ext_store(self):
        from tests._load import sidereus
        self.assertEqual(set(H.PLATFORMS) - {"cc"}, set(sidereus("ext_store").EXT_PLAT))


if __name__ == "__main__":
    unittest.main()
