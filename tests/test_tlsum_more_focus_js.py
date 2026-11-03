"""Window summary «More»/«Less» keeps keyboard focus on #tlsmore across the innerHTML redraw.
One node run with a stub DOM; no clock, no live files."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

STUB = r"""
let more = false, gen = 0, cur = null;
const body = {id: 'BODY'};
var document = {body, activeElement: body, getElementById: id => id === 'tlsmore' ? cur : null};
const mkBtn = () => { const b = {id: 'tlsmore', gen: ++gen, onclick: null, onkeydown: null, scrollOpt: null,
  focus(o){ this.scrollOpt = o; document.activeElement = this; }}; return b; };
const host = {firstChild: null, _h: '', get innerHTML(){ return this._h; },
  set innerHTML(v){ this._h = v; this.firstChild = v ? {} : null;
    if(document.activeElement && document.activeElement.id === 'tlsmore') document.activeElement = body;
    cur = v.indexOf('id=tlsmore') >= 0 ? mkBtn() : null; }};
var tlSumHtml = '', TLD = {ok: true, at: 1000, hours: 12, rows: [{kind: 'sess'}, {kind: 'ag', start: 0, end: 10}]};
var BURN = {cur: {start: 0}};
const T = s => s, TV = o => o.msg, esc = s => String(s), rangeLbl = () => '12h';
function tlSumMoreOn(){ return more; }
function tlSumMoreSet(on){ more = on; }
function tlSumWork(){ return {c: 0, n: 0, ok: 0, bad: 0, lb: 0, ev: 0, pass: 0, fail: 0, step: ''}; }
function tlSumDur(s){ return s + 's'; }
function curWinTok(){ return null; }
function tlExtTok(){ return {}; }
function aiLogo(p){ return p; }
function fmtTok(n){ return String(n); }
"""


def run(body):
    code = STUB + js_fn("tlSumDraw") + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));"
    r = subprocess.run(node_e(code), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TlSumMoreFocus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
tlSumDraw(host);
const b0 = cur; b0.focus(); const g0 = b0.gen;
b0.onkeydown({type: 'keydown', key: 'Enter'});
R.a1 = document.activeElement.id; R.new1 = document.activeElement.gen !== g0; R.more1 = more;
R.opt = document.activeElement.scrollOpt;
document.activeElement.onkeydown({type: 'keydown', key: 'Enter'});
R.a2 = document.activeElement.id; R.more2 = more;
document.activeElement = body; cur.onclick({type: 'click'});
R.a3 = document.activeElement.id; R.more3 = more;
""")

    def test_enter_keeps_focus_on_new_toggle(self):
        self.assertEqual(self.R["a1"], "tlsmore")
        self.assertTrue(self.R["new1"])
        self.assertTrue(self.R["more1"])
        self.assertEqual(self.R["opt"], {"preventScroll": True})

    def test_second_enter_toggles_back(self):
        self.assertEqual(self.R["a2"], "tlsmore")
        self.assertFalse(self.R["more2"])

    def test_unfocused_click_does_not_steal_focus(self):
        self.assertEqual(self.R["a3"], "BODY")
        self.assertTrue(self.R["more3"])


if __name__ == "__main__":
    unittest.main()
