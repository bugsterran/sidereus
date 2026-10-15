"""«Stage catalog» (sidereus/stage_catalog.py + stage_catalog.json): every shipped template validates as a stage, bad templates are
dropped, `{sidereus}` is filled, `task` goes out as `instr`, tool availability comes from a patched `which` only."""
import json
import os
import re
import subprocess
import tempfile
import unittest

from sidereus import pipeline_schema, stage_catalog
from tests._load import ROOT, js_all
from tests._node import node_e

GOOD = {"id": "lint", "group": "quality", "title": {"ko": "린트", "en": "Lint"}, "role": "check", "model": "sonnet",
        "task": "Run {sidereus}/scripts/x.py once.", "gate": "python3 {sidereus}/scripts/x.py --verify", "gateHint": "", "asserts": "1+ files",
        "loop": {"to": ["구현"], "max": 2},
        "tools": [{"id": "ruff", "bin": "ruff", "install": "pipx install ruff", "net": False},
                  {"id": "osv", "bin": "osv-scanner", "install": "brew install osv-scanner", "net": True}]}


class Shipped(unittest.TestCase):
    def test_every_template_valid(self):
        d = stage_catalog.load()
        self.assertGreaterEqual(len(d["templates"]), 80)
        self.assertEqual(len(stage_catalog.catalog()["items"]), len(d["templates"]))   # none dropped (id or ko title clash)
        self.assertEqual([t["id"] for t in d["templates"] if stage_catalog.errors(t)], [])
        self.assertEqual([g["id"] for g in d["groups"]], list(stage_catalog.GROUPS))
        ids = [t["id"] for t in d["templates"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual({t["group"] for t in d["templates"]}, set(stage_catalog.GROUPS))   # no empty group

    def test_graded_templates_assert_and_use_sidereus_runner(self):
        for t in stage_catalog.load()["templates"]:
            if t["gate"]:
                self.assertTrue(t["asserts"], t["id"])                       # a gate says what «did work» means
                self.assertIn("{sidereus}/scripts/", t["gate"], t["id"])        # runs from any repo

    def test_covers_standard_templates(self):
        from sidereus import pipeline_std
        cat = {t["title"]["ko"] for t in stage_catalog.load()["templates"]}
        need = {s[0] for _k, _t, _src, st in pipeline_std.STD for s in st}
        self.assertEqual(sorted(need - cat), [])                            # every standard-template stage is in the catalog
        per = {}
        for t in stage_catalog.load()["templates"]:
            per[t["group"]] = per.get(t["group"], 0) + 1
        self.assertLessEqual(max(per.values()), 10, per)                    # generic building blocks, not every pipeline's stage

    def test_every_template_has_an_instruction(self):
        from sidereus import pipeline
        dt = pipeline.default_tasks()                                        # parsed from the runner file in this repo
        for t in stage_catalog.load()["templates"]:
            if t["title"]["ko"] in pipeline_schema.STAGE_TITLES:            # the runner always sends its default; a task would repeat it
                self.assertTrue(dt.get(t["title"]["ko"]), t["id"])
                self.assertFalse(t.get("task"), t["id"])
            else:
                self.assertGreater(len(t.get("task") or ""), 40, t["id"])

    def test_std_stage_without_task_takes_catalog_task(self):
        from sidereus import pipeline_std
        old = pipeline_std.STD
        self.addCleanup(setattr, pipeline_std, "STD", old)
        pipeline_std.STD = (("x", "x", "", [("측정", "M", False, None, None), ("검증", "C", False, None, None)]),)
        st = pipeline_std.std_drafts({}, [], {"측정": "Measure it.", "검증": "dup"})[0]["P"]["stages"]
        self.assertEqual([s.get("task") for s in st], ["Measure it.", None])   # recommended title keeps the runner default only

    def test_only_lists_runner_tool_ids(self):
        from sidereus import arch_checks, sec_checks
        ids = {"quality": set(arch_checks.TOOL_IDS), "security": set(sec_checks.SEC_IDS)}
        for t in stage_catalog.load()["templates"]:
            m = re.search(r"--category (\w+) --only ([\w,-]+)", t.get("task") or "")
            if m:                                                           # an unknown --only id is a runner usage error
                self.assertLessEqual(set(m.group(2).split(",")), ids[m.group(1)], t["id"])

    def test_english_names_match_display_table(self):
        src = js_all()
        names = re.search(r"^const PLG_NAMES = [\s\S]*?^PLG_NAMES\.ko = \{\};", src, re.M).group(0)
        titles = [t["title"] for t in stage_catalog.load()["templates"]]
        code = "%s\nconsole.log(JSON.stringify(%s.map(t => PLG_NAMES.en[t.ko] || t.ko)));" % (names, json.dumps(titles))
        out = json.loads(subprocess.run(node_e(code), capture_output=True, text=True, check=True).stdout)
        self.assertEqual(out, [t["en"] for t in titles])


class Catalog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old = (stage_catalog.CAT_FILE, stage_catalog._which, stage_catalog.CODE_DIR)
        self.addCleanup(self._restore)
        stage_catalog.CAT_FILE = os.path.join(self.tmp.name, "cat.json")
        stage_catalog.CODE_DIR = "/opt/my sidereus"
        stage_catalog._which = lambda b: "/bin/" + b if b == "ruff" else None

    def _restore(self):
        stage_catalog.CAT_FILE, stage_catalog._which, stage_catalog.CODE_DIR = self.old

    def _write(self, templates):
        with open(stage_catalog.CAT_FILE, "w", encoding="utf-8") as f:
            json.dump({"v": 1, "groups": [{"id": "quality", "en": "Quality"}], "templates": templates}, f)

    def test_catalog_body(self):
        self._write([GOOD])
        c = stage_catalog.catalog()
        self.assertEqual(c["groups"], [{"id": "quality", "en": "Quality"}])
        it = c["items"][0]
        self.assertEqual(it["gate"], "python3 '/opt/my sidereus'/scripts/x.py --verify")   # shell-quoted repo path
        self.assertEqual(it["instr"], "Run '/opt/my sidereus'/scripts/x.py once.")
        self.assertNotIn("task", it)                                                  # page code never reads `task`
        self.assertEqual([(x["id"], x["avail"]) for x in it["tools"]], [("ruff", True), ("osv", False)])
        self.assertEqual(it["loop"], {"to": ["구현"], "max": 2})

    def test_bad_templates_dropped(self):
        bad = [dict(GOOD, id="a", group="nope"), dict(GOOD, id="b", title={"ko": "a/b", "en": "x"}), dict(GOOD, id="c", model="gpt"),
               dict(GOOD, id="d", gate="x" * 201), dict(GOOD, id="e", tools=[{"id": "x", "bin": "rm -rf", "install": "", "net": False}]),
               dict(GOOD, id="f", role="boss"), dict(GOOD, id="g", title={"ko": "커스텀", "en": "Custom"}, task=""),
               dict(GOOD, id="h", loop={"to": ["구현"], "max": 9})]
        for t in bad:
            self.assertTrue(stage_catalog.errors(t), t["id"])
        self.assertEqual(stage_catalog.errors(dict(GOOD, title={"ko": "설계", "en": "Design"}, task="")), [])   # built-in title: no task needed
        self._write(bad + [GOOD, dict(GOOD, id="lint2")])                             # same ko title twice: first wins
        self.assertEqual([t["id"] for t in stage_catalog.catalog()["items"]], ["lint"])

    def test_unreadable_file(self):
        stage_catalog.CAT_FILE = os.path.join(self.tmp.name, "missing.json")
        self.assertEqual(stage_catalog.catalog(), {"groups": [], "items": []})

    def test_stage_passes_schema(self):
        P = {"v": 1, "name": "x", "title": "x", "defaults": {"model": "inherit", "retry": 0}, "stages": [stage_catalog.stage_of(GOOD)]}
        self.assertEqual(pipeline_schema.validate(P, "x"), [])


class Guards(unittest.TestCase):
    """`guards` on the canvas save (pipeline._replace) and stage rename (pipeline._apply) — pure, no files."""
    P = {"v": 1, "name": "x", "title": "x", "defaults": {"model": "inherit", "retry": 0},
         "stages": [{"title": "구현", "agent": "a"}, {"title": "검증", "agent": "a", "gate": "scripts/check.sh --fast"}]}

    def test_replace_sets_and_drops(self):
        from sidereus import pipeline
        g = {"requireGates": ["검증"], "maxLoopBacks": 3}
        new = pipeline._replace(self.P, {"stages": self.P["stages"], "guards": g})
        self.assertEqual(new["guards"], g)
        self.assertEqual(pipeline_schema.validate(new, "x"), [])
        self.assertNotIn("guards", pipeline._replace(new, {"stages": self.P["stages"], "guards": {}}))
        self.assertEqual(pipeline._replace(new, {"stages": self.P["stages"]})["guards"], g)   # absent = kept
        with self.assertRaises(ValueError):
            pipeline._replace(self.P, {"stages": self.P["stages"], "guards": ["검증"]})

    def test_rename_follows_require_gates(self):
        from sidereus import pipeline
        P = dict(self.P, guards={"requireGates": ["검증"]})
        new = pipeline._apply(P, {"stages": {"검증": {"title": "빠른 검사"}}})
        self.assertEqual(new["guards"], {"requireGates": ["빠른 검사"]})
        self.assertEqual(P["guards"], {"requireGates": ["검증"]})                               # input untouched


if __name__ == "__main__":
    unittest.main()
