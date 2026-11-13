"""arch-map pipeline file: schema v2 task text, with titles, stage count and models unchanged (repo file, not live data)."""
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, ".claude", "pipelines", "arch-map.json")
TITLES = ["읽기 계획", "모듈 그리기", "흐름 그리기", "검증", "개요 그리기", "개요 검증"]
MODELS = ["opus", "opus", "opus", "sonnet", "opus", "sonnet"]
BRIEF = os.path.join(ROOT, ".claude", "pipelines", "arch-brief.json")
LANG_TASK = "Human text: the request's Language line (none = English)."
LANG_RULE = "Language: all human text in map/flows/brief.json (not ids, paths, symbols) follows the request's Language line (none = English)."
PRE = "Run `/usr/bin/python3 scripts/arch_brief.py --pre --repo <repo>` → S; on a miss stop. "


class ArchMapPipelineV2Test(unittest.TestCase):
    def setUp(self):
        with open(P, encoding="utf-8") as f:
            self.d = json.load(f)
        self.st = {s["title"]: s for s in self.d["stages"]}

    def test_titles_models_unchanged(self):
        self.assertEqual([s["title"] for s in self.d["stages"]], TITLES)
        self.assertEqual([s.get("model") for s in self.d["stages"]], MODELS)
        self.assertEqual(self.st["검증"]["onFail"], {"goto": "모듈 그리기", "max": 1})

    def test_draw_modules_v2(self):
        t = self.st["모듈 그리기"]["task"]
        for w in ("v:2", "`v: 2`", "groups:[{id,name}]", "layer", "group", "summary", "read", "write", "serve", "event", "owns", "web->api"):
            self.assertIn(w, t)

    def test_plan_v2(self):
        t = self.st["읽기 계획"]["task"]
        for w in ("groups:", "entries:", "stores:", "changed = all module ids"):
            self.assertIn(w, t)

    def test_fe_screen_entries(self):
        t = self.st["읽기 계획"]["task"]
        for w in ("FE screens", "not entries", "route/prefix"):
            self.assertIn(w, t)
        self.assertIn("FE screen entry", self.d["rules"])
        self.assertIn("component name", self.st["모듈 그리기"]["task"])
        self.assertIn("page module for a FE screen entry", self.st["흐름 그리기"]["task"])

    def test_text_budgets(self):
        # ⚠ the runner caps rules at 2000 and each stage task at 1000 chars.
        self.assertLessEqual(len(self.d["rules"]), 2000)
        for s in self.d["stages"]:
            self.assertLessEqual(len(s["task"]), 1000, s["title"])

    def test_verify_reports_schema(self):
        self.assertIn("schema", self.st["검증"]["task"])

    def test_overview_stages(self):
        self.assertEqual(len(self.st), len(self.d["stages"]))   # titles unique: [pl:] tags and onFail goto name them
        draw, ver = self.st["개요 그리기"], self.st["개요 검증"]
        self.assertEqual([draw["agent"], ver["agent"]], ["general-purpose", "general-purpose"])
        self.assertIn("scripts/arch_brief.py --pre --repo <repo>", draw["task"])
        self.assertIn("on a miss stop", draw["task"])
        self.assertIn("Write S/brief.json only", draw["task"])
        self.assertEqual(ver["gate"], "/usr/bin/python3 scripts/arch_brief.py --last")
        self.assertEqual(ver["onFail"], {"goto": "개요 그리기", "max": 1})
        self.assertIn("S/brief.json", self.d["rules"])
        self.assertIn("never invalidates the verified map", self.d["rules"])

    def test_overview_matches_arch_brief(self):
        # arch-brief stays the overview-only redraw: same draw schema and the same gate as arch-map's overview stages
        with open(os.path.join(ROOT, ".claude", "pipelines", "arch-brief.json"), encoding="utf-8") as f:
            b = {s["title"]: s for s in json.load(f)["stages"]}
        self.assertEqual(self.st["개요 검증"]["task"], b["검증"]["task"])
        self.assertEqual(self.st["개요 검증"]["gate"], b["검증"]["gate"])
        schema = re.search(r"Write S/brief\.json only: (\{v:2, .*?\] <=12\})", b["개요 그리기"]["task"]).group(1)
        self.assertIn(schema, self.st["개요 그리기"]["task"])
        # one rule, one place: arch-map's draw task is arch-brief's verbatim after its --pre sentence
        self.assertEqual(self.st["개요 그리기"]["task"], PRE + b["개요 그리기"]["task"])

    def test_language_line_r1(self):
        # R1: human text follows the request's Language line, not map.json's label language
        with open(BRIEF, encoding="utf-8") as f:
            b = json.load(f)
        bt = {s["title"]: s for s in b["stages"]}
        for t in (self.st["모듈 그리기"], self.st["흐름 그리기"], self.st["개요 그리기"], bt["개요 그리기"]):
            self.assertIn(LANG_TASK, t["task"])
        for r in (self.d["rules"], b["rules"]):
            self.assertIn(LANG_RULE, r)
        for x in [self.d["rules"], b["rules"]] + [s["task"] for s in self.d["stages"] + b["stages"]]:
            self.assertNotIn("label language", x)

    def test_overview_v2_caps_r1_to_r5(self):
        # R1 title+what; R2 3..7 components, <=1 pkgs, 1..4 externals with 1..3 uses; R3 labelled arrows on map edges, <=12; R4 2..4 principles with file:line
        with open(BRIEF, encoding="utf-8") as f:
            b = json.load(f)
        bt = {s["title"]: s for s in b["stages"]}
        for t in (self.st["개요 그리기"]["task"], bt["개요 그리기"]["task"]):
            for w in ("title<=60, what<=120", "] 3..7 (<=1 with pkgs)", "uses:[{name<=30,note?<=40}] 1..3", "modules:[ids] 1..}] 1..4",
                      "principles:[{text<=100,evidence:{file,line}}] 2..4}", "label<=32 required", "edges:[map edge index] 1..5}] <=12}",
                      "main DB too", "No request sequence/route table.",
                      "heads: plain nouns (Architecture), no sentences/legends.", "one per box pair; use on each into externals"):
                self.assertIn(w, t)
            for w in ("bands:", "boxes:", "route:", "v:1", "flows", "spine"):
                self.assertNotIn(w, t)
        for t in (self.st["개요 검증"]["task"], bt["검증"]["task"]):
            for w in ("3..7 components", "1..4 externals", "1..3 uses", "2..4 principles", "<=12 arrows", "outside externals",
                      "without label", "actor endpoint", "absent at the commit", "redraw as v2"):
                self.assertIn(w, t)
        self.assertNotIn("flows", b["rules"].split("Needs")[1].split("\n")[0])   # R3: the overview reads map + verify only
        self.assertIn("Overview stages write only S/brief.json", self.d["rules"])
        self.assertNotIn("decision order", b["use"])

    def test_request_lists_every_title(self):
        # the request text names every stage verbatim ([pl:] tags match them)
        with open(os.path.join(ROOT, "web", "js", "84jc-structure-arch-request.js"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("'.json (" + " → ".join(TITLES) + ")\\n'", src)


if __name__ == "__main__":
    unittest.main()
