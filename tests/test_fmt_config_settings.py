"""Config-format tests: settings.json hooks/env/autoCompact, settings.local.json, plugin hooks.json, .mcp.json and
~/.claude.json fed through the real readers (toolinv · ctxsrc · harness · cc_settings · burn_scan).

Every variant (minimal, full, extra keys, wrong types, missing optional keys, empty, BOM, CRLF) must neither crash
nor mis-read. ⚠Synthetic files in a temp dir only; ctxsrc/toolinv/cc_settings/burn_scan path globals are patched.
Pipelines (.claude/pipelines/*.json) are covered by tests/test_pipeline.py.
"""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import load, sidereus

load()
cx = sidereus("ctxsrc")
tv = sidereus("toolinv")
hn = sidereus("harness")
cc = sidereus("cc_settings")
bu = sidereus("burn_scan")

BOM = "﻿"


def _crlf(s):
    return s.replace("\n", "\r\n")


def _hooks_full():
    """Every hooks-block shape Claude Code accepts: matcher string / absent / empty / regex, command/prompt type, timeout."""
    return {
        "PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 $CLAUDE_PROJECT_DIR/h/guard.py", "timeout": 30}]},
            {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "/abs/fmt.sh"}]},
        ],
        "Stop": [{"hooks": [{"type": "command", "command": "node ~/.claude/hooks/stop.js", "timeout": 5.5}]}],
        "SessionStart": [{"matcher": "", "hooks": [{"type": "prompt", "prompt": "p"}]}],
        "UserPromptSubmit": [{"hooks": [{"command": "bash x.sh"}]}],   # type omitted = command
        "FutureEvent": [{"matcher": "*", "hooks": [{"type": "command", "command": "a.py", "newKey": 1}], "extra": {}}],
    }


def _hooks_bad():
    """Wrong types at every level — each bad entry must be skipped, the good one kept."""
    return {
        "PreToolUse": [None, 3, "str", {"matcher": 5, "hooks": "nope"},
                       {"matcher": ["x"], "hooks": [None, 1, {"type": "command", "command": ["argv"]},
                                                    {"type": "command", "command": "ok.py", "timeout": "30"},
                                                    {"type": "command", "command": "t.py", "timeout": True}]}],
        "Stop": {"hooks": []},     # dict instead of list
        "Notification": "x",
        "": [],
    }


class _Base(unittest.TestCase):
    def setUp(self):
        t = self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-fmtcfg-"))
        self.home = os.path.join(t, "home", ".claude")
        self.cj = os.path.join(t, "home", ".claude.json")
        self.proj = os.path.join(t, "work", "repo")
        os.makedirs(self.home)
        os.makedirs(os.path.join(self.proj, ".claude"))
        self.saved = (cx.CLAUDE_DIR, cx.CLAUDE_JSON, tv._allowed_cwds, cc.SETTINGS_PATH, bu.CLAUDE_SETTINGS)
        cx.CLAUDE_DIR, cx.CLAUDE_JSON = self.home, self.cj
        tv._allowed_cwds = lambda: {}
        cc.SETTINGS_PATH = os.path.join(self.home, "settings.json")
        bu.CLAUDE_SETTINGS = os.path.join(self.home, "settings.json")
        cx._cj_memo.clear() if hasattr(cx._cj_memo, "clear") else None
        self.cj_write({"projects": {self.proj: {}}})

    def tearDown(self):
        cx.CLAUDE_DIR, cx.CLAUDE_JSON, tv._allowed_cwds, cc.SETTINGS_PATH, bu.CLAUDE_SETTINGS = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def w(self, p, text):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text)

    def cj_write(self, d):
        self.w(self.cj, json.dumps(d) if not isinstance(d, str) else d)
        try:
            os.utime(self.cj, None)
        except OSError:
            pass

    def user_settings(self, d):
        self.w(os.path.join(self.home, "settings.json"), json.dumps(d, indent=2) if not isinstance(d, str) else d)

    def items(self, kind):
        return [it for it in tv._raw_items() if it["kind"] == kind]


class SettingsHooks(_Base):
    def test_full_shapes_read_by_every_reader(self):
        self.user_settings({"hooks": _hooks_full(), "env": {"A": "1"}, "autoCompactWindow": 300000,
                            "autoCompactEnabled": False, "unknownTopKey": {"x": [1]}})
        hs = self.items("hook")
        names = sorted(it["name"] for it in hs)
        self.assertEqual(names, ["FutureEvent *", "PreToolUse Bash", "PreToolUse Edit|Write", "SessionStart",
                                 "Stop", "UserPromptSubmit"])
        self.assertTrue(all(it["scope"] == "user" and not it["ro"] for it in hs))
        ev = {e["ev"]: e["hooks"] for e in hn._hook_rows(hs, self.proj, {})}
        self.assertEqual(ev["PreToolUse"][0]["cmd"], "guard.py")
        self.assertEqual(ev["PreToolUse"][0]["timeout"], 30)
        self.assertEqual(ev["PreToolUse"][1]["matcher"], "Edit|Write")
        self.assertEqual(ev["Stop"][0]["timeout"], 5.5)
        self.assertEqual(ev["SessionStart"][0]["cmd"], "prompt")      # non-command hook: its type, never its prompt
        self.assertEqual(ev["UserPromptSubmit"][0]["cmd"], "x.sh")    # type omitted = command
        self.assertIn("FutureEvent", ev)                              # unknown event kept, listed after known ones
        counts = {h["event"]: h["n"] for h in cx._hooks(self.proj, "")}
        self.assertEqual(counts, {"FutureEvent": 1, "PreToolUse": 2, "SessionStart": 1, "Stop": 1, "UserPromptSubmit": 1})

    def test_minimal_and_missing_optional_keys(self):
        self.user_settings({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "s.sh"}]}]}})
        row = hn._hook_rows(self.items("hook"), self.proj, {})
        stop = [e for e in row if e["ev"] == "Stop"][0]["hooks"][0]
        self.assertEqual((stop["matcher"], stop["cmd"], stop["timeout"]), ("", "s.sh", None))
        self.user_settings({})
        self.assertEqual(self.items("hook"), [])
        self.assertEqual(cx._hooks(self.proj, ""), [])

    def test_wrong_types_skipped_not_crashing(self):
        self.user_settings({"hooks": _hooks_bad()})
        hs = self.items("hook")
        self.assertEqual(sorted(it["name"] for it in hs), ["PreToolUse", "PreToolUse"])   # non-string matcher dropped
        pre = [e for e in hn._hook_rows(hs, self.proj, {}) if e["ev"] == "PreToolUse"][0]["hooks"]
        self.assertEqual([h["cmd"] for h in pre], ["command", "ok.py", "t.py"])   # list command -> type label, never argv
        self.assertEqual([h["timeout"] for h in pre], [None, None, None])         # "30" and True are not timeouts
        for bad in ({"hooks": []}, {"hooks": "x"}, {"hooks": None}, [1, 2], "str", 5):
            self.user_settings(bad)
            self.assertEqual(self.items("hook"), [], bad)
            self.assertEqual(cx._hooks(self.proj, ""), [], bad)

    def test_ctxsrc_counts_only_dict_hooks(self):
        # ⚠null/number entries in a group's `hooks` list are not hooks (toolinv/harness skip them too).
        self.user_settings({"hooks": {"Stop": [{"hooks": [None, 1, {"type": "command", "command": "s.sh"}]}]}})
        self.assertEqual(cx._hooks(self.proj, ""), [{"event": "Stop", "n": 1}])

    def test_empty_bom_crlf(self):
        body = json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "s.sh"}]}]}}, indent=2)
        self.user_settings(_crlf(body))
        self.assertEqual([it["name"] for it in self.items("hook")], ["Stop"])   # CRLF is JSON whitespace
        self.assertEqual(cx._hooks(self.proj, ""), [{"event": "Stop", "n": 1}])
        for raw in ("", "   \n", "{", BOM + body):
            self.user_settings(raw)
            self.assertIn(len(self.items("hook")), (0, 1), repr(raw[:5]))       # BOM: read or skipped, never a crash
            self.assertIsInstance(cx._hooks(self.proj, ""), list)
        self.user_settings(BOM + body)                                        # leading BOM stripped (ctxsrc.read_text)
        self.assertEqual([it["name"] for it in self.items("hook")], ["Stop"])
        self.assertEqual(cx._hooks(self.proj, ""), [{"event": "Stop", "n": 1}])

    def test_project_and_local_settings(self):
        hooks = {"Stop": [{"hooks": [{"type": "command", "command": "p.sh"}]}]}
        self.w(os.path.join(self.proj, ".claude", "settings.json"), json.dumps({"hooks": hooks, "permissions": {"allow": []}}))
        self.w(os.path.join(self.proj, ".claude", "settings.local.json"),
               _crlf(json.dumps({"hooks": hooks, "disabledMcpjsonServers": ["gone"]}, indent=1)))
        self.w(os.path.join(self.home, "settings.local.json"), json.dumps({"hooks": hooks}))
        hs = self.items("hook")
        src = sorted(hn._src(it) for it in hs)
        self.assertEqual(src, ["project", "project-local", "user-local"])
        ro = {hn._src(it): it["ro"] for it in hs}
        self.assertEqual(ro, {"project": True, "project-local": False, "user-local": True})
        self.assertEqual(cx._hooks(self.proj, ""), [{"event": "Stop", "n": 3}])

    def test_disabled_mcpjson_servers_wrong_type(self):
        # ⚠A string/dict `disabledMcpjsonServers` is ignored — it must not take down the whole «도구» list.
        self.w(os.path.join(self.proj, ".claude", "settings.local.json"), json.dumps({"disabledMcpjsonServers": "gh"}))
        self.w(os.path.join(self.proj, ".mcp.json"), json.dumps({"mcpServers": {"gh": {"command": "gh"}}}))
        self.assertEqual([it["name"] for it in self.items("mcp")], ["gh"])


class McpConfig(_Base):
    def mcp(self, servers, raw=None):
        self.w(os.path.join(self.proj, ".mcp.json"), raw if raw is not None else json.dumps({"mcpServers": servers}))
        return {it["name"]: it for it in self.items("mcp") if it["file"].endswith(".mcp.json")}

    def test_stdio_http_sse_shapes(self):
        got = self.mcp({
            "fs": {"command": "npx", "args": ["-y", "srv", "--api-key", "K123"], "env": {"TOKEN": "s3cret"}},
            "typed": {"type": "stdio", "command": "node", "args": []},
            "web": {"type": "http", "url": "https://h.example/mcp", "headers": {"Authorization": "Bearer s3cret"}},
            "ev": {"type": "sse", "url": "https://h.example/sse"},
            "extra": {"command": "x", "futureKey": {"a": 1}},
        })
        self.assertEqual(sorted(got), ["ev", "extra", "fs", "typed", "web"])
        tr = {n: hn._transport(it["entry"]) for n, it in got.items()}
        self.assertEqual(tr, {"ev": "sse", "extra": "stdio", "fs": "stdio", "typed": "stdio", "web": "http"})
        m = tv.mask_mcp(got["fs"]["entry"])
        self.assertEqual(m["env"], {"TOKEN": tv.MASK})
        self.assertEqual(m["args"][3], tv.MASK)
        self.assertEqual(tv.mask_mcp(got["web"]["entry"])["headers"], {"Authorization": tv.MASK})
        rows = hn._mcp_rows(list(got.values()), {})
        self.assertNotIn("s3cret", json.dumps(rows))
        self.assertEqual(sorted(r["name"] for r in ctxsrc_rows(self.proj)), ["ev", "extra", "fs", "typed", "web"])

    def test_wrong_types_and_missing_keys(self):
        got = self.mcp({"nocmd": {}, "num": 5, "lst": ["a"], "badenv": {"command": "c", "env": "K=V", "args": "one"},
                        "badtype": {"type": 7, "url": 3}, "hdr": {"type": "http", "url": "u", "headers": ["Auth: x"]}})
        self.assertEqual(sorted(got), ["badenv", "badtype", "hdr", "lst", "nocmd", "num"])
        for it in got.values():
            m = tv.mask_mcp(it["entry"])     # never raises
            self.assertIsInstance(m, dict)
        self.assertEqual(tv.mask_mcp(got["badenv"]["entry"])["env"], tv.MASK)
        self.assertEqual(tv.mask_mcp(got["hdr"]["entry"])["headers"], tv.MASK)
        self.assertEqual(hn._transport(got["num"]["entry"]), "")
        self.assertEqual(hn._transport(got["badtype"]["entry"]), "")
        self.assertEqual(len(hn._mcp_rows(list(got.values()), {})), 6)
        for top in ({"mcpServers": []}, {"mcpServers": "x"}, {"other": {}}, [1]):
            self.assertEqual(self.mcp(None, raw=json.dumps(top)), {}, top)

    def test_empty_bom_crlf(self):
        body = json.dumps({"mcpServers": {"a": {"command": "c"}}}, indent=2)
        self.assertEqual(sorted(self.mcp(None, raw=_crlf(body))), ["a"])
        for raw in ("", "{", BOM + body):
            self.assertIn(sorted(self.mcp(None, raw=raw)), ([], ["a"]), repr(raw[:5]))
            self.assertIsInstance(ctxsrc_rows(self.proj), list)

    def test_claude_json_user_and_project_servers(self):
        self.cj_write({"mcpServers": {"u": {"command": "c"}, "bad": 1},
                       "projects": {self.proj: {"mcpServers": {"loc": {"type": "http", "url": "u"}},
                                                "disabledMcpjsonServers": ["p"]},
                                    "/rel": {"mcpServers": {"x": {}}}, "/notdict": 3},
                       "otherKey": [1, 2]})
        self.mcp({"p": {"command": "c"}})
        got = {(it["scope"], it["name"]): it["on"] for it in self.items("mcp")}
        self.assertEqual(got, {("user", "bad"): True, ("user", "u"): True, ("project", "loc"): True, ("project", "p"): False})
        for raw in ("", "[]", '{"projects": []}', '{"mcpServers": "x", "projects": {"/a": null}}'):
            self.cj_write(raw)
            self.assertIsInstance(self.items("mcp"), list, raw)
            self.assertIsInstance(ctxsrc_rows(self.proj), list, raw)


def ctxsrc_rows(proj):
    cx._cj_memo.clear() if hasattr(cx._cj_memo, "clear") else None
    return cx._mcp(proj, "")


class PluginHooks(_Base):
    def plugin(self, hooks_json, plugin_json=None, reg=None):
        plug = os.path.join(self.home, "plugins", "cache", "mk", "pl", "1.0.0")
        os.makedirs(plug, exist_ok=True)
        if hooks_json is not None:
            self.w(os.path.join(plug, "hooks", "hooks.json"), hooks_json)
        if plugin_json is not None:
            self.w(os.path.join(plug, ".claude-plugin", "plugin.json"), plugin_json)
        self.w(os.path.join(self.home, "plugins", "installed_plugins.json"),
               json.dumps(reg if reg is not None else {"version": 2, "plugins": {"pl@mk": [{"installPath": plug, "scope": "user"}]}}))
        return plug

    def test_hooks_json_shapes(self):
        body = json.dumps({"description": "d", "hooks": {
            "PostToolUse": [{"matcher": "Write", "hooks": [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/s/fmt.py", "timeout": 10}]}],
            "Stop": [{"hooks": [{"type": "command", "command": "x"}]}]}})
        plug = self.plugin(body, json.dumps({"name": "pl", "description": "Formats files", "version": "1.0.0"}))
        hs = self.items("hook")
        self.assertEqual(sorted(it["name"] for it in hs), ["PostToolUse Write", "Stop"])
        self.assertTrue(all(it["scope"] == "plugin" and it["ro"] for it in hs))
        ev = {e["ev"]: e["hooks"] for e in hn._hook_rows(hs, self.proj, {})}
        r = ev["PostToolUse"][0]
        self.assertEqual((r["cmd"], r["timeout"], r["plug"], r["src"]), ("fmt.py", 10, "pl", "plugin"))
        self.assertEqual(r["desc"], "Formats files")    # plugin.json description when the script has none
        self.assertTrue(os.path.isdir(plug))

    def test_bad_hooks_json_and_registry(self):
        for raw in ("", "{", "[]", '{"hooks": []}', '{"hooks": {"Stop": "x"}}', BOM + '{"hooks": {}}',
                    _crlf('{\n "hooks": {\n  "Stop": [{"hooks": [{"command": "a"}]}]\n }\n}')):
            self.plugin(raw, plugin_json="not json")
            hs = self.items("hook")
            self.assertLessEqual(len(hs), 1, repr(raw[:8]))
            self.assertIsInstance(hn._hook_rows(hs, self.proj, {}), list)
        for reg in ({"plugins": []}, {"plugins": {"pl@mk": "x"}}, {"plugins": {"pl@mk": [None, {"installPath": 3}]}}, {}):
            self.plugin('{"hooks": {}}', reg=reg)
            self.assertEqual([it for it in tv._raw_items() if it["scope"] == "plugin"], [], reg)


class CompactKeys(_Base):
    def test_cc_get_shapes(self):
        cases = [({"autoCompactEnabled": False, "autoCompactWindow": 300000, "extra": 1}, (False, 300000), None),
                 ({}, (True, None), None),
                 ({"autoCompactEnabled": "false", "autoCompactWindow": "300000"}, (True, None), None),
                 ({"autoCompactEnabled": 0, "autoCompactWindow": True}, (True, None), None),
                 ({"autoCompactWindow": 10}, (True, None), None)]          # out of range shows the default
        for d, want, err in cases:
            self.user_settings(d)
            out, e = cc.cc_get()
            self.assertEqual((out["cc_auto_compact"]["value"], out["cc_compact_window"]["value"]), want, d)
            self.assertEqual(e, err)
        self.user_settings(_crlf(json.dumps({"autoCompactWindow": 400000}, indent=2)))
        self.assertEqual(cc.cc_get()[0]["cc_compact_window"]["value"], 400000)
        self.user_settings(BOM + "{}")                 # a BOM is valid (Windows editors write one): empty object, no error
        self.assertEqual(cc.cc_get()[1], None)
        for raw in ("", "{", "[1]", "5", BOM + "[1]"):
            self.user_settings(raw)
            out, e = cc.cc_get()
            self.assertIsNone(out["cc_compact_window"]["value"])
            self.assertTrue(e, repr(raw))         # reported, so nothing is ever written over it
        os.remove(os.path.join(self.home, "settings.json"))
        self.assertEqual(cc.cc_get()[1], "settings.json not found")

    def test_otel_env_shapes(self):
        for env, want in (({"OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:8799"}, True),
                          ({"OTEL_EXPORTER_OTLP_ENDPOINT": "https://remote:4318"}, False),
                          ({"OTEL_EXPORTER_OTLP_ENDPOINT": 8799}, False), ({}, False), ([], False), ("x", False), (None, False)):
            self.user_settings({"env": env})
            self.assertEqual(cc.otel_get()["ok"], want, env)
        self.user_settings("[]")
        self.assertFalse(cc.otel_get()["ok"])

    def test_burn_scan_window(self):
        for d, want in (({"autoCompactWindow": 300000}, 300000), ({}, bu.COMPACT_DEFAULT),
                        ({"autoCompactWindow": "abc"}, bu.COMPACT_DEFAULT), ({"autoCompactWindow": 5}, bu.COMPACT_DEFAULT),
                        ({"autoCompactWindow": 300000, "env": {"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "200000"}}, 200000),
                        ({"env": {"DISABLE_AUTOCOMPACT": "1"}}, bu.COMPACT_DEFAULT), ({"env": None}, bu.COMPACT_DEFAULT)):
            self.user_settings(d)
            self.assertEqual(bu._compact_setting()[0], want, d)
        self.user_settings(_crlf(json.dumps({"autoCompactWindow": 250000}, indent=2)))
        self.assertEqual(bu._compact_setting()[0], 250000)
        for raw in ("", "{"):
            self.user_settings(raw)
            self.assertIsNone(bu._compact_setting()[0])     # mid-write: caller keeps the previous window

    def test_burn_scan_wrong_types(self):
        # ⚠A non-object top level (`[]`) or `env` ("x", [...]) falls back to the default window, never a crash.
        for d in ([1], {"env": ["a"]}, {"env": "x"}):
            self.user_settings(d)
            self.assertEqual(bu._compact_setting()[0], bu.COMPACT_DEFAULT, d)


if __name__ == "__main__":
    unittest.main()
