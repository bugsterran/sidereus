"""Pipelines canvas stage nodes and edge hit paths are keyboard stops (web/js/48d-pipeline-canvas.js plNodeHtml/plHitA,
48d-pipeline-cv-input.js keydown).

⚠Selection is on pointerdown, and 98-a11y skipped .plnd (cursor:move), so selecting a stage was mouse-only;
the edge hit paths got role=button from 98-a11y with no accessible name. Run under node with stubs."""
import json
import re
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

STUBS = r"""
const T = s => s, TV = j => j.msg, LANG = 'en';
function esc(s){ return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;'); }
function plgFam(){ return 'x'; } function plgHue(){ return ''; } function plgShow(t){ return t; }
function plgNode(G, id){ return G.nodes.find(n => n.id === id) || null; }
const PL_JUDGED = [], PL_LOW = [];
"""


def _listener():
    """The keydown listener added right after the «Keyboard twin» comment, as source."""
    src = js_all()
    m = re.search(r"^// Keyboard twin of the pointerdown selection[^\n]*\n(?://[^\n]*\n)*(document\.addEventListener\('keydown', [\s\S]*?^\}\);)", src, re.M)
    if m is None:
        raise LookupError("48d-pipeline-cv-input.js: keyboard selection listener not found")
    return m.group(1)


def run(body):
    fns = "\n".join(js_fn(f) for f in ("plFlagChips", "plNodeHtml", "plHitA"))
    code = STUBS + fns + "\n" + body
    out = subprocess.run(node_e(code), capture_output=True, text=True, check=True, encoding="utf-8").stdout
    return json.loads(out)


G = "const G = { defaults: { model: 'inherit' }, loops: [], nodes: [{ id: 'a', title: 'Plan', agent: 'x', ui: { x: 0, y: 0 } }, { id: 'b', title: 'Build', ui: { x: 0, y: 0 } }] };"


class NodeKb(unittest.TestCase):
    def test_node_markup_is_a_named_button(self):
        out = run(G + "console.log(JSON.stringify(plNodeHtml({ G }, G.nodes[0], false, null)));")
        self.assertIn("tabindex=0", out)
        self.assertIn("role=button", out)
        self.assertIn('aria-label="Plan"', out)

    def test_node_label_carries_live_status(self):
        out = run(G + "const PL_OUTCOME = { done: 'Done' }; function plOc(){ return 'Done'; } function plPassSel(){ return -1; } function ago(){ return '1m'; }"
                  "console.log(JSON.stringify(plNodeHtml({ G }, G.nodes[0], false, { Plan: { st: 'done' } })));")
        self.assertIn('aria-label="Plan · Done"', out)

    def test_edge_hit_path_is_named(self):
        out = run(G + "console.log(JSON.stringify(plHitA(G, 'a', 'b')));")
        self.assertIn('aria-label="Plan → Build"', out)
        self.assertIn("role=button", out)

    def test_enter_selects_like_click_and_keeps_view(self):
        body = G + r"""
          let L = null, PAINTS = 0, FOCUS = null, NOFIRST = 0;
          const E = { G, view: { x: 5, y: 6, z: 1 }, sel: null };
          const document = { addEventListener(t, f){ L = f; } };
          const CSS = { escape: s => s };
          function plCurEnt(){ return E; } function plPaint(){ PAINTS++; } function plNoFirst(){ NOFIRST++; }
          function plRefocus(s){ FOCUS = s; }
          """ + _listener() + r"""
          const mk = (attrs, sel) => ({ matches: s => s === '.plw [data-plnode], .plw path[data-pledge]' && sel, getAttribute: a => attrs[a] || null });
          let prevented = 0; const ev = (key, t) => ({ key, target: t, preventDefault(){ prevented++; } });
          L(ev('Enter', mk({ 'data-plnode': 'b' }, true)));
          const nodeSel = E.sel;
          L(ev(' ', mk({ 'data-pledge': 'f:0' }, true)));
          const edgeSel = E.sel;
          L(ev('Enter', mk({}, false)));   // not a node/edge: ignored
          console.log(JSON.stringify([nodeSel, edgeSel, PAINTS, prevented, FOCUS, E.view, NOFIRST]));"""
        out = run(body)
        self.assertEqual(out[0], {"k": "n", "id": "b"})
        self.assertEqual(out[1], {"k": "f", "i": 0})
        self.assertEqual(out[2:5], [2, 2, 'path[data-pledge="f:0"]'])
        self.assertEqual(out[5], {"x": 5, "y": 6, "z": 1})
        self.assertEqual(out[6], 2)


if __name__ == "__main__":
    unittest.main()
