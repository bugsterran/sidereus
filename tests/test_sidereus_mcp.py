"""mcp/sidereus_mcp.py — JSON-RPC handshake, tool list, tool calls over mocked HTTP, Sidereus-down path."""
import importlib.util
import io
import json
import os
import unittest

_P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mcp", "sidereus_mcp.py")
_spec = importlib.util.spec_from_file_location("sidereus_mcp", _P)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)
SECRET = "SECRET-CONVERSATION-TEXT"

REPLIES = {
    "/api/agent/quota": {"ok": True, "age": 5, "fiveHour": {"pct": 55.0, "leftSec": 7000},
                         "sevenDay": {"pct": 38.0, "leftSec": 90000}, "used5Tok": 27_000_000, "emptyAt": None,
                         "saver": {"on": False, "why": "auto"},
                         "pace": {"lv": 1, "name": "빠름", "earlyMin": 29, "goal": 100, "rec": 1},
                         "advice": "slow down — burning faster than the goal"},
    "/api/agent/peers": {"ok": True, "repo": "/r", "n": 1, "peers": [
        {"sid8": "aaaaaaaa", "project": "r", "branch": "main", "sameWorktree": True, "state": "tool", "tool": "Edit",
         "ctxPct": 25, "ageSec": 5, "subagents": [{"type": "general-purpose", "idle": False}]}]},
    "/api/agent/file": {"ok": True, "path": "/r/a.py", "uncommitted": True, "windowMin": 30, "n": 2, "liveN": 2,
                        "editors": [{"sid8": "aaaaaaaa", "unit": "main", "agent": "main", "project": "r",
                                     "agoSec": 60, "live": True},
                                    {"sid8": "cccccccc", "unit": "bbbbbbbb", "agent": "general-purpose",
                                     "project": "r", "agoSec": 90, "live": True}]},
    "/api/agent/attention": {"ok": True, "rows": [{"sid8": "aaaaaaaa", "project": "r", "branch": "main",
                                                   "why": "질문 대기", "score": 90}]},
}


class Base(unittest.TestCase):
    def setUp(self):
        self.calls = []
        old = m._get

        def fake(path, params=None):
            self.calls.append((path, params))
            return REPLIES[path]
        m._get = fake
        self.addCleanup(setattr, m, "_get", old)
        env = os.environ.pop("CLAUDE_CONFIG_DIR", None)   # the runner's own account must not leak into calls
        if env is not None:
            self.addCleanup(os.environ.__setitem__, "CLAUDE_CONFIG_DIR", env)

    def rpc(self, *msgs):
        out = io.StringIO()
        m.serve(io.StringIO("".join(json.dumps(x) + "\n" for x in msgs)), out)
        return [json.loads(l) for l in out.getvalue().splitlines()]


class TestProtocol(Base):
    def test_handshake_echoes_supported_version(self):
        r = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                      "params": {"protocolVersion": "2025-06-18", "capabilities": {}}},
                     {"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual(len(r), 1)          # notification gets no reply
        self.assertEqual(r[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("tools", r[0]["result"]["capabilities"])

    def test_unknown_version_gets_latest(self):
        r = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}})
        self.assertEqual(r[0]["result"]["protocolVersion"], m.PROTOCOLS[0])

    def test_tools_list_schema(self):
        r = self.rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = {t["name"]: t for t in r[0]["result"]["tools"]}
        self.assertEqual(set(tools), {"sidereus_quota", "sidereus_file_peers", "sidereus_peers", "sidereus_attention"})
        for t in tools.values():
            self.assertEqual(t["inputSchema"]["type"], "object")
            self.assertTrue(t["description"])
        self.assertEqual(tools["sidereus_file_peers"]["inputSchema"]["required"], ["path"])

    def test_bad_json_and_unknown_method(self):
        out = io.StringIO()
        m.serve(io.StringIO("{nope\n" + json.dumps({"jsonrpc": "2.0", "id": 3, "method": "x/y"}) + "\n"), out)
        r = [json.loads(l) for l in out.getvalue().splitlines()]
        self.assertEqual(r[0]["error"]["code"], -32700)
        self.assertEqual(r[1]["error"]["code"], -32601)


class TestTools(Base):
    def call(self, name, args=None):
        r = self.rpc({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": name, "arguments": args or {}}})
        return r[0]["result"]

    def test_quota_null_pct_prints_question_mark(self):
        out = m.fmt_quota({"fiveHour": {"pct": None}, "sevenDay": {"pct": None}})
        self.assertNotIn("None", out)
        self.assertIn("5h: ?% used", out)
        self.assertIn("7d: ?% used", out)

    def test_quota(self):
        res = self.call("sidereus_quota")
        t = res["content"][0]["text"]
        self.assertFalse(res["isError"])
        self.assertIn("5h: 55.0% used", t)
        self.assertIn("advice: slow down", t)
        self.assertLessEqual(len(t.splitlines()), 15)

    def _env(self, val):
        old = os.environ.get("CLAUDE_CONFIG_DIR")
        if val is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = val
        self.addCleanup(lambda: os.environ.__setitem__("CLAUDE_CONFIG_DIR", old) if old is not None
                        else os.environ.pop("CLAUDE_CONFIG_DIR", None))

    def test_quota_extra_account_sends_dir(self):
        self._env("/tmp/acct b/.claude-work")  # nosec B108 -- fake path, never touched
        self.call("sidereus_quota")
        self.assertEqual(self.calls[-1], ("/api/agent/quota", {"dir": "/tmp/acct b/.claude-work"}))  # nosec B108 -- fake path, never touched

    def test_quota_default_account_sends_no_param(self):
        base = self.call("sidereus_quota")["content"][0]["text"]
        for val in (None, os.path.expanduser("~/.claude"), "~/.claude"):
            self._env(val)
            t = self.call("sidereus_quota")["content"][0]["text"]
            self.assertEqual(self.calls[-1], ("/api/agent/quota", None))
            self.assertEqual(t, base)
            self.assertNotIn("account:", t)

    def test_quota_account_line_and_null_tokens(self):
        out = m.fmt_quota({"ok": True, "acct": "work", "used5Tok": None,
                           "fiveHour": {"pct": 10}, "sevenDay": {"pct": 5}})
        self.assertEqual(out.splitlines()[0], "account: work")
        self.assertIn("? tokens used", out)
        self.assertNotIn("None", out)

    def test_quota_primary_unmeasured_keeps_old_output(self):
        out = m.fmt_quota({"ok": False, "fiveHour": {"pct": None}, "sevenDay": {"pct": None}})
        self.assertEqual(out.splitlines()[0], "5h: ?% used · ? tokens used on this PC · resets in ?")
        self.assertIn("pace: no verdict", out)
        self.assertIn("advice: ok", out)
        self.assertNotIn("unavailable", out)

    def test_quota_unknown_account_no_fallback(self):
        REPLIES_OLD = REPLIES["/api/agent/quota"]
        REPLIES["/api/agent/quota"] = {"ok": False, "err": "unknown account"}
        self.addCleanup(REPLIES.__setitem__, "/api/agent/quota", REPLIES_OLD)
        self._env("/tmp/nope")  # nosec B108 -- fake path, never touched
        res = self.call("sidereus_quota")
        t = res["content"][0]["text"]
        self.assertTrue(res["isError"])
        self.assertEqual(t, "quota unavailable: unknown account")
        self.assertNotIn("5h:", t)

    def test_peers_passes_cwd(self):
        res = self.call("sidereus_peers", {"cwd": "/r"})
        self.assertIn("aaaaaaaa r@main", res["content"][0]["text"])
        self.assertEqual(self.calls[-1], ("/api/agent/peers", {"cwd": "/r"}))

    def test_peers_outside_git_is_a_note_not_error(self):
        old = REPLIES["/api/agent/peers"]
        REPLIES["/api/agent/peers"] = {"ok": True, "repo": "", "peers": [], "n": 0, "note": "not a git repo (/z) — x"}
        self.addCleanup(REPLIES.__setitem__, "/api/agent/peers", old)
        res = self.call("sidereus_peers", {"cwd": "/z"})
        self.assertFalse(res["isError"])
        self.assertEqual(res["content"][0]["text"], "not a git repo (/z) — x")

    def test_file_peers_warns_on_two_live(self):
        t = self.call("sidereus_file_peers", {"path": "a.py", "cwd": "/r"})["content"][0]["text"]
        self.assertIn("uncommitted", t)
        self.assertIn("warning", t)

    def raw(self, params):
        return self.rpc({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": params})[0]

    def test_file_peers_requires_path(self):
        self.assertEqual(self.raw({"name": "sidereus_file_peers", "arguments": {}})["error"]["code"], -32602)
        self.assertTrue(self.call("sidereus_file_peers", {"path": ""})["isError"])

    def test_schema_enforced(self):
        for p in ({"name": "sidereus_file_peers", "arguments": {"path": 123}},
                  {"name": "sidereus_peers", "arguments": {"cwd": ["a"]}},
                  {"name": "sidereus_quota", "arguments": {"bogus": 1}},
                  {"name": "sidereus_quota", "arguments": "x"}):
            self.assertEqual(self.raw(p)["error"]["code"], -32602, p)
        self.assertEqual(self.raw("x")["error"]["code"], -32602)
        self.assertEqual(self.calls, [])          # nothing reached the viewer

    def test_missing_file_is_not_clean(self):
        old = dict(REPLIES["/api/agent/file"])
        REPLIES["/api/agent/file"].update({"uncommitted": False, "exists": False})
        self.addCleanup(REPLIES["/api/agent/file"].update, old)
        t = self.call("sidereus_file_peers", {"path": "nope.py", "cwd": "/r"})["content"][0]["text"]
        self.assertIn("no such file", t)
        self.assertNotIn("clean", t)

    def test_attention(self):
        self.assertIn("질문 대기", self.call("sidereus_attention")["content"][0]["text"])

    def test_no_text_fields_leak(self):
        for p in REPLIES.values():          # a server reply carrying stray text fields must not surface them
            p["task"] = p["reply"] = SECRET
        try:
            for n, a in (("sidereus_quota", {}), ("sidereus_peers", {}), ("sidereus_file_peers", {"path": "/r/a.py"}),
                         ("sidereus_attention", {})):
                self.assertNotIn(SECRET, self.call(n, a)["content"][0]["text"])
        finally:
            for p in REPLIES.values():
                p.pop("task", None)
                p.pop("reply", None)


class TestDown(unittest.TestCase):
    def test_sidereus_down_is_tool_error_not_crash(self):
        old = m.urllib.request.urlopen

        def refused(*a, **k):
            raise m.urllib.error.URLError(ConnectionRefusedError(61, "refused"))
        m.urllib.request.urlopen = refused
        self.addCleanup(setattr, m.urllib.request, "urlopen", old)
        old_label = m.launchd_label             # ⚠never resolve against the live config.local.json
        m.launchd_label = lambda: "io.sidereus.viewer"
        self.addCleanup(setattr, m, "launchd_label", old_label)
        old_pl, old_pp = m.PLATFORM, m._plist_path   # ⚠never look at the live ~/Library/LaunchAgents
        self.addCleanup(setattr, m, "PLATFORM", old_pl)
        self.addCleanup(setattr, m, "_plist_path", old_pp)

        def text():
            out = io.StringIO()
            m.serve(io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                            "params": {"name": "sidereus_quota", "arguments": {}}}) + "\n"), out)
            res = json.loads(out.getvalue())["result"]
            self.assertTrue(res["isError"])
            return res["content"][0]["text"]
        m.PLATFORM, m._plist_path = "darwin", lambda label: _P   # an existing file stands in for the plist
        t = text()
        self.assertIn("not reachable", t)
        self.assertIn("python3 -m sidereus start", t)
        self.assertIn("/io.sidereus.viewer", t)
        m._plist_path = lambda label: _P + ".missing"
        self.assertNotIn("launchctl", text())
        m.PLATFORM, m._plist_path = "win32", lambda label: _P
        t = text()
        self.assertIn("python3 -m sidereus start", t)
        self.assertNotIn("launchctl", t)


if __name__ == "__main__":
    unittest.main()
