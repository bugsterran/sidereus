"""Status bar fit (60-statusbar.js sbFit): drop order keeps the external «오늘» label behind cheaper drops."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import jconst
from tests._node import node_e

# Fake bar: each part has a width and a .sbdN class; padding step 't' saves 8px per cell (10px -> 6px each side).
FAKE = """
function bar(cw, parts, cells){
  const cls = new Set(), steps = [];
  const nodes = parts.map(([k, w]) => ({k, w, hid: false, classList: {add: c => { if(c === 'sbh'){ nodes_hide(k); } }}}));
  function nodes_hide(k){ nodes.filter(n => n.k === k).forEach(n => { n.hid = true; }); }
  return {clientWidth: cw, steps,
    classList: {add: c => { cls.add(c); if(c === 'sbtight') steps.push('t'); }, remove: c => cls.delete(c), contains: c => cls.has(c)},
    get scrollWidth(){ return nodes.filter(n => !n.hid).reduce((a, n) => a + n.w, 0) - (cls.has('sbtight') ? cells * 8 : 0); },
    querySelectorAll: sel => { const k = +sel.slice(4); if(nodes.some(n => n.k === k)) steps.push(k); return nodes.filter(n => n.k === k); },
    hidden: () => nodes.filter(n => n.hid).map(n => n.k)};
}
// Total 1682; without 1+2 = 1272, tight = 1208, without 3 = 1148.
const P = [[0, 900], [1, 290], [2, 120], [3, 60], [4, 21], [4, 21], [5, 180], [6, 90]];
const out = {};
for(const [name, cw] of [['short4', 1268], ['wide', 2000], ['tightNotEnough', 1150]]){
  const el = bar(cw, P, 8);
  sbFit(el);
  out[name] = {hidden: [...new Set(el.hidden())], tight: el.classList.contains('sbtight')};
}
const el = bar(900, P, 8); sbFit(el); el.clientWidth = 5000; sbFit(el);
out.refit = el.classList.contains('sbtight');
process.stdout.write(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SbarFit(unittest.TestCase):
    def run_js(self):
        src = jconst("SB_STEPS") + "\n" + js_fn("sbFit") + "\n" + FAKE
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        return json.loads(r.stdout)

    def test_order(self):
        o = self.run_js()
        # A few px short after the two forecasts: padding absorbs it, «오늘» (sbd4) stays.
        self.assertEqual(o["short4"], {"hidden": [1, 2], "tight": True})
        self.assertEqual(o["wide"], {"hidden": [], "tight": False})
        # Padding not enough: the duplicate «남은 ≈» (sbd3) goes before «오늘».
        self.assertEqual(o["tightNotEnough"], {"hidden": [1, 2, 3], "tight": True})
        # A refit starts untightened (class removed first), so a wider bar gets its padding back.
        self.assertFalse(o["refit"])
