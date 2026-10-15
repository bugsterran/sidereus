"""sidereus/pipeline_schema.validate == the runner's validate block (.claude/workflows/pipeline.js, as scripts/pipeline_check.mjs
runs it): boundary cases for every field both check must pass or fail in both. Also every repo pipeline file. No live data."""
import copy
import glob
import json
import os
import shutil
import subprocess
import unittest

from tests._load import ROOT, sidereus
from tests._node import node_e

PS = sidereus("pipeline_schema")
RUNNER = os.path.join(ROOT, ".claude", "workflows", "pipeline.js")

BASE = {"v": 1, "name": "x", "title": "T", "use": "u", "rules": "r", "after": ["a"], "defaults": {"model": "inherit", "retry": 0},
        "guards": {"requireGates": ["검증"], "maxLoopBacks": 3},
        "stages": [{"title": "설계", "agent": "Explore"},
                   {"title": "검증", "agent": "general-purpose", "gate": "bash scripts/check.sh --fast", "skill": "s-1", "task": "t",
                    "model": "opus", "retry": 3, "parallel": 16, "onError": "stop", "ui": {"x": 1, "y": -2, "color": "#a0b1c2"},
                    "onFail": {"goto": "설계", "max": 5, "stopOn": ["unrelated"]}}]}


def _set(path, val):
    def f(P):
        o = P
        for k in path[:-1]:
            o = o[k]
        if val is KeyError:
            del o[path[-1]]
        else:
            o[path[-1]] = val
    return f


def _custom(n):
    def f(P):
        P["stages"] = P["stages"][:1] + [{"title": "c%d" % i, "agent": "a", "task": "t"} for i in range(n)]
        P["guards"] = {}
    return f


S1 = ("stages", 1)
CASES = [  # (label, mutation, expected valid)
    ("base", lambda P: None, True),
    ("v 2", _set(("v",), 2), False), ("v 1.0", _set(("v",), 1.0), True), ("v true", _set(("v",), True), False),
    ("title 80", _set(("title",), "t" * 80), True), ("title 81", _set(("title",), "t" * 81), False),
    ("title astral 40", _set(("title",), "\U0001F600" * 40), True), ("title astral 41", _set(("title",), "\U0001F600" * 41), False),
    ("title empty", _set(("title",), ""), False), ("title nl", _set(("title",), "a\nb"), False),
    ("use 120", _set(("use",), "u" * 120), True), ("use 121", _set(("use",), "u" * 121), False),
    ("use blank", _set(("use",), "  "), False), ("use cr", _set(("use",), "a\rb"), False), ("use null", _set(("use",), None), False),
    ("use absent", _set(("use",), KeyError), True), ("use x1f", _set(("use",), "\x1f"), True), ("use nbsp", _set(("use",), " "), False),
    ("rules 2000", _set(("rules",), "r" * 2000), True), ("rules 2001", _set(("rules",), "r" * 2001), False), ("rules num", _set(("rules",), 1), False),
    ("after 200", _set(("after",), ["a" * 200]), True), ("after 201", _set(("after",), ["a" * 201]), False), ("after str", _set(("after",), "a"), False),
    ("model bad", _set(("defaults", "model"), "gpt"), False), ("retry 4", _set(("defaults", "retry"), 4), False),
    ("no stages", _set(("stages",), []), False),
    ("stage title 40", _set(S1 + ("title",), "검" * 40), False),   # custom: needs its own guard reference fixed
    ("slot title", _set(("stages", 0, "title"), "사용자 단계 1"), False),
    ("custom needs task", _set(("stages", 0, "title"), "custom"), False),
    ("renamed legacy", lambda P: P["stages"].append({"title": "최종 검증", "agent": "a"}), True),
    ("goto legacy title", lambda P: P["stages"].insert(0, {"title": "최종 검증", "agent": "a"}) or P["stages"][2]["onFail"].update(goto="재검증"), True),
    ("legacy+new dup", lambda P: P["stages"].insert(0, {"title": "최종 검증", "agent": "a"}) or P["stages"].insert(0, {"title": "재검증", "agent": "a"}), False),
    ("dup title", _set(("stages", 0, "title"), "검증"), False),
    ("agent 60", _set(("stages", 0, "agent"), "a" * 60), True), ("agent 61", _set(("stages", 0, "agent"), "a" * 61), False),
    ("agent _x", _set(("stages", 0, "agent"), "_x"), False),
    ("skill bad", _set(S1 + ("skill",), "S"), False), ("skill 61", _set(S1 + ("skill",), "s" * 61), False),
    ("task 1000", _set(S1 + ("task",), "t" * 1000), True), ("task 1001", _set(S1 + ("task",), "t" * 1001), False),
    ("stage model", _set(S1 + ("model",), "x"), False), ("stage retry 4", _set(S1 + ("retry",), 4), False),
    ("parallel 17", _set(S1 + ("parallel",), 17), False), ("parallel 0", _set(S1 + ("parallel",), 0), False),
    ("gate 200", _set(S1 + ("gate",), "bash scripts/check.sh --fast " + "x" * 171), True),
    ("gate 201", _set(S1 + ("gate",), "bash scripts/check.sh --fast " + "x" * 172), False),
    ("gate empty", _set(S1 + ("gate",), ""), False),
    ("produces", _set(S1 + ("produces",), "x"), False), ("fanout no producer", _set(S1 + ("fanout",), "slices"), False),
    ("onError", _set(S1 + ("onError",), "retry"), False), ("onlyOnJump str", _set(S1 + ("onlyOnJump",), "y"), False),
    ("first onlyOnJump", _set(("stages", 0, "onlyOnJump"), True), False),
    ("ui extra", _set(S1 + ("ui",), {"x": 1, "y": 1, "z": 1}), False), ("ui far", _set(S1 + ("ui",), {"x": 100001, "y": 0}), False),
    ("ui color", _set(S1 + ("ui",), {"x": 1, "y": 1, "color": "#ABCDEF"}), False), ("ui bool", _set(S1 + ("ui",), {"x": True, "y": 1}), False),
    ("onFail max 6", _set(S1 + ("onFail", "max"), 6), False), ("onFail goto later", _set(S1 + ("onFail", "goto"), "검증"), False),
    ("onFail then earlier", _set(S1 + ("onFail", "then"), "설계"), False), ("stopOn bad", _set(S1 + ("onFail", "stopOn"), ["x"]), False),
    ("guards extra", _set(("guards", "x"), 1), False), ("guards maxLoopBacks 11", _set(("guards", "maxLoopBacks"), 11), False),
    ("requireGates ungraded", _set(("guards", "requireGates"), ["설계"]), False), ("requireGates missing", _set(("guards", "requireGates"), ["없음"]), False),
    ("custom 12", _custom(12), True), ("custom 13", _custom(13), False),
]


def _cases():
    out = []
    for label, f, want in CASES:
        P = copy.deepcopy(BASE)
        f(P)
        out.append((label, P, want))
    return out


def _runner(items):
    js = ("const fs = require('fs'), src = fs.readFileSync(%s, 'utf8');"
          "const T = JSON.parse(src.match(/^const STAGE_TITLES = (\\[.*\\])$/m)[1].replace(/'/g, '\"'));"
          "const M = JSON.parse(src.match(/^const MODELS = (\\[.*\\])$/m)[1].replace(/'/g, '\"'));"
          "const a = src.indexOf('// ---- validate'), b = src.indexOf('\\nif (errs.length)', a);"
          "const v = new Function('P', 'pipelineName', 'STAGE_TITLES', 'MODELS', src.slice(a, b) + '\\nreturn errs');"
          "const input = JSON.parse(fs.readFileSync(0, 'utf8'));"
          "console.log(JSON.stringify(input.map(([n, P]) => v(P, n, T, M))));") % json.dumps(RUNNER)
    r = subprocess.run(node_e(js), input=json.dumps(items, ensure_ascii=False), capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SchemaMirror(unittest.TestCase):
    def test_cases_agree(self):
        cs = _cases()
        js = _runner([["x", P] for _l, P, _w in cs])
        for (label, P, want), je in zip(cs, js):
            pe = PS.validate(P, "x")
            self.assertEqual(not pe, want, (label, pe))
            self.assertEqual(not je, want, (label, je))

    def test_repo_pipelines_agree(self):
        files = sorted(p for p in glob.glob(os.path.join(ROOT, ".claude", "pipelines", "*.json")) if not os.path.basename(p).startswith("_"))
        items = []
        for p in files:
            with open(p, encoding="utf-8") as f:
                items.append([os.path.basename(p)[:-5], json.load(f)])
        for (n, P), je in zip(items, _runner(items)):
            self.assertEqual(PS.validate(P, n), [], n)
            self.assertEqual(je, [], n)


if __name__ == "__main__":
    unittest.main()
