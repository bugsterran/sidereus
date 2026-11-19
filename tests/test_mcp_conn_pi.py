"""pi MCP records for the «Connections» view: ext_store per-server counts from the pi extension hook events
(sidereus/ext_store.py `_mcp_note`/`ext_mcp`) read by sidereus/mcp_conn.py `_pi`. Temp pi root, no live store writes."""
import json
import os
import shutil
import tempfile
import time
import types
import unittest

from tests._load import load, sidereus

load()
MC = sidereus("mcp_conn")
ST = sidereus("ext_store")
PP = sidereus("plat_pi")
NOW = 1_800_000_000.0
SID = "01a1e376-e208-7556-b827-2f15b57f95f6"
SECRET = "SECRET-PAYLOAD-never-kept"


class PiMcp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-mcpi-")
        os.makedirs(os.path.join(self.tmp, "pi"))
        with open(os.path.join(self.tmp, "pi", "mcp.json"), "w") as f:
            json.dump({"mcpServers": {"mailbox": {"command": "x", "env": {"K": SECRET}}, "docs": {"url": "u"}}}, f)
        self.saved = [(ST, "_ext_save_locked", ST._ext_save_locked), (ST, "_runs_save_locked", ST._runs_save_locked),
                      (PP, "root", PP.root), (MC, "sessions_rows", MC.sessions_rows), (MC, "_now", MC._now),
                      (ST, "time", ST.time)]
        ST.time = types.SimpleNamespace(**dict(vars(time), time=lambda: NOW))   # ingest clamps future ts to its clock
        self.ext = dict(ST._ext)
        ST._ext.clear()
        ST._ext_save_locked = ST._runs_save_locked = lambda: None
        PP.root = lambda: os.path.join(self.tmp, "pi")
        MC.sessions_rows = lambda: [{"sid": SID, "plat": "pi", "cwd": self.tmp}]
        MC._now = lambda: NOW
        MC._MC_CACHE["body"].clear()

    def tearDown(self):
        for mod, k, v in self.saved:
            setattr(mod, k, v)
        ST._ext.clear()
        ST._ext.update(self.ext)
        MC._MC_CACHE["body"].clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def feed(self, ev, ts, **kw):
        req = {"platform": "pi", "session_id": SID, "event": ev, "cwd": self.tmp, "ts": ts}
        req.update(kw)
        return ST.ext_ingest(req)

    def conn(self):
        MC._MC_CACHE["body"].clear()
        b = MC.conn(SID)
        return b, dict((s["name"], s) for s in b["servers"])

    def test_counts_and_state_from_extension_events(self):
        t = NOW - 100
        self.feed("SessionStart", t)
        self.feed("PreToolUse", t + 1, tool_name="codemode")
        self.feed("PreToolUse", t + 2, tool_name="mcp__mailbox__mailbox_send", tool_input={"x": SECRET})
        self.feed("PostToolUse", t + 3, tool_name="mcp__mailbox__mailbox_send", is_error=False)
        self.feed("PreToolUse", t + 4, tool_name="mcp__mailbox__mailbox_inbox")
        self.feed("PreToolUse", t + 5, tool_name="mcp__other_srv__do_it")
        self.feed("PostToolUse", t + 6, tool_name="mcp__other_srv__do_it", is_error=True)
        b, by = self.conn()
        self.assertEqual((b["counts"], b["since"]), (True, 0))
        self.assertEqual((by["mailbox"]["state"], by["mailbox"]["n"], by["mailbox"]["last"]), ("ok", 2, int(t + 4)))
        self.assertEqual((by["docs"]["state"], by["docs"]["n"]), ("unknown", 0))           # configured, never called
        self.assertEqual((by["other_srv"]["scope"], by["other_srv"]["state"], by["other_srv"]["n"]), ("seen", "fail", 1))
        self.assertEqual(by["other_srv"]["err"], "")
        self.assertNotIn(SECRET, json.dumps(b) + json.dumps(list(ST._ext.values())))

    def test_older_extension_without_flag_stays_unknown(self):
        self.feed("SessionStart", NOW - 50)
        self.feed("PreToolUse", NOW - 49, tool_name="mcp__mailbox__mailbox_ack")
        self.feed("PostToolUse", NOW - 48, tool_name="mcp__mailbox__mailbox_ack")
        self.feed("PostToolUse", NOW - 47, tool_name="mcp__mailbox__mailbox_ack", is_error="yes")   # not a bool
        _, by = self.conn()
        self.assertEqual((by["mailbox"]["state"], by["mailbox"]["n"]), ("unknown", 1))

    def test_record_from_before_counting_is_partial(self):
        ST._ext[("pi", SID)] = {"firstSeen": NOW - 500, "lastSeen": NOW - 400, "cwd": self.tmp, "state": "wait"}   # stored by an older viewer
        self.feed("PreToolUse", NOW - 10, tool_name="mcp__mailbox__mailbox_send")
        b, by = self.conn()
        self.assertEqual((b["counts"], b["since"]), (True, int(NOW - 10)))     # counted since then, not since start
        self.assertEqual((by["mailbox"]["n"], by["mailbox"]["last"]), (1, int(NOW - 10)))

    def test_hookless_row_has_no_counts(self):
        b, by = self.conn()
        self.assertEqual((b["counts"], b["since"], by["mailbox"]["state"], by["mailbox"]["n"]), (False, 0, "unknown", None))

    def test_server_cap(self):
        self.feed("SessionStart", NOW - 300)
        for i in range(ST.EXT_MCP_N + 5):
            self.feed("PreToolUse", NOW - 200 + i, tool_name="mcp__s%d__t" % i)
        self.assertEqual(len(ST.ext_mcp("pi", SID)[0]), ST.EXT_MCP_N)

    def test_ext_hook_forwards_bool_only(self):
        import importlib.util
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ext-hooks", "ext_hook.py")
        spec = importlib.util.spec_from_file_location("ext_hook_t", p)
        eh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(eh)
        eh.cli_pid_ex, eh.parent_sid = (lambda: (None, "", "")), (lambda env=None: "")
        base = {"hook_event_name": "PostToolUse", "session_id": SID, "tool_name": "mcp__a__b"}
        self.assertIs(eh.build("pi", dict(base, is_error=True))[0]["is_error"], True)
        self.assertNotIn("is_error", eh.build("pi", dict(base, is_error="1"))[0])
        self.assertNotIn("result", eh.build("pi", dict(base, is_error=False, result=SECRET))[0])


if __name__ == "__main__":
    unittest.main()
