"""Status bar fit (60-statusbar.js sbFit): drop order keeps the external «Today» label behind cheaper drops."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import jconst
from tests._node import node_e

# Fake bar: each part has a width and a .sbdN class; sbFit hides whole parts in SB_STEPS order (no padding squeeze).
FAKE = """
function bar(cw, parts){
  const steps = [];
  const nodes = parts.map(([k, w]) => ({k, w, hid: false, classList: {add: c => { if(c === 'sbh'){ nodes_hide(k); } }}}));
  function nodes_hide(k){ nodes.filter(n => n.k === k).forEach(n => { n.hid = true; }); }
  return {clientWidth: cw, steps,
    classList: {add: () => {}, remove: () => {}, contains: () => false},
    get scrollWidth(){ return nodes.filter(n => !n.hid).reduce((a, n) => a + n.w, 0); },
    querySelectorAll: sel => { const k = +sel.slice(4); if(nodes.some(n => n.k === k)) steps.push(k); return nodes.filter(n => n.k === k); },
    hidden: () => nodes.filter(n => n.hid).map(n => n.k)};
}
// Total 1682; without 1+2 = 1272, without 3 = 1212, without 5 = 1032.
const P = [[0, 900], [1, 290], [2, 120], [3, 60], [4, 21], [4, 21], [5, 180], [6, 90]];
const out = {};
for(const [name, cw] of [['fit12', 1272], ['wide', 2000], ['drop3', 1212], ['drop5', 1100]]){
  const el = bar(cw, P);
  sbFit(el);
  out[name] = [...new Set(el.hidden())];
}
process.stdout.write(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SbarFit(unittest.TestCase):
    def run_js(self):
        src = jconst("SB_STEPS") + "\n" + js_fn("sbFit") + "\n" + FAKE
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        return json.loads(r.stdout)

    def test_order(self):
        o = self.run_js()
        self.assertEqual(o["fit12"], [1, 2])
        self.assertEqual(o["wide"], [])
        # The duplicate «left ≈» (sbd3) goes before the cheaper ext parts, and «Today» (sbd4) outlives 5 and 6.
        self.assertEqual(o["drop3"], [1, 2, 3])
        self.assertEqual(o["drop5"], [1, 2, 3, 5])
