"""Review pipeline templates in docs/examples/pipelines (repo fixtures, not live data) and their docs links."""
import json
import os
import unittest

from tests._load import load, sidereus

load()
PS = sidereus("pipeline_schema")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "docs", "examples", "pipelines")
NAMES = ("review-claude", "review-codex", "review-gemini")
DOCS = ("docs/REVIEW-PIPELINES.md", "docs/REVIEW-PIPELINES.ko.md")


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class ReviewTemplates(unittest.TestCase):
    def test_validates(self):
        for n in NAMES:
            P = json.loads(_read("docs/examples/pipelines/%s.json" % n))
            self.assertEqual(PS.validate(P, n), [], n)

    def test_verify_after_find_and_round_cap(self):
        for n in NAMES:
            S = json.loads(_read("docs/examples/pipelines/%s.json" % n))["stages"]
            titles = [s["title"] for s in S]
            self.assertLess(titles.index("Find"), titles.index("Verify"), n)
            for s in S:
                if "onFail" in s:
                    self.assertLessEqual(s["onFail"]["max"], 3, n)
            self.assertTrue(any("onFail" in s for s in S), n)

    def test_codex_gemini_marked_untested(self):
        for n in ("review-codex", "review-gemini"):
            P = json.loads(_read("docs/examples/pipelines/%s.json" % n))
            self.assertIn("untested", (P["title"] + P["use"]).lower(), n)

    def test_docs_link_each_template(self):
        self.assertEqual(sorted(f[:-5] for f in os.listdir(DIR) if f.endswith(".json")), sorted(NAMES))
        for d in DOCS:
            text = _read(d)
            for n in NAMES:
                self.assertIn("(examples/pipelines/%s.json)" % n, text, d)


if __name__ == "__main__":
    unittest.main()
