"""60 buildSbar with a non-primary «Main account»: its est is always low (no history for non-primary accounts),
so the bar still shows «left ≈» from it with low accuracy in the tooltip; the primary path is unchanged."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import i18n, jconst
from tests._node import node_e

FNS = ("acctList", "mainAcct", "mainAcctOk", "acctHash", "acctCls", "fmtPct", "knQ", "lsGet", "lsSet", "lsDel",
       "acctLabel", "acctPick", "acctInPick", "buildSbar", "sbPctCls", "sbPrimNote", "burnMainDir", "burnFor",
       "burnEst", "burnEstTip", "burnWkEst", "estLeftTxt")

BODY = r"""
let SV = null, SBAR_SV = null, SVSW = null, EXTU = null, CONN = {}, SDRW_OPEN = false, HTML = '', BURNM = null, BURNM_DIR = '';
const SBEL = {title: '', clientWidth: 1100, _fitW: 1100};
document.getElementById = id => id === 'sbar' ? SBEL : id === 'dot' ? {classList: {contains: () => false}} : null;
function svParts(){ return null; } function svLive(){ return null; } function sbExt(){ return ''; } function aiLogo(){ return ''; }
function connAge(){ return ''; } function setHtml(el, h){ HTML = h; return true; } function sbFit(){} function buildQwho(){}
function popIsOpen(){ return false; } const SRVLOAD = null; function sbBusy(){ return null; }
function LATER(s){ return s; } function HM(m){ return m + 'm'; }
ACCTS = [{label: 'me', primary: true}, {label: 'work', dir: '/w'}];
QLAST = {q: {five_hour: {pct: 10}, seven_day: {pct: 20}, accounts: [{label: 'work', five_hour: {pct: 33}, seven_day: {pct: 44}}]}};
BURN = {ok: true, at: 1, cur: {used_local: 5000, now_pct: 10}, est: {h5_left: 7000, h5_n: 5, h5_src: 'med', wk_left: 70000, wk_n: 4}};
buildSbar(); R.prim = HTML;
STORE.mbMainAcct = 'work'; BURNM_DIR = '/w';
BURNM = {ok: true, at: 1, cur: {now_pct: 33, used_acct: 777}, wk: {now_pct: 44, used_acct: 8888},
  est: {low: true, h5_left: 25000000, h5_n: 0, h5_src: 'win', wk_left: 300000000, wk_used: 90000000}};
buildSbar(); R.main = HTML;
BURNM = {ok: true, at: 1, cur: {now_pct: 33}, est: {low: true}};
buildSbar(); R.none = HTML;
"""


def run():
    src = ("var document = {getElementById: () => null};\nconst NL = String.fromCharCode(10);\n"
           "let QLAST = null, SESS = [], ACCTS = [], USG = null, STORE = {}, BURN = null;\n"
           "const UIS = {getItem: k => k in STORE ? STORE[k] : null, setItem: (k, v) => { STORE[k] = String(v); }, removeItem: k => { delete STORE[k]; }};\n"
           "function softErr(){}\nfunction burnUsedTip(){ return 'u'; } function fmtTok(n){ return String(n); }\n"
           "function bnHM(){ return '10:00'; } function CLK(d){ return 'clk'; } function RST7(d){ return {abs: 'abs', rel: 'rel'}; }\n"
           + i18n() + "\n" + jconst("esc") + "\n" + "\n".join(js_fn(f) for f in FNS)
           + "\nconst R = {};\nLANG = 'en';\n" + BODY + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"), encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def seg(html, k):
    return next((x for x in html.split("<span title=") if "<b>" + k + "</b>" in x), "")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class MainLowEst(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run()

    def test_main_low_est_shows_left(self):
        s5, s7 = seg(self.R["main"], "5h"), seg(self.R["main"], "7d")
        self.assertIn("left ≈</small> <b>25000000</b>", s5)
        self.assertIn("left ≈</small> <b>300000000</b>", s7)
        # low accuracy is said once per tooltip, not as a visible bar marker
        self.assertEqual(s5.count("Not enough history — low accuracy"), 1)
        self.assertEqual(s7.count("Not enough history — low accuracy"), 1)
        self.assertNotIn("5000<", self.R["main"])   # never the primary's used_local

    def test_main_low_est_without_numbers_shows_nothing(self):
        self.assertNotIn("left ≈", self.R["none"])   # unknown stays unknown, not «left ≈ 0»

    def test_primary_unchanged(self):
        s5, s7 = seg(self.R["prim"], "5h"), seg(self.R["prim"], "7d")
        self.assertIn("left ≈</small> <b>7000</b>", s5)
        self.assertIn("left ≈", s7)
        self.assertNotIn("low accuracy", self.R["prim"])


if __name__ == "__main__":
    unittest.main()
