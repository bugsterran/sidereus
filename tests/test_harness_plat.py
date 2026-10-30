"""Harness map per platform (sidereus/harness_plat.py + plat_codex/plat_gemini harness_items): lanes, transports,
rule order, plats detection, refs. Fixture homes live in a temp dir; `root` is patched on the plat modules."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import load, sidereus

load()
HP = sidereus("harness_plat")
H = sidereus("harness")
CX = sidereus("plat_codex")
GM = sidereus("plat_gemini")
CS = sidereus("ctxsrc")
SECRET = "SENTINEL-sk-9f8e7d"  # gitleaks:allow


def _w(p, body):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:   # LF fixture on Windows too
        f.write(body if isinstance(body, str) else json.dumps(body))


class HarnessPlatTest(unittest.TestCase):
    def setUp(self):
        t = self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-hp-"))
        cx, gm, self.repo = os.path.join(t, "codex"), os.path.join(t, "gemini"), os.path.join(t, "repo")
        self.proj = os.path.join(self.repo, "sub", "proj")
        _w(os.path.join(cx, "hooks", "inject.py"), 'print({"additionalContext": 1})\n')
        _w(os.path.join(t, "out", "far.py"), "x = 1\n")
        hook = lambda c, **kw: [dict({"hooks": [dict({"type": "command", "command": c}, **kw)]})]
        _w(os.path.join(cx, "hooks.json"), {"hooks": {
            "PreToolUse": hook("SECRET_TOKEN=%s python3 %s --key %s" % (SECRET, os.path.join(cx, "hooks", "inject.py"), SECRET), timeout=5),
            "Interrupt": hook("python3 " + os.path.join(t, "out", "far.py")),
            "PermissionRequest": hook("true"), "SessionEnd": hook("true"), "Weird": hook("true")}})
        _w(os.path.join(cx, "config.toml"), "\n".join([
            'model = "x"', '[mcp_servers.local]', 'command = "node"', 'args = ["--token", "%s"]' % SECRET,
            '[mcp_servers.local.env]', 'API_KEY = "%s"' % SECRET, 'enabled = false',
            '[mcp_servers."web.api"]', 'url = "https://h/?t=%s"' % SECRET, 'enabled = false  # off',
            '[profiles.x]', 'command = "nope"', '']))
        _w(os.path.join(cx, "AGENTS.md"), "u\n")
        _w(os.path.join(cx, "prompts", "ship.md"), "p\n")
        _w(os.path.join(self.repo, "AGENTS.md"), "root\n")
        _w(os.path.join(self.proj, "AGENTS.md"), "proj\n")
        _w(os.path.join(gm, "settings.json"), {
            "hooksConfig": {"enabled": True}, "mcp": {"excluded": ["gone"]},
            "mcpServers": {"s": {"command": "x", "env": {"K": SECRET}}, "u": {"url": "https://%s" % SECRET},
                           "h": {"httpUrl": "https://x", "headers": {"Authorization": SECRET}}, "gone": {"command": "y"}},
            "hooks": {"BeforeTool": [{"matcher": ".*", "hooks": [{"type": "command", "command": "python3 x.py", "timeout": 5000}]}],
                      "PreCompress": hook("true"), "BeforeModel": hook("true")}})
        _w(os.path.join(gm, "GEMINI.md"), "g\n")
        _w(os.path.join(gm, "extensions", "ext1", "gemini-extension.json"), {"mcpServers": {"em": {"command": "z", "args": [SECRET]}}})
        _w(os.path.join(gm, "commands", "git", "pr.toml"), 'prompt = "x"\n')
        _w(os.path.join(gm, "agents", "rev.md"), "agent\n")
        _w(os.path.join(gm, "skills", "sk", "SKILL.md"), "skill\n")
        _w(os.path.join(self.proj, "GEMINI.md"), "gp\n")
        os.symlink(os.path.join(t, "out", "far.py"), os.path.join(gm, "agents", "link.md"))
        self.saved = [(CX, "root", CX.root), (GM, "root", GM.root), (HP, "_proj_ok", HP._proj_ok), (HP, "DATA_DIR", HP.DATA_DIR),
                      (CS, "_git_root", CS._git_root), (HP, "_real_home", HP._real_home)]
        CX.root, GM.root = (lambda: cx), (lambda: gm)
        HP._proj_ok = lambda p: p == self.proj
        HP.DATA_DIR = os.path.join(t, "data")
        CS._git_root = lambda p: self.repo
        HP._real_home = lambda: t
        self.cx, self.gm = cx, gm
        H._EFF_CACHE.clear()

    def tearDown(self):
        for mod, k, v in self.saved:
            setattr(mod, k, v)
        H._EFF_CACHE.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _body(self, plat):
        code, b = HP.harness_plat(plat, self.proj, 30)
        self.assertEqual(code, 200, b)
        return b

    def test_lane_values_in_events(self):
        for m in (CX, GM):
            self.assertTrue(set(m.LANE.values()) <= set(H.EVENTS) | {""}, m.KEY)

    def test_codex_lanes_and_effects(self):
        b = self._body("cx")
        lanes = [(e["ev"], e["lane"]) for e in b["events"]]
        self.assertEqual(lanes, [("PreToolUse", "PreToolUse"), ("Interrupt", "Stop"), ("PermissionRequest", "Notification"),
                                 ("SessionEnd", ""), ("Weird", "")])
        h = b["events"][0]["hooks"][0]
        self.assertEqual((h["cmd"], h["eff"], h["timeout"], h["n"], h["last"]), ("inject.py", "inject", 5, None, None))
        self.assertTrue(h["open"])
        far = b["events"][1]["hooks"][0]
        self.assertEqual((far["eff"], far["open"]), ("ext", ""))   # outside the roots: never opened

    def test_codex_mcp_rules_cmds(self):
        b = self._body("cx")
        m = {x["name"]: x for x in b["mcps"]}
        self.assertEqual(set(m), {"local", "web.api"})
        self.assertEqual((m["local"]["transport"], m["local"]["on"]), ("stdio", True))   # enabled under .env is env's
        self.assertEqual((m["web.api"]["transport"], m["web.api"]["on"], m["web.api"]["status"]), ("http", False, ""))
        self.assertEqual([r["path"].split(os.sep)[-2:] for r in b["rules"]],
                         [["codex", "AGENTS.md"], ["repo", "AGENTS.md"], ["proj", "AGENTS.md"]])
        self.assertEqual(b["counts"], {"skill": 0, "cmd": 1, "mcp": 1})
        self.assertEqual((b["plat"], b["scanning"]), ("cx", False))

    def test_gemini_rows(self):
        b = self._body("gm")
        lanes = dict((e["ev"], e["lane"]) for e in b["events"])
        self.assertEqual(lanes, {"BeforeTool": "PreToolUse", "PreCompress": "PreCompact", "BeforeModel": ""})
        self.assertEqual(b["events"][0]["hooks"][0]["timeout"], 5.0)   # ms -> s
        m = {x["name"]: x for x in b["mcps"]}
        self.assertEqual({k: v["transport"] for k, v in m.items()}, {"s": "stdio", "u": "sse", "h": "http", "gone": "stdio", "em": "stdio"})
        self.assertEqual((m["gone"]["on"], m["em"]["scope"], m["em"]["plug"]), (False, "plugin", "ext1"))
        self.assertEqual([r["path"].split(os.sep)[-2:] for r in b["rules"]], [["gemini", "GEMINI.md"], ["proj", "GEMINI.md"]])
        self.assertEqual(b["counts"], {"skill": 1, "cmd": 1, "mcp": 4})
        ag = {a["name"]: a for a in b["agents"]}
        self.assertTrue(ag["rev"]["open"])
        self.assertEqual(ag["link"]["open"], "")   # symlink pointing outside the roots

    def test_no_secret(self):
        for p in ("cx", "gm"):
            blob = json.dumps(self._body(p), ensure_ascii=False)
            for bad in (SECRET, "API_KEY", "Authorization", "https://", "--token", "--key"):
                self.assertNotIn(bad, blob, p)

    def test_plats_and_bad_plat(self):
        self.assertEqual(sorted(HP.plats()), ["cc", "cx", "gm"])
        shutil.rmtree(self.cx)
        self.assertNotIn("cx", HP.plats())
        self.assertEqual(HP.harness_plat("zz", self.proj)[0], 400)
        self.assertEqual(HP.harness_plat("gm", "/nope")[0], 400)
        self.assertEqual(HP.harness_plat_file("zz", self.proj, "r:0")[0], 400)

    def test_file_refs(self):
        b = self._body("cx")
        code, f = HP.harness_plat_file("cx", self.proj, b["events"][0]["hooks"][0]["open"])
        self.assertEqual((code, f["name"]), (200, "inject.py"))
        self.assertEqual(HP.harness_plat_file("cx", self.proj, "r:2")[1]["text"], "proj\n")
        self.assertEqual(HP.harness_plat_file("cx", self.proj, "h:Interrupt:0")[0], 404)   # outside roots
        self.assertEqual(HP.harness_plat_file("cx", self.proj, "r:9")[0], 404)
        self.assertEqual(HP.harness_plat_file("gm", self.proj, "a:link")[0], 404)
        self.assertEqual(HP.harness_plat_file("cx", self.proj, "../x")[0], 400)

    def test_config_files_never_openable(self):
        roots = HP._roots(CX, self.proj)
        for p in (os.path.join(self.cx, "config.toml"), os.path.join(self.gm, "settings.json"), os.path.join(self.cx, "hooks.json")):
            self.assertFalse(HP._openable(p, self.proj, roots), p)
        os.symlink(os.path.join(self.gm, "settings.json"), os.path.join(self.proj, "AGENTS.md.lnk"))
        self.assertFalse(HP._openable(os.path.join(self.proj, "AGENTS.md.lnk"), self.proj, HP._roots(GM, self.proj)))

    def test_cc_passthrough(self):
        saved = H.harness
        H.harness = lambda proj, days: (200, {"ok": True, "events": []})
        try:
            code, b = HP.harness_plat("", self.proj)
        finally:
            H.harness = saved
        self.assertEqual((code, b["plat"], b["plats"][0]), (200, "cc", "cc"))

    def test_trail_rides_body_one_evidence_read(self):
        """One scan feeds evidence (30) + report (every row) + guards; the 7-node flow is gone (R5)."""
        calls, reports, guards = [], [], []
        saved = (H.harness, HP.harness_evidence.scan, HP.harness_trail.trail, HP.harness_trail.report, HP.harness_flow.guards)
        H.harness = lambda proj, days: (200, {"ok": True, "events": []})
        HP.harness_evidence.scan = lambda proj: calls.append(proj) or ([{"ts": i} for i in range(500)], 77.0)
        HP.harness_trail.trail = lambda *a, **k: self.fail("trail() has no page reader; it spawns git")
        HP.harness_trail.report = lambda rows, repo, git=True: reports.append((len(rows), repo)) or {"counts": {}}
        HP.harness_flow.guards = lambda proj, runs=None: guards.append(proj) or {"runs": 0}
        try:
            for plat in ("cc", "cx"):
                del calls[:]
                code, b = HP.harness_plat(plat, self.proj)
                self.assertEqual(code, 200, b)
                self.assertEqual((b["report"]["counts"], b["guards"]), ({"person": 0}, {"runs": 0}))   # R1: no catch=person file
                self.assertEqual(b["report"]["person"], {"pipes": [], "runs": 0, "cards": [], "git": False})
                self.assertEqual((len(calls), len(b["evidence"])), (1, 30))
                self.assertEqual((reports[-1], guards[-1]), ((500, self.proj), self.proj))
                self.assertNotIn("flow", b)
                self.assertNotIn("trail", b)
        finally:
            H.harness, HP.harness_evidence.scan, HP.harness_trail.trail, HP.harness_trail.report, HP.harness_flow.guards = saved

    def test_person_joins_report_copy(self):
        """R1: counts.person + person ride the report; the cached report dict is never mutated."""
        saved = (H.harness, HP.harness_trail.report, HP.harness_person.person)
        cached = {"counts": {"caught": 2}, "incidents": []}
        H.harness = lambda proj, days: (200, {"ok": True, "events": []})
        HP.harness_trail.report = lambda rows, repo, git=True: cached
        HP.harness_person.person = lambda proj, git=True: {"pipes": ["quick-fix"], "runs": 3, "cards": [], "git": True}
        try:
            for plat in ("cc", "cx"):
                rep = self._body(plat)["report"]
                self.assertEqual(rep["counts"], {"caught": 2, "person": 3})
                self.assertEqual(rep["person"]["runs"], 3)
            self.assertEqual(cached, {"counts": {"caught": 2}, "incidents": []})
        finally:
            H.harness, HP.harness_trail.report, HP.harness_person.person = saved

    def test_demo_carries_person_cards(self):
        """R1/R4: the demo report has counts.person and cards with and without tests."""
        from sidereus import demo
        rep = demo._demo_harness(1e9, "/api/harness")[1]["report"]
        p = rep["person"]
        self.assertEqual((rep["counts"]["person"], p["runs"], len(p["cards"])), (3, 3, 3))
        self.assertEqual([len(c["commits"]) for c in p["cards"]], [2, 1, 1])
        self.assertEqual([c["tests"] for c in p["cards"]], [["tests/test_timeline_gap.py"], [], ["tests/test_quota_reset.py"]])

    def test_runtime_card_every_platform(self):
        """runtime = sec_runtime.view of arch/deps-last.json, read from the patched ARCH_DIR only (none + cmd when absent)."""
        saved = (H.harness, HP.arch_verify.ARCH_DIR)
        H.harness = lambda proj, days: (200, {"ok": True, "events": []})
        HP.arch_verify.ARCH_DIR = os.path.join(self.tmp, "arch")
        try:
            for plat in ("cc", "cx"):
                rt = self._body(plat)["runtime"]
                self.assertEqual((rt["state"], rt["items"]), ("none", []), plat)
                self.assertIn("--category security --dev", rt["cmd"])
            sidereus("sec_runtime").write(HP.arch_verify.ARCH_DIR, {"at": 1.0, "report": "", "dev": False, "offline": True,
                                                                     "items": []})
            for plat in ("cc", "cx"):
                rt = self._body(plat)["runtime"]
                self.assertEqual((rt["state"], rt["offline"], rt["stale"]), ("unknown", True, True), plat)
        finally:
            H.harness, HP.arch_verify.ARCH_DIR = saved

    def test_evidence_only_commits_limit_60(self):
        calls = []
        saved = (HP.harness_evidence.recent, HP.harness_evidence.commits)
        HP.harness_evidence.recent = lambda proj, limit=30: calls.append(limit) or []
        HP.harness_evidence.commits = lambda proj: [{"h": "abcdef1", "ct": 5}]
        try:
            code, b = HP.harness_evidence_only(self.proj)
        finally:
            HP.harness_evidence.recent, HP.harness_evidence.commits = saved
        self.assertEqual((code, calls, b["commits"]), (200, [60], [{"h": "abcdef1", "ct": 5}]))


if __name__ == "__main__":
    unittest.main()
