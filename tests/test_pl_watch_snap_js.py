"""«Pipelines» Watch: the result pane clip edge never cuts a text line (48k plWSnap, todo #95).
Pure functions under node with stubs; no live files."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

PRE = """
const PLW_MIN = [260, 80, 84]; let PLWDRAG = null;
const ST = {}, TOP = 100;
const P = {getBoundingClientRect(){ return {bottom: TOP + parseFloat(ST['--plwph'])}; }};
const G = {style: {setProperty(k, v){ ST[k] = v; }}, querySelector(){ return P; }}, OC = {style: {}};
var document = {querySelectorAll(){ return []; }};
function getComputedStyle(){ return {borderBottomWidth: '0px'}; }
let LINES = [];
function plWLines(){ return LINES; }
// Mixed line heights (title 21, body 15, mono 18, small 13.6); relative to the pane top.
const rows = [[0, 21], [27, 42], [48, 66], [72, 85.6], [91.6, 106.6], [112.6, 130.6], [136.6, 150.2]];
const inside = B => LINES.some(l => l.t < B && B < l.b);
"""


def _fn():
    return "\n".join(js_fn(n) for n in ("plWApply", "plWSnapCut", "plWSnap")) + "\nconst PLW_SNAP_MAX = 32;"


def run(body):
    r = subprocess.run(node_e(PRE + _fn() + "\n" + body), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PlWatchSnap(unittest.TestCase):
    def test_edge_never_inside_a_line_and_total_kept(self):
        o = run("LINES = rows.map(([t, b]) => ({t: TOP + t, b: TOP + b})); const out = [];"
                "for(const ph of [90, 100, 117, 140]){ const s = [600, ph, 110]; plWApply(G, OC, s); const t = plWSnap(G, OC, s);"
                " const B = TOP + parseFloat(ST['--plwph']);"
                " out.push([inside(B), t[0] + t[1] + t[2] - ph, t[1] <= ph, parseFloat(OC.style.height)]); }"
                "console.log(JSON.stringify(out));")
        for cut, total, shrunk, card in o:
            self.assertFalse(cut)               # clip edge outside every line box
            self.assertAlmostEqual(total, 710)  # canvas + pane + card unchanged
            self.assertTrue(shrunk)             # never grows the pane
        self.assertAlmostEqual(o[1][3], 110 + (100 - 91.6))   # freed px went to the Running card

    def test_side_by_side_lines_of_mixed_height(self):
        # A 15px label beside an 18px chip: the taller box decides.
        o = run("LINES = [{t: 170, b: 185}, {t: 169, b: 187}, {t: 190, b: 205}, {t: 188, b: 210}];"
                "const s = [600, 100, 110]; plWApply(G, OC, s); const t = plWSnap(G, OC, s);"
                "console.log(JSON.stringify([t, inside(TOP + parseFloat(ST['--plwph']))]));")
        self.assertEqual(o[0], [600, 88, 122])
        self.assertFalse(o[1])

    def test_bounded_and_no_op_cases(self):
        o = run("const out = []; let s;"
                "LINES = [{t: 160, b: 220}]; s = [600, 100, 110]; plWApply(G, OC, s); out.push(plWSnap(G, OC, s));"   # cut 40 > cap: kept
                "LINES = [{t: 150, b: 200}]; s = [600, 80, 110]; plWApply(G, OC, s); out.push(plWSnap(G, OC, s));"   # pane under its min: kept
                "LINES = [{t: 180, b: 190}, {t: 210, b: 220}]; s = [600, 100, 110]; plWApply(G, OC, s); out.push(plWSnap(G, OC, s));"   # edge in a gap
                "LINES = [{t: 160, b: 200}]; s = [600, 100, 110]; plWApply(G, OC, s); out.push(plWSnap(G, OC, s));"   # edge on a line bottom
                "PLWDRAG = {}; LINES = [{t: 190, b: 210}]; s = [600, 100, 110]; plWApply(G, OC, s); out.push(plWSnap(G, OC, s)); PLWDRAG = null;"
                "out.push(plWSnap(G, null, s));"                                                                # no card: total cannot be kept
                "console.log(JSON.stringify(out));")
        self.assertEqual(o, [[600, 100, 110], [600, 80, 110], [600, 100, 110], [600, 100, 110], [600, 100, 110], [600, 100, 110]])

    def test_fit_snaps_after_the_last_apply(self):
        fit = js_fn("plWatchFit")
        self.assertIn("plWSnap(g, oc, s);", fit)
        self.assertLess(fit.index("if(over > 0)"), fit.index("plWSnap(g, oc, s);"))
        self.assertIn("if(!p || PLWDRAG) return s;", js_fn("plWSnap"))
        self.assertIn("r.getClientRects()", js_fn("plWLines"))   # measured line boxes, not a fixed px step


if __name__ == "__main__":
    unittest.main()
