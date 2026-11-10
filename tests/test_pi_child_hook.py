"""pi subagent child: parent env window around the `subagent` tool, child agent_name, ext_hook allow-list. Tmp dirs only."""
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

import tests._load  # noqa: F401  (sets SIDEREUS_HOOK_NO_PID before the hook runs)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "ext-hooks", "pi-extension.ts")
NODE = shutil.which("node")
HOOK = os.path.join(ROOT, "ext-hooks", "ext_hook.py")
_spec = importlib.util.spec_from_file_location("ext_hook_pi_child", HOOK)
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)
_spec2 = importlib.util.spec_from_file_location("pi_ext_harness", os.path.join(ROOT, "tests", "test_pi_extension.py"))
harness = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(harness)

SCRIPTS = ("ext-hooks/ext_hook.py", "ext-hooks/pi_wake.py", "hooks/pl_mark.py", "hooks/pl_flow.py",
           "hooks/invite_notice.py", "hooks/pipelines_brief.py")
ENV_KEYS = ("SIDEREUS_PARENT_SID", "SIDEREUS_PARENT_PLAT", "SIDEREUS_CHILD_AGENT")

# Every spawned script logs its name, stdin and the three window env values; pi_wake exits at once.
STUB = r'''import json, os, sys
data = "" if os.path.basename(sys.argv[0]) == "pi_wake.py" else sys.stdin.read()
with open(os.environ["PI_TEST_LOG"], "a", encoding="utf-8") as f:
    f.write(json.dumps({"script": os.path.basename(sys.argv[0]), "argv": sys.argv[1:],
                        "stdin": json.loads(data or "{}"),
                        "env": {k: os.environ.get(k) for k in %r}}) + "\n")
''' % (ENV_KEYS,)

# Scenario driver: prints {snaps}, each snap = the window env this process would hand to a spawned subagent.
DRIVER = r'''
const [ext, scenario, want, log] = process.argv.slice(2, 6);
const fs = await import("node:fs");
const mod = await import(ext);
const handlers = {};
mod.default({ on: (n, f) => { handlers[n] = f; }, sendUserMessage: () => {} });
const ctx = { cwd: "/tmp/proj", sessionManager: { getSessionId: () => "sess-0001" },
              isIdle: () => true, hasPendingMessages: () => false };
const K = ["SIDEREUS_PARENT_SID", "SIDEREUS_PARENT_PLAT", "SIDEREUS_CHILD_AGENT"];
const snaps = [];
const snap = () => snaps.push(Object.fromEntries(K.map((k) => [k, process.env[k] ?? null])));
const n = () => { try { return fs.readFileSync(log, "utf8").split("\n").filter(Boolean).length; } catch { return 0; } };
// ⚠session_shutdown kills the waiter; a slow python start would die before logging, so wait for its line first.
const untilWake = async () => {
  if (!process.env.PI_TEST_NEED_WAKE) return;
  const has = () => { try { return fs.readFileSync(log, "utf8").includes('"script": "pi_wake.py"'); } catch { return false; } };
  const t = Date.now();
  while (!has() && Date.now() - t < 8000) await new Promise((r) => setTimeout(r, 20));
};
const call = (id, input) => handlers.tool_call({ toolName: "subagent", toolCallId: id, input }, ctx);
const end = (id) => handlers.tool_execution_end({ toolName: "subagent", toolCallId: id }, ctx);
if (scenario === "parent") {
  await handlers.session_start({ reason: "startup" }, ctx);
  await untilWake();
  await call("s1", { agent: "scout", task: "SECRET TASK" });
  snap();
  await handlers.tool_call({ toolName: "read", toolCallId: "r1", input: { path: "/x" } }, ctx);
  await end("s1");
  snap();
} else if (scenario === "overlap") {
  await call("s1", { tasks: [{ agent: "scout", task: "SECRET" }, { agent: "scout", task: "SECRET" }] });
  snap();
  await call("s2", { chain: [{ agent: "scout" }, { agent: "planner" }] });
  snap();
  await end("s1");
  snap();
  await end("s2");
  snap();
} else if (scenario === "child") {
  await handlers.session_start({ reason: "startup" }, ctx);
  await untilWake();
  await handlers.tool_call({ toolName: "read", toolCallId: "r1", input: { path: "/x" } }, ctx);
  await handlers.agent_settled({}, ctx);
  await handlers.session_shutdown({ reason: "quit" }, ctx);
}
const t0 = Date.now();
while (n() < Number(want) && Date.now() - t0 < 8000) await new Promise((r) => setTimeout(r, 20));
await new Promise((r) => setTimeout(r, 300));
console.log(JSON.stringify({ snaps }));
if (scenario !== "child") await handlers.session_shutdown({ reason: "quit" }, ctx);
'''


@unittest.skipUnless(NODE, "node not installed")
class PiChildExtension(unittest.TestCase):
    def setUp(self):
        self.args = harness._node_args()
        if self.args is None:
            self.skipTest("node cannot strip TypeScript types")
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.code = os.path.join(self.d, "code")
        for n in SCRIPTS:
            dst = os.path.join(self.code, *n.split("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "w", encoding="utf-8") as f:
                f.write(STUB)
        with open(SRC, encoding="utf-8") as f:
            src = f.read()
        ext = os.path.join(self.d, "ext.ts")
        with open(ext, "w", encoding="utf-8") as f:
            f.write(src.replace('"<PYTHON>"', json.dumps(sys.executable))
                    .replace('"<MAILBOX_CODE_DIR>"', json.dumps(self.code)))
        self.ext_url = pathlib.Path(ext).as_uri()
        self.driver = os.path.join(self.d, "driver.mjs")
        with open(self.driver, "w", encoding="utf-8") as f:
            f.write(DRIVER)
        self.log = os.path.join(self.d, "calls.jsonl")

    def drive(self, scenario, want, env=None, extra=(), wake=False):
        e = dict(os.environ, PI_TEST_LOG=self.log)
        for k in ENV_KEYS + ("CLAUDE_CODE_SESSION_ID", "PI_TEST_NEED_WAKE"):
            e.pop(k, None)
        e.update(env or {})
        if wake:
            e["PI_TEST_NEED_WAKE"] = "1"
        r = subprocess.run([NODE] + self.args + ["--no-warnings", self.driver, self.ext_url, scenario,
                                                 str(want), self.log] + list(extra),
                           capture_output=True, text=True, encoding="utf-8", timeout=60, env=e)
        self.assertEqual(r.returncode, 0, r.stderr)
        try:
            with open(self.log, encoding="utf-8") as f:
                calls = [json.loads(x) for x in f if x.strip()]
        except OSError:
            calls = []
        return json.loads(r.stdout.strip().splitlines()[-1])["snaps"], calls

    def test_R1_window_sets_own_sid_and_restores(self):
        snaps, calls = self.drive("parent", 7, wake=True)
        self.assertEqual(snaps[0], {"SIDEREUS_PARENT_SID": "sess-0001", "SIDEREUS_PARENT_PLAT": "pi",
                                    "SIDEREUS_CHILD_AGENT": "scout"})
        self.assertEqual(snaps[1], dict.fromkeys(ENV_KEYS))
        hooks = [c for c in calls if c["script"] == "ext_hook.py"]
        self.assertTrue(any(c["stdin"]["hook_event_name"] == "PreToolUse" and c["stdin"].get("tool_name") == "read"
                            for c in hooks))   # an event sent inside the window
        for c in calls:   # the parent's own hooks never see its own sid as parent
            self.assertIsNone(c["env"]["SIDEREUS_PARENT_SID"])
            self.assertNotIn("agent_name", c["stdin"])
        self.assertNotIn("SECRET", json.dumps(calls))
        self.assertIn("pi_wake.py", [c["script"] for c in calls])

    def test_R1_preset_parent_reaches_own_hooks_not_window_sid(self):
        snaps, calls = self.drive("parent", 7, env={"SIDEREUS_PARENT_SID": "outer-1"})
        outer = {"SIDEREUS_PARENT_SID": "outer-1", "SIDEREUS_PARENT_PLAT": None, "SIDEREUS_CHILD_AGENT": None}
        self.assertEqual(snaps, [outer, outer])   # parented pi: window stays shut, children keep the outer parent
        self.assertTrue(calls)
        for c in calls:
            self.assertEqual(c["env"]["SIDEREUS_PARENT_SID"], "outer-1")

    def test_R1_R4_claude_parented_pi_leaves_env_untouched(self):
        snaps, calls = self.drive("parent", 7, env={"CLAUDE_CODE_SESSION_ID": "claude-1"})
        self.assertEqual(snaps, [dict.fromkeys(ENV_KEYS)] * 2)   # never own sid: subagents stay under the Claude row
        self.assertTrue(calls)
        for c in calls:
            self.assertIsNone(c["env"]["SIDEREUS_PARENT_SID"])

    def test_R3_overlapping_calls_refcount_and_shared_name(self):
        snaps, _ = self.drive("overlap", 0)
        self.assertEqual(snaps[0]["SIDEREUS_CHILD_AGENT"], "scout")   # tasks[] all one name
        self.assertIsNone(snaps[1]["SIDEREUS_CHILD_AGENT"])           # chain[] mixed names: no label
        self.assertEqual(snaps[2]["SIDEREUS_PARENT_SID"], "sess-0001")  # one call still open
        self.assertEqual(snaps[3], dict.fromkeys(ENV_KEYS))

    def test_R1_R3_child_sends_agent_name_from_prompt_file(self):
        prompt = os.path.join(self.d, "pi-subagent-x", "prompt-scout.md")
        _, calls = self.drive("child", 5, env={"SIDEREUS_PARENT_SID": "parent-1", "SIDEREUS_PARENT_PLAT": "pi",
                                               "SIDEREUS_CHILD_AGENT": "other"},
                              extra=["--mode", "json", "-p", "--no-session", "--append-system-prompt", prompt,
                                     "Task: SECRET TASK prompt-evil.md"])
        scripts = [c["script"] for c in calls]
        self.assertNotIn("pi_wake.py", scripts)
        self.assertNotIn("invite_notice.py", scripts)
        hooks = [c for c in calls if c["script"] == "ext_hook.py"]
        self.assertEqual(sorted(c["stdin"]["hook_event_name"] for c in hooks),
                         ["PreToolUse", "SessionEnd", "SessionStart", "Stop"])
        for c in calls:
            self.assertEqual(c["stdin"].get("agent_name"), "scout")
            self.assertEqual(c["env"]["SIDEREUS_PARENT_SID"], "parent-1")
        self.assertNotIn("SECRET", json.dumps(calls))
        self.assertNotIn("evil", json.dumps(calls))

    def test_R3_child_env_name_fallback_sanitized(self):
        _, calls = self.drive("child", 5, env={"SIDEREUS_PARENT_SID": "parent-1", "SIDEREUS_PARENT_PLAT": "pi",
                                               "SIDEREUS_CHILD_AGENT": "my agent!"},
                              extra=["--append-system-prompt", "/tmp/notes.md"])
        self.assertTrue(calls)
        for c in calls:
            self.assertEqual(c["stdin"].get("agent_name"), "my_agent_")

    def test_R4_no_env_is_a_plain_row(self):
        prompt = os.path.join(self.d, "prompt-scout.md")
        _, calls = self.drive("child", 7, extra=["-p", "--append-system-prompt", prompt], wake=True)
        scripts = [c["script"] for c in calls]
        self.assertIn("pi_wake.py", scripts)
        self.assertIn("invite_notice.py", scripts)
        for c in calls:
            self.assertNotIn("agent_name", c["stdin"])
            self.assertIsNone(c["env"]["SIDEREUS_PARENT_SID"])

    def test_R4_parent_sid_without_pi_plat_is_not_a_child(self):
        _, calls = self.drive("child", 7, wake=True, env={"SIDEREUS_PARENT_SID": "claude-1"},
                              extra=["--append-system-prompt", os.path.join(self.d, "prompt-scout.md")])
        self.assertIn("pi_wake.py", [c["script"] for c in calls])
        for c in calls:
            self.assertNotIn("agent_name", c["stdin"])


class ExtHookAgentName(unittest.TestCase):
    def setUp(self):
        for name, val in (("parent_sid", lambda env=None: "parent-1"), ("cli_pid_ex", lambda: (0, "", "")),
                          ("time", types.SimpleNamespace(time=lambda: 1790000000.0))):
            p = mock.patch.object(hook, name, val)
            p.start()
            self.addCleanup(p.stop)

    def build(self, name):
        out, _ = hook.build("pi", {"hook_event_name": "SessionStart", "session_id": "c-1", "cwd": "/w",
                                   "agent_name": name})
        return out

    def test_R3_good_name_passes_with_parent(self):
        out = self.build("scout.v2_x-1")
        self.assertEqual(out["agent_name"], "scout.v2_x-1")
        self.assertEqual(out["parent"], "parent-1")

    def test_R3_bad_names_dropped(self):
        for bad in ("", "a b", "x" * 65, "../etc", "naïve", "Task: run", 7, None, ["scout"]):
            self.assertNotIn("agent_name", self.build(bad), bad)


if __name__ == "__main__":
    unittest.main()
