"""Pipelines canvas shows stage names through plgShow() (web/js/48d-pipeline-canvas.js plEdgesSvg loop pill, plPanel flow title).

⚠The loop-back pill printed `then` raw, so «재검증» showed in English mode. Run under node with stubs."""
import json
import re
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

HANGUL = re.compile("[가-힣]")

STUBS = r"""
const T = s => s, LANG = 'en';
function esc(s){ return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;'); }
function plgNode(G, id){ return G.nodes.find(n => n.id === id) || null; }
function plVG(E){ return E.G; } function plgLoopLanes(G){ return G.loops.map(() => 1); }
function plgLoopPath(){ return { d: 'M0 0', lx: 100, ly: 10 }; } function plgW(){ return 184; } function plgH(){ return 100; }
function plHitA(){ return ''; } function plPulseOn(){ return false; }
const PLS = { proj: '', data: {} }, PLG_MODELS = ['inherit'];
"""


def run(body):
    src = js_all()
    names = re.search(r"^const PLG_NAMES = \{[\s\S]*?^\}\s*\};?$", src, re.M)
    if names is None:
        raise LookupError("06-i18n-w.js: PLG_NAMES not found")
    fns = "\n".join(js_fn(f) for f in ("plgBase", "plgShow", "plEdgesSvg", "plRow", "plOpt", "plPanel"))
    out = subprocess.run(node_e(STUBS + names.group(0) + "\n" + fns + "\n" + body), capture_output=True, text=True, check=True, encoding="utf-8").stdout
    return json.loads(out)


G = ("const G = { defaults: { model: 'inherit', retry: 0 }, flow: [], loops: [{ from: 'b', to: 'a', max: 2, then: '재검증' }],"
     " nodes: [{ id: 'a', title: '구현', ui: { x: 0, y: 0 } }, { id: 'b', title: '리뷰', ui: { x: 300, y: 0 } }] };")


class CanvasNames(unittest.TestCase):
    def test_loop_pill_then_in_english(self):
        out = run(G + "console.log(JSON.stringify(plEdgesSvg({ G, sel: {} })));")
        self.assertIn("→ Re-verify", out)
        self.assertIsNone(HANGUL.search(out), out)

    def test_flow_panel_title_in_english(self):
        out = run(G + "G.flow = [['a', 'b']]; console.log(JSON.stringify(plPanel({ G, sel: { k: 'f', i: 0 } }, {})));")
        self.assertIn("<b>Implement → Review</b>", out)
        self.assertIsNone(HANGUL.search(out), out)

    def test_loop_panel_header_and_then_options_in_english(self):
        out = run(G + "G.flow = [['a', 'b']]; G.nodes.push({ id: 'c', title: '재검증', ui: { x: 600, y: 0 } }); G.flow.push(['b', 'c']);"
                  " G.loops[0].from = 'a'; G.loops[0].to = 'a';"
                  " function plgOrder(G){ return { order: ['a', 'b', 'c'] }; }"
                  " console.log(JSON.stringify(plPanel({ G, sel: { k: 'l', i: 0 } }, {})));")
        self.assertIn("<b>Implement ↩ Implement</b>", out)
        self.assertIn('<option value="재검증" selected>Re-verify</option>', out)   # value stays the saved title
        self.assertIn('<option value="리뷰">Review</option>', out)


if __name__ == "__main__":
    unittest.main()
