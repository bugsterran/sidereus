"""ext-hooks/pi-extension.ts under node with a fake `pi` object and a stub Python that logs argv + stdin. Tmp dirs only."""
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "ext-hooks", "pi-extension.ts")
NODE = shutil.which("node")

STUB = r'''#!%s
import json, os, signal, sys
if os.path.basename(sys.argv[1]) == "pi_wake.py":
    # Waiter stub: mode from PI_TEST_WAKE; every event goes to PI_TEST_WLOG.
    wlog = os.environ.get("PI_TEST_WLOG") or os.devnull
    def wl(o):
        with open(wlog, "a", encoding="utf-8") as f:
            f.write(json.dumps(o) + "\n")
    def term(_s, _f):
        wl({"end": "term"})
        os._exit(0)
    signal.signal(signal.SIGTERM, term)
    try:
        with open(wlog, encoding="utf-8") as f:
            k = sum(1 for x in f if '"spawn"' in x)
    except OSError:
        k = 0
    wl({"spawn": k, "argv": sys.argv[2:]})
    mode = os.environ.get("PI_TEST_WAKE", "block")
    if mode == "silent":   # slot busy: exits with no line
        wl({"exit": k})
        sys.exit(0)
    if mode == "wake" or (mode == "timeout" and k == 0):
        out = {"wake": "[mailbox] 1 new mail for `p-pi` — from: zed(DM)."} if mode == "wake" else {"end": "timeout"}
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()
        if mode == "timeout":
            sys.exit(0)
    line = sys.stdin.readline()
    wl({"ack": line.strip()} if line else {"end": "eof"})
    sys.exit(0)
data = sys.stdin.read()
with open(os.environ["PI_TEST_LOG"], "a", encoding="utf-8") as f:
    f.write(json.dumps({"argv": sys.argv[1:], "stdin": json.loads(data or "{}")}) + "\n")
s = os.path.basename(sys.argv[1])
if s == "pl_flow.py" and os.environ.get("PI_TEST_DENY"):
    sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                        "permissionDecisionReason": "jump refused"}}))
elif s == "pipelines_brief.py":
    sys.stdout.write(json.dumps({"hookSpecificOutput": {"additionalContext": "BRIEF"}}))
elif s == "invite_notice.py":
    sys.stdout.write("INVITE")
'''

# Loads the rendered extension, fires one scenario, waits for `want` stub calls, prints {ret, sections}.
DRIVER = r'''
const [ext, scenario, want, log] = process.argv.slice(2);
const fs = await import("node:fs");
const mod = await import(ext);
const handlers = {};
mod.default({ on: (n, f) => { handlers[n] = f; } });
const ctx = { cwd: "/tmp/proj", sessionManager: { getSessionId: () => "sess-0001" } };
let ret = null, sections = {};
if (scenario === "bash") ret = await handlers.tool_call({ toolName: "bash", toolCallId: "t1", input: { command: "echo hi" } }, ctx);
if (scenario === "read") ret = await handlers.tool_call({ toolName: "read", toolCallId: "t2", input: { path: "/x" } }, ctx);
if (scenario === "prompt") {
  await handlers.session_start({ reason: "startup" }, ctx);
  await handlers.before_agent_start({ prompt: "SECRET PROMPT", systemPromptOptions: { sections } }, ctx);
}
const n = () => { try { return fs.readFileSync(log, "utf8").split("\n").filter(Boolean).length; } catch { return 0; } };
const t0 = Date.now();
while (n() < Number(want) && Date.now() - t0 < 8000) await new Promise((r) => setTimeout(r, 20));
await new Promise((r) => setTimeout(r, 150));
console.log(JSON.stringify({ ret: ret ?? null, sections }));
'''


def _node_args():
    """[] when node strips TypeScript by default, the flag when it needs one, None when it cannot."""
    try:
        v = subprocess.run([NODE, "--version"], capture_output=True, text=True, encoding="utf-8", timeout=10).stdout.strip()
        major, minor = (int(x) for x in v.lstrip("v").split(".")[:2])
    except Exception:
        return None
    if (major, minor) >= (23, 6) or (major == 22 and minor >= 18):
        return []
    return ["--experimental-strip-types"] if major >= 22 else None


@unittest.skipUnless(NODE, "node not installed")
class PiExtension(unittest.TestCase):
    def setUp(self):
        self.args = _node_args()
        if self.args is None:
            self.skipTest("node cannot strip TypeScript types")
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.py = os.path.join(self.d, "stub.py")
        with open(self.py, "w", encoding="utf-8") as f:
            f.write(STUB % sys.executable)
        os.chmod(self.py, os.stat(self.py).st_mode | stat.S_IEXEC)
        with open(SRC, encoding="utf-8") as f:
            src = f.read()
        self.assertEqual(src.count('"<PYTHON>"'), 1)
        self.assertEqual(src.count('"<MAILBOX_CODE_DIR>"'), 1)
        self.ext = os.path.join(self.d, "ext.ts")
        with open(self.ext, "w", encoding="utf-8") as f:
            f.write(src.replace('"<PYTHON>"', json.dumps(self.py)).replace('"<MAILBOX_CODE_DIR>"', json.dumps("/code")))
        self.driver = os.path.join(self.d, "driver.mjs")
        with open(self.driver, "w", encoding="utf-8") as f:
            f.write(DRIVER)
        self.log = os.path.join(self.d, "calls.jsonl")

    def drive(self, scenario, want, deny=False):
        env = dict(os.environ, PI_TEST_LOG=self.log)
        env.pop("PI_TEST_DENY", None)
        if deny:
            env["PI_TEST_DENY"] = "1"
        r = subprocess.run([NODE] + self.args + ["--no-warnings", self.driver, "file://" + self.ext, scenario,
                                                 str(want), self.log],
                           capture_output=True, text=True, encoding="utf-8", timeout=60, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        try:
            with open(self.log, encoding="utf-8") as f:
                calls = [json.loads(x) for x in f if x.strip()]
        except OSError:
            calls = []
        return json.loads(r.stdout.strip().splitlines()[-1]), calls

    def by_script(self, calls):
        return {os.path.relpath(c["argv"][0], "/code"): c for c in calls}

    def test_bash_tool_call_three_calls(self):
        out, calls = self.drive("bash", 3)
        self.assertIsNone(out["ret"])
        self.assertEqual(len(calls), 3)
        for c in calls:
            self.assertEqual(c["argv"][1:], ["--platform", "pi"])
        s = self.by_script(calls)
        base = {"session_id": "sess-0001", "cwd": "/tmp/proj", "hook_event_name": "PreToolUse", "tool_name": "bash"}
        self.assertEqual(s[os.path.join("ext-hooks", "ext_hook.py")]["stdin"], base)   # no tool_input
        full = dict(base, tool_input={"command": "echo hi"})
        self.assertEqual(s[os.path.join("hooks", "pl_mark.py")]["stdin"], full)
        self.assertEqual(s[os.path.join("hooks", "pl_flow.py")]["stdin"], full)

    def test_deny_blocks(self):
        out, _ = self.drive("bash", 3, deny=True)
        self.assertEqual(out["ret"], {"block": True, "reason": "jump refused"})

    def test_other_tool_one_call_no_input(self):
        out, calls = self.drive("read", 1)
        self.assertIsNone(out["ret"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["stdin"], {"session_id": "sess-0001", "cwd": "/tmp/proj",
                                             "hook_event_name": "PreToolUse", "tool_name": "read"})

    def test_before_agent_start_sets_section(self):
        out, calls = self.drive("prompt", 5)
        self.assertEqual(out["sections"], {"sidereus": "INVITE\n\nBRIEF"})
        self.assertNotIn("SECRET", json.dumps(calls))   # the prompt never leaves pi
        ups = [c for c in calls if c["stdin"]["hook_event_name"] == "UserPromptSubmit"]
        self.assertEqual(sorted(os.path.basename(c["argv"][0]) for c in ups), ["ext_hook.py", "pipelines_brief.py"])

# Wake scenarios: fake pi with sendUserMessage, ctx with isIdle/hasPendingMessages; prints {sends, idleCalls}.
WAKE_DRIVER = r'''
const [ext, scenario, wlog, busy] = process.argv.slice(2);
const fs = await import("node:fs");
const realST = globalThis.setTimeout;
globalThis.setTimeout = (f, ms, ...a) => realST(f, ms >= 10000 ? 300 : ms, ...a);   // the 16 s re-arm runs in 0.3 s
const mod = await import(ext);
const handlers = {};
const sends = [];
mod.default({ on: (n, f) => { handlers[n] = f; }, sendUserMessage: (t) => { sends.push(t); } });
const ctx = { cwd: "/tmp/proj", sessionManager: { getSessionId: () => "sess-0001" },
              isIdle: () => busy !== "1", hasPendingMessages: () => false };
const rows = () => { try { return fs.readFileSync(wlog, "utf8").split("\n").filter(Boolean).map((x) => JSON.parse(x)); } catch { return []; } };
const until = async (f) => { const t0 = Date.now(); while (!f(rows()) && Date.now() - t0 < 8000) await new Promise((r) => setTimeout(r, 20)); };
const n = (k) => (r) => r.filter((x) => k in x).length;
const pause = (ms) => new Promise((r) => setTimeout(r, ms));
if (scenario === "wake") {
  await handlers.session_start({ reason: "startup" }, ctx);
  await until((r) => n("ack")(r) >= 1);
} else if (scenario === "cap") {
  await handlers.session_start({ reason: "startup" }, ctx);
  await until((r) => n("ack")(r) >= 1);
  await handlers.agent_settled({}, ctx);
  await until((r) => n("ack")(r) >= 2);
  await handlers.input({ source: "interactive", text: "x" }, ctx);
  await handlers.agent_settled({}, ctx);
  await until((r) => n("ack")(r) >= 3);
} else if (scenario === "kill") {
  await handlers.session_start({ reason: "startup" }, ctx);
  await until((r) => n("spawn")(r) >= 1);
  await handlers.before_agent_start({ systemPromptOptions: {} }, ctx);
  await until((r) => n("end")(r) >= 1);
} else if (scenario === "one") {
  await handlers.session_start({ reason: "startup" }, ctx);
  await handlers.agent_settled({}, ctx);
  await handlers.agent_settled({}, ctx);
  await until((r) => n("spawn")(r) >= 1);
  await pause(400);
} else if (scenario === "shutdown") {
  await handlers.session_start({ reason: "startup" }, ctx);
  await until((r) => n("spawn")(r) >= 1);
  await handlers.session_shutdown({ reason: "quit" }, ctx);
  await handlers.agent_settled({}, ctx);
  await until((r) => n("end")(r) >= 1);
  await pause(400);
} else if (scenario === "rearm") {
  await handlers.session_start({ reason: "startup" }, ctx);
  await until((r) => n("spawn")(r) >= 2);
  await pause(800);
} else if (scenario === "rearm-input") {
  await handlers.session_start({ reason: "startup" }, ctx);
  await until((r) => n("exit")(r) >= 1);
  await pause(100);
  await handlers.input({ source: "interactive", text: "x" }, ctx);
  await pause(800);
} else if (scenario === "timeout") {
  await handlers.session_start({ reason: "startup" }, ctx);
  await until((r) => n("spawn")(r) >= 2);
}
await pause(150);
console.log(JSON.stringify({ sends }));
if (scenario !== "shutdown") await handlers.session_shutdown({ reason: "quit" }, ctx);
'''


@unittest.skipUnless(NODE, "node not installed")
class PiExtensionWake(unittest.TestCase):
    def setUp(self):
        PiExtension.setUp(self)   # same rendered extension and stub; not a subclass, so its tests do not run twice
        self.wdriver = os.path.join(self.d, "wake.mjs")
        with open(self.wdriver, "w", encoding="utf-8") as f:
            f.write(WAKE_DRIVER)
        self.wlog = os.path.join(self.d, "wake.jsonl")

    def wake(self, scenario, mode="block", busy=False, cap=None):
        env = dict(os.environ, PI_TEST_LOG=self.log, PI_TEST_WLOG=self.wlog, PI_TEST_WAKE=mode)
        env.pop("SIDEREUS_MAIL_WAIT_MAX", None)
        if cap is not None:
            env["SIDEREUS_MAIL_WAIT_MAX"] = str(cap)
        r = subprocess.run([NODE] + self.args + ["--no-warnings", self.wdriver, "file://" + self.ext, scenario,
                                                 self.wlog, "1" if busy else "0"],
                           capture_output=True, text=True, encoding="utf-8", timeout=60, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(self.wlog, encoding="utf-8") as f:
            rows = [json.loads(x) for x in f if x.strip()]
        return json.loads(r.stdout.strip().splitlines()[-1])["sends"], rows

    def test_R1_idle_wake_sends_once_and_acks_ok(self):
        sends, rows = self.wake("wake", "wake")
        self.assertEqual(sends, ["[mailbox] 1 new mail for `p-pi` — from: zed(DM)."])
        self.assertEqual([x["ack"] for x in rows if "ack" in x], ["ok"])
        self.assertEqual(rows[0]["argv"], ["sess-0001", "/tmp/proj"])   # ids and paths only

    def test_R4_busy_no_send_acks_no(self):
        sends, rows = self.wake("wake", "wake", busy=True)
        self.assertEqual(sends, [])
        self.assertEqual([x["ack"] for x in rows if "ack" in x], ["no"])

    def test_R4_before_agent_start_kills_waiter(self):
        sends, rows = self.wake("kill")
        self.assertEqual(sends, [])
        self.assertEqual(len([x for x in rows if "end" in x]), 1)

    def test_R4_one_waiter_at_a_time(self):
        _, rows = self.wake("one")
        self.assertEqual(len([x for x in rows if "spawn" in x]), 1)

    def test_R4_no_rearm_after_shutdown(self):
        _, rows = self.wake("shutdown")
        self.assertEqual(len([x for x in rows if "spawn" in x]), 1)

    def test_R2_timeout_rearms_without_send(self):
        sends, rows = self.wake("timeout", "timeout")
        self.assertEqual(sends, [])
        self.assertEqual(len([x for x in rows if "spawn" in x]), 2)

    def test_R1_R4_silent_exit_rearms_once(self):
        # A waiter that exits with no line (stale lock after a Windows kill) is retried once, never looped.
        sends, rows = self.wake("rearm", "silent")
        self.assertEqual(sends, [])
        self.assertEqual(len([x for x in rows if "spawn" in x]), 2)

    def test_R4_silent_exit_no_rearm_when_busy_or_typed(self):
        _, rows = self.wake("rearm", "silent", busy=True)
        self.assertEqual(len([x for x in rows if "spawn" in x]), 1)
        os.remove(self.wlog)
        _, rows = self.wake("rearm-input", "silent")
        self.assertEqual(len([x for x in rows if "spawn" in x]), 1)

    def test_cap_stops_sends_until_typed_input(self):
        sends, rows = self.wake("cap", "wake", cap=1)
        self.assertEqual(len(sends), 2)
        self.assertEqual([x["ack"] for x in rows if "ack" in x], ["ok", "no", "ok"])


class PluginVersion(unittest.TestCase):
    def test_version_has_pi_support(self):
        # pi in the hook scripts shipped with plugin 0.9.0; the built manifest carries the build script's VERSION.
        with open(os.path.join(ROOT, "scripts", "build_plugin.py"), encoding="utf-8") as f:
            v = re.search(r'^VERSION = "([0-9.]+)"', f.read(), re.M).group(1)
        with open(os.path.join(ROOT, "plugin", ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["version"], v)
        self.assertGreaterEqual(tuple(int(x) for x in v.split(".")), (0, 9, 0))

if __name__ == "__main__":
    unittest.main()
