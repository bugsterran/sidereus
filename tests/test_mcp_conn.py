"""Token tab «Connections» data (sidereus/mcp_conn.py): per-session MCP nodes and states for cc / Codex / pi.
Every root is a temp dir and every reader is patched on its owner module (never the live ~/.claude, ~/.codex or ~/.pi)."""
import ast
import json
import os
import shutil
import tempfile
import unittest

from tests._load import load, sidereus

load()
MC = sidereus("mcp_conn")
TI = sidereus("toolidx")
TV = sidereus("toolinv")
CX = sidereus("ctxsrc")
PC = sidereus("plat_codex")
PP = sidereus("plat_pi")
H = sidereus("harness")
NOW = 1_800_000_000.0
SECRET = "SECRET-PAYLOAD-never-kept"
S1, S2 = "11111111-aaaa-4bbb-8ccc-000000000001", "22222222-aaaa-4bbb-8ccc-000000000002"
CXS = "019a0000-0000-7000-8000-00000000c0de"


def _iso(ts):
    import datetime
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _tu(tid, name, ts):
    return {"type": "assistant", "timestamp": _iso(ts),
            "message": {"content": [{"type": "tool_use", "id": tid, "name": name, "input": {"q": SECRET}}]}}


def _delta(ts, added=(), failed=()):
    return {"type": "attachment", "uuid": "d%d" % ts, "timestamp": _iso(ts),
            "attachment": {"type": "deferred_tools_delta", "addedNames": list(added),
                           "failedMcpServers": [dict(f, error=SECRET) for f in failed]}}


def _w(p, data):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        if isinstance(data, list):
            f.write("".join(json.dumps(r) + "\n" for r in data))
        elif isinstance(data, dict):
            json.dump(data, f)
        else:
            f.write(data)
    os.utime(p, (NOW - 60, NOW - 60))


class McpConnTest(unittest.TestCase):
    def setUp(self):
        t = self.tmp = tempfile.mkdtemp(prefix="sidereus-mc-")
        self.cwd, self.other = os.path.join(t, "repo"), os.path.join(t, "other")
        os.makedirs(self.cwd)
        os.makedirs(self.other)
        cd, plug = os.path.join(t, "claude"), os.path.join(t, "claude", "plugins", "cache", "mk", "browser", "1.0.0")
        _w(os.path.join(plug, ".mcp.json"), {"mcpServers": {"browser": {"command": "x"}}})
        _w(os.path.join(cd, "plugins", "installed_plugins.json"), {"plugins": {"browser@mk": [{"installPath": plug}]}})
        _w(os.path.join(cd, "settings.json"), {"enabledPlugins": {"browser@mk": True}})
        _w(os.path.join(t, "cj.json"), {"mcpServers": {"docs": {"command": "npx", "env": {"API_KEY": SECRET}}},
                                        "projects": {self.cwd: {"mcpServers": {"tracker": {"type": "http", "url": SECRET}}},
                                                     self.other: {"mcpServers": {"elsewhere": {"command": "y"}}}}})
        self.rows = [{"sid": S1, "plat": "cc", "cwd": self.cwd}, {"sid": S2, "plat": "cc", "cwd": self.cwd},
                     {"sid": CXS, "plat": "cx", "cwd": self.cwd}, {"sid": "pi-1", "plat": "pi", "cwd": self.cwd},
                     {"sid": "gm-1", "plat": "gm", "cwd": self.cwd}]
        self.saved = [(CX, "CLAUDE_DIR", CX.CLAUDE_DIR), (CX, "CLAUDE_JSON", CX.CLAUDE_JSON), (TV, "_allowed_cwds", TV._allowed_cwds),
                      (TI, "CLAUDE_PROJECTS", TI.CLAUDE_PROJECTS), (TI, "TI_BG", TI.TI_BG), (PC, "root", PC.root), (PP, "root", PP.root),
                      (MC, "sessions_rows", MC.sessions_rows), (MC, "_now", MC._now), (MC, "_git_root", MC._git_root)]
        CX.CLAUDE_DIR, CX.CLAUDE_JSON = cd, os.path.join(t, "cj.json")
        TV._allowed_cwds = lambda: []
        TI.CLAUDE_PROJECTS, TI.TI_BG = os.path.join(t, "projects"), False
        PC.root, PP.root = (lambda: os.path.join(t, "codex")), (lambda: os.path.join(t, "pi"))
        MC.sessions_rows, MC._now, MC._git_root = (lambda: self.rows), (lambda: NOW), (lambda d: "")
        TI.reset()
        self._clear()

    def tearDown(self):
        for mod, k, v in self.saved:
            setattr(mod, k, v)
        TI.reset()
        self._clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def _clear():
        MC._MC_CACHE["body"].clear()
        MC._MC_CACHE["cx"].clear()

    def _tx(self, sid, recs, sub=False):
        d = os.path.join(TI.CLAUDE_PROJECTS, "-repo")
        _w(os.path.join(d, sid, "subagents", "agent-a.jsonl") if sub else os.path.join(d, sid + ".jsonl"), recs)

    @staticmethod
    def _by(body):
        return dict((s["name"], s) for s in body["servers"])

    def test_R1_cc_nodes_user_project_plugin_cloud_fold(self):
        d = NOW - 3600
        self._tx(S1, [_tu("t1", "mcp__docs__search", d), _tu("t2", "mcp__claude_ai_Gmail__find", d + 1),
                      _tu("t3", "mcp__adhoc__x", d + 2), _tu("t4", "mcp__plugin_browser_browser__go", d + 3)])
        self._tx(S1, [_tu("t1", "mcp__docs__search", d), _tu("t5", "mcp__docs__search", d + 5)], sub=True)
        b = MC.conn(S1)
        self.assertTrue(b["ok"] and b["supported"] and b["counts"])
        by = self._by(b)
        self.assertEqual(sorted(by), ["adhoc", "browser", "claude_ai_Gmail", "docs", "tracker"])   # `elsewhere` = another cwd
        self.assertEqual([(by[k]["scope"], by[k]["transport"]) for k in ("tracker", "docs", "browser", "claude_ai_Gmail", "adhoc")],
                         [("project", "http"), ("user", "stdio"), ("plugin", "stdio"), ("cloud", ""), ("seen", "")])
        self.assertEqual((by["docs"]["n"], by["docs"]["last"], by["docs"]["state"]), (2, int(d + 5), "ok"))   # t1 twice = once
        self.assertEqual((by["browser"]["plug"], by["browser"]["n"]), ("browser", 1))
        self.assertEqual((by["tracker"]["state"], by["tracker"]["n"]), ("unknown", 0))   # configured, no evidence: never ok
        self.assertEqual(b["totals"], {"ok": 4, "fail": 0, "auth": 0, "unknown": 1})
        self.assertNotIn(SECRET, json.dumps(b))
        self.assertEqual(set(b), {"ok", "now", "sid", "plat", "supported", "counts", "since", "scanning", "checked", "servers", "totals",
                                  "kinds"})
        self.assertEqual(set(b["servers"][0]), {"name", "scope", "plug", "transport", "on", "state", "err", "at", "n", "last"})

    def test_R1_key_forms_match_harness(self):
        it = {"name": "srv-1", "scope": "plugin", "file": "/x/cache/mk/browser/2.0.1/.mcp.json", "entry": {"command": "c"}, "on": True}
        uses = {"mcp:srv-1": {"n": 2, "last": 5}, "mcp:plugin_browser_srv-1": {"n": 3, "last": 9}, "mcp:zz": {"n": 7, "last": 1}}
        hr = H._mcp_rows([it], uses)[0]
        keys = MC._keys(it["name"], MC._plug_name(os.path.dirname(it["file"])))
        self.assertEqual((MC._plug_name(os.path.dirname(it["file"])), sum(uses.get(k, {}).get("n", 0) for k in keys)),
                         (hr["plug"], hr["n"]))
        for p in ("/c/mk/browser/1.0.0", "/c/mk/browser", "", "/c/mk/9lives/1.2"):
            self.assertEqual(MC._plug_name(p), H._plug_name(p))

    def test_dotted_server_calls_counted_under_tool_name_form(self):
        # Tool names carry `a.b` as `a_b`; the config name alone matched no use key, so calls read 0.
        it = {"name": "claude.ai Docs", "scope": "user", "file": "/x/.claude.json", "entry": {"type": "http"}, "on": True}
        uses = {"mcp:claude_ai_Docs": {"n": 4, "last": 7}}
        hr = H._mcp_rows([it], uses)[0]
        self.assertEqual((hr["n"], hr["last"]), (4, 7))
        plain = dict(it, name="docs")   # nothing to sanitize: one key, not counted twice
        self.assertEqual(H._mcp_rows([plain], {"mcp:docs": {"n": 2, "last": 1}})[0]["n"], 2)

    def test_R2_state_per_session_not_global(self):
        d = NOW - 3600
        self._tx(S1, [_tu("a1", "mcp__docs__q", d - 50), _delta(d, failed=[{"name": "docs", "errorCode": "CONNECTION_CLOSED"}])])
        self._tx(S2, [_tu("b1", "mcp__docs__q", d + 100), _tu("b2", "mcp__docs__q", d + 200)])
        TI.tool_uses(30, now=NOW)
        self.assertEqual(TI.mcp_status(30, now=NOW)["mcp:docs"]["status"], "ok")   # the global view says ok
        one, two = self._by(MC.conn(S1))["docs"], self._by(MC.conn(S2))["docs"]
        self.assertEqual((one["state"], one["err"], one["at"], one["n"]), ("fail", "CONNECTION_CLOSED", int(d), 1))
        self.assertEqual((two["state"], two["err"], two["at"], two["n"], two["last"]), ("ok", "", int(d + 200), 2, int(d + 200)))

    def test_R2_fail_code_only_no_error_text(self):
        d = NOW - 3600
        self._tx(S1, [_delta(d, failed=[{"name": "docs", "errorCode": "x " + SECRET}, {"name": "claude.ai Notes", "errorCode": "AUTH_FAILED"}])])
        b = MC.conn(S1)
        by = self._by(b)
        self.assertEqual((by["docs"]["state"], by["docs"]["err"]), ("fail", ""))         # free text in the code slot dropped
        self.assertEqual((by["claude_ai_Notes"]["scope"], by["claude_ai_Notes"]["err"]), ("cloud", "AUTH_FAILED"))
        self.assertNotIn(SECRET, json.dumps(b))
        self.assertNotIn(SECRET, json.dumps(TI._TI_SESS, default=str))

    def test_R2_auth_only_connector(self):
        d = NOW - 3600
        self._tx(S1, [_delta(d, added=["mcp__claude_ai_Drive__authenticate", "mcp__claude_ai_Drive__complete_authentication",
                                       "mcp__claude_ai_Cal__list", "mcp__claude_ai_Cal__authenticate"])])
        self._tx(S2, [_delta(d, added=["mcp__claude_ai_Drive__authenticate"]), _tu("c1", "mcp__claude_ai_Drive__search", d + 9)])
        one = self._by(MC.conn(S1))
        self.assertEqual((one["claude_ai_Drive"]["state"], one["claude_ai_Drive"]["at"], one["claude_ai_Drive"]["scope"]),
                         ("auth", int(d), "cloud"))
        self.assertEqual(one["claude_ai_Cal"]["state"], "ok")            # real tools beside authenticate: connected
        self.assertEqual(self._by(MC.conn(S2))["claude_ai_Drive"]["state"], "ok")   # a later call clears the login prompt

    def test_R2_auth_tool_call_stays_auth(self):
        d = NOW - 3600
        self._tx(S1, [_delta(d, added=["mcp__claude_ai_Drive__authenticate", "mcp__claude_ai_Drive__complete_authentication"]),
                      _tu("a1", "mcp__claude_ai_Drive__authenticate", d + 5), _tu("a2", "mcp__claude_ai_Drive__complete_authentication", d + 9),
                      _tu("a3", "mcp__docs__q", d + 9)])
        b = self._by(MC.conn(S1))
        self.assertEqual((b["claude_ai_Drive"]["state"], b["claude_ai_Drive"]["n"]), ("auth", 0))   # sign-in never finished
        self.assertEqual(b["docs"]["n"], 1)
        u = TI.tool_uses(30, now=NOW)
        self.assertEqual((u["mcpauth:claude_ai_Drive"]["n"], "mcp:claude_ai_Drive" in u, u["mcp:docs"]["n"]), (2, False, 1))

    def _rollout(self, rel, items):
        recs = [{"timestamp": _iso(NOW - 600), "type": "session_meta", "payload": {"id": CXS, "cwd": self.cwd}}]
        for i, (cid, srv, status, ts) in enumerate(items):
            it = {"type": "McpToolCall", "id": cid, "server": srv, "tool": "t", "status": status, "duration": 1,
                  "arguments": {"q": SECRET}}
            it.update({"error": SECRET} if status == "failed" else {"result": {"content": SECRET}})
            recs.append({"timestamp": _iso(ts), "type": "event_msg", "ordinal": i,
                         "payload": {"type": "item_completed", "thread_id": CXS, "turn_id": "t", "item": it}})
        recs.append({"timestamp": _iso(NOW), "type": "event_msg", "payload": {"type": "item_started", "item": {"type": "McpToolCall", "server": "ghost"}}})
        _w(os.path.join(self.tmp, "codex", rel), recs)

    def test_R3_codex_counts_status_from_rollout(self):
        _w(os.path.join(self.tmp, "codex", "config.toml"), '[mcp_servers.docs]\ncommand = "npx"\n\n[mcp_servers.idle]\nurl = "%s"\n' % SECRET)
        _w(os.path.join(self.cwd, ".codex", "config.toml"), '[mcp_servers.local]\ncommand = "x"\n')
        live = "sessions/2026/01/01/rollout-2026-01-01T00-00-00-%s.jsonl" % CXS
        self._rollout(live, [("c1", "docs", "completed", NOW - 500), ("c2", "docs", "completed", NOW - 400),
                             ("c3", "web", "completed", NOW - 300), ("c4", "web", "failed", NOW - 200)])
        self._rollout("archived_sessions/rollout-2026-01-01T00-00-00-%s.jsonl" % CXS, [("c1", "docs", "completed", NOW - 500)])
        b = MC.conn(CXS)
        by = self._by(b)
        self.assertTrue(b["supported"] and b["counts"])
        self.assertEqual((by["docs"]["scope"], by["docs"]["state"], by["docs"]["n"], by["docs"]["last"]), ("user", "ok", 2, int(NOW - 400)))
        self.assertEqual((by["web"]["scope"], by["web"]["state"], by["web"]["err"], by["web"]["n"]), ("seen", "fail", "", 2))
        self.assertEqual((by["idle"]["state"], by["idle"]["n"], by["idle"]["transport"]), ("unknown", 0, "http"))
        self.assertEqual((by["local"]["scope"], by["local"]["state"]), ("project", "unknown"))
        self.assertNotIn("ghost", by)                                        # item_started is not a completion
        # appended tail: read incrementally, cache entry reused
        p = os.path.join(self.tmp, "codex", live)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps({"timestamp": _iso(NOW - 100), "type": "event_msg", "payload": {"type": "item_completed",
                                "item": {"type": "McpToolCall", "id": "c5", "server": "web", "status": "completed"}}}) + "\n")
        self._clear_body()
        w = self._by(MC.conn(CXS))["web"]
        self.assertEqual((w["state"], w["n"]), ("ok", 3))

    def _clear_body(self):
        MC._MC_CACHE["body"].clear()

    def test_R3_codex_no_args_result_error_in_payload(self):
        self._rollout("sessions/2026/01/01/rollout-x-%s.jsonl" % CXS, [("c1", "docs", "completed", NOW - 50), ("c2", "docs", "failed", NOW - 40)])
        b = MC.conn(CXS)
        self.assertEqual(self._by(b)["docs"]["state"], "fail")
        self.assertNotIn(SECRET, json.dumps(b))
        self.assertNotIn(SECRET, json.dumps(MC._MC_CACHE, default=str))

    def test_R3_codex_no_rollout_counts_unknown(self):
        _w(os.path.join(self.tmp, "codex", "config.toml"), '[mcp_servers.docs]\ncommand = "npx"\n')
        b = MC.conn(CXS)
        self.assertEqual((b["counts"], b["servers"][0]["n"], b["servers"][0]["state"]), (False, None, "unknown"))
        self.rows.append({"sid": "../etc", "plat": "cx", "cwd": self.cwd})
        self.assertEqual(MC.conn("../etc")["servers"], [])                    # sid checked before any glob

    def test_R3_pi_names_trusted_project_only_unknown_null(self):
        _w(os.path.join(self.tmp, "pi", "mcp.json"), {"mcpServers": {"docs": {"command": "x", "env": {"K": SECRET}}, "off": {"url": "u", "disabled": True}}})
        _w(os.path.join(self.cwd, ".pi", "mcp.json"), {"mcpServers": {"proj": {"command": "y"}}})
        b = MC.conn("pi-1")
        self.assertEqual((b["supported"], b["counts"], sorted(self._by(b))), (True, False, ["docs", "off"]))   # untrusted folder
        self.assertEqual(set((s["state"], s["n"], s["last"]) for s in b["servers"]), {("unknown", None, None)})
        self.assertFalse(self._by(b)["off"]["on"])
        _w(os.path.join(self.tmp, "pi", "trust.json"), {self.cwd: True, self.other: False})
        self._clear_body()
        b = MC.conn("pi-1")
        self.assertEqual((self._by(b)["proj"]["scope"], b["totals"]["unknown"]), ("project", 3))
        _w(os.path.join(self.tmp, "pi", "trust.json"), {self.cwd: False})
        self._clear_body()
        self.assertNotIn("proj", self._by(MC.conn("pi-1")))
        self.assertNotIn(SECRET, json.dumps(b))

    def test_other_cli_unsupported(self):
        b = MC.conn("gm-1")
        self.assertEqual((b["ok"], b["supported"], b["servers"], b["counts"]), (True, False, [], False))

    def test_nongoal_no_spawn_imports(self):
        bad = {"subprocess", "socket", "pty", "multiprocessing", "asyncio", "http", "urllib"}
        for mod in (MC, sidereus("toolidx_fmt")):
            with open(mod.__file__, encoding="utf-8") as f:
                tree = ast.parse(f.read())
            names = set()
            for n in ast.walk(tree):
                if isinstance(n, ast.Import):
                    names |= set(a.name.split(".")[0] for a in n.names)
                elif isinstance(n, ast.ImportFrom):
                    names.add((n.module or "").split(".")[0])
                elif isinstance(n, ast.Attribute) and n.attr in ("system", "popen", "spawnv", "execv", "fork"):
                    names.add("os." + n.attr)
            self.assertEqual(names & (bad | {"os.system", "os.popen", "os.spawnv", "os.execv", "os.fork"}), set(), mod.__name__)

    def test_unknown_sid_refused(self):
        for sid in ("nope", "", None, "x" * 200):
            b = MC.conn(sid)
            self.assertEqual((b["ok"], set(b)), (False, {"ok", "msg", "vars"}))
        self.assertEqual(MC._MC_CACHE["body"], {})

    def test_route_registered_and_wired(self):
        cs = load()
        self.assertEqual(cs.Handler._GET_ROUTES["/api/mcp-conn"].__name__, "_g_mcp_conn")
        rg, got = sidereus("routes_get"), {}
        saved = rg.mcp_conn
        rg.mcp_conn = lambda sid: {"ok": False, "msg": "m", "vars": {"sid": sid}}
        h = rg._GetRoutes()
        h._raw_json = lambda code, out: got.update(code=code, out=out)
        try:
            h._g_mcp_conn(type("U", (), {"query": "sid=abc"})())
        finally:
            rg.mcp_conn = saved
        self.assertEqual((got["code"], got["out"]["vars"]["sid"]), (200, "abc"))

    def test_demo_shape_matches(self):
        dt = sidereus("demo_tools")
        rows = [{"sid": "d-cc", "plat": "cc"}, {"sid": "d-pi", "plat": "pi"}, {"sid": "d-gm", "plat": "gm"}]
        code, b = dt._demo_mcp_conn(NOW, "d-cc", rows)
        self.assertEqual((code, set(b), set(b["servers"][0])),
                         (200, {"ok", "now", "sid", "plat", "supported", "counts", "since", "scanning", "checked", "servers", "totals",
                                "kinds"}, {"name", "scope", "plug", "transport", "on", "state", "err", "at", "n", "last"}))
        kd = b["kinds"]
        self.assertEqual((set(kd), set(kd["skill"])), (set(MC.MC_KINDS), {"supported", "items", "more"}))
        self.assertEqual(set(kd["skill"]["items"][0]), {"name", "kind", "scope", "plug", "path", "n", "last"})   # = test_mcp_conn_kinds live shape
        self.assertEqual(set(kd["agent"]["items"][0]), {"name", "scope", "plug", "path", "n", "last"})
        self.assertEqual(set(kd["hook"]["items"][0]), {"name", "scope", "plug", "path", "files", "subs", "n", "last"})
        self.assertEqual((set(kd["hook"]["items"][0]["files"][0]), set(kd["hook"]["items"][0]["subs"][0])),
                         ({"scope", "path", "matcher"}, {"name", "n", "last"}))
        self.assertTrue(all(type(r["n"]) is int for k in MC.MC_KINDS for r in kd[k]["items"]))
        self.assertTrue(any(len(dt._demo_mcp_conn(NOW, s, [{"sid": s, "plat": "cc"}])[1]["kinds"]["skill"]["items"]) >= 60
                            for s in ("a", "b", "c")))   # one cc session per k carries the 60-skill layout case
        for s in ("d-pi", "d-gm"):
            self.assertEqual(dt._demo_mcp_conn(NOW, s, rows)[1]["kinds"], MC._kinds_none())
        self.assertEqual(set(s["state"] for s in b["servers"]), set(MC.MC_STATES))
        self.assertEqual(set(s["n"] for s in dt._demo_mcp_conn(NOW, "d-pi", rows)[1]["servers"]), {None})
        self.assertFalse(dt._demo_mcp_conn(NOW, "d-gm", rows)[1]["supported"])
        self.assertFalse(dt._demo_mcp_conn(NOW, "zz", rows)[1]["ok"])


if __name__ == "__main__":
    unittest.main()
