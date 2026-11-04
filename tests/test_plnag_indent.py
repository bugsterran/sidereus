"""Subagent groups under a card line up: the run bar is a colour, never extra width.

Reads web/css/43-pipeline.css only.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rule(css, sel):
    m = re.search(r"(?m)^" + re.escape(sel) + r"\{([^}]*)\}", css)
    return m.group(1) if m else None


class PlnagIndent(unittest.TestCase):
    def test_run_group_adds_no_width(self):
        with open(os.path.join(ROOT, "web/css/43-pipeline.css"), encoding="utf-8") as fh:
            css = fh.read()
        base, run = rule(css, ".plnag"), rule(css, ".plnag.plnagrn")
        self.assertIsNotNone(base)
        self.assertIsNotNone(run)
        self.assertIn("border-left:2px solid transparent", base)
        self.assertIn("padding-left:4px", base)
        for prop in ("padding", "margin", "border-left:", "border-left-width", "border-width"):
            self.assertNotIn(prop, run, prop)


if __name__ == "__main__":
    unittest.main()
