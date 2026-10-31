"""ext_hook.py Cursor CLI mapping: camelCase events, cwd/session fallbacks, allow-list, empty stdout."""
import importlib.util
import io
import json
import os
import sys
import unittest
from unittest import mock

import tests._load  # noqa: F401  (sets SIDEREUS_HOOK_NO_PID before the hook runs)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "ext-hooks", "ext_hook.py")
_spec = importlib.util.spec_from_file_location("ext_hook_cursor", HOOK)
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)

CID = "c0ffee00-1111-2222-3333-444455556666"
EMAIL = "someone-SECRET@example.com"
TEXT = "SECRET-CURSOR-RESPONSE-TEXT"
CMD = "SECRET-CURSOR-COMMAND rm -rf x"


def _payload(event, **extra):
    d = {"hook_event_name": event, "conversation_id": CID, "session_id": CID, "generation_id": "g1",
         "workspace_roots": ["/work/proj"], "transcript_path": None, "cursor_version": "2026.10.22-27dcf5f",
         "model": "claude-4.5-sonnet", "user_email": EMAIL}
    d.update(extra)
    return d


class CursorHook(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict(os.environ, {"SIDEREUS_HOOK_NO_PID": "1"})
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("SIDEREUS_PARENT_SID", None)
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)

    def test_mapping(self):
        want = {"sessionStart": "SessionStart", "sessionEnd": "SessionEnd",
                "beforeSubmitPrompt": "UserPromptSubmit", "stop": "Stop", "preToolUse": "PreToolUse",
                "postToolUse": "PostToolUse", "postToolUseFailure": "PostToolUse"}
        self.assertEqual(hook.EVENTS["cursor"], dict(hook.EVENTS["codex"], **want))
        for raw, std in want.items():
            out, _ = hook.build("cursor", _payload(raw))
            self.assertEqual(out["event"], std, raw)
            self.assertEqual(out["platform"], "cursor")
        # older configs pass `--event <standard name>`; those still map
        for std in ("PreToolUse", "Stop", "Notification", "SessionStart"):
            out, _ = hook.build("cursor", _payload("afterAgentResponse"), std)
            self.assertEqual(out["event"], std)
        for raw in ("afterAgentThought", "afterAgentResponse", "beforeShellExecution", "afterShellExecution",
                    "beforeReadFile"):
            out, got = hook.build("cursor", _payload(raw))
            self.assertIsNone(out, raw)
            self.assertEqual(got, raw)

    def test_cwd_from_workspace_roots(self):
        out, _ = hook.build("cursor", _payload("preToolUse", cwd="", workspace_roots=["", "rel/x", "/a/b", "/c"]))
        self.assertEqual(out["cwd"], "/a/b")
        out, _ = hook.build("cursor", _payload("sessionStart"))
        self.assertEqual(out["cwd"], "/work/proj")
        out, _ = hook.build("cursor", _payload("sessionStart", cwd="/real", workspace_roots=["/work/proj"]))
        self.assertEqual(out["cwd"], "/real")
        out, _ = hook.build("cursor", _payload("sessionStart", workspace_roots="/not/a/list"))
        self.assertNotIn("cwd", out)
        out, _ = hook.build("cursor", _payload("sessionStart", workspace_roots=[]))
        self.assertNotIn("cwd", out)

    def test_session_id_fallback(self):
        d = _payload("stop")
        del d["session_id"]
        out, _ = hook.build("cursor", d)
        self.assertEqual(out["session_id"], CID)
        out, _ = hook.build("cursor", _payload("stop", session_id="sid-own"))
        self.assertEqual(out["session_id"], "sid-own")
        d = _payload("stop", conversation_id=42)
        del d["session_id"]
        out, _ = hook.build("cursor", d)
        self.assertNotIn("session_id", out)

    def test_allow_list(self):
        for raw in ("preToolUse", "postToolUse", "stop", "beforeSubmitPrompt"):
            d = _payload(raw, tool_name="Shell", tool_input={"command": CMD, "cwd": "", "timeout": 30},
                         text=TEXT, prompt=TEXT, cwd="")
            out, _ = hook.build("cursor", d)
            body = json.dumps(out)
            for key in ("user_email", "text", "tool_input", "prompt", "generation_id", "workspace_roots",
                        "cursor_version", "conversation_id"):
                self.assertNotIn(key, out, (raw, key))
            for secret in (EMAIL, TEXT, CMD):
                self.assertNotIn(secret, body, raw)
            self.assertNotIn("transcript_path", out)   # null until the first tool

    def test_stop_usage(self):
        tok = dict(input_tokens=14645, output_tokens=28, cache_read_tokens=3968, cache_write_tokens=0)
        out, _ = hook.build("cursor", _payload("stop", generation_id="gen-1_a", text=TEXT, status="completed",
                                               transcript_path="/x/SECRET.jsonl", **tok))
        self.assertEqual(out["usage"], {"in": 14645, "out": 28, "cr": 3968, "cw": 0})
        self.assertEqual(out["gen_id"], "gen-1_a")
        self.assertEqual(set(out) - {"platform", "event", "ts", "session_id", "cwd", "model", "transcript_path"},
                         {"usage", "gen_id"})
        body = json.dumps(out)
        for secret in (EMAIL, TEXT, "completed"):
            self.assertNotIn(secret, body)
        for key in ("user_email", "text", "input_tokens", "generation_id", "status"):
            self.assertNotIn(key, out)
        # bad values dropped one by one; a bad generation id is dropped too
        out, _ = hook.build("cursor", _payload("stop", generation_id="bad id!", input_tokens=True,
                                               output_tokens=-1, cache_read_tokens="5", cache_write_tokens=7))
        self.assertEqual(out["usage"], {"cw": 7})
        self.assertNotIn("gen_id", out)
        out, _ = hook.build("cursor", _payload("stop", input_tokens=10 ** 9, generation_id="x" * 65))
        self.assertNotIn("usage", out)
        self.assertNotIn("gen_id", out)

    def test_usage_only_on_cursor_stop(self):
        for raw in ("preToolUse", "beforeSubmitPrompt", "sessionEnd"):
            out, _ = hook.build("cursor", _payload(raw, input_tokens=5, output_tokens=5))
            self.assertNotIn("usage", out, raw)
            self.assertNotIn("gen_id", out, raw)
        out, _ = hook.build("cursor", _payload("afterAgentResponse", input_tokens=5))
        self.assertIsNone(out)
        for plat, ev in (("codex", "Stop"), ("gemini", "AfterAgent"), ("copilot", "Stop")):
            out, _ = hook.build(plat, _payload(ev, input_tokens=5, output_tokens=5))
            self.assertNotIn("usage", out, plat)
            self.assertNotIn("gen_id", out, plat)

    def test_other_maps_unchanged(self):
        self.assertEqual(hook.EVENTS["gemini"]["AfterAgent"], "Stop")
        self.assertEqual(hook.EVENTS["codex"]["PermissionRequest"], "Notification")
        self.assertNotIn("sessionStart", hook.EVENTS["codex"])
        self.assertEqual(hook.EVENTS["copilot"], dict(hook.EVENTS["codex"], permissionRequest="Notification"))

    def test_main_dry_run_stdout_empty(self):
        stdin = io.StringIO(json.dumps(_payload("preToolUse", tool_name="Shell", tool_input={"command": CMD})))
        so, se = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["ext_hook.py", "--platform", "cursor", "--dry-run"]), \
                mock.patch.object(sys, "stdin", stdin), mock.patch.object(sys, "stdout", so), \
                mock.patch.object(sys, "stderr", se), \
                mock.patch.object(hook.urllib.request, "urlopen", side_effect=AssertionError("network")):
            hook.main()
        self.assertEqual(so.getvalue(), "")
        sent = json.loads(se.getvalue())
        self.assertEqual((sent["event"], sent["cwd"], sent["session_id"]), ("PreToolUse", "/work/proj", CID))
        self.assertNotIn(CMD, se.getvalue())


if __name__ == "__main__":
    unittest.main()
