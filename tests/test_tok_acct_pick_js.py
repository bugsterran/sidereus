"""Tokens «Period totals» account pick (45 loadWkRange · 46 paintToken): `&acct=` only when picked,
a reply for an older pick is dropped, one account = no #acpk-tok."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests.test_saver_quota_js import i18n, jconst
from tests._node import node_e

FNS = ("acctList", "mainAcct", "mainAcctOk", "lsGet", "lsSet", "lsDel", "acctLabel", "acctPick", "acctPickHtml")

STUBS = r"""
let ACCTS = [], STORE = {}, URLS = [], PAINT = 0, PEND = [];
var document = {getElementById: () => null, activeElement: null, addEventListener(){}};
const UIS = {getItem: k => k in STORE ? STORE[k] : null, setItem: (k, v) => { STORE[k] = String(v); }, removeItem: k => { delete STORE[k]; }};
function softErr(){}
function paintToken(){ PAINT++; }
function keepGood(p, m){ return {err: m}; }
function getJSON(u){ URLS.push(u); return new Promise(r => PEND.push(r)); }
let WKR = null, WKRANGE = 7, wkrAt = 0, wkrWatch = 0;
const WKU_TICK_MS = 3000, WKU_WAIT_TICKS = 100, WKU_WAIT_SEC = 300;
"""

SCEN = r"""
(async () => {
  const TWO = [{label: 'me', primary: true}, {label: 'work'}];
  ACCTS = TWO;
  loadWkRange(true); PEND.shift()({acct: '', at: 0, err: 'x'}); await 0; await 0;
  STORE['mbAcctPick.tok'] = 'work';
  loadWkRange(true); PEND.shift()({acct: 'work', at: 5}); await 0; await 0;
  R.urls = URLS.slice(); R.wkr = WKR;
  // stale: request for work in flight, pick switched to All, the work reply arrives
  WKR = null; loadWkRange(true); delete STORE['mbAcctPick.tok'];
  PEND.shift()({acct: 'work', at: 9}); await 0; await 0;
  R.stale = [WKR, URLS[URLS.length - 1]];
  // other views' picks do not leak in
  STORE = {'mbAcctPick.sess': 'work', 'mbAcctPick.time': 'work'}; URLS = [];
  loadWkRange(true); R.indep = URLS[0];
  R.html2 = acctPickHtml('tok');
  ACCTS = [{label: 'me', primary: true}]; STORE['mbAcctPick.tok'] = 'work';
  R.html1 = acctPickHtml('tok'); R.pick1 = acctPick('tok');
  process.stdout.write(JSON.stringify(R));
})();
"""


def _load_wk_range():
    m = re.search(r"^async function loadWkRange\(.*?^}$", js_all(), re.S | re.M)
    return m.group(0)


def run():
    src = (STUBS + i18n() + "\n" + jconst("esc") + "\n" + "\n".join(js_fn(f) for f in FNS) + "\n" + _load_wk_range()
           + "\nconst R = {};\nLANG = 'en';\n" + SCEN)
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"), encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TokAcctPick(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run()

    def test_acct_only_when_picked(self):
        self.assertEqual(self.R["urls"], ["/api/wkuse?range=7", "/api/wkuse?range=7&acct=work"])
        self.assertEqual(self.R["wkr"], {"acct": "work", "at": 5})

    def test_stale_reply_dropped(self):
        self.assertEqual(self.R["stale"], [None, "/api/wkuse?range=7&acct=work"])

    def test_pick_is_per_tab(self):
        self.assertEqual(self.R["indep"], "/api/wkuse?range=7")

    def test_picker_only_with_two_accounts(self):
        self.assertIn('id="acpk-tok"', self.R["html2"])
        self.assertEqual((self.R["html1"], self.R["pick1"]), ("", ""))

    def test_paint_token_wires_picker(self):
        src = js_fn("paintToken")
        self.assertIn("acctPickHtml('tok')", src)
        self.assertIn("acctPickWire('tok'", src)
        self.assertIn("acctPickFocusId()", src)


if __name__ == "__main__":
    unittest.main()
