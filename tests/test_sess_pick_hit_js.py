"""Session-card invite pick (40b sessPickHtml/sessClick): the checkbox sits in a padded label,
and a click on that label never opens the work log while the forwarded input click toggles the pick once."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import jconst
from tests._node import node_e

FNS = ("sessPickHtml", "sessClick")

STUBS = r"""
const picked = new Set(); let OPEN = 0, INV = 0, SESS = [];
const T = s => s, TV = o => o.msg.replace('{n}', o.vars.n);
const mboxIn = x => !!x.mbox;
function acctOthClick(){ return false; }
function buildInvite(){ INV++; }
function openSession(){ OPEN++; }
function extTid(){ return ''; }
var window = {getSelection: () => ''};
const el = (tag, cls, up, attrs) => ({tagName: tag, cls, up, attrs: attrs || {},
  getAttribute(k){ return this.attrs[k]; },
  closest(sel){ for(let n = this; n; n = n.up) if(sel.split(',').some(p => match(n, p.trim()))) return n; return null; }});
function match(n, p){
  if(p === '.sxw > .sx') return n.cls === 'sx' && n.up && n.up.cls === 'sxw';
  if(p === 'input.spick[data-mb]') return n.tagName === 'INPUT' && n.cls === 'spick' && 'data-mb' in n.attrs;
  if(p.startsWith('.')) return n.cls === p.slice(1);
  return n.tagName === p.toUpperCase();
}
const wrap = el('DIV', 'sxw', null, {'data-scwd': '/r', 'data-ssid': 's1'});
const row = el('DIV', 'sx', wrap), lab = el('LABEL', 'spickw', row);
const inp = el('INPUT', 'spick', lab, {'data-mb': 'cc-a'}); inp.checked = true;
const ev = t => ({target: t, stopPropagation(){}});
"""

SCEN = r"""
R.html = sessPickHtml({state: 'run', mbox: 'cc-a'});
R.dot = sessPickHtml({state: 'run', mbox: ''});
// native label click: first the label itself, then the forwarded click on the input
sessClick(ev(lab)); sessClick(ev(inp));
R.lab = [OPEN, INV, [...picked]];
sessClick(ev(row)); R.row = OPEN;
"""


def run(body):
    src = (STUBS + jconst("esc") + "\n" + "\n".join(js_fn(f) for f in FNS)
           + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"), encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SessPickHit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(SCEN)

    def test_input_wrapped_in_label(self):
        h = self.R["html"]
        self.assertTrue(h.startswith("<label class=spickw><input type=checkbox class=spick"), h)
        self.assertIn('data-mb="cc-a"', h)
        self.assertTrue(h.endswith("</label>"), h)

    def test_unpickable_dot_unchanged(self):
        self.assertNotIn("label", self.R["dot"])
        self.assertIn("<span class=spick", self.R["dot"])

    def test_label_click_toggles_once_no_log(self):
        self.assertEqual(self.R["lab"], [0, 1, ["cc-a"]])

    def test_row_click_still_opens_log(self):
        self.assertEqual(self.R["row"], 1)


if __name__ == "__main__":
    unittest.main()
