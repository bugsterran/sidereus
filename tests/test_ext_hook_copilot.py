"""ext_hook.py Copilot CLI mapping: snake payloads, camelCase PermissionRequest, allow-list, empty stdout."""
import importlib.util
import io
import json
import os
import sys
import types
import unittest
from unittest import mock

import tests._load  # noqa: F401  (sets SIDEREUS_HOOK_NO_PID before the hook runs)
from tests._load import sidereus

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "ext-hooks", "ext_hook.py")
_spec = importlib.util.spec_from_file_location("ext_hook_copilot", HOOK)
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)

st = sidereus("ext_store")

SID = "cafe0000-1111-2222-3333-444455556666"
SECRET = "SECRET-COPILOT-INPUT rm -rf x"
NOW = 1790000000.0


def _perm(name, **extra):
    d = {"hookName": name, "sessionId": SID, "timestamp": 1790000000123, "cwd": "/work/proj",
         "toolName": "bash", "toolInput": {"command": SECRET}, "permissionSuggestions": [SECRET]}
    d.update(extra)
    return d


class CopilotHook(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict(os.environ, {"SIDEREUS_HOOK_NO_PID": "1"})
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("SIDEREUS_PARENT_SID", None)
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)

    def test_r1_snake_payloads_map(self):
        for raw in ("SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"):
            out, _ = hook.build("copilot", {"hook_event_name": raw, "session_id": SID, "cwd": "/work/proj"})
            self.assertEqual((out["platform"], out["event"], out["session_id"], out["cwd"]),
                             ("copilot", raw, SID, "/work/proj"), raw)

    def test_r2_camel_permission_request(self):
        for name in ("permissionRequest", "PermissionRequest"):
            out, raw = hook.build("copilot", _perm(name))
            self.assertEqual(raw, name)
            self.assertEqual((out["event"], out["session_id"], out["tool_name"]), ("Notification", SID, "bash"))
            body = json.dumps(out)
            self.assertNotIn("SECRET", body)
            for key in ("toolInput", "permissionSuggestions", "timestamp", "sessionId", "toolName", "hookName"):
                self.assertNotIn(key, out)
            self.assertNotEqual(out["ts"], 1790000000123)
        # snake keys win; non-str camel values are dropped
        out, _ = hook.build("copilot", _perm("permissionRequest", session_id="own", tool_name="edit"))
        self.assertEqual((out["session_id"], out["tool_name"]), ("own", "edit"))
        out, _ = hook.build("copilot", _perm("permissionRequest", sessionId=42, toolName=""))
        self.assertNotIn("session_id", out)
        self.assertNotIn("tool_name", out)

    def test_rule1_no_content_keys(self):
        for raw in ("UserPromptSubmit", "PostToolUse", "PreToolUse"):
            d = {"hook_event_name": raw, "session_id": SID, "prompt": SECRET, "initial_prompt": SECRET,
                 "tool_input": {"c": SECRET}, "tool_result": SECRET, "transformedPrompt": SECRET,
                 "toolInput": SECRET, "permissionSuggestions": [SECRET]}
            out, _ = hook.build("copilot", d)
            self.assertNotIn("SECRET", json.dumps(out), raw)

    def test_main_dry_run_stdout_empty(self):
        stdin = io.StringIO(json.dumps(_perm("permissionRequest")))
        so, se = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["ext_hook.py", "--platform", "copilot", "--dry-run"]), \
                mock.patch.object(sys, "stdin", stdin), mock.patch.object(sys, "stdout", so), \
                mock.patch.object(sys, "stderr", se), \
                mock.patch.object(hook.urllib.request, "urlopen", side_effect=AssertionError("network")):
            hook.main()
        self.assertEqual(so.getvalue(), "")
        sent = json.loads(se.getvalue())
        self.assertEqual((sent["event"], sent["session_id"]), ("Notification", SID))
        self.assertNotIn("SECRET", se.getvalue())

    def test_r2_store_blocked_until_post_tool_use(self):
        saved = dict(st._ext), dict(st._runs)
        patches = [mock.patch.object(st, n, lambda: None)
                   for n in ("_ext_save_locked", "_runs_save_locked", "_hooktok_save_locked")]
        patches.append(mock.patch.object(st, "time", types.SimpleNamespace(time=lambda: NOW)))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        st._ext.clear()
        try:
            out, _ = hook.build("copilot", _perm("permissionRequest"))
            out["ts"] = NOW
            self.assertEqual(st.ext_ingest(out), (True, "ok"))
            v = st._ext[("copilot", SID)]
            self.assertTrue(v["blocked"])
            self.assertEqual(v["state"], "ask")
            out, _ = hook.build("copilot", {"hook_event_name": "PostToolUse", "session_id": SID, "toolName": "bash"})
            out["ts"] = NOW + 1
            st.ext_ingest(out)
            v = st._ext[("copilot", SID)]
            self.assertFalse(v["blocked"])
            self.assertEqual(v["state"], "think")
        finally:
            st._ext.clear()
            st._ext.update(saved[0])
            st._runs.clear()
            st._runs.update(saved[1])


if __name__ == "__main__":
    unittest.main()
