"""Connections `kinds` block (sidereus/mcp_conn.py `_cc_kinds`): skills (+ slash commands), agents and hook events per session.
Every root is a temp dir and every reader is patched on its owner module (never the live ~/.claude)."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import load, sidereus
from tests.test_mcp_conn import CXS, NOW, S1, S2, SECRET, _iso, _w

load()
MC = sidereus("mcp_conn")
TI = sidereus("toolidx")
TV = sidereus("toolinv")
CX = sidereus("ctxsrc")
PC = sidereus("plat_codex")
PP = sidereus("plat_pi")


def _call(tid, name, inp, ts):
    return {"type": "assistant", "timestamp": _iso(ts),
            "message": {"content": [{"type": "tool_use", "id": tid, "name": name, "input": dict(inp, prompt=SECRET)}]}}


def _slash(uid, name, ts):
    return {"type": "user", "uuid": uid, "timestamp": _iso(ts),
            "message": {"content": "<command-name>/%s</command-name><command-args>%s</command-args>" % (name, SECRET)}}


def _hook(uid, hn, ts, typ="hook_success"):
    return {"type": "attachment", "uuid": uid, "timestamp": _iso(ts),
            "attachment": {"type": typ, "hookName": hn, "command": SECRET, "stdout": SECRET, "content": SECRET}}


def _md(p, name=None):
    _w(p, "---\nname: %s\ndescription: d\n---\n%s\n" % (name, SECRET) if name else "# x\n" + SECRET)


class McpConnKindsTest(unittest.TestCase):
    def setUp(self):
        t = self.tmp = tempfile.mkdtemp(prefix="sidereus-mck-")
        self.cwd, self.other = os.path.join(t, "repo"), os.path.join(t, "other")
        cd = self.cd = os.path.join(t, "claude")
        live, dead = (os.path.join(cd, "plugins", "cache", "mk", p, "1.0.0") for p in ("browser", "dead"))
        cmd_hooks = [{"type": "command", "command": SECRET}]
        _w(os.path.join(cd, "settings.json"), {
            "enabledPlugins": {"browser@mk": True, "dead@mk": False}, "skillOverrides": {"offsk": "off"},
            "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": cmd_hooks}, {"matcher": "Edit|Write", "hooks": cmd_hooks}],
                      "Stop": [{"hooks": cmd_hooks}]}})
        _w(os.path.join(cd, "plugins", "installed_plugins.json"),
           {"plugins": {"browser@mk": [{"installPath": live}], "dead@mk": [{"installPath": dead}]}})
        for d, n in ((cd, "alpha"), (cd, "offsk"), (os.path.join(self.cwd, ".claude"), "projsk"),
                     (os.path.join(self.other, ".claude"), "elsewhere"), (live, "snap"), (dead, "ghost")):
            _md(os.path.join(d, "skills", n, "SKILL.md"))
        _md(os.path.join(cd, "commands", "ship.md"))
        _md(os.path.join(cd, "commands", "alpha.md"))                      # same name as a skill: one node
        _md(os.path.join(cd, "agents", "reviewer.md"), "reviewer")
        _md(os.path.join(cd, "sidereus-off", "agents", "parked.md"), "parked")
        _md(os.path.join(self.cwd, ".claude", "agents", "builder.md"), "builder")
        _md(os.path.join(self.other, ".claude", "agents", "far.md"), "far")
        _md(os.path.join(dead, "agents", "deadagent.md"), "deadagent")
        _w(os.path.join(self.cwd, ".claude", "settings.json"), {"hooks": {"PostToolUse": [{"matcher": "Write", "hooks": cmd_hooks}]}})
        _w(os.path.join(live, "hooks", "hooks.json"), {"hooks": {"SessionStart": [{"hooks": cmd_hooks}]}})
        _w(os.path.join(dead, "hooks", "hooks.json"), {"hooks": {"Notification": [{"hooks": cmd_hooks}]}})
        _w(os.path.join(t, "cj.json"), {"projects": {self.cwd: {}, self.other: {}}})
        self.rows = [{"sid": S1, "plat": "cc", "cwd": self.cwd}, {"sid": S2, "plat": "cc", "cwd": self.cwd},
                     {"sid": CXS, "plat": "cx", "cwd": self.cwd}, {"sid": "pi-1", "plat": "pi", "cwd": self.cwd},
                     {"sid": "gm-1", "plat": "gm", "cwd": self.cwd}]
        self.saved = [(CX, "CLAUDE_DIR", CX.CLAUDE_DIR), (CX, "CLAUDE_JSON", CX.CLAUDE_JSON), (TV, "_allowed_cwds", TV._allowed_cwds),
                      (TI, "CLAUDE_PROJECTS", TI.CLAUDE_PROJECTS), (TI, "TI_BG", TI.TI_BG), (PC, "root", PC.root), (PP, "root", PP.root),
                      (MC, "sessions_rows", MC.sessions_rows), (MC, "_now", MC._now), (MC, "_git_root", MC._git_root),
                      (MC, "MC_KIND_MAX", MC.MC_KIND_MAX)]
        CX.CLAUDE_DIR, CX.CLAUDE_JSON = cd, os.path.join(t, "cj.json")
        TV._allowed_cwds = lambda: []
        TI.CLAUDE_PROJECTS, TI.TI_BG = os.path.join(t, "projects"), False
        PC.root, PP.root = (lambda: os.path.join(t, "codex")), (lambda: os.path.join(t, "pi"))
        MC.sessions_rows, MC._now, MC._git_root = (lambda: self.rows), (lambda: NOW), (lambda d: "")
        TI.reset()
        MC._MC_CACHE["body"].clear()

    def tearDown(self):
        for mod, k, v in self.saved:
            setattr(mod, k, v)
        TI.reset()
        MC._MC_CACHE["body"].clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _tx(self, sid, recs, sub=False):
        d = os.path.join(TI.CLAUDE_PROJECTS, "-repo")
        _w(os.path.join(d, sid, "subagents", "agent-a.jsonl") if sub else os.path.join(d, sid + ".jsonl"), recs)

    def _s1(self):
        d = NOW - 3600
        self._tx(S1, [_call("s1", "Skill", {"skill": "alpha"}, d), _slash("c1", "alpha", d + 1), _slash("c2", "ship", d + 2),
                      _slash("c3", "clear", d + 3), _call("s2", "Skill", {"skill": "browser:snap"}, d + 4),
                      _call("s3", "Skill", {"skill": "frontend-x"}, d + 5), _call("a1", "Agent", {"subagent_type": "reviewer"}, d + 6),
                      _call("a3", "Task", {"subagent_type": "Explore"}, d + 7),
                      _hook("h1", "PreToolUse:Bash", d + 8), _hook("h1", "PreToolUse:Bash", d + 8, "hook_additional_context"),
                      _hook("h2", "PreToolUse:Edit", d + 9), _hook("h5", "PreToolUse:Bash", d + 12), _hook("h3", "Stop", d + 10),
                      _hook("h4", "SubagentStop", d + 11)])
        self._tx(S1, [_call("a1", "Agent", {"subagent_type": "reviewer"}, d + 6), _call("a2", "Agent", {"subagent_type": "reviewer"}, d + 20)],
                 sub=True)
        self._tx(S2, [_call("t1", "Skill", {"skill": "alpha"}, d + 30)])
        return d

    @staticmethod
    def _by(body, kind):
        return dict((r["name"], r) for r in body["kinds"][kind]["items"])

    def test_R2_skill_nodes_loadable_only_counts_per_session(self):
        d = self._s1()
        b = MC.conn(S1)
        sk = self._by(b, "skill")
        self.assertEqual(sorted(sk), ["alpha", "browser:snap", "frontend-x", "projsk", "ship"])   # offsk / elsewhere / ghost / clear out
        self.assertEqual((sk["alpha"]["kind"], sk["alpha"]["scope"], sk["alpha"]["n"], sk["alpha"]["last"]), ("skill", "user", 2, int(d + 1)))
        self.assertEqual((sk["ship"]["kind"], sk["ship"]["n"]), ("cmd", 1))
        self.assertEqual((sk["browser:snap"]["scope"], sk["browser:snap"]["plug"], sk["browser:snap"]["n"]), ("plugin", "browser", 1))
        self.assertEqual((sk["frontend-x"]["scope"], sk["frontend-x"]["path"]), ("seen", ""))
        self.assertEqual((sk["projsk"]["scope"], sk["projsk"]["n"], sk["projsk"]["last"]), ("project", 0, 0))
        self.assertEqual([r["name"] for r in b["kinds"]["skill"]["items"]], ["projsk", "alpha", "ship", "browser:snap", "frontend-x"])
        self.assertEqual(self._by(MC.conn(S2), "skill")["alpha"]["n"], 1)
        self.assertEqual(set(b["kinds"]["skill"]), {"supported", "items", "more"})
        self.assertEqual(set(sk["alpha"]), {"name", "kind", "scope", "plug", "path", "n", "last"})

    def test_R2_agent_nodes_subagent_dup_once_seen_builtin(self):
        self._s1()
        ag = self._by(MC.conn(S1), "agent")
        self.assertEqual(sorted(ag), ["Explore", "builder", "reviewer"])        # parked / far / deadagent out
        self.assertEqual((ag["reviewer"]["scope"], ag["reviewer"]["n"]), ("user", 2))   # a1 in parent + subagent file = once
        self.assertEqual((ag["builder"]["scope"], ag["builder"]["n"]), ("project", 0))
        self.assertEqual((ag["Explore"]["scope"], ag["Explore"]["path"], ag["Explore"]["n"]), ("seen", "", 1))
        self.assertEqual(set(ag["reviewer"]), {"name", "scope", "plug", "path", "n", "last"})

    def test_R3_hooks_per_event_no_command_text(self):
        d = self._s1()
        b = MC.conn(S1)
        hk = self._by(b, "hook")
        self.assertEqual(sorted(hk), ["PostToolUse", "PreToolUse", "SessionStart", "Stop", "SubagentStop"])   # Notification = disabled plugin
        pre = hk["PreToolUse"]
        self.assertEqual((pre["n"], pre["last"], pre["scope"]), (3, int(d + 12), "user"))   # additional_context of h1 not added
        self.assertEqual([(s["name"], s["n"]) for s in pre["subs"]], [("PreToolUse:Bash", 2), ("PreToolUse:Edit", 1)])
        self.assertEqual([f["matcher"] for f in pre["files"]], ["Bash", "Edit|Write"])
        self.assertEqual((hk["PostToolUse"]["scope"], hk["PostToolUse"]["files"][0]["matcher"], hk["PostToolUse"]["n"]), ("project", "Write", 0))
        self.assertEqual((hk["SessionStart"]["scope"], hk["SessionStart"]["plug"]), ("plugin", "browser"))
        self.assertEqual((hk["SubagentStop"]["scope"], hk["SubagentStop"]["files"], hk["SubagentStop"]["n"]), ("seen", [], 1))
        self.assertEqual(set(pre), {"name", "scope", "plug", "path", "files", "subs", "n", "last"})
        self.assertNotIn(SECRET, json.dumps(b))
        self.assertNotIn(SECRET, json.dumps(TI._TI_SESS, default=str))
        ev = TI.session_mcp(S1, NOW - 86400, NOW)
        self.assertTrue(all(k.startswith("mcp:") for k in ev["uses"]))
        self.assertFalse(any(k.startswith(("mcp:", "hookc:", "hookctx:", "tool:")) for k in ev["kinds"]))
        self.assertEqual(ev["kinds"]["hook:PreToolUse:Bash"]["n"], 2)

    def test_R4_path_is_tools_form(self):
        self._s1()
        # Patch expanduser, not HOME: Windows Python resolves «~» from USERPROFILE and ignores HOME.
        real = os.path.expanduser
        with mock.patch("os.path.expanduser", lambda p: self.tmp + p[1:] if p.startswith("~") else real(p)):
            b = MC.conn(S1)
        tl = lambda *parts: os.path.join("~", *parts)   # «~» + os.sep form, as toolinv._abbrev builds it
        self.assertEqual(self._by(b, "skill")["alpha"]["path"], tl("claude", "skills", "alpha", "SKILL.md"))
        self.assertEqual(self._by(b, "agent")["builder"]["path"], tl("repo", ".claude", "agents", "builder.md"))
        self.assertEqual(self._by(b, "hook")["Stop"]["path"], tl("claude", "settings.json"))

    def test_cap_keeps_used_reports_more(self):
        self._s1()
        MC.MC_KIND_MAX = 3
        kd = MC.conn(S1)["kinds"]["skill"]
        self.assertEqual(([r["name"] for r in kd["items"]], kd["more"]), (["alpha", "ship", "browser:snap"], 2))   # 0-call projsk, ...
        ag = MC._kind_cap([{"name": n, "scope": "user", "plug": "", "n": 0} for n in ("d", "B", "a", "c")])
        self.assertEqual(([r["name"] for r in ag["items"]], ag["more"]), (["a", "B", "c"], 1))

    def test_nongoal_other_clis_not_read(self):
        self._s1()
        for sid in (CXS, "pi-1", "gm-1"):
            kd = MC.conn(sid)["kinds"]
            self.assertEqual(kd, dict((k, {"supported": False, "items": [], "more": 0}) for k in ("skill", "agent", "hook")), sid)

    def test_mcp_rows_unchanged_by_kinds(self):
        self._s1()
        b = MC.conn(S1)
        self.assertEqual(b["servers"], [])          # skill/agent/hook evidence never becomes an MCP row
        self.assertTrue(b["kinds"]["skill"]["supported"])


if __name__ == "__main__":
    unittest.main()
