"""pi `-p --no-session` subagent child tokens: extension `Usage` event -> ext_hook allow-list -> child-only store -> gms."""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from datetime import datetime
from unittest import mock

import tests._load  # noqa: F401  (sets SIDEREUS_HOOK_NO_PID before the hook runs)
from tests._load import sidereus
from tests.test_pi_child_hook import ENV_KEYS, NODE, SRC, STUB, harness, hook, read_log

ext = sidereus("ext")
st = sidereus("ext_store")   # owner of _ext / _runs / _hooktok / EXT_HOOKTOK_FILE
PI = ext.PLAT_MODS["pi"]

PAR = "0199aaaa-bbbb-7ccc-8ddd-0000000000p1"
KID = "0199aaaa-bbbb-7ccc-8ddd-0000000000k1"
CWD = "/w/pi-proj"
SECRET = "SECRET-PI-ANSWER-TEXT"


class ExtHookUsage(unittest.TestCase):
    def setUp(self):
        for name, val in (("parent_sid", lambda env=None: PAR), ("cli_pid_ex", lambda: (0, "", "")),
                          ("time", types.SimpleNamespace(time=lambda: 1790000000.0))):
            p = mock.patch.object(hook, name, val)
            p.start()
            self.addCleanup(p.stop)

    def build(self, event="Usage", **kw):
        d = {"hook_event_name": event, "session_id": KID, "cwd": CWD, "generation_id": "g-1", "model": "m1",
             "input_tokens": 100, "output_tokens": 20, "cache_read_tokens": 300, "cache_write_tokens": 4,
             "content": SECRET}
        d.update(kw)
        return hook.build("pi", d)[0]

    def test_usage_forwarded(self):
        out = self.build()
        self.assertEqual(out["event"], "Usage")
        self.assertEqual(out["usage"], {"in": 100, "out": 20, "cr": 300, "cw": 4})
        self.assertEqual((out["gen_id"], out["parent"], out["model"]), ("g-1", PAR, "m1"))
        self.assertNotIn(SECRET, json.dumps(out))

    def test_invalid_usage_and_gen_dropped(self):
        out = self.build(input_tokens=-1, output_tokens=True, cache_read_tokens="5", cache_write_tokens=10 ** 9,
                         generation_id="bad id/../x")
        self.assertNotIn("usage", out)
        self.assertNotIn("gen_id", out)

    def test_other_pi_events_carry_no_usage(self):
        self.assertNotIn("usage", self.build(event="Stop"))
        self.assertIsNone(hook.build("gemini", {"hook_event_name": "Usage", "session_id": KID})[0])


class ChildTokStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.now = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0).timestamp()
        clock = mock.Mock()
        clock.time = lambda: self.now
        self.saved = (dict(st._ext), dict(st._runs), dict(st._tok), dict(st._hooktok), dict(st._ext_ended))
        for p in (mock.patch.object(st, "time", clock),
                  mock.patch.object(st, "EXT_HOOKTOK_FILE", os.path.join(self.tmp, "ext-hooktok.json")),
                  mock.patch.object(st, "EXT_RUNS_FILE", os.path.join(self.tmp, "ext-runs.json")),
                  mock.patch.object(st, "_ext_save_locked", lambda: None),
                  mock.patch.object(PI, "session_msgs", lambda path: None),
                  mock.patch.object(ext, "adapter_scan", lambda mod, since: []),
                  mock.patch.object(st.plat_copilot, "msgs_since", lambda since=0.0: {})):
            p.start()
            self.addCleanup(p.stop)
        for d in (st._ext, st._runs, st._tok, st._hooktok, st._ext_ended):
            d.clear()

    def tearDown(self):
        for d, v in zip((st._ext, st._runs, st._tok, st._hooktok, st._ext_ended), self.saved):
            d.clear(); d.update(v)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def feed(self, ev, sid=KID, **kw):
        req = {"platform": "pi", "session_id": sid, "event": ev, "cwd": CWD, "ts": self.now - 30}
        req.update(kw)
        return st.ext_ingest(req)

    def usage(self, gen, sid=KID, **kw):
        return self.feed("Usage", sid=sid, gen_id=gen, model="m1", usage={"in": 100, "out": 20, "cr": 300, "cw": 4}, **kw)

    def gms(self):
        rows = [{"sid": PAR}]
        ext.ext_children(rows, now=self.now)
        return rows[0].get("gms") or []

    def test_child_usage_reaches_gms_once(self):
        self.feed("SessionStart", sid=PAR)
        self.feed("SessionStart", parent=PAR, agent_name="scout")
        self.feed("PreToolUse", parent=PAR, tool_name="read")
        self.assertEqual(self.gms()[0]["tok"], 0)                 # nothing sent yet
        self.assertEqual(self.usage("g-1", parent=PAR), (True, "usage"))
        self.assertEqual(st._ext[("pi", KID)]["state"], "tool")   # Usage never flips row state
        self.usage("g-1", parent=PAR)                             # repeated generation: counted once
        self.usage("g-2", parent=PAR)
        g = self.gms()[0]
        self.assertEqual((g["tok"], g["model"]), (848, "m1"))
        u = ext.ext_usage_today(now=self.now)["pi"]
        self.assertEqual((u["tok"], u["n_sessions"]), (848, 0))   # a subagent child is not a session
        self.feed("SessionEnd")
        self.assertEqual(st._runs[KID]["tok"], 848)               # timeline keeps it after the run ends

    def test_parent_or_orphan_usage_refused(self):
        self.feed("SessionStart", sid=PAR)
        self.assertEqual(self.usage("g-1", sid=PAR), (False, "usage refused"))          # parent reads its file
        self.assertEqual(self.usage("g-1", sid=PAR, parent=KID)[0], False)             # no row with that parent
        self.feed("SessionStart", parent="claude-sess-1")                               # Claude-parented pi has a file
        self.assertEqual(self.usage("g-1", parent="claude-sess-1")[0], False)
        self.assertEqual(st._hooktok, {})


@unittest.skipUnless(NODE, "node not installed")
class ExtensionSendsUsage(unittest.TestCase):
    DRIVER = r'''
const [ext, log, want] = process.argv.slice(2, 5);
const fs = await import("node:fs");
const mod = await import(ext);
const handlers = {};
mod.default({ on: (n, f) => { handlers[n] = f; }, sendUserMessage: () => {} });
const ctx = { cwd: "/tmp/proj", sessionManager: { getSessionId: () => "sess-0001" },
              isIdle: () => true, hasPendingMessages: () => false };
const usage = { input: 100, output: 20, cacheRead: 300, cacheWrite: 4, totalTokens: 424 };
await handlers.message_end({ message: { role: "user", content: "SECRET-Q", usage } }, ctx);
await handlers.message_end({ message: { role: "assistant", content: [{ type: "text", text: "SECRET-A" }],
                                        model: "m1", responseId: "resp_1", usage } }, ctx);
await handlers.message_end({ message: { role: "assistant", content: "SECRET-B", usage } }, ctx);
const n = () => { try { return fs.readdirSync(log).filter((x) => x.endsWith(".json")).length; } catch { return 0; } };
const t0 = Date.now();
while (n() < Number(want) && Date.now() - t0 < 8000) await new Promise((r) => setTimeout(r, 20));
await new Promise((r) => setTimeout(r, 300));
'''

    def setUp(self):
        self.args = harness._node_args()
        if self.args is None:
            self.skipTest("node cannot strip TypeScript types")
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        code = os.path.join(self.d, "code")
        for n in ("ext-hooks/ext_hook.py", "ext-hooks/pi_wake.py", "hooks/pl_mark.py", "hooks/pl_flow.py",
                  "hooks/invite_notice.py", "hooks/pipelines_brief.py"):
            dst = os.path.join(code, *n.split("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "w", encoding="utf-8") as f:
                f.write(STUB)
        with open(SRC, encoding="utf-8") as f:
            src = f.read()
        e = os.path.join(self.d, "ext.ts")
        with open(e, "w", encoding="utf-8") as f:
            f.write(src.replace('"<PYTHON>"', json.dumps(sys.executable))
                    .replace('"<MAILBOX_CODE_DIR>"', json.dumps(code)))
        self.ext_url = pathlib.Path(e).as_uri()
        self.driver = os.path.join(self.d, "driver.mjs")
        with open(self.driver, "w", encoding="utf-8") as f:
            f.write(self.DRIVER)
        self.log = os.path.join(self.d, "calls")

    def drive(self, env, want):
        e = dict(os.environ, PI_TEST_LOG=self.log)
        for k in ENV_KEYS + ("CLAUDE_CODE_SESSION_ID",):
            e.pop(k, None)
        e.update(env)
        r = subprocess.run([NODE] + self.args + ["--no-warnings", self.driver, self.ext_url, self.log, str(want)],
                           capture_output=True, text=True, encoding="utf-8", timeout=60, env=e)
        self.assertEqual(r.returncode, 0, r.stderr)
        return read_log(self.log)

    def test_child_sends_counts_only(self):
        calls = self.drive({"SIDEREUS_PARENT_SID": "parent-1", "SIDEREUS_PARENT_PLAT": "pi"}, 2)
        got = [c["stdin"] for c in calls]
        self.assertEqual([c["hook_event_name"] for c in got], ["Usage", "Usage"])   # assistant messages only
        self.assertEqual(got[0]["generation_id"], "resp_1")
        self.assertRegex(got[1]["generation_id"], r"^[0-9a-z]+-1$")
        for c in got:
            self.assertEqual((c["input_tokens"], c["output_tokens"], c["cache_read_tokens"], c["cache_write_tokens"]),
                             (100, 20, 300, 4))
        self.assertEqual(got[0]["model"], "m1")
        self.assertNotIn("SECRET", json.dumps(calls))

    def test_non_child_sends_nothing(self):
        self.assertEqual(self.drive({}, 0), [])


if __name__ == "__main__":
    unittest.main()
