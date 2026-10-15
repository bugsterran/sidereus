"""«표준 초안» (sidereus/pipeline_std.py + pipeline.py std rows / create std:<key>).

⚠Project and backups live in a tmp dir: `_agents`/`_rule_files`/`_proj_ok`/`BAK_DIR`/`default_tasks` on pipeline are patched.
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import load, sidereus
from tests._node import node_e

load()
PL = sidereus("pipeline")
PN = sidereus("pipeline_new")
STD = sidereus("pipeline_std")
PS = sidereus("pipeline_schema")

ROLE_AGENTS = ["sidereus-designer", "sidereus-implementer", "sidereus-verifier", "sidereus-reviewer"]
FULL = ROLE_AGENTS + ["sidereus-triage", "sidereus-fixer", "sidereus-live", "sidereus-probe"]


def _ag(names):
    return [{"name": n, "scope": "project"} for n in names]


class StdDrafts(unittest.TestCase):
    def setUp(self):
        self.proj = tempfile.mkdtemp()
        self.bak = tempfile.mkdtemp()
        self.agents = []
        self.patches = [mock.patch.object(PL, "_agents", lambda p: _ag(self.agents)),
                        mock.patch.object(PL, "_rule_files", lambda p: ["AGENTS.md"]),
                        mock.patch.object(PL, "_proj_ok", lambda p: p == self.proj),
                        mock.patch.object(PN, "_agents", lambda p: _ag(self.agents)),   # create() imports these by name
                        mock.patch.object(PN, "_proj_ok", lambda p: p == self.proj),
                        mock.patch.object(PL, "default_tasks", lambda: {}),
                        mock.patch.object(PL, "BAK_DIR", self.bak),
                        mock.patch.object(sidereus("prefs"), "CONFIG_PATH", os.path.join(self.bak, "config.local.json"))]   # apply_get: never the live config
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.proj, ignore_errors=True)
        shutil.rmtree(self.bak, ignore_errors=True)

    def _drafts(self, names):
        self.agents = names
        return PL.suggest(self.proj, std=True)

    def test_titles_match_runner(self):
        self.assertEqual(STD._REC, PS.STAGE_TITLES)

    def test_all_validate(self):
        for names in ([], FULL):
            d = self._drafts(names)
            self.assertEqual(len(d), 11, names)
            for x in d:
                self.assertEqual(PS.validate(x["P"], x["name"]), [], x["name"])

    def test_all_validate_in_runner(self):
        # Same extraction as scripts/pipeline_check.mjs: the runner's own validate block, not the Python port.
        runner = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".claude", "workflows", "pipeline.js")
        drafts = [{"name": x["name"], "P": x["P"]} for x in self._drafts(FULL)]
        self.assertTrue({"hook", "skill", "mcp"} <= {x["name"] for x in drafts})
        js = ("const fs = require('fs'), src = fs.readFileSync(%s, 'utf8');"
              "const T = JSON.parse(src.match(/^const STAGE_TITLES = (\\[.*\\])$/m)[1].replace(/'/g, '\"'));"
              "const M = JSON.parse(src.match(/^const MODELS = (\\[.*\\])$/m)[1].replace(/'/g, '\"'));"
              "const a = src.indexOf('// ---- validate'), b = src.indexOf('\\nif (errs.length)', a);"
              "const v = new Function('P', 'pipelineName', 'STAGE_TITLES', 'MODELS', src.slice(a, b) + '\\nreturn errs');"
              "const out = {}; for (const d of %s) out[d.name] = v(d.P, d.name, T, M); console.log(JSON.stringify(out));"
              ) % (json.dumps(runner), json.dumps(drafts, ensure_ascii=False))
        import subprocess
        r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        for name, errs in json.loads(r.stdout).items():
            self.assertEqual(errs, [], name)

    def test_no_agents_all_gp(self):
        for d in self._drafts([]):
            self.assertTrue(all(s["agent"] == "general-purpose" for s in d["P"]["stages"]))
            self.assertEqual(d["gp"], [s["title"] for s in d["P"]["stages"]])

    def test_roles_map(self):
        want = {"P": "sidereus-designer", "B": "sidereus-implementer", "C": "sidereus-verifier", "R": "sidereus-reviewer"}
        for d in self._drafts(ROLE_AGENTS):
            role = {c["title"]: c["role"] for c in d["chain"]}
            for s in d["P"]["stages"]:
                r = role[s["title"]]
                self.assertEqual(s["agent"], want.get(r, "general-purpose"), (d["name"], s["title"]))
                self.assertEqual(s["title"] in d["gp"], r not in want)
                if r == "C":
                    self.assertEqual(s.get("model"), "sonnet")

    def test_saved_pipeline_agents_and_fix_fallback(self):
        # ★2026-10-01 cart-api: global agents only (cart-api-*), review/live agents outside that family but used by its bugfix.json
        os.makedirs(os.path.join(self.proj, ".claude", "pipelines"))
        with open(os.path.join(self.proj, ".claude", "pipelines", "bugfix.json"), "w", encoding="utf-8") as f:
            f.write('{"v":1,"name":"bugfix","stages":[{"title":"수정","agent":"p-bugfix"},{"title":"리뷰","agent":"x-code-review"},{"title":"라이브 검증","agent":"x-live-verify"}]}')
        self.agents = ["p-bugfix", "x-code-review", "x-live-verify"]
        with mock.patch.object(PL, "_agents", lambda p: [{"name": n, "scope": "global"} for n in self.agents]):
            d = {x["name"]: x for x in PL.suggest(self.proj, std=True)}
        st = {s["title"]: s["agent"] for s in d["bugfix"]["P"]["stages"]}
        self.assertEqual((st["재현"], st["원인"], st["수정"], st["리뷰"]), ("p-bugfix", "p-bugfix", "p-bugfix", "x-code-review"))
        self.assertNotIn("리뷰", d["bugfix"]["gp"])

    def test_fix_first(self):
        d = {x["name"]: x for x in self._drafts(FULL)}
        agent = lambda k, t: next(s["agent"] for s in d[k]["P"]["stages"] if s["title"] == t)
        self.assertEqual(agent("bugfix", "수정"), "sidereus-fixer")
        self.assertEqual(agent("feature", "구현"), "sidereus-implementer")

    def test_tasks(self):
        for d in self._drafts(FULL):
            for s in d["P"]["stages"]:
                if s["title"] in PS.STAGE_TITLES:
                    self.assertNotIn("task", s)
                else:
                    self.assertTrue(0 < len(s["task"]) <= 300, s["title"])
            self.assertLessEqual(sum(1 for s in d["P"]["stages"] if s["title"] not in PS.STAGE_TITLES), PS.CUSTOM_MAX)

    def test_optional_chain_only(self):
        d = {x["name"]: x for x in self._drafts(FULL)}
        for key, t in (("bugfix", "라이브 검증"), ("perf", "리뷰"), ("security", "재현"), ("review", "지적 검증")):
            self.assertIn({"title": t, "role": next(c["role"] for c in d[key]["chain"] if c["title"] == t), "opt": True}, d[key]["chain"])
            self.assertNotIn(t, [s["title"] for s in d[key]["P"]["stages"]])

    def test_goto_earlier(self):
        for d in self._drafts(FULL):
            titles = [s["title"] for s in d["P"]["stages"]]
            for i, s in enumerate(d["P"]["stages"]):
                if "onFail" in s:
                    self.assertLess(titles.index(s["onFail"]["goto"]), i)
                    self.assertLessEqual(s["onFail"]["max"], 2)

    def test_get_std_rows(self):
        self.agents = FULL
        code, out = PL.pipelines(self.proj)
        self.assertEqual(code, 200)
        self.assertEqual(len(out["std"]), 11)
        r = out["std"][0]
        self.assertTrue(r["std"] and r["ok"] and r["src"].startswith("https://"))
        self.assertTrue({"name", "title", "rules", "defaults", "stages", "after", "chain", "gp"} <= set(r))

    def test_create(self):
        code, out = PN.create({"proj": self.proj, "name": "fix-it", "title": "버그", "template": "std:bugfix", "dry": True,
                               "stages": [{"title": "evil", "agent": "x"}]})
        self.assertEqual(code, 200)
        self.assertIn("+++ b/.claude/pipelines/fix-it.json", out["diff"])
        self.assertNotIn("evil", out["diff"])
        self.assertEqual(out["replaced"], ["재현", "원인", "실패 테스트", "수정", "검증", "리뷰"])
        code, out = PN.create({"proj": self.proj, "name": "fix-it", "title": "버그", "template": "std:bugfix", "dry": False})
        self.assertEqual(code, 200)
        with open(os.path.join(self.proj, ".claude", "pipelines", "fix-it.json"), encoding="utf-8") as f:
            P = json.load(f)
        self.assertEqual((P["name"], P["title"]), ("fix-it", "버그"))
        self.assertEqual(PS.validate(P, "fix-it"), [])
        self.assertEqual(PN.create({"proj": self.proj, "name": "y", "template": "std:x", "dry": True})[0], 400)


if __name__ == "__main__":
    unittest.main()
