"""Run side layer (role=dialog) moves focus in on open and back to «Run» on close (Esc and ✕)."""
import os
import re
import unittest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "js", "48b-pipeline-run.js")


class RunLayerFocus(unittest.TestCase):
    def setUp(self):
        with open(SRC, encoding="utf-8") as f:
            self.s = f.read()

    def test_close_returns_focus_to_run(self):
        m = re.search(r"function plRunClose\(\)\{(.*?)\}\n", self.s)
        self.assertTrue(m)
        self.assertIn("[data-plrun]", m.group(1))
        self.assertIn(".focus()", m.group(1))

    def test_esc_and_x_use_close(self):
        self.assertRegex(self.s, r"e\.key === 'Escape'[^\n]*plRunClose\(\)")
        self.assertRegex(self.s, r"\[data-plrx\]'\)\)\{ plRunClose\(\)")

    def test_open_focuses_inside(self):
        self.assertIn("plPaint(); plRunFocusIn(); }", self.s)


if __name__ == "__main__":
    unittest.main()
