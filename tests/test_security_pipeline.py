"""security-checks pipeline file: threat-model review stage contract (repo file, not live data)."""
import json
import os
import unittest

D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".claude", "pipelines")


def _load(name):
    with open(os.path.join(D, name), encoding="utf-8") as f:
        return json.load(f)


class SecurityPipelineTest(unittest.TestCase):
    def setUp(self):
        self.d = _load("security-checks.json")
        self.st = self.d["stages"]

    def test_stage_fields(self):
        self.assertEqual([s["title"] for s in self.st], ["보안 검사", "위협 모델 리뷰"])
        s = self.st[1]
        self.assertEqual((s["agent"], s["model"]), ("general-purpose", "opus"))
        self.assertNotIn("gate", s)
        self.assertIn("gate", self.st[0])

    def test_task_contract(self):
        t = self.st[1]["task"]
        for w in ("<repo>/.oss-scanner/threat_model.md", "<repo>/threat_model.md",
                  "no threat model — copy <sidereus>/templates/oss-scanner/ to <repo>/.oss-scanner/",
                  "--log-show", "--mark <slug>@<file> resolved", "--log-review",
                  "Never quote", "unverified", "in-scope", "severity rubric", "no installs"):
            self.assertIn(w, t)
        self.assertLess(t.index("--log-show"), t.index("--mark"))
        self.assertLess(t.index("--mark"), t.index("--log-review"))

    def test_never_marks_false_positive(self):
        t = self.st[1]["task"]
        self.assertIn("NEVER mark false-positive", t)
        self.assertNotIn("false-positive [", t)
        self.assertNotIn("--mark <slug>@<file> false-positive", t)

    def test_rules_name_log(self):
        self.assertIn("security-log.jsonl", self.d["rules"])
        self.assertIn("--log-review", self.d["rules"])

    def test_monthly_alongside_deps_audit(self):
        d = _load("deps-audit.json")
        self.assertIn("security-checks", d["use"])
        self.assertIn("security-checks", d["rules"])


if __name__ == "__main__":
    unittest.main()
