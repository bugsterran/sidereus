"""Run side layer (role=dialog) moves focus in on open and back to «Run» on close (Esc and ✕)."""
import json
import os
import re
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _node import node_e  # noqa: E402

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

    def test_repaints_refocus_same_control(self):
        # «Change models for this run only» and the three selects repaint; each must refocus inside .plrun.
        self.assertIn("PLRUN.mOpen = !PLRUN.mOpen; plPaint(); plRunRefocus('data-plrmo');", self.s)
        self.assertIn("plPaint(); plRunRefocus('data-plrs'); }", self.s)
        self.assertIn("plPaint(); plRunRefocus('data-plrmode'); }", self.s)
        self.assertIn("plPaint(); plRunRefocus('data-plrm', k); }", self.s)

    def test_refocus_picks_matching_node_inside_plrun(self):
        m = re.search(r"^function plRunRefocus\(attr, val\)\{.*\}$", self.s, re.M)
        self.assertTrue(m)
        js = m.group(0) + r"""
const mk = (a, v) => ({ a, v, getAttribute(n){ return n === this.a ? this.v : null; }, focus(){ got.push(this.a + '=' + this.v); } });
let got = [], seen = [];
const nodes = [mk('data-plrmo', ''), mk('data-plrs', ''), mk('data-plrm', 'plan'), mk('data-plrm', 'review')];
globalThis.document = { querySelectorAll(q){ seen.push(q); const a = q.match(/\[(.+)\]/)[1]; return nodes.filter(n => n.a === a); } };
plRunRefocus('data-plrmo'); plRunRefocus('data-plrs'); plRunRefocus('data-plrm', 'review'); plRunRefocus('data-plrm', 'gone');
process.stdout.write(JSON.stringify({ got, seen }));
"""
        out = subprocess.run(node_e(js), capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(out.returncode, 0, out.stderr)
        r = json.loads(out.stdout)
        self.assertEqual(r["got"], ["data-plrmo=", "data-plrs=", "data-plrm=review"])
        self.assertTrue(all(q.startswith(".plrun [") for q in r["seen"]))

    def test_send_error_uses_te(self):
        # Server error text may hold user data: TE translates known keys only, never T().
        self.assertIn("TE((e && e.message) || e)", self.s)
        self.assertNotIn("T((e && e.message) || e)", self.s.replace("TE((e", "X"))


if __name__ == "__main__":
    unittest.main()
