"""Retro OTel-card account pick (86 loadRetro · rtAcctHead · paintRetro): `&acct=` only when picked,
a reply for an older pick is dropped, one account = no #acpk-retro, the «no account» line only under a pick."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import i18n, jconst
from tests._node import node_e

FNS = ("acctList", "mainAcct", "mainAcctOk", "lsGet", "lsSet", "lsDel", "acctLabel", "acctPick", "acctPickHtml",
       "loadRetro", "rtAcctHead")

STUBS = r"""
let ACCTS = [], STORE = {}, URLS = [], PEND = [];
var document = {getElementById: () => null, activeElement: null, addEventListener(){}};
const UIS = {getItem: k => k in STORE ? STORE[k] : null, setItem: (k, v) => { STORE[k] = String(v); }, removeItem: k => { delete STORE[k]; }};
function softErr(){}
function paintRetro(){}
let REJ = [];
function getJSON(u){ URLS.push(u); return new Promise((r, j) => { PEND.push(r); REJ.push(j); }); }
let RETRO = null, retroDays = 7, retroBusy = 0, retroAt = 0, retroWant = 0;
// Fixed clock: range start for days=7 is 2026-10-09.
const _D = Date; Date = class extends _D { constructor(...a){ super(...(a.length ? a : [2026, 9, 15, 12])); } static now(){ return 1; } };
"""

SCEN = r"""
(async () => {
  const tick = async () => { for(let i = 0; i < 4; i++) await 0; };
  ACCTS = [{label: 'me', primary: true}, {label: 'work'}];
  loadRetro(true); PEND.shift()({ok: true, days: 7}); await tick();
  STORE['mbAcctPick.retro'] = 'work';
  loadRetro(true); PEND.shift()({ok: true, days: 7, acct: 'work', acctSince: '2026-10-12'}); await tick();
  R.urls = URLS.slice(); R.retro = RETRO;
  // stale: request for work in flight, pick switched to All, the work reply arrives -> dropped, All reloaded
  RETRO = null; URLS = []; loadRetro(true); delete STORE['mbAcctPick.retro'];
  PEND.shift()({ok: true, days: 7, acct: 'work', acctSince: '2026-10-12'}); await tick();
  R.staleRetro = RETRO; R.staleUrls = URLS.slice();
  PEND.shift()({ok: true, days: 7}); await tick(); R.after = RETRO;
  // stale error: work request fails after the pick switched to All -> error dropped, All reloaded
  REJ.length = 0; PEND.length = 0;
  STORE['mbAcctPick.retro'] = 'work'; RETRO = null; URLS = []; loadRetro(true); delete STORE['mbAcctPick.retro'];
  REJ.shift()({status: 500}); PEND.shift(); await tick();
  R.errRetro = RETRO; R.errUrls = URLS.slice();
  PEND.shift()({ok: true, days: 7}); await tick(); R.errAfter = RETRO;
  REJ.length = 0; PEND.length = 0;
  // other views' picks do not leak in
  STORE = {'mbAcctPick.tok': 'work', 'mbAcctPick.hist': 'work'}; URLS = [];
  loadRetro(true); R.indep = URLS[0]; PEND.shift()({ok: true, days: 7}); await tick();
  // R3 line
  R.headAll = rtAcctHead({ok: true, days: 7, acctSince: '2026-10-12'});
  STORE['mbAcctPick.retro'] = 'work';
  R.headIn = rtAcctHead({ok: true, days: 7, acct: 'work', acctSince: '2026-10-12'});
  R.headOld = rtAcctHead({ok: true, days: 7, acct: 'work', acctSince: '2026-10-01'});
  R.headStart = rtAcctHead({ok: true, days: 7, acct: 'work', acctSince: '2026-10-09'});
  ACCTS = [{label: 'me', primary: true}];
  R.head1 = rtAcctHead({ok: true, days: 7, acct: 'work', acctSince: '2026-10-12'}); R.pick1 = acctPick('retro');
  R.store = STORE;
  process.stdout.write(JSON.stringify(R));
})();
"""


def run():
    src = (STUBS + i18n() + "\n" + jconst("esc") + "\n" + jconst("rtP2") + "\n" + jconst("rtYmd") + "\n" + "\n".join(js_fn(f) for f in FNS)
           + "\nconst R = {};\nLANG = 'en';\n" + SCEN)
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"), encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class RetroAcctPick(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run()

    def test_acct_only_when_picked(self):
        self.assertEqual(self.R["urls"], ["/api/retro?days=7", "/api/retro?days=7&acct=work"])
        self.assertEqual(self.R["retro"]["acct"], "work")

    def test_stale_reply_dropped(self):
        self.assertIsNone(self.R["staleRetro"])
        self.assertEqual(self.R["staleUrls"], ["/api/retro?days=7&acct=work", "/api/retro?days=7"])
        self.assertNotIn("acct", self.R["after"])

    def test_stale_error_dropped(self):
        self.assertIsNone(self.R["errRetro"])
        self.assertEqual(self.R["errUrls"], ["/api/retro?days=7&acct=work", "/api/retro?days=7"])
        self.assertEqual(self.R["errAfter"], {"ok": True, "days": 7})

    def test_pick_is_per_tab(self):
        self.assertEqual(self.R["indep"], "/api/retro?days=7")

    def test_no_account_line_only_under_pick_in_range(self):
        self.assertIn('id="acpk-retro"', self.R["headAll"])
        self.assertNotIn("have no account", self.R["headAll"])
        self.assertIn("Records before 10/12 have no account", self.R["headIn"])
        self.assertNotIn("have no account", self.R["headOld"])
        self.assertNotIn("have no account", self.R["headStart"])

    def test_one_account_no_picker(self):
        self.assertEqual((self.R["head1"], self.R["pick1"]), ("", ""))

    def test_never_writes_main_account(self):
        self.assertNotIn("mbMainAcct", self.R["store"])
        for f in ("loadRetro", "rtAcctHead", "paintRetro"):
            self.assertNotIn("mbMainAcct", js_fn(f))

    def test_paint_wires_picker_focus_safe(self):
        src = js_fn("paintRetro")
        self.assertIn("rtAcctHead(r)", src)
        self.assertIn("acctPickWire('retro'", src)
        self.assertIn("acctPickFocusId()", src)
        # picker sits above the OTel cards only: failure trend comes before it, weekly summary after
        self.assertLess(src.index("Failure trend"), src.index("rtAcctHead(r)"))
        self.assertLess(src.index("rtAcctHead(r)"), src.index("rtRank(r)"))


if __name__ == "__main__":
    unittest.main()
