"""Per-view account picker (40b acctPick/acctInPick/acctPickHtml/acctPickWire):
default All = every row, picks are per view, one account = no picker and no filter, old «Only main account» migrates once."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import i18n, jconst
from tests._node import node_e

FNS = ("acctList", "mainAcct", "mainAcctOk", "lsGet", "lsSet", "lsDel", "acctLabel",
       "acctPick", "acctInPick", "acctPickHtml", "acctPickFocusId", "acctPickWire")

STUBS = r"""
let ACCTS = [], STORE = {}, EL = {}, FOC = null;
var document = {getElementById: id => EL[id] || null, get activeElement(){ return FOC; }};
const UIS = {getItem: k => k in STORE ? STORE[k] : null, setItem: (k, v) => { STORE[k] = String(v); }, removeItem: k => { delete STORE[k]; }};
function softErr(){}
const ACC_OTH = {sess: 1, srec: 1, attn: 1, time: 1};
const ROWS = [{sid: 'p', plat: 'cc'}, {sid: 'w', plat: 'cc', acct: 'work'}, {sid: 'x', plat: 'cx'}, {sid: 'q'}];
const keep = v => ROWS.filter(x => acctInPick(x, v)).map(x => x.sid).join(',');
"""

SCEN = r"""
const TWO = [{label: 'me', primary: true}, {label: 'work'}, {label: '<b>'}];
// R4: one account — no picker, no filter, even with a stored pick
ACCTS = [{label: 'me', primary: true}]; STORE['mbAcctPick.sess'] = 'work';
R.one = [acctPickHtml('sess'), keep('sess'), acctPick('sess')];
// R1: default All = every row
ACCTS = TWO; STORE = {};
R.all = [keep('sess'), keep('time'), acctPick('sess')];
R.html = acctPickHtml('sess');
// R2: picks are per view
STORE['mbAcctPick.sess'] = 'work'; R.sessW = [keep('sess'), keep('time')];
STORE['mbAcctPick.time'] = 'me'; R.both = [keep('sess'), keep('time')];
STORE['mbAcctPick.sess'] = 'gone'; R.stale = keep('sess');
// Wire: change writes / clears only its own key, resets the folds of that view, redraws, keeps mbMainAcct untouched
STORE = {mbMainAcct: 'work'}; let RD = 0;
const sel = {id: 'acpk-sess', value: 'work', focus(){ FOC = sel; }}; EL['acpk-sess'] = sel;
acctPickWire('sess', () => { RD++; }); sel.onchange();
R.wire1 = [STORE['mbAcctPick.sess'], 'mbAcctPick.time' in STORE, RD, Object.keys(ACC_OTH).sort(), STORE.mbMainAcct];
sel.value = ''; sel.onchange(); R.wire2 = ['mbAcctPick.sess' in STORE, RD];
// Focus: a repaint that replaced the focused select refocuses the new one by id
FOC = {id: 'acpk-sess', classList: {contains: c => c === 'acpk'}}; const fo = acctPickFocusId();
acctPickWire('sess', () => {}, fo); R.foc = [fo, FOC === sel];
// Migration: old toggle on -> main account (or primary label), key removed; off -> All
STORE = {mbOnlyMain: '1'}; R.migP = [acctPick('sess'), STORE['mbAcctPick.sess'], 'mbOnlyMain' in STORE];
STORE = {mbOnlyMain: '1', mbMainAcct: 'work'}; R.migW = [acctPick('time'), acctPick('sess'), 'mbOnlyMain' in STORE, STORE.mbMainAcct];
STORE = {}; R.migOff = [acctPick('sess'), Object.keys(STORE)];
"""


def run(body):
    src = (STUBS + i18n() + "\n" + jconst("esc") + "\n" + "\n".join(js_fn(f) for f in FNS)
           + "\nconst R = {};\nLANG = 'en';\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"), encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class AcctPick(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(SCEN)

    def test_one_account_no_picker(self):
        self.assertEqual(self.R["one"], ["", "p,w,x,q", ""])

    def test_default_all(self):
        self.assertEqual(self.R["all"], ["p,w,x,q", "p,w,x,q", ""])
        h = self.R["html"]
        self.assertIn('id="acpk-sess"', h)
        self.assertIn('<option value="" selected>All accounts</option>', h)
        self.assertIn("&lt;b&gt;", h); self.assertNotIn("<b>", h)          # labels are escaped user data

    def test_picks_per_view(self):
        self.assertEqual(self.R["sessW"], ["w,x", "p,w,x,q"])               # external CLI row stays; acct '' = primary
        self.assertEqual(self.R["both"], ["w,x", "p,x,q"])
        self.assertEqual(self.R["stale"], "p,w,x,q")

    def test_wire(self):
        self.assertEqual(self.R["wire1"], ["work", False, 1, ["time"], "work"])
        self.assertEqual(self.R["wire2"], [False, 2])
        self.assertEqual(self.R["foc"], ["acpk-sess", True])

    def test_migration(self):
        self.assertEqual(self.R["migP"], ["me", "me", False])
        self.assertEqual(self.R["migW"], ["", "work", False, "work"])      # time never migrates; main account unchanged
        self.assertEqual(self.R["migOff"], ["", []])


if __name__ == "__main__":
    unittest.main()
