"""Shipped .claude/pipelines/osv-triage.json: parses, is builtin, every command goes through scripts/osv_rules.py,
the triage stage is gated by `osv_rules.py --check`, stage titles fit the [pl:...] tag. Reads the repo file only."""
import json
import os
import re
import unittest

from tests._load import ROOT, sidereus
from tests import test_pl_flow as F

PATH = os.path.join(ROOT, ".claude", "pipelines", "osv-triage.json")
CMD = re.compile(r"`([^`]+)`")


class OsvTriagePipeline(unittest.TestCase):
    def setUp(self):
        with open(PATH, encoding="utf-8") as f:
            self.P = json.load(f)

    def test_parses_valid_and_builtin(self):
        self.assertIs(self.P.get("builtin"), True)
        self.assertEqual(sidereus("pipeline_schema").validate(self.P, "osv-triage"), [])

    def test_commands_only_through_osv_rules(self):
        # ⚠A stage that ran another writer (sed, echo >, python -c) could hand-edit the rule file or touch the scanned repo.
        cmds = []
        for s in self.P["stages"]:
            for c in CMD.findall(s.get("task", "")):
                if c.startswith("/usr/bin/python3"):
                    cmds.append(c)
                    self.assertIn("scripts/osv_rules.py", c, c)
        self.assertTrue(any("--unjudged" in c for c in cmds))
        self.assertTrue(any("--append" in c for c in cmds))
        for c in CMD.findall(self.P["rules"]):
            if c.startswith("/usr/bin/python3"):
                self.assertIn("scripts/osv_rules.py", c, c)

    def test_gate_checks_rule_file(self):
        gates = [s["gate"] for s in self.P["stages"] if s.get("gate")]
        self.assertEqual(gates, ["/usr/bin/python3 scripts/osv_rules.py --check"])
        last = self.P["stages"][-1]
        self.assertEqual(last.get("model"), "opus")
        self.assertIn("--append", last["task"])

    def test_rules_text(self):
        r = self.P["rules"]
        for s in ("Do not edit", "Never hand-edit", "Metadata only", "never paste code lines"):
            self.assertIn(s, r)

    def test_titles_taggable(self):
        for s in self.P["stages"]:
            tag = "[pl:osv-triage/%s]" % s["title"]
            m = F.H.TAG.search(tag)
            self.assertIsNotNone(m, tag)
            self.assertEqual(m.group(2), s["title"])


if __name__ == "__main__":
    unittest.main()
