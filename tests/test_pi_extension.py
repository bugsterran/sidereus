"""ext-hooks/pi-extension.ts under node with a fake `pi` object and a stub Python that logs argv + stdin. Tmp dirs only."""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "ext-hooks", "pi-extension.ts")
NODE = shutil.which("node")

# ⚠Copied under each spawned script's name and run by the real interpreter: Windows cannot spawn a .py without a shell.
STUB = r'''import json, os, signal, sys, time, uuid
SEQ = [0]
def put(d, o):
    # One file per record named by wall clock + pid + counter, so readers sort into write order.
    # ⚠Not perf_counter_ns: on 3.9 macOS it starts at 0 in each process, so it cannot order across processes.
    if not d:
        return
    os.makedirs(d, exist_ok=True)
    SEQ[0] += 1
    name = "%020d-%010d-%04d-%s" % (time.time_ns(), os.getpid(), SEQ[0], uuid.uuid4().hex)
    tmp = os.path.join(d, name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(o))
    os.replace(tmp, os.path.join(d, name + ".json"))
if os.path.basename(sys.argv[0]) == "pi_wake.py":
    # Waiter stub: mode from PI_TEST_WAKE; every event goes to the PI_TEST_WLOG directory.
    wlog = os.environ.get("PI_TEST_WLOG", "")
    def wl(o):
        put(wlog, o)
    def term(_s, _f):
        wl({"end": "term"})
        os._exit(0)
    signal.signal(signal.SIGTERM, term)
    if sys.argv[3:] == ["quiet"]:   # PI_TEST_QUIET_DELAY: a slow quiet-waiter start, as on a loaded Windows runner
        time.sleep(float(os.environ.get("PI_TEST_QUIET_DELAY") or 0))
    k = 0
    try:
        for x in os.listdir(wlog):
            if x.endswith(".json"):
                with open(os.path.join(wlog, x), encoding="utf-8") as f:
                    k += "spawn" in json.load(f)
    except (OSError, ValueError):
        pass
    wl({"spawn": k, "argv": sys.argv[1:]})
    mode = os.environ.get("PI_TEST_WAKE", "block")
    if sys.argv[3:] == ["quiet"]:   # quiet waiter: the pending mail never wakes it
        mode = "block"
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
put(os.environ["PI_TEST_LOG"], {"argv": sys.argv, "stdin": json.loads(data or "{}")})
s = os.path.basename(sys.argv[0])
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
const n = () => { try { return fs.readdirSync(log).filter((x) => x.endsWith(".json")).length; } catch { return 0; } };
const t0 = Date.now();
while (n() < Number(want) && Date.now() - t0 < 8000) await new Promise((r) => setTimeout(r, 20));
await new Promise((r) => setTimeout(r, 150));
console.log(JSON.stringify({ ret: ret ?? null, sections }));
'''


def read_dir(d):
    """Stub records in write order (file names sort by clock, pid, counter)."""
    out = []
    for x in sorted(os.listdir(d)):
        if x.endswith(".json"):
            with open(os.path.join(d, x), encoding="utf-8") as f:
                out.append(json.load(f))
    return out


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
        with open(SRC, encoding="utf-8") as f:
            src = f.read()
        self.assertEqual(src.count('"<PYTHON>"'), 1)
        self.assertEqual(src.count('"<MAILBOX_CODE_DIR>"'), 1)
        self.code = os.path.join(self.d, "code")
        names = set(re.findall(r'"((?:ext-hooks|hooks)/\w+\.py)"', src)) | {"ext-hooks/pi_wake.py"}
        self.assertEqual(len(names), 6)   # every script the extension spawns gets a stub copy
        for n in names:
            dst = os.path.join(self.code, *n.split("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "w", encoding="utf-8") as f:
                f.write(STUB)
        self.ext = os.path.join(self.d, "ext.ts")
        with open(self.ext, "w", encoding="utf-8") as f:
            f.write(src.replace('"<PYTHON>"', json.dumps(sys.executable))
                    .replace('"<MAILBOX_CODE_DIR>"', json.dumps(self.code)))
        self.ext_url = pathlib.Path(self.ext).as_uri()   # file:///C:/... on Windows; "file://" + path is not a URL there
        self.driver = os.path.join(self.d, "driver.mjs")
        with open(self.driver, "w", encoding="utf-8") as f:
            f.write(DRIVER)
        # ⚠One file per stub record, never a shared append: concurrent O_APPEND writes are not atomic on Windows.
        self.log = os.path.join(self.d, "calls")
        os.makedirs(self.log)

    def drive(self, scenario, want, deny=False):
        env = dict(os.environ, PI_TEST_LOG=self.log)
        env.pop("PI_TEST_DENY", None)
        if deny:
            env["PI_TEST_DENY"] = "1"
        r = subprocess.run([NODE] + self.args + ["--no-warnings", self.driver, self.ext_url, scenario,
                                                 str(want), self.log],
                           capture_output=True, text=True, encoding="utf-8", timeout=60, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1]), read_dir(self.log)

    def by_script(self, calls):
        return {os.path.relpath(c["argv"][0], self.code): c for c in calls}

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

    def _with_rev(self, rev):
        with open(self.ext, encoding="utf-8") as f:
            src = f.read()
        self.assertEqual(src.count('"<SIDEREUS_REV>"'), 1)
        with open(self.ext, "w", encoding="utf-8") as f:
            f.write(src.replace('"<SIDEREUS_REV>"', json.dumps(rev)))

    def test_r1_rendered_rev_rides_on_events(self):
        self._with_rev("0123456789ab")
        _out, calls = self.drive("read", 1)
        self.assertEqual(calls[0]["stdin"], {"session_id": "sess-0001", "cwd": "/tmp/proj", "ext_rev": "0123456789ab",
                                             "hook_event_name": "PreToolUse", "tool_name": "read"})

    def test_r1_bad_rev_sends_nothing(self):
        self._with_rev("0123456789AB")   # not 12 lowercase hex: same as an unrendered template
        _out, calls = self.drive("read", 1)
        self.assertNotIn("ext_rev", calls[0]["stdin"])

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
const rows = () => { try { return fs.readdirSync(wlog).filter((x) => x.endsWith(".json")).sort().map((x) => JSON.parse(fs.readFileSync(wlog + "/" + x, "utf8"))); } catch { return []; } };
const until = async (f) => { const t0 = Date.now(); while (!f(rows()) && Date.now() - t0 < 8000) await new Promise((r) => setTimeout(r, 20)); };
const n = (k) => (r) => r.filter((x) => k in x).length;
const pause = (ms) => new Promise((r) => setTimeout(r, ms));
if (scenario === "wake") {
  await handlers.session_start({ reason: "startup" }, ctx);
  // ⚠Busy: wait for the quiet re-arm's spawn record too, or shutdown kills it before it starts (slow CI).
  await until((r) => n("ack")(r) >= 1 && (busy !== "1" || n("spawn")(r) >= 2));
} else if (scenario === "cap") {
  await handlers.session_start({ reason: "startup" }, ctx);
  await until((r) => n("ack")(r) >= 1);
  await handlers.agent_settled({}, ctx);
  await until((r) => n("ack")(r) >= 2);
  await handlers.input({ source: "interactive", text: "x" }, ctx);
  await handlers.agent_settled({}, ctx);
  await until((r) => n("ack")(r) >= 3);
} else if (scenario === "settle") {
  await handlers.session_start({ reason: "startup" }, ctx);
  await until((r) => n("ack")(r) >= 1 && n("spawn")(r) >= 2);
  await handlers.agent_settled({}, ctx);
  await until((r) => n("spawn")(r) >= 3);
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
        self.wlog = os.path.join(self.d, "wake")
        os.makedirs(self.wlog)

    def wake(self, scenario, mode="block", busy=False, cap=None, quiet_delay=0):
        env = dict(os.environ, PI_TEST_LOG=self.log, PI_TEST_WLOG=self.wlog, PI_TEST_WAKE=mode,
                   PI_TEST_QUIET_DELAY=str(quiet_delay))
        env.pop("SIDEREUS_MAIL_WAIT_MAX", None)
        if cap is not None:
            env["SIDEREUS_MAIL_WAIT_MAX"] = str(cap)
        r = subprocess.run([NODE] + self.args + ["--no-warnings", self.wdriver, self.ext_url, scenario,
                                                 self.wlog, "1" if busy else "0"],
                           capture_output=True, text=True, encoding="utf-8", timeout=60, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])["sends"], read_dir(self.wlog)

    def test_R1_idle_wake_sends_once_and_acks_ok(self):
        sends, rows = self.wake("wake", "wake")
        self.assertEqual(sends, ["[mailbox] 1 new mail for `p-pi` — from: zed(DM)."])
        self.assertEqual([x["ack"] for x in rows if "ack" in x], ["ok"])
        self.assertEqual(rows[0]["argv"], ["sess-0001", "/tmp/proj"])   # ids and paths only

    def test_R4_busy_no_send_acks_no(self):
        sends, rows = self.wake("wake", "wake", busy=True)
        self.assertEqual(sends, [])
        self.assertEqual([x["ack"] for x in rows if "ack" in x], ["no"])

    def test_R4_refused_wake_rearms_quiet(self):
        # ⚠An idle session never fires agent_settled: after "no" a quiet waiter must keep the heartbeat.
        _, rows = self.wake("wake", "wake", busy=True)
        spawns = [x for x in rows if "spawn" in x]
        self.assertEqual([x["argv"] for x in spawns], [["sess-0001", "/tmp/proj"],
                                                       ["sess-0001", "/tmp/proj", "quiet"]])

    def test_R4_refused_wake_rearms_quiet_slow_start(self):
        # A quiet waiter slower to start than the driver's fixed pause is still recorded before shutdown.
        _, rows = self.wake("wake", "wake", busy=True, quiet_delay=0.5)
        self.assertEqual([x["argv"] for x in rows if "spawn" in x], [["sess-0001", "/tmp/proj"],
                                                                     ["sess-0001", "/tmp/proj", "quiet"]])

    def test_agent_settled_replaces_quiet_waiter(self):
        _, rows = self.wake("settle", "wake", busy=True)
        spawns = [x["argv"] for x in rows if "spawn" in x]
        self.assertGreaterEqual(len(spawns), 3)
        self.assertEqual(spawns[1][2:], ["quiet"])
        self.assertEqual(spawns[2], ["sess-0001", "/tmp/proj"])   # normal again: the refused mail is offered at turn end

    def test_R4_before_agent_start_kills_waiter(self):
        sends, rows = self.wake("kill")
        self.assertEqual(sends, [])
        ends = len([x for x in rows if "end" in x])
        if os.name == "nt":   # ⚠kill() is TerminateProcess there: the stub's SIGTERM handler never runs
            self.assertIn(ends, (0, 1))
        else:
            self.assertEqual(ends, 1)

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
        shutil.rmtree(self.wlog)
        os.makedirs(self.wlog)
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
