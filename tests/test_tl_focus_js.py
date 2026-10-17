"""Timeline focus: popTabOut closes a popover with nothing focusable when Tab leaves its opener (others unchanged);
tlgFocusId names a focused chip control; paintTl refocuses it after rebuilding the toolbar; #tlq has a focus ring."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def src(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


STUB = r"""
const mk = (id, sel, kids) => ({id, hidden: false, offsetParent: {}, kids: kids || [],
  closest(s){ return s.split(',').map(x => x.trim()).includes(sel) ? this : null; },
  contains(x){ return x === this || this.kids.includes(x); },
  querySelectorAll(){ return this.kids; }});
const btn = mk('b', 'button'), tlq = mk('tlq', '#tlq'), other = mk('x', '#x'), knc = mk('knc', '#kn .kni');
const tlqp = mk('tlqp', '#tlqp'), knpop = mk('knpop', '#knpop', [btn]);
const els = {tlqp, knpop};
var document = {activeElement: null, getElementById: id => els[id] || null};
const closed = [];
const UIPOPS = [{id: 'tlqp', inside: '#tlqp, #tlq', close: b => { closed.push('tlqp:' + b); tlqp.hidden = true; }},
                {id: 'knpop', inside: '#kn .kni, #knpop', close: b => { closed.push('knpop:' + b); knpop.hidden = true; }}];
const ev = (k, sh) => ({key: k, shiftKey: !!sh, prevented: false, preventDefault(){ this.prevented = true; }});
"""


def run(body):
    code = (STUB + js_fn("popTabOut") + "\n" + js_fn("tlgFocusId")
            + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(code), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TlFocus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
let e = ev('Tab');
document.activeElement = other; popTabOut(e);
R.elsewhere = closed.slice();
document.activeElement = tlq; e = ev('Tab'); popTabOut(e);
R.opener = closed.slice(); R.openerPrevented = e.prevented;
document.activeElement = knc; e = ev('Tab'); popTabOut(e);
R.knOpener = closed.slice();
document.activeElement = btn; e = ev('Tab'); popTabOut(e);
R.knLast = closed.slice(); R.knPrevented = e.prevented;
document.activeElement = {id: 'tlgss'}; R.fo = tlgFocusId();
document.activeElement = {id: 'tlgcp'}; R.fo2 = tlgFocusId();
document.activeElement = {id: 'tlgbm'}; R.none = tlgFocusId();
document.activeElement = null; R.nul = tlgFocusId();
""")

    def test_tab_elsewhere_keeps_popover(self):
        self.assertEqual(self.R["elsewhere"], [])

    def test_tab_off_opener_closes_empty_popover(self):
        self.assertEqual(self.R["opener"], ["tlqp:false"])
        self.assertFalse(self.R["openerPrevented"])

    def test_focusable_popover_unchanged(self):
        self.assertEqual(self.R["knOpener"], ["tlqp:false"])
        self.assertEqual(self.R["knLast"], ["tlqp:false", "knpop:true"])
        self.assertTrue(self.R["knPrevented"])

    def test_rail_focus_id(self):
        self.assertEqual(self.R["fo"], "tlgss")
        self.assertEqual(self.R["fo2"], "tlgcp")
        self.assertEqual(self.R["none"], "")
        self.assertEqual(self.R["nul"], "")

    def test_paint_tl_refocuses_rail(self):
        s = js_fn("paintTl")
        self.assertIn("tlgFocusId()", s)
        self.assertLess(s.index("tlgFocusId()"), s.index("tbSet('time', tlCtlHtml() + tlgChipHtml());\n"))
        self.assertIn("getElementById(tlgFo)", s)

    def test_tlq_focus_ring(self):
        self.assertIn(".tlq:focus-visible{outline:2px solid var(--nx-info)", src("web/css/90-main-ui.css"))
