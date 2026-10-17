"""«하네스 지도» (sidereus/harness.py): event order, matcher/basename/timeout, effect from the script text, secrets kept
out, agent↔stage from a pipeline file, metadata only. Everything lives in a tmp dir (ctxsrc/toolinv/harness patched)."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import load, sidereus
from tests.test_pipeline import SAMPLE

load()
H = sidereus("harness")
CX = sidereus("ctxsrc")
TV = sidereus("toolinv")
PL = sidereus("pipeline")
SENTINEL = "SENTINEL-transcript-body-do-not-leak"


def _w(p, body):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(body if isinstance(body, str) else json.dumps(body))


class HarnessTest(unittest.TestCase):
    def setUp(self):
        t = self.tmp = tempfile.mkdtemp(prefix="sidereus-hn-")
        cd, self.proj = os.path.join(t, "claude"), os.path.join(t, "proj")
        hk = os.path.join(cd, "hooks")
        _w(os.path.join(hk, "inject.py"), 'print(json.dumps({"hookSpecificOutput": {"additionalContext": "x"}}))\n')
        _w(os.path.join(hk, "block.py"), 'import sys\nsys.exit(2)\n')
        _w(os.path.join(hk, "log.py"), 'open("/dev/null", "a").write("x")\n')
        _w(os.path.join(cd, "settings.json"), {"hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": "python3 " + os.path.join(hk, "log.py")}]}],
            "PreToolUse": [{"matcher": "Bash|Edit", "hooks": [
                {"type": "command", "command": "/usr/bin/python3 -u " + os.path.join(hk, "block.py") + " --token=xyzzy", "timeout": 5}]}],
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "FOO=secret node " + os.path.join(hk, "inject.py")}]}],
            "SessionStart": [{"hooks": [{"type": "command", "command": "/nowhere/missing.sh --key=xyzzy"}]}],
            "Zeta": [{"hooks": [{"type": "command", "command": "--token=xyzzy"}]}]}})
        _w(os.path.join(cd, "CLAUDE.md"), "rules\n")
        _w(os.path.join(self.proj, "AGENTS.md"), "proj rules\n")
        _w(os.path.join(self.proj, ".claude", "agents", "designer.md"), "---\nname: designer\n---\n")
        _w(os.path.join(self.proj, ".claude", "pipelines", "demo.json"), SAMPLE)
        _w(os.path.join(t, "cj.json"), {})
        self.saved = [(CX, "CLAUDE_DIR", CX.CLAUDE_DIR), (CX, "CLAUDE_JSON", CX.CLAUDE_JSON),
                      (CX, "CLAUDE_PROJECTS", CX.CLAUDE_PROJECTS), (CX, "_git_root", CX._git_root),
                      (TV, "known_projects", TV.known_projects), (PL, "_proj_ok", PL._proj_ok),
                      (H, "_proj_ok", H._proj_ok), (H, "tool_uses", H.tool_uses), (H, "scanning", H.scanning), (H, "mcp_status", H.mcp_status),
                      (H, "DATA_DIR", H.DATA_DIR)]
        CX.CLAUDE_DIR, CX.CLAUDE_JSON, CX.CLAUDE_PROJECTS = cd, os.path.join(t, "cj.json"), os.path.join(t, "projects")
        CX._git_root = lambda c: ""
        TV.known_projects = lambda: [self.proj]
        PL._proj_ok = H._proj_ok = lambda p: p == self.proj
        H.tool_uses = lambda d: {"hook:PreToolUse:Bash": {"n": 3, "last": 10}, "hook:PreToolUse:Read": {"n": 9, "last": 20},
                                 "hook:Stop": {"n": 2, "last": 5}, "agent:designer": {"n": 4, "last": 1}}
        H.scanning = lambda: False
        H.mcp_status = lambda d: {}
        H.DATA_DIR = os.path.join(t, "data")
        H._EFF_CACHE.clear()

    def tearDown(self):
        for mod, k, v in self.saved:
            setattr(mod, k, v)
        H._EFF_CACHE.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _body(self):
        code, b = H.harness(self.proj, 30)
        self.assertEqual(code, 200)
        return b

    def _hook(self, b, ev):
        return next(e for e in b["events"] if e["ev"] == ev)["hooks"][0]

    def test_event_order_and_fields(self):
        hk, hh = os.path.join(self.tmp, "claude", "hooks"), sidereus("toolidx").hook_hash
        blk, log = "/usr/bin/python3 -u " + os.path.join(hk, "block.py") + " --token=xyzzy", "python3 " + os.path.join(hk, "log.py")
        H.tool_uses = lambda d: {"hookc:PreToolUse:Bash#" + hh(blk): {"n": 3, "last": 10}, "hookc:PreToolUse:Read#" + hh(blk): {"n": 9, "last": 20},
                                 "hookc:Stop#" + hh(log): {"n": 2, "last": 5}}
        b = self._body()
        self.assertEqual([e["ev"] for e in b["events"]], list(H.EVENTS) + ["Zeta"])
        h = self._hook(b, "PreToolUse")
        self.assertEqual((h["matcher"], h["cmd"], h["timeout"], h["src"], h["n"], h["last"]), ("Bash|Edit", "block.py", 5, "user", 3, 10))
        self.assertEqual((self._hook(b, "Stop")["n"], self._hook(b, "Stop")["timeout"]), (2, None))

    def test_runs_per_hook_or_group(self):
        hk = os.path.join(self.tmp, "claude", "hooks")
        a, c = "python3 " + os.path.join(hk, "log.py"), "python3 " + os.path.join(hk, "inject.py")
        _w(os.path.join(self.tmp, "claude", "settings.json"), {"hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": a}, {"type": "command", "command": c}]}],
            "PreCompact": [{"hooks": [{"type": "command", "command": a}, {"type": "command", "command": c}]}]}})
        tid = sidereus("toolidx")
        H.tool_uses = lambda d: {"hook:Stop": {"n": 5, "last": 9}, "hookc:Stop#" + tid.hook_hash(a): {"n": 5, "last": 9},
                                 "hook:PreCompact": {"n": 4, "last": 8}}
        b = self._body()
        st = next(e for e in b["events"] if e["ev"] == "Stop")["hooks"]
        self.assertEqual([(h["n"], h["quiet"]) for h in st], [(5, 0), (None, 1)])   # no record = unknown, not 0
        pc = next(e for e in b["events"] if e["ev"] == "PreCompact")["hooks"]
        self.assertEqual([(h["n"], h["quiet"]) for h in pc], [(None, 1), (None, 1)])   # event total never borrowed

    def test_effects(self):
        b = self._body()
        self.assertEqual([self._hook(b, e)["eff"] for e in ("UserPromptSubmit", "PreToolUse", "Stop", "SessionStart")],
                         ["inject", "block", "log", "unknown"])

    def test_binary_and_outside_roots(self):
        cd = os.path.join(self.tmp, "claude", "hooks")
        with open(os.path.join(cd, "bin"), "wb") as f:
            f.write(b"\xca\xfe\xba\xbe\0\0\0\2additionalContext")
        out = os.path.join(self.tmp, "elsewhere.py")   # outside ~/.claude · data dir · project
        _w(out, 'print("additionalContext")\n')
        self.assertEqual(H.effect(os.path.join(cd, "bin"), self.proj), "bin")
        self.assertEqual(H.effect(out, self.proj), "ext")
        self.assertEqual(H.effect(os.path.join(self.tmp, "nope.py"), self.proj), "unknown")

    def test_secrets_basename_only(self):
        b = self._body()
        self.assertEqual(self._hook(b, "UserPromptSubmit")["cmd"], "inject.py")
        self.assertEqual(self._hook(b, "SessionStart")["cmd"], "missing.sh")
        self.assertEqual(self._hook(b, "Zeta")["cmd"], TV.MASK)
        blob = json.dumps(b["events"])   # rule paths and proj carry the tmp dir by design; hook rows never do
        for bad in ("xyzzy", "secret", "FOO", "/usr/bin", self.tmp):   # ⚠fixture secret must not be hex: rows carry hex "ch" hashes
            self.assertNotIn(bad, blob)

    def test_cmd_name_masks_inline_code(self):
        for c in ('node -e "if(/x/.test(cmd)){console.error(\'SENTINEL_X\')}"', 'bash -c "jq -r .x | grep SENTINEL_X"'):
            self.assertEqual(H.cmd_name(c), TV.MASK)
        self.assertEqual(H.cmd_name("python3 /a/b/hook.py --x"), "hook.py")

    def test_agents_rules_counts(self):
        b = self._body()
        ag = {a["name"]: a for a in b["agents"]}
        self.assertEqual((ag["designer"]["scope"], ag["designer"]["n"], ag["designer"]["pipes"]),
                         ("project", 4, [{"pipe": "demo", "stage": "설계"}]))
        self.assertEqual(ag["verifier"]["scope"], "")
        self.assertEqual(sorted(s["stage"] for s in ag["verifier"]["pipes"]), ["검증", "재검증"])
        self.assertEqual([r["order"] for r in b["rules"]], [1, 2])
        self.assertEqual(sorted(b["counts"]), ["cmd", "mcp", "skill"])
        self.assertFalse(b["scanning"])

    def test_metadata_only(self):
        tp = os.path.join(self.tmp, "projects", "-p", "s.jsonl")
        _w(tp, json.dumps({"type": "attachment", "uuid": "u", "attachment": {"type": "hook_success", "hookName": "Stop",
                           "content": SENTINEL, "stdout": SENTINEL}}) + "\n")
        blob = json.dumps(self._body(), ensure_ascii=False)
        self.assertNotIn(SENTINEL, blob)
        self.assertNotIn("secret-task-text", blob)
        self.assertNotIn("additionalContext", blob)

    def test_header_desc(self):
        hk = os.path.join(self.tmp, "claude", "hooks")
        cases = {
            "doc.py": ('#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\n"""**Inject** the `quota` line.\n\nMore.\n"""\n', "Inject the quota line."),
            "doc2.py": ('"""\n  Second   line  starts here\n"""\n', "Second line starts here"),
            "hash.sh": ("#!/bin/bash\n#\n#   'Log every stop'\n# more\necho x\n", "Log every stop"),
            "slash.js": ("#!/usr/bin/env node\n//\n// Guard the edit tool\nconsole.log(1)\n", "Guard the edit tool"),
            "code.py": ("import os  # not a header\n", ""),
            "sec.sh": ("# API_TOKEN=abcdef0123456789abcdef0123\n", ""),  # gitleaks:allow
            "long.py": ("# " + "x" * 300 + "\n", "x" * (H.HN_DESC_MAX - 1) + "…"),
        }
        for nm, (src, want) in cases.items():
            _w(os.path.join(hk, nm), src)
            self.assertEqual(H._scan(os.path.join(hk, nm), self.proj)[1], want, nm)
        out = os.path.join(self.tmp, "elsewhere.py")   # outside the readable roots: never opened
        _w(out, "# Outside header\n")
        self.assertEqual(H._scan(out, self.proj), ("ext", ""))
        b = self._body()
        self.assertTrue(all(h["desc"] == "" for e in b["events"] for h in e["hooks"]))

    def test_plugin_desc_fallback(self):
        cd = os.path.join(self.tmp, "claude")
        root = os.path.join(cd, "plugins", "cache", "mk", "demo", "1.0.0")
        _w(os.path.join(root, ".claude-plugin", "plugin.json"), {"description": "Demo `plugin` " + "y" * 200})
        _w(os.path.join(root, "hooks", "run.py"), "print(1)\n")
        _w(os.path.join(root, "hooks", "hdr.py"), "# Own header\n")
        hf = os.path.join(root, "hooks", "hooks.json")
        g = lambda s: {"hooks": [{"type": "command", "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/" + s}]}
        items = [{"scope": "plugin", "file": hf, "key": ("hook", "Stop"), "entry": g("run.py")},
                 {"scope": "plugin", "file": hf, "key": ("hook", "Stop"), "entry": g("hdr.py")}]
        rows = next(e for e in H._hook_rows(items, self.proj, {}) if e["ev"] == "Stop")["hooks"]
        self.assertEqual(rows[0]["desc"], ("Demo plugin " + "y" * 200)[:H.HN_DESC_MAX - 1] + "…")
        self.assertEqual(rows[1]["desc"], "Own header")
        self.assertEqual(rows[0]["plug"], "demo")

    def test_open_refs(self):
        b = self._body()
        refs = {e["ev"]: e["hooks"][0]["open"] for e in b["events"] if e["hooks"]}
        self.assertEqual(refs["PreToolUse"], "h:PreToolUse:0")
        self.assertEqual((refs["SessionStart"], refs["Zeta"]), ("", ""))   # unknown effect: not clickable
        code, f = H.harness_file(self.proj, refs["PreToolUse"])
        self.assertEqual((code, f["name"], f["lang"]), (200, "block.py", "python"))
        self.assertIn("sys.exit(2)", f["text"])
        self.assertNotIn(self.tmp, json.dumps(b["events"]))
        r = H.harness_file(self.proj, b["rules"][1]["open"])
        self.assertEqual((r[0], r[1]["text"]), (200, "proj rules\n"))
        ag = next(a for a in b["agents"] if a["name"] == "designer")
        self.assertEqual(H.harness_file(self.proj, ag["open"])[1]["name"], "designer.md")
        self.assertEqual(next(a for a in b["agents"] if a["name"] == "verifier")["open"], "")

    def test_hook_script_redacted(self):
        gh, sk = "ghp_" + "A1b2C3d4E5f6G7h8", "sk-ant-api03-" + "Zz9Yy8Xx7Ww6Vv5"
        with open(os.path.join(self.tmp, "claude", "hooks", "block.py"), "a", encoding="utf-8") as f:
            f.write("TOK = '%s'\nK = '%s'\nsys.exit(2)\n" % (gh, sk))
        code, f = H.harness_file(self.proj, "h:PreToolUse:0")
        self.assertEqual(code, 200)
        self.assertNotIn(gh, f["text"])
        self.assertNotIn(sk, f["text"])
        self.assertIn("ghp_", f["text"])

    def test_open_refused(self):
        hk = os.path.join(self.tmp, "claude", "hooks")
        out = os.path.join(self.tmp, "elsewhere.py")
        _w(out, "print(1)\n")
        with open(os.path.join(hk, "bin"), "wb") as f:
            f.write(b"\xca\xfe\xba\xbe\0\0")
        cfg = os.path.join(self.tmp, "claude", "settings.json")
        _w(cfg, {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "python3 " + out},
                                               {"type": "command", "command": os.path.join(hk, "bin")}]}]}})
        b = self._body()
        st = next(e for e in b["events"] if e["ev"] == "Stop")["hooks"]
        self.assertEqual([(h["eff"], h["open"]) for h in st], [("ext", ""), ("bin", "")])
        self.assertEqual(H.harness_file(self.proj, "h:Stop:0")[0], 404)   # outside the roots even when asked directly
        self.assertEqual(H.harness_file(self.proj, "h:Stop:1")[0], 404)
        for bad in ("", "x", "h:Stop", "r:-1", "a:../x", "/etc/passwd", "h:Stop:0/../1"):
            self.assertEqual(H.harness_file(self.proj, bad)[0], 400, bad)
        self.assertEqual(H.harness_file(self.proj, "r:99")[0], 404)
        self.assertEqual(H.harness_file(self.proj, "a:nobody")[0], 404)
        self.assertEqual(H.harness_file("/elsewhere", "r:0")[0], 400)
        big = os.path.join(self.proj, ".claude", "agents", "big.md")
        _w(big, "x" * (H.HN_FILE_MAX + 1))
        self.assertEqual(H.harness_file(self.proj, "a:big")[0], 413)
        _w(big, "a\0b")
        self.assertEqual(H.harness_file(self.proj, "a:big")[0], 415)
        out = os.path.join(self.tmp, "outside.md")   # symlinked agent pointing outside the roots
        _w(out, "secret\n")
        os.symlink(out, os.path.join(self.proj, ".claude", "agents", "link.md"))
        self.assertEqual(H.harness_file(self.proj, "a:link")[0], 404)

    def _mcp_fixture(self):
        cd = os.path.join(self.tmp, "claude")
        sec = {"env": {"API_KEY": SENTINEL}, "headers": {"Authorization": SENTINEL}}
        _w(os.path.join(self.tmp, "cj.json"), {"mcpServers": {"web": dict(sec, type="http", url="https://x/?token=" + SENTINEL)}})
        _w(os.path.join(self.proj, ".mcp.json"), {"mcpServers": {
            "local": dict(sec, command="node", args=["--api-key", SENTINEL]), "off": {"command": "x"}}})
        _w(os.path.join(self.proj, ".claude", "settings.local.json"), {"disabledMcpjsonServers": ["off"]})
        root = os.path.join(cd, "plugins", "cache", "mk", "demo", "1.0.0")
        _w(os.path.join(root, ".mcp.json"), {"mcpServers": {"pm": dict(sec, type="sse", url="https://y/" + SENTINEL)}})
        _w(os.path.join(root, "skills", "pk", "SKILL.md"), "---\nname: pk\n---\nplugin skill\n")
        _w(os.path.join(cd, "plugins", "installed_plugins.json"), {"plugins": {"demo@mk": [{"installPath": root}]}})
        _w(os.path.join(cd, "skills", "us", "SKILL.md"), "---\nname: us\n---\nuser skill\n")
        _w(os.path.join(self.proj, ".claude", "skills", "ps", "SKILL.md"), "project skill\n")
        H.tool_uses = lambda d: {"mcp:local": {"n": 2, "last": 7}, "mcp:web": {"n": 5, "last": 3},
                                 "mcp:pm": {"n": 1, "last": 4}, "mcp:plugin_demo_pm": {"n": 3, "last": 9},
                                 "skill:us": {"n": 6, "last": 11}, "skill:demo:pk": {"n": 1, "last": 2}}

    def test_mcps_fields_and_no_secret(self):
        self._mcp_fixture()
        b = self._body()
        self.assertEqual([m["name"] for m in b["mcps"]], ["web", "pm", "local", "off"])   # on first, then n desc
        m = {x["name"]: x for x in b["mcps"]}
        self.assertEqual(m["web"], {"name": "web", "scope": "user", "plug": "", "transport": "http", "on": True, "n": 5, "last": 3,
                                  "status": "none", "err": "", "fail_at": 0, "ok_at": 0})
        self.assertEqual((m["pm"]["scope"], m["pm"]["plug"], m["pm"]["transport"], m["pm"]["n"], m["pm"]["last"]),
                         ("plugin", "demo", "sse", 4, 9))   # summed across both key forms
        self.assertEqual((m["local"]["transport"], m["local"]["n"], m["off"]["on"], m["off"]["n"]), ("stdio", 2, False, 0))
        self.assertEqual(b["counts"]["mcp"], 3)
        blob = json.dumps(b, ensure_ascii=False)
        for bad in (SENTINEL, "API_KEY", "Authorization", "https://", "--api-key"):
            self.assertNotIn(bad, blob)

    def test_mcp_status_rows(self):
        self._mcp_fixture()
        H.mcp_status = lambda d: {"mcp:local": {"status": "fail", "err": "CONNECT_TIMEOUT", "fail_at": 8, "ok_at": 7},
                                  "mcp:plugin_demo_pm": {"status": "ok", "err": "", "fail_at": 2, "ok_at": 9}}
        b = self._body()
        self.assertEqual([m["name"] for m in b["mcps"]], ["local", "web", "pm", "off"])   # failed first
        m = {x["name"]: x for x in b["mcps"]}
        self.assertEqual((m["local"]["status"], m["local"]["err"], m["local"]["fail_at"]), ("fail", "CONNECT_TIMEOUT", 8))
        self.assertEqual((m["pm"]["status"], m["web"]["status"]), ("ok", "none"))

    def test_skills_and_open(self):
        self._mcp_fixture()
        b = self._body()
        sk = {s["name"]: s for s in b["skills"]}
        self.assertEqual(b["skills"][0]["name"], "us")
        self.assertEqual((sk["us"]["scope"], sk["us"]["n"], sk["us"]["last"], sk["us"]["plug"]), ("user", 6, 11, ""))
        self.assertEqual((sk["demo:pk"]["scope"], sk["demo:pk"]["plug"], sk["demo:pk"]["n"]), ("plugin", "demo", 1))
        self.assertEqual(sk["ps"]["scope"], "project")
        self.assertNotIn(self.tmp, json.dumps(b["skills"]))
        for nm, want in (("us", "user skill"), ("demo:pk", "plugin skill"), ("ps", "project skill")):
            code, f = H.harness_file(self.proj, sk[nm]["open"])
            self.assertEqual((code, f["name"]), (200, "SKILL.md"), nm)
            self.assertIn(want, f["text"])
        self.assertEqual(H.harness_file(self.proj, "s:999")[0], 404)
        for bad in ("s:", "s:us", "s:-1", "s:0/../1"):
            self.assertEqual(H.harness_file(self.proj, bad)[0], 400, bad)

    def test_skill_stage_refs(self):
        self._mcp_fixture()
        _w(os.path.join(self.proj, ".claude", "pipelines", "sk.json"), {"v": 1, "name": "sk", "title": "t", "defaults": {"model": "inherit", "retry": 0}, "stages": [
            {"title": "만들기", "agent": "impl", "task": "x", "skill": "us"}, {"title": "유령", "agent": "impl", "task": "x", "skill": "ghost"}]})
        H.tool_uses = lambda d: {"skill:us": {"n": 6, "last": 11}, "skill:ghost": {"n": 2, "last": 3}}
        b = self._body()
        sk = {s["name"]: s for s in b["skills"]}
        self.assertEqual(sk["us"]["pipes"], [{"pipe": "sk", "stage": "만들기"}])
        self.assertEqual((sk["ps"]["pipes"], sk["demo:pk"]["pipes"]), ([], []))
        g = sk["ghost"]
        self.assertEqual((g["open"], g["scope"], g["plug"], g["on"], g["n"], g["last"], g["pipes"]),
                         ("", "", "", True, 2, 3, [{"pipe": "sk", "stage": "유령"}]))
        code, f = H.harness_file(self.proj, sk["us"]["open"])   # open index still the pre-sort one
        self.assertEqual(code, 200)
        self.assertIn("user skill", f["text"])
        ag = {a["name"]: a for a in b["agents"]}
        self.assertIn({"pipe": "sk", "stage": "만들기"}, ag["impl"]["pipes"])
        self.assertEqual(H._stage_refs({"pipelines": [{"name": "p", "stages": [{"title": "a"}, {"title": "b", "skill": ""}]}]}, "skill"), {})

    def test_skill_open_outside_roots_refused(self):
        out = os.path.join(self.tmp, "outside", "SKILL.md")
        _w(out, SENTINEL + "\n")
        d = os.path.join(self.tmp, "claude", "skills", "ln")
        os.makedirs(d)
        os.symlink(out, os.path.join(d, "SKILL.md"))
        b = self._body()
        s = next(x for x in b["skills"] if x["name"] == "ln")
        self.assertEqual(s["open"], "")
        i = [it["name"] for it in H._skill_list(self.proj)].index("ln")
        self.assertEqual(H.harness_file(self.proj, "s:%d" % i)[0], 404)   # refused even when asked directly
        self.assertNotIn(SENTINEL, json.dumps(b))

    def test_unknown_project(self):
        self.assertEqual(H.harness("/elsewhere", 30)[0], 400)
        self.assertEqual(H.harness(self.proj, "x")[0], 400)


if __name__ == "__main__":
    unittest.main()
