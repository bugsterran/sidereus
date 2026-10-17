"""dragTrack (web/js/08-ui-kit.js): a drag ends once on pointerup, pointercancel or a move with no buttons held."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

PRE = """
let ERR = 0; function softErr(){ ERR++; }
function mkRoot(){
  const L = {};
  return { L, addEventListener(t, f){ (L[t] = L[t] || []).push(f); }, removeEventListener(t, f){ L[t] = (L[t] || []).filter(x => x !== f); },
           fire(t, ev){ (L[t] || []).slice().forEach(f => f(Object.assign({type: t}, ev))); },
           n(){ return Object.keys(L).reduce((a, k) => a + L[k].length, 0); } };
}
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class DragTrack(unittest.TestCase):
    def run_case(self, finish):
        js = (PRE + js_fn("dragTrack") + """
const R = mkRoot(), caps = [], moves = [], ends = [];
const cap = { setPointerCapture(id){ caps.push(id); } };
dragTrack({pointerId: 7}, cap, ev => moves.push(ev.clientX), ev => ends.push(ev.type), R);
R.fire('pointermove', {buttons: 1, clientX: 10});
""" + finish + """
R.fire('pointermove', {buttons: 1, clientX: 30});
R.fire('pointerup', {});
process.stdout.write(JSON.stringify({caps, moves, ends, left: R.n()}));""")
        r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_buttonless_move_ends(self):
        # Release outside the window: no pointerup arrives, the next move reports buttons = 0.
        out = self.run_case("R.fire('pointermove', {buttons: 0, clientX: 20});")
        self.assertEqual(out, {"caps": [7], "moves": [10], "ends": ["pointermove"], "left": 0})

    def test_pointercancel_ends(self):
        out = self.run_case("R.fire('pointercancel', {});")
        self.assertEqual(out, {"caps": [7], "moves": [10], "ends": ["pointercancel"], "left": 0})

    def test_pointerup_ends(self):
        out = self.run_case("R.fire('pointerup', {});")
        self.assertEqual(out, {"caps": [7], "moves": [10], "ends": ["pointerup"], "left": 0})


if __name__ == "__main__":
    unittest.main()
