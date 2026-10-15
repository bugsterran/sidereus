"""«컨텍스트 출처» (sidereus/ctxsrc.py): discovery, estimates, counts, validation, no content leakage.
Fixtures live in a temp dir; ctxsrc's path/lookup attributes are patched (never the live ~/.claude)."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import load, sidereus

load()
cx = sidereus("ctxsrc")
SECRET = "SECRET-BODY-TEXT-do-not-leak"


class CtxSrcTest(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-ctx-"))
        t = self.tmp
        self.home = os.path.join(t, "home", ".claude")
        self.repo = os.path.join(t, "work", "repo")
        self.cwd = os.path.join(self.repo, "pkg", "sub")
        os.makedirs(self.cwd)
        os.makedirs(os.path.join(self.repo, ".git"))
        self._w(os.path.join(t, "work", "CLAUDE.md"), "outside git root")      # above the root: not loaded
        self._w(os.path.join(self.home, "CLAUDE.md"), "u" * 700)
        self._w(os.path.join(self.repo, "AGENTS.md"), "a" * 350)
        self._w(os.path.join(self.repo, "pkg", "CLAUDE.local.md"), "l" * 35)
        self._w(os.path.join(self.cwd, "CLAUDE.md"), SECRET)
        self._w(os.path.join(self.repo, ".claude", "rules", "style.md"), SECRET)
        proj = os.path.join(t, "projects")
        mem = os.path.join(proj, cx._slug(self.cwd), "memory")
        self._w(os.path.join(mem, "MEMORY.md"), "m" * 70)
        self._w(os.path.join(mem, "a.md"), SECRET)
        self._w(os.path.join(mem, "b.md"), SECRET)
        cj = os.path.join(t, "home", ".claude.json")
        self._w(cj, json.dumps({"mcpServers": {"ctx7": {"command": SECRET}, "shared": {}},
                                "projects": {self.cwd: {"mcpServers": {"pw": {"env": {"K": SECRET}}}}}}))
        self._w(os.path.join(self.repo, ".mcp.json"), json.dumps({"mcpServers": {"gh": {"args": [SECRET]}, "shared": {}}}))
        self._w(os.path.join(self.home, "settings.json"), json.dumps({"hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": SECRET}, {"type": "command", "command": "x"}]}],
            "PreCompact": [{"matcher": "", "hooks": [{"type": "command", "command": SECRET}]}]}}))
        self._w(os.path.join(self.repo, ".claude", "settings.local.json"),
                json.dumps({"hooks": {"Stop": [{"hooks": [{"command": SECRET}]}], "Bad": "x"}}))
        self._w(os.path.join(self.home, "skills", "one", "SKILL.md"), SECRET)
        os.makedirs(os.path.join(self.home, "skills", "empty"))
        self._w(os.path.join(self.home, "agents", "a.md"), SECRET)
        self._w(os.path.join(self.repo, ".claude", "agents", "b.md"), SECRET)
        self._w(os.path.join(self.repo, ".claude", "agents", "c.md"), SECRET)
        self.saved = {k: getattr(cx, k) for k in ("CLAUDE_DIR", "CLAUDE_JSON", "CLAUDE_PROJECTS", "_git_root",
                                                   "_allowed_cwds", "_past_row")}
        cx.CLAUDE_DIR, cx.CLAUDE_JSON, cx.CLAUDE_PROJECTS = self.home, cj, proj
        cx._git_root = lambda d: self.repo if d.startswith(self.repo) else ""
        cx._allowed_cwds = lambda: {self.cwd: {"cwd": self.cwd}}
        cx._past_row = lambda cwd, sid: None
        cx._ctx_cache.clear()
        cx._cj_memo.clear()

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(cx, k, v)
        cx._ctx_cache.clear()
        cx._cj_memo.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def _w(p, text):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)

    def test_discovery_up_to_git_root(self):
        code, d = cx.session_context(self.cwd, "")
        self.assertEqual(code, 200)
        paths = [r["path"] for r in d["instr"]]
        self.assertEqual(paths, [os.path.join(self.home, "CLAUDE.md"), os.path.join(self.repo, "AGENTS.md"),
                                 os.path.join(self.repo, ".claude", "rules", "style.md"),
                                 os.path.join(self.repo, "pkg", "CLAUDE.local.md"), os.path.join(self.cwd, "CLAUDE.md")])
        self.assertNotIn(os.path.join(self.tmp, "work", "CLAUDE.md"), paths)
        self.assertEqual(d["root"], self.repo)
        self.assertEqual([r["scope"] for r in d["instr"]], ["user", "project", "rule", "local", "project"])

    def test_no_git_root_is_cwd_only(self):
        cx._git_root = lambda d: ""
        d = cx.context_sources(self.cwd)
        self.assertEqual([r["path"] for r in d["instr"]],
                         [os.path.join(self.home, "CLAUDE.md"), os.path.join(self.cwd, "CLAUDE.md")])

    def test_size_and_token_estimate(self):
        d = cx.context_sources(self.cwd)
        by = {os.path.basename(r["path"]): r for r in d["instr"]}
        self.assertEqual((by["AGENTS.md"]["bytes"], by["AGENTS.md"]["tokens"]), (350, 100))
        self.assertEqual(by["CLAUDE.local.md"]["tokens"], 10)
        self.assertEqual(d["memory"]["bytes"], 70)
        self.assertEqual(d["memory"]["tokens"], 20)
        self.assertEqual(d["memory"]["files"], 3)
        total = sum(r["bytes"] for r in d["instr"]) + 70
        self.assertEqual((d["bytes"], d["tokens"]), (total, int(round(total / 3.5))))

    def test_mcp_hooks_skills_agents(self):
        d = cx.context_sources(self.cwd)
        self.assertEqual(d["mcp"], [{"name": "pw", "scope": "local"}, {"name": "gh", "scope": "project"},
                                    {"name": "shared", "scope": "project"}, {"name": "ctx7", "scope": "user"}])
        self.assertEqual(d["hooks"], [{"event": "PreCompact", "n": 1}, {"event": "Stop", "n": 3}])
        self.assertEqual(d["counts"], {"instr": 5, "memory": 3, "mcp": 4, "hooks": 4})
        self.assertEqual(d["skills"], {"user": 1, "project": 0})
        self.assertEqual(d["agents"], {"user": 1, "project": 2})

    def test_no_content_leak(self):
        code, d = cx.session_context(self.cwd, "")
        blob = json.dumps(d, ensure_ascii=False)
        self.assertNotIn(SECRET, blob)
        for ch in ("uuuu", "aaaa", "mmmm"):
            self.assertNotIn(ch, blob)

    def test_validation(self):
        self.assertEqual(cx.session_context("", "")[0], 400)
        self.assertEqual(cx.session_context("relative/path", "")[0], 400)
        self.assertEqual(cx.session_context(self.cwd, "../../etc")[0], 400)
        self.assertEqual(cx.session_context(os.path.join(self.tmp, "work"), "")[0], 400)   # not a session cwd
        self.assertEqual(cx.session_context(self.cwd, "0123abcd-ef")[0], 200)

    def test_cached_per_cwd(self):
        a = cx.session_context(self.cwd, "")[1]
        self._w(os.path.join(self.repo, "CLAUDE.md"), "new")
        self.assertIs(cx.session_context(self.cwd, "")[1], a)
        cx._ctx_cache.clear()
        self.assertEqual(cx.session_context(self.cwd, "")[1]["counts"]["instr"], 6)

    def test_route_registered(self):
        cs = load()
        self.assertEqual(cs.Handler._GET_ROUTES["/api/session/context"].__name__, "_g_session_context")


if __name__ == "__main__":
    unittest.main()
