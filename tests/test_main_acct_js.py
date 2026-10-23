"""«Main account» view setting (40b mainAcct/acctCls, 55a knQ, 41 sesCount):
no key = the primary window; a valid key moves the quota window and counts; stale key or unknown quota falls back with a flag."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import i18n, jconst
from tests._node import node_e

FNS = ("acctList", "mainAcct", "mainAcctOk", "acctHash", "acctCls", "fmtPct", "knQ",
       "lsGet", "lsSet", "lsDel", "acctLabel", "acctPick", "acctInPick", "sesCount")


def run(body):
    src = ("var document = {getElementById: () => null};\nconst NL = String.fromCharCode(10);\n"
           "let QLAST = null, SESS = [], ACCTS = [], USG = null, STORE = {};\n"
           "let BURN = {ok: true, cur: {used_local: 5000, now_pct: 40}, proj: {over_at: 1}};\n"
           "const UIS = {getItem: k => k in STORE ? STORE[k] : null, setItem: (k, v) => { STORE[k] = String(v); }, removeItem: k => { delete STORE[k]; }};\n"
           "function softErr(){}\n"
           "function burnEst(){ return {tip: 't', left: 9}; } function burnUsedTip(){ return 'u'; } function fmtTok(n){ return String(n); }\n"
           "function bnHM(){ return '10:00'; } function burnWkEst(){ return null; }\n"
           "function CLK(d){ return 'clk'; } function RST7(d){ return {abs: 'abs', rel: 'rel'}; }\n"
           + i18n() + "\n" + jconst("esc") + "\n" + "\n".join(js_fn(f) for f in FNS)
           + "\nconst R = {};\nLANG = 'en';\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"), encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


SNAP = r"""
const kq = k => { const r = knQ(k); return [r.w && r.w.pct, r.main, r.miss]; };
const snap = () => [kq('5h'), kq('7d'), acctCls('work'), acctCls('')];
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class MainAcct(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(SNAP + r"""
ACCTS = [{label: 'me', primary: true}, {label: 'work'}, {label: 'side'}];
SESS = [{sid: 'a', state: 'idle'}, {sid: 'b', state: 'idle', acct: 'work'}];
QLAST = {q: {five_hour: {pct: 10}, seven_day: {pct: 20},
  accounts: [{label: 'work', five_hour: {pct: 33}, seven_day: {pct: 44}}, {label: 'side', five_hour: {pct: 50}}]}};
R.none = snap(); R.noneMain = mainAcct();
STORE.mbMainAcct = 'gone'; R.stale = snap();
STORE.mbMainAcct = 'me'; R.prim = snap();
STORE.mbMainAcct = 'work'; R.work = snap(); R.workMain = mainAcct(); R.side = acctCls('side');
R.plan = [mainAcctOk('junk'), mainAcctOk('me'), mainAcctOk('side')];
QLAST.q.accounts[0].err = 'http'; R.err = kq('5h');
QLAST.q.accounts[0].age = 40; R.errKept = kq('5h'); QLAST.q.accounts[0].age = 1801; R.errOld = kq('5h'); delete QLAST.q.accounts[0].age;
delete QLAST.q.accounts[0].err; QLAST.q.accounts[0].five_hour = {pct: null}; R.nopct = [kq('5h'), kq('7d')];
QLAST.q.accounts = [QLAST.q.accounts[1]]; R.norow = kq('5h');
ACCTS = [{label: 'me', primary: true}]; R.one = [mainAcct(), kq('5h')];
""")

    def test_no_key_matches_stale_and_primary(self):
        self.assertEqual(self.R["noneMain"], "")
        self.assertEqual(self.R["none"], self.R["stale"])
        self.assertEqual(self.R["none"], self.R["prim"])
        n = self.R["none"]
        self.assertEqual(n[:2], [[10, "", False], [20, "", False]])
        self.assertEqual(n[3], "acb acc0")

    def test_main_work(self):
        w = self.R["work"]
        self.assertEqual(self.R["workMain"], "work")
        self.assertEqual(w[:2], [[33, "work", False], [44, "work", False]])
        self.assertEqual(w[2], "acb acc0")
        self.assertRegex(w[3], r"^acb acc[1-6]$")
        self.assertNotEqual(w[3], self.R["side"])

    def test_fallback_flag(self):
        self.assertEqual(self.R["err"], [10, "work", True])
        self.assertEqual(self.R["errKept"], [33, "work", False])   # failed refetch: kept fresh numbers still show
        self.assertEqual(self.R["errOld"], [10, "work", True])     # kept past quota_roots.ROW_KEEP_S = unmeasured
        self.assertEqual(self.R["nopct"], [[10, "work", True], [44, "work", False]])
        self.assertEqual(self.R["norow"], [10, "work", True])

    def test_validation(self):
        self.assertEqual(self.R["plan"], ["", "", "side"])   # junk / primary label never become main

    def test_single_account_ignores_key(self):
        self.assertEqual(self.R["one"], ["", [10, "", False]])


ONLY = r"""
function waitOnLabel(){ return ''; }
ACCTS = [{label: 'me', primary: true}, {label: 'work'}];
SESS = [{sid: 'a', state: 'think'}, {sid: 'b', state: 'idle', acct: 'work'}, {sid: 'c', state: 'ask', acct: 'work'}];
R.off = sesCount();
STORE['mbAcctPick.sess'] = 'me';
R.on = sesCount();
STORE['mbAcctPick.sess'] = 'work';
R.onWork = sesCount();
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class OnlyMain(unittest.TestCase):
    """Sessions account pick: sesCount (header badge, chips) drops other accounts and tallies them in oth."""

    @classmethod
    def setUpClass(cls):
        cls.R = run(ONLY)

    def test_count_follows_filter(self):
        self.assertEqual(self.R["off"]["open"], 3)
        on = self.R["on"]
        self.assertEqual([on["open"], on["work"], on["need"], on["oth"]], [1, 1, 0, 2])
        self.assertEqual([self.R["onWork"]["open"], self.R["onWork"]["oth"]], [2, 1])


SBAR = r"""
let SV = null, SBAR_SV = null, SVSW = null, EXTU = null, CONN = {}, SDRW_OPEN = false, HTML = '', BURNM = null, BURNM_DIR = '';
const SBEL = {title: '', clientWidth: 1100, _fitW: 1100};
document.getElementById = id => id === 'sbar' ? SBEL : id === 'dot' ? {classList: {contains: () => false}} : null;
function svParts(){ return null; } function svLive(){ return null; } function sbExt(){ return ''; } function aiLogo(){ return ''; }
function connAge(){ return ''; } function setHtml(el, h){ HTML = h; return true; } function sbFit(){} function buildQwho(){}
function popIsOpen(){ return false; }
function LATER(s){ return s; } function HM(m){ return m + 'm'; } function burnEstTip(){ return 'e'; }
BURN.proj = {pct: 70, over_at: 1}; BURN.cur.rate_pph = 10; BURN.at = 1;
const seg = k => HTML.split('<span').find(x => x.indexOf('<b>' + k + '</b>') >= 0) || '';
const bar = () => { buildSbar(); return [seg('5h'), seg('7d'), HTML.indexOf('sbd2') >= 0, HTML.indexOf('sbd1') >= 0]; };
ACCTS = [{label: 'me', primary: true}, {label: 'work', dir: '/w'}];
QLAST = {q: {five_hour: {pct: 10}, seven_day: {pct: 20}, accounts: [{label: 'work', five_hour: {pct: 33}, seven_day: {pct: 44}}]}};
R.b0 = bar(); R.n0 = sbPrimNote();
STORE.mbMainAcct = 'work'; R.b1 = bar(); R.n1 = sbPrimNote();
BURNM_DIR = '/w'; BURNM = {ok: true, at: 1, cur: {now_pct: 33, rate_pph: 10}, proj: {pct: 60, over_at: 1}}; R.b3 = bar(); BURNM = null;
BURNM = {ok: true, at: 1, est: {low: true}, cur: {now_pct: 33, used_acct: 777}, wk: {now_pct: 44, used_acct: 8888}, proj: {pct: 60}};
R.b4 = bar(); R.t4 = HTML; BURNM = null;
QLAST.q.accounts[0].err = 'http'; R.b2 = bar();
QLAST.q.accounts[0].age = 40; R.b2k = bar(); QLAST.q.accounts[0].age = 1801; R.b2o = bar();
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class StatusBarFollowsMain(unittest.TestCase):
    """60 buildSbar reads knQ: the bar's «left N%» follows the main account, primary-only BURN parts hide with main set."""

    @classmethod
    def setUpClass(cls):
        src = "\n".join(js_fn(f) for f in ("buildSbar", "sbPctCls", "sbPrimNote", "burnMainDir", "burnFor"))
        cls.R = run(src + "\n" + SBAR)

    def test_default_primary_with_burn(self):
        b = self.R["b0"]
        self.assertIn(">90%</b>", b[0])
        self.assertTrue(b[2] and b[3])            # projection + ETA from BURN
        self.assertIn("used", b[0])
        self.assertEqual(self.R["n0"], "")

    def test_main_set_bar_follows_main(self):
        b = self.R["b1"]
        self.assertIn(">67%</b>", b[0]); self.assertIn(">56%</b>", b[1])
        self.assertFalse(b[2] or b[3])            # primary burndown hidden
        self.assertNotIn("used", b[0])
        self.assertIn("Main account work", b[0])
        self.assertIn("(me)", self.R["n1"])
        b3 = self.R["b3"]   # main's own ?dir= body: projection + ETA come back, tokens stay hidden
        self.assertTrue(b3[2] and b3[3])
        self.assertNotIn("used", b3[0])

    def test_main_own_used_is_approx(self):
        b = self.R["b4"]   # main's own hour-bucket sums: «used ≈», never «used», low est keeps «left ≈» out
        self.assertIn("used ≈</small> <b>777</b>", b[0]); self.assertIn("used ≈</small> <b>8888</b>", b[1])
        self.assertNotIn("<small>· used</small>", self.R["t4"]); self.assertNotIn("left ≈</small>", self.R["t4"])
        self.assertNotIn("5000", self.R["t4"])   # ⚠never the primary's used_local
        self.assertNotIn("left ≈", self.R["b1"][0]); self.assertNotIn("used", self.R["b1"][0])

    def test_main_unknown_falls_back(self):
        b = self.R["b2"]
        self.assertIn(">90%</b>", b[0])
        self.assertIn("Main account quota unknown", b[0])
        k = self.R["b2k"]   # failed refetch with fresh kept data: main's own window, no fallback note
        self.assertIn(">67%</b>", k[0]); self.assertNotIn("Main account quota unknown", k[0])
        self.assertEqual(self.R["b2o"][0], b[0])   # kept past quota_roots.ROW_KEEP_S: same fallback as no data



if __name__ == "__main__":
    unittest.main()
