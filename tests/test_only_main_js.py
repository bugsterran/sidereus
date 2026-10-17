"""Sessions account pick lists (40b acctPick/acctInPick/acctOthHtml/acctOthClick, buildSessions, 41b srecRows, 17 buildAttn):
All or <2 accounts = byte-identical; a pick = other-account rows behind one count line per list, expanded per list on click."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import i18n, jconst
from tests._node import node_e

FNS = ("acctList", "mainAcct", "mainAcctOk", "lsGet", "lsSet", "lsDel", "acctLabel", "acctPick", "acctInPick", "acctOthHtml", "acctOthClick",
       "buildSessions", "wfFoldBtns", "sessClick", "srecRows", "buildAttn")

STUBS = r"""
const EL = {sess: {innerHTML: ''}, attn: {innerHTML: '', querySelector: () => null, contains: () => false}};
var document = {getElementById: id => EL[id] || null, activeElement: null};
let SESS = [], ACCTS = [], STORE = {}, sessHover = false, sessDirty = false, sessOpen = false, stFil = '', idleMin = 0, gitFil = '';
let SREC = {rows: [], q: '', err: false}, ATTN_MAX = 5, attnMore = false, attnLow = true, attnHtml = '', ATTR = null;
const UIS = {getItem: k => k in STORE ? STORE[k] : null, setItem: (k, v) => { STORE[k] = String(v); }, removeItem: k => { delete STORE[k]; }};
function softErr(){}
function buildFilters(){} function sessFit(){} function buildInvite(){} function isIdle(){ return true; } function hasGit(){ return true; }
function morphHtml(el, h){ el.innerHTML = h; } function setHtml(el, h){ el.innerHTML = h; }
function TV(o){ return T(o.msg).replace('{n}', o.vars.n); }
function sessRowHtml(x){ return '<R' + x.sid + '>'; }
function acctRowCls(){ return ''; } function acctTip(){ return ''; } function acctChip(){ return ''; } function srecCmd(){ return ''; }
const PK = 'mbAcctPick.sess';
function cpfbLabel(k, s){ return s; } function cpfbBox(){ return ''; } function plStrip(s){ return s; } function agoAt(){ return 'ago'; }
function attnRows(){ return JSON.parse(JSON.stringify(ATTR)); }
function attnBadgeN(){ return attnRows().shown.filter(x => x.badge).length; }
function attnSess(r){ return SESS.find(x => x.sid === r.sid) || null; }
function attnRowHTML(x){ return '<A' + x.r.sid + '>'; }
const tgt = sel => ({target: {closest: s => s === '[data-ao]' ? sel : null}});
const cnt = (h, s) => h.split(s).length - 1;
"""


def run(body):
    src = (STUBS + i18n() + "\n" + jconst("esc") + "\n" + "\n".join(js_fn(f) for f in FNS)
           + "\nconst ACC_OTH = {};\nconst R = {};\nLANG = 'en';\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"), encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


SCEN = r"""
const all = () => { buildSessions(); const s = EL.sess.innerHTML; const r = srecRows(); attnHtml = ''; buildAttn(); return [s, r, EL.attn.innerHTML]; };
SESS = [{sid: 'p', state: 'tool', plat: 'cc'}, {sid: 'w', state: 'tool', plat: 'cc', acct: 'work'},
        {sid: 'x', state: 'ask', plat: 'cx'}, {sid: 'd', state: 'done', plat: 'cc', acct: 'work'}];
SREC.rows = [{sid: 'p1', name: 'a'}, {sid: 'w1', name: 'b', acct: 'work'}, {sid: 'w2', name: 'c', acct: 'work'}];
ATTR = {shown: [{r: {sid: 'p'}, badge: 1}, {r: {sid: 'w'}, badge: 1}, {r: {sid: 'zz'}, badge: 1}], snoozed: 0, quiet: 1, low: [{r: {sid: 'd'}, badge: 0}]};
ACCTS = [{label: 'me', primary: true}];
R.oneOff = all(); STORE[PK] = 'me'; R.oneOn = all();
ACCTS = [{label: 'me', primary: true}, {label: 'work'}];
delete STORE[PK]; R.off = all(); R.badge0 = attnBadgeN();
STORE[PK] = 'me'; R.on = all(); R.badge1 = attnBadgeN();
sessOpen = true; R.onOpen = all(); sessOpen = false; attnLow = false; R.lowShut = all(); attnLow = true;
STORE[PK] = 'gone'; R.stale = all();
STORE[PK] = 'work'; R.work = all();
STORE[PK] = 'me';
ATTR.shown[1].badge = 0; ATTR.shown[1].r.sid = 'd'; ATTR.low = []; ATTR.quiet = 0; attnHtml = ''; buildAttn(); R.cold = EL.attn.innerHTML;
ATTR = {shown: [{r: {sid: 'p'}, badge: 1}, {r: {sid: 'w'}, badge: 1}], snoozed: 0, quiet: 0, low: []};
sessHover = true; sessDirty = true;
R.clk = [acctOthClick(tgt(null), () => {}), sessClick(tgt({getAttribute: () => 'sess'}))];
R.exp = all(); R.expKeys = Object.keys(ACC_OTH); R.hover = [sessHover, sessDirty];
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class OnlyMain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(SCEN)

    def test_off_and_single_account_identical(self):
        self.assertEqual(self.R["oneOff"], self.R["oneOn"])
        self.assertEqual(self.R["oneOff"], self.R["off"])
        for h in self.R["off"]:
            self.assertNotIn("acoth", h)

    def test_on_hides_other_rows_one_line_each(self):
        s, r, a = self.R["on"]
        self.assertIn("<Rp>", s); self.assertIn("<Rx>", s)          # primary + external CLI row stay
        self.assertNotIn("<Rw>", s)
        self.assertEqual(s.count("data-ao="), 1); self.assertIn("In other accounts: 1", s)   # ended row under the closed fold not counted
        self.assertEqual(r.count("data-ao="), 1); self.assertIn("In other accounts: 2", r)
        self.assertNotIn(">b<", r); self.assertIn(">a<", r)
        self.assertEqual(a.count("data-ao="), 1); self.assertIn("In other accounts: 2", a)   # shown + low
        self.assertIn("<Ap>", a); self.assertIn("<Azz>", a)          # unknown session stays
        self.assertNotIn("<Aw>", a)
        self.assertIn("<b>2</b>", a)                                  # header counts visible only

    def test_counts_follow_folds(self):
        self.assertIn("In other accounts: 2", self.R["onOpen"][0])     # ended fold open: the ended row counts
        a = self.R["lowShut"][2]
        self.assertIn("In other accounts: 1", a)                         # low fold closed: hidden low row not counted
        self.assertIn("acothd", a)

    def test_hot_dot(self):
        self.assertIn("acothd", self.R["on"][2])
        self.assertNotIn("acothd", self.R["on"][1])
        self.assertNotIn("acothd", self.R["cold"])

    def test_badge_count_unfiltered(self):
        self.assertEqual(self.R["badge0"], 3)
        self.assertEqual(self.R["badge1"], 3)

    def test_stale_pick_is_all(self):
        self.assertEqual(self.R["stale"], self.R["off"])

    def test_pick_work_hides_primary(self):
        s, r, a = self.R["work"]
        self.assertIn("<Rw>", s); self.assertNotIn("<Rp>", s); self.assertIn("<Rx>", s)
        self.assertIn("In other accounts: 1", r)
        self.assertIn("<Azz>", a); self.assertNotIn("<Ap>", a)          # session not in SESS stays with pick 'work'

    def test_click_expands_only_that_list(self):
        self.assertEqual(self.R["clk"], [False, None])
        self.assertEqual(self.R["expKeys"], ["sess"])
        self.assertEqual(self.R["hover"], [False, False])
        s, r, a = self.R["exp"]
        self.assertIn("<Rw>", s); self.assertNotIn("acoth", s)
        self.assertIn("acoth", r); self.assertIn("acoth", a)


if __name__ == "__main__":
    unittest.main()
