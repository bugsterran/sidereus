"""arch-map pipeline file: schema v2 task text, with titles, stage count and models unchanged (repo file, not live data)."""
import json
import os
import unittest

P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".claude", "pipelines", "arch-map.json")
TITLES = ["읽기 계획", "모듈 그리기", "흐름 그리기", "검증"]
MODELS = ["opus", "opus", "opus", "sonnet"]


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
        for w in ("v:2", "`v: 2`", "layer", "group", "summary", "read", "write", "serve", "event", "owns", "web->api"):
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


if __name__ == "__main__":
    unittest.main()
