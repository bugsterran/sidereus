"""History account picker (85-history.js paintHist + 40b acctPick*): All = today's rows and day totals,
a pick keeps that account's cc rows plus every external CLI row and recomputes the day header, one account = no picker."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import i18n, jconst
from tests._node import node_e

FNS = ("acctList", "mainAcct", "mainAcctOk", "lsGet", "lsSet", "lsDel", "acctLabel", "acctPick", "acctInPick",
       "acctPickHtml", "acctPickFocusId", "acctPickWire", "acctOthHtml", "acctOthClick",
       "histMatch", "histExtKeys", "histDayTot", "histProjs", "histProjHtml", "paintHist")

STUBS = r"""
let ACCTS = [], STORE = {}, TB = '', HIST = null, histDays = 7, histBusy = 0, histWant = 0, histProj = [], histQ = '';
const HIST_STEPS = [7], histOpen = new Set(), ACC_OTH = {};
const BOX = {innerHTML: '', querySelectorAll: () => [], querySelector: () => null};
var document = {getElementById: id => id === 'feed' ? BOX : null, activeElement: null};
const UIS = {getItem: k => k in STORE ? STORE[k] : null, setItem: (k, v) => { STORE[k] = String(v); }, removeItem: k => { delete STORE[k]; }};
function softErr(){}
function popIsOpen(){ return false; }
function tbSlot(k, h){ TB = h; return null; }
function platName(k){ return k; }
function histSpan(){ return ''; }
function aiLogo(){ return ''; }
function histGmRow(x){ return '<div class=hsr data-x="' + x.sid + '"></div>'; }
function histUnitsHtml(){ return ''; }
function histActive(h){ return 'h' + h; }
function histUnitsBind(){}
function money(v){ return '$' + v; }
function fmtTok(v){ return 'T' + v; }
function extCostStr(v){ return 'E' + v; }
function histCostTip(){ return ''; }
// Day 1: primary p1, work w1, Gemini g1 · day 2: work only
const D1 = {date: '2026-10-02', n: 2, tok: 30, cost: 3, rows: [
  {date: '2026-10-02', sid: 'p1', plat: 'cc', project: 'a', from: 2, to: 3, tok: 10, cost: 1},
  {date: '2026-10-02', sid: 'w1', plat: 'cc', acct: 'work', project: 'a', from: 1, to: 2, tok: 20, cost: 2}],
  gm: {tok: 5, estCost: 0.5, rows: [{date: '2026-10-02', sid: 'g1', plat: 'gm', project: 'a', from: 0, to: 1, tok: 5, estCost: 0.5}]}};
const D2 = {date: '2026-10-01', n: 1, tok: 7, cost: 0.7, rows: [
  {date: '2026-10-01', sid: 'w2', plat: 'cc', acct: 'work', project: 'a', from: 0, to: 1, tok: 7, cost: 0.7}]};
HIST = {ok: true, days: 7, list: [D1, D2]};
const sids = () => (BOX.innerHTML.match(/data-sid="([^"]+)"|data-x="([^"]+)"/g) || []).map(s => s.split('"')[1]).join(',');
const heads = () => (BOX.innerHTML.match(/<div class=hsd>.*?<\/div>/g) || []).map(s => s.replace(/<[^>]+>/g, ''));
const snap = () => ({sids: sids(), heads: heads(), oth: /data-ao="hist"/.test(BOX.innerHTML), pick: /id="acpk-hist"/.test(TB),
                     body: BOX.innerHTML});
"""

SCEN = r"""
const TWO = [{label: 'me', primary: true}, {label: 'work'}];
ACCTS = [{label: 'me', primary: true}]; STORE = {'mbAcctPick.hist': 'work'}; paintHist(); R.one = snap();
ACCTS = TWO; STORE = {}; paintHist(); R.all = snap();
STORE['mbAcctPick.hist'] = 'work'; paintHist(); R.work = snap();
STORE['mbAcctPick.hist'] = 'me'; paintHist(); R.me = snap();
ACC_OTH.hist = 1; paintHist(); R.open = snap(); delete ACC_OTH.hist;
STORE = {'mbAcctPick.sess': 'work', 'mbAcctPick.time': 'work'}; paintHist(); R.indep = snap();
"""


def run(body):
    src = (STUBS + i18n() + "\n" + jconst("esc") + "\n" + "\n".join(js_fn(f) for f in FNS)
           + "\nconst R = {};\nLANG = 'en'; mainView = 'hist';\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"))
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class HistAcctPick(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(SCEN)

    def test_one_account_no_picker(self):
        one = self.R["one"]
        self.assertFalse(one["pick"])
        self.assertEqual(one["sids"], "p1,w1,g1,w2")
        self.assertEqual(one["body"], self.R["all"]["body"])        # a stored pick is ignored with one account

    def test_all_is_todays_view(self):
        a = self.R["all"]
        self.assertTrue(a["pick"])
        self.assertEqual(a["sids"], "p1,w1,g1,w2")
        self.assertFalse(a["oth"])
        self.assertIn("Sessions 2 · T30 · $3", a["heads"][0])       # server day totals, untouched
        self.assertIn("Sessions 1 · T7 · $0.7", a["heads"][1])

    def test_work_pick(self):
        w = self.R["work"]
        self.assertEqual(w["sids"], "w1,g1,w2")                     # external CLI row stays
        self.assertIn("Sessions 1 · T20 · $2", w["heads"][0])       # recomputed from shown rows
        self.assertIn("gm T5", w["heads"][0])
        self.assertTrue(w["oth"])
        self.assertIn("In other accounts: 1", w["body"])
        self.assertNotIn("Clear filters", w["body"])               # the chip/search note is not for the account pick

    def test_primary_pick_drops_empty_day(self):
        m = self.R["me"]
        self.assertEqual(m["sids"], "p1,g1")
        self.assertEqual(len(m["heads"]), 1)                        # day 2 has no shown rows
        self.assertIn("In other accounts: 2", m["body"])

    def test_expanded_other_line_shows_all(self):
        self.assertEqual(self.R["open"]["sids"], "p1,w1,g1,w2")
        self.assertFalse(self.R["open"]["oth"])

    def test_independent_of_sessions_and_timeline(self):
        self.assertEqual(self.R["indep"]["body"], self.R["all"]["body"])


if __name__ == "__main__":
    unittest.main()
