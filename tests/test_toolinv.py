"""«도구» inventory (sidereus/toolinv.py): kinds, scopes, flags, masking, plugin ro, stable ids, demo.
Fixtures live in a temp dir; ctxsrc.CLAUDE_DIR/CLAUDE_JSON and toolinv's lookups are patched (never the live ~/.claude)."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import load, sidereus

load()
cx = sidereus("ctxsrc")
tv = sidereus("toolinv")
SECRET = "SECRET-ENV-do-not-leak"
HOOKSECRET = "API_TOKEN=abcdef0123456789abcdef"


class ToolInvTest(unittest.TestCase):
    def setUp(self):
        t = self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-tv-"))
        self.home = os.path.join(t, "home", ".claude")
        self.proj = os.path.join(t, "work", "repo")
        self.gone = os.path.join(t, "work", "gone")
        self.cj = os.path.join(t, "home", ".claude.json")
        w = self._w
        w(os.path.join(self.home, "skills", "ship", "SKILL.md"), "---\nname: ship\n---\nbody")
        w(os.path.join(self.home, "skills", "shipp", "SKILL.md"), "x")
        w(os.path.join(self.home, "skills", "quiet", "SKILL.md"), "x")
        w(os.path.join(self.home, "agents", "rev.md"), "---\nname: reviewer\ndescription: d\n---\n")
        w(os.path.join(self.home, "sidereus-off", "agents", "parked.md"), "x")
        w(os.path.join(self.home, "commands", "git", "push.md"), "x")
        w(os.path.join(self.home, "settings.json"), json.dumps({
            "skillOverrides": {"quiet": "off"},
            "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "run " + HOOKSECRET}]}]},
            "enabledPlugins": {"pl@mk": True}}))
        w(os.path.join(self.proj, ".claude", "skills", "ship", "SKILL.md"), "p" * 70)
        w(os.path.join(self.proj, ".claude", "settings.local.json"),
          json.dumps({"disabledMcpjsonServers": ["gh"]}))
        w(os.path.join(self.proj, ".mcp.json"), json.dumps({"mcpServers": {
            "gh": {"command": "gh", "env": {"GH_TOKEN": SECRET}}, "ok": {"url": "u", "headers": {"Auth": SECRET}}}}))
        w(self.cj, json.dumps({"mcpServers": {"docs": {"command": "npx", "env": {"K": SECRET}}},
                               "projects": {self.proj: {"mcpServers": {"loc": {"command": "c"}}},
                                            self.gone: {"mcpServers": {"x": {}}}}}))
        plug = os.path.join(self.home, "plugins", "cache", "mk", "pl", "1.0")
        w(os.path.join(plug, "skills", "lint", "SKILL.md"), "x")
        w(os.path.join(plug, ".mcp.json"), json.dumps({"mcpServers": {"pw": {"env": {"T": SECRET}}}}))
        w(os.path.join(self.home, "plugins", "installed_plugins.json"),
          json.dumps({"plugins": {"pl@mk": [{"installPath": plug}]}}))
        self.saved = (cx.CLAUDE_DIR, cx.CLAUDE_JSON, tv._allowed_cwds, tv.tool_uses)
        cx.CLAUDE_DIR, cx.CLAUDE_JSON = self.home, self.cj
        tv._allowed_cwds = lambda: {}
        tv.tool_uses = lambda days: {"skill:ship": {"n": 4, "last": 100}, "mcp:docs": {"n": 2, "last": 50}}

    def tearDown(self):
        cx.CLAUDE_DIR, cx.CLAUDE_JSON, tv._allowed_cwds, tv.tool_uses = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def _w(p, text):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)

    def _by(self):
        return {(r["kind"], r["scope"], r["name"]): r for r in tv.scan_items(30)}

    def test_known_projects(self):
        self.assertEqual(tv.known_projects(), [self.proj])          # missing dir dropped
        extra = os.path.join(self.tmp, "work")
        tv._allowed_cwds = lambda: {extra: {}, "relative": {}}
        self.assertEqual(tv.known_projects(), sorted([self.proj, extra]))

    def test_kinds_scopes(self):
        by = self._by()
        self.assertEqual(set(by), {
            ("skill", "user", "ship"), ("skill", "user", "shipp"), ("skill", "user", "quiet"),
            ("skill", "project", "ship"), ("skill", "plugin", "pl:lint"),
            ("agent", "user", "reviewer"), ("agent", "user", "parked"), ("cmd", "user", "git:push"),
            ("mcp", "user", "docs"), ("mcp", "project", "loc"), ("mcp", "project", "gh"), ("mcp", "project", "ok"),
            ("mcp", "plugin", "pw"), ("hook", "user", "Stop")})
        self.assertFalse(by[("skill", "user", "quiet")]["on"])
        self.assertFalse(by[("agent", "user", "parked")]["on"])
        self.assertFalse(by[("mcp", "project", "gh")]["on"])
        self.assertTrue(by[("mcp", "project", "ok")]["on"])
        r = by[("skill", "project", "ship")]
        self.assertEqual((r["bytes"], r["tok"], r["proj"]), (70, 20, tv._abbrev(self.proj)))   # Windows temp is under ~
        self.assertEqual((by[("skill", "user", "ship")]["uses"], by[("skill", "user", "ship")]["last"]), (4, 100))

    def test_flags(self):
        by = self._by()
        self.assertIn("dup", by[("skill", "user", "ship")]["flags"])
        self.assertIn("near", by[("skill", "user", "shipp")]["flags"])
        self.assertIn("unused", by[("skill", "user", "shipp")]["flags"])
        self.assertNotIn("unused", by[("skill", "user", "ship")]["flags"])
        self.assertNotIn("unused", by[("skill", "user", "quiet")]["flags"])   # off items are not «unused»
        self.assertEqual(by[("hook", "user", "Stop")]["flags"], [])

    def test_plugin_read_only(self):
        by = self._by()
        self.assertTrue(by[("skill", "plugin", "pl:lint")]["ro"])
        self.assertTrue(by[("mcp", "plugin", "pw")]["ro"])
        self.assertFalse(by[("skill", "user", "ship")]["ro"])

    def test_plugin_agent_templates_and_cmd_skill_fold(self):
        plug = os.path.join(self.home, "plugins", "cache", "mk", "pl", "1.0")
        self._w(os.path.join(plug, "agents", "real.md"), "---\nname: real\n---\n")
        self._w(os.path.join(plug, "agents", "templates", "base.md"), "# template")
        self._w(os.path.join(plug, "commands", "lint.md"), "x")
        self._w(os.path.join(plug, "commands", "solo.md"), "x")
        self._w(os.path.join(self.home, "commands", "ship.md"), "x")   # user scope pair stays two rows
        tv.tool_uses = lambda days: {"skill:pl:lint": {"n": 2, "last": 10}, "cmd:pl:lint": {"n": 3, "last": 40},
                                     "skill:ship": {"n": 1, "last": 5}, "cmd:ship": {"n": 7, "last": 6}}
        rows = tv.scan_items(30)
        plugin = [(r["kind"], r["name"]) for r in rows if r["scope"] == "plugin" and r["kind"] in ("skill", "agent", "cmd")]
        self.assertEqual(sorted(plugin), [("agent", "pl:real"), ("cmd", "pl:solo"), ("skill", "pl:lint")])
        by = self._by()
        self.assertEqual((by[("skill", "plugin", "pl:lint")]["uses"], by[("skill", "plugin", "pl:lint")]["last"]), (5, 40))
        self.assertEqual(by[("skill", "user", "ship")]["uses"], 1)
        self.assertEqual(by[("cmd", "user", "ship")]["uses"], 7)

    def test_masked_everywhere(self):
        blob = json.dumps(tv.scan_items(30), ensure_ascii=False)
        self.assertNotIn(SECRET, blob)
        self.assertNotIn(HOOKSECRET, blob)
        for r in tv.scan_items(30):
            code, d = tv.tool_file(r["id"])
            self.assertEqual(code, 200)
            self.assertNotIn(SECRET, d["text"])
            self.assertNotIn("abcdef0123456789abcdef", d["text"])
        gh = self._by()[("mcp", "project", "gh")]
        d = json.loads(tv.tool_file(gh["id"])[1]["text"])
        self.assertEqual(d, {"command": "gh", "env": {"GH_TOKEN": "••••"}})
        self.assertEqual(tv.mask_mcp({"headers": {"A": "b"}, "args": ["a"]}), {"headers": {"A": "••••"}, "args": ["a"]})

    def test_mcp_args_url_masked(self):
        m = tv.mask_mcp({"args": ["-y", "srv", "--api-key", SECRET, "--token=" + SECRET, "--port", "80"],
                         "url": "https://h/x?token=%s&v=1" % SECRET})
        self.assertNotIn(SECRET, json.dumps(m, ensure_ascii=False))
        self.assertEqual(m["args"][:4] + m["args"][5:], ["-y", "srv", "--api-key", "••••", "--port", "80"])
        self.assertTrue(m["url"].startswith("https://h/x?token=") and m["url"].endswith("&v=1"))

    def test_mcp_dsn_password_masked(self):
        # A connection string in args carries no keyword hint; the userinfo password must still go.
        pw = "FakePw0rdNotReal123"
        m = tv.mask_mcp({"command": "srv postgresql://u:%s@db.example:5432/x" % pw,
                         "args": ["-y", "@x/server-postgres", "postgresql://postgres:%s@h.example:31506/railway" % pw],
                         "url": "https://bot:%s@api.example/v1" % pw})
        blob = json.dumps(m, ensure_ascii=False)
        self.assertNotIn(pw, blob)
        self.assertEqual(m["args"][2], "postgresql://postgres:•••@h.example:31506/railway")
        self.assertIn("db.example:5432/x", m["command"])
        self.assertEqual(m["args"][:2], ["-y", "@x/server-postgres"])

    def test_mcp_nested_secrets_masked(self):
        m = tv.mask_mcp({"type": "http", "url": "https://h/x", "headersHelper": "/bin/echo X-Api-Key: HELPERSECRET888",
                         "oauth": {"clientId": "cid", "clientSecret": "OAUTHSECRET999"},
                         "extra": [{"Password": "PWSECRET777", "name": "n"}]})
        blob = json.dumps(m, ensure_ascii=False)
        for s in ("HELPERSECRET888", "OAUTHSECRET999", "PWSECRET777"):
            self.assertNotIn(s, blob)
        self.assertEqual((m["type"], m["url"], m["extra"][0]["name"]), ("http", "https://h/x", "n"))

    def test_file_symlink_out_refused(self):
        out = os.path.join(self.tmp, "outside.md")
        tr = os.path.join(self.home, "projects", "x", "abc.jsonl")
        self._w(out, "OUTSIDE-BODY")
        self._w(tr, '{"message": "TRANSCRIPT-BODY"}')
        os.makedirs(os.path.join(self.home, "skills", "lnk"))
        os.symlink(out, os.path.join(self.home, "skills", "lnk", "SKILL.md"))
        os.symlink(tr, os.path.join(self.home, "agents", "tr.md"))
        by = self._by()
        for key in (("skill", "user", "lnk"), ("agent", "user", "tr")):
            code, d = tv.tool_file(by[key]["id"])
            self.assertEqual(code, 404, key)
            self.assertNotIn("BODY", json.dumps(d))

    def test_file_payload(self):
        r = self._by()[("skill", "project", "ship")]
        code, d = tv.tool_file(r["id"])
        self.assertEqual((code, d["text"], d["kind"]), (200, "p" * 70, "skill"))
        self.assertEqual(d["sha"], r["sha"])
        self.assertEqual(len(d["sha"]), 64)
        self.assertEqual(tv.tool_file("skill:000000000000")[0], 404)
        self.assertEqual(tv.tool_file("../etc/passwd")[0], 404)

    def test_stable_ids_and_lookup(self):
        a = [r["id"] for r in tv.scan_items(30)]
        self.assertEqual(a, [r["id"] for r in tv.scan_items(30)])
        self.assertEqual(len(a), len(set(a)))
        gh = self._by()[("mcp", "project", "gh")]
        it = tv.item_by_id(gh["id"])
        self.assertEqual((it["file"], it["key"], it["proj"]), (os.path.join(self.proj, ".mcp.json"), ["mcpServers", "gh"], self.proj))
        loc = tv.item_by_id(self._by()[("mcp", "project", "loc")]["id"])
        self.assertEqual(loc["key"], ["projects", self.proj, "mcpServers", "loc"])
        self.assertIsNone(tv.item_by_id("nope"))

    def test_demo_tools(self):
        demo = sidereus("demo")
        w = demo.World(page_build="x")
        code, d = demo.respond(w, "/api/tools", _U(""))
        self.assertEqual((code, d["ok"]), (200, True))
        mcp = [r for r in d["items"] if r["kind"] == "mcp"][0]
        code, f = demo.respond(w, "/api/tools/file", _U("id=" + mcp["id"]))
        self.assertIn("••••", f["text"])


class _U(object):
    def __init__(self, q):
        self.query = q


if __name__ == "__main__":
    unittest.main()
