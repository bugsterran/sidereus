"""Header row has no per-session activity strip (#actv); the title and right-hand chips (#todo, #sesb) stay.
Needs-me pills keep rendering into the rail «Attention» list (#rattnl). Repo sources only."""
import glob
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class HeaderNoActivityStrip(unittest.TestCase):
    def test_header_row_without_strip(self):
        html = _read("web/index.html")
        row = re.search(r"<div class=hrow>(.*?)\n</div>", html, re.S).group(1)
        self.assertNotIn("actv", row)
        for kept in ("id=vtitle", "id=todo", "id=sesb"):
            self.assertIn(kept, row)

    def test_no_strip_code_left(self):
        for p in sorted(glob.glob(os.path.join(ROOT, "web", "js", "*.js"))):
            src = open(p, encoding="utf-8").read()
            for gone in ("#actv", "'actv'", "actFit", "actPop", "actChips", "Top context {p}"):
                self.assertNotIn(gone, src, "%s still has %s" % (os.path.basename(p), gone))

    def test_rail_pills_and_chips_still_built(self):
        act = _read("web/js/42-activity.js")
        self.assertIn("getElementById('rattnl')", act)
        self.assertRegex(act, r"function actPaint\(\)")
        todo = _read("web/js/25-health-todo.js")
        self.assertIn("getElementById('todo')", todo)


if __name__ == "__main__":
    unittest.main()
