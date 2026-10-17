"""Timeline «Window summary» card (web/js/76 tlSumDraw): Results + Evidence by default, «More» adds
Waited on you · Outliers · Cost (remembered in localStorage), and a throwing storage still renders."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

FNS = ("TV", "tlSumDur", "tlExtTok", "tlSumMoreOn", "tlSumMoreSet", "tlSumWork", "tlSumDraw")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TlWindowSummary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src = "\n".join(js_fn(n) for n in FNS) + r"""
const rangeLbl = h => h + 'h', softErr = () => {};
const T = s => s, U = (n, u) => n + u, fmtTok = n => 'K' + n, aiLogo = p => '[' + p + ']';
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const TLSUM_MORE_KEY = 'sidereus.tlsumMore';
const document = { getElementById: () => null };
let STORE = {}, THROW = false;
const lsGet = (k, d) => { if(THROW) throw new Error('blocked'); return k in STORE ? STORE[k] : d; };
const lsSet = (k, v) => { if(THROW) throw new Error('blocked'); STORE[k] = v; };
const curWinTok = () => 5000, BURN = { cur: { start: 0 } };
let tlSumHtml = '';
const SESS = [{ cwd: '/w/a', repos: ['/r/a'], plrun: [
  { t0: 1100, end: 1500, stages: { s1: { o: 'done', from: { s2: 2 } }, s2: { o: 'done', from: {} } },
    past: [{ t0: 1050, end: 1080, stages: { s1: { o: 'fail', from: {} } } }, { t0: 10, end: 20, stages: {} }] },
  { t0: 1700, end: 0, stages: { s1: { o: 'run', from: {} } } }] }];
const tlLiveOf = (cwd) => SESS.find(x => x.cwd === cwd);
const PLEV = { '/r/a': {
  rows: [{ ts: 1200, rc: 0, steps: [] }, { ts: 1300, rc: 1, steps: [{ name: 'gates', rc: 0 }, { name: 'tests', rc: 2 }] },
         { ts: 1250, rc: 1, steps: [{ name: 'older', rc: 1 }] }, { ts: 10, rc: 1, steps: [] }],
  cms: [{ h: 'aaaaaaa1', ct: 1100 }, { h: 'aaaaaaa1', ct: 1100 }, { h: 'bbbbbbb2', ct: 1900 }, { h: 'ccccccc3', ct: 5 }] } };
const plEvRows = p => (PLEV[p] || {}).rows || [], plEvCommits = p => (PLEV[p] || {}).cms || [];
const ag = (s, e, x) => Object.assign({ kind: 'agent', start: s, end: e, tc: 3, fin: 1, type: 'worker<x>' }, x || {});
const TLD = { ok: true, at: 2000, hours: 1, tok: { t0: 1000, sum: 9 }, rows: [
  { kind: 'sess', cwd: '/w/a', wt: [2, 120] }, { kind: 'sess', cwd: '/w/b', plat: 'cx', tk: 40 },
  ag(1000, 1060), ag(1000, 1060), ag(1000, 1060), ag(1000, 1900)] };
const draw = () => { const host = { innerHTML: '', firstChild: null }; tlSumHtml = ''; tlSumDraw(host); return host.innerHTML; };
const out = { def: draw() };
STORE['sidereus.tlsumMore'] = '1'; out.more = draw();
THROW = true; out.thr = draw();
let setOk = true; try { tlSumMoreSet(true); } catch(e) { setOk = false; }
out.setOk = setOk;
process.stdout.write(JSON.stringify(out));
"""
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        cls.R = json.loads(r.stdout)

    def test_default_rows(self):
        h = self.R["def"]
        self.assertIn("<i>Results</i>", h)
        self.assertIn("<i>Evidence</i>", h)
        for k in ("Waited on you", "Outliers", "Cost"):
            self.assertNotIn("<i>" + k + "</i>", h)
        self.assertIn("More ▾", h)

    def test_results_and_evidence_values(self):
        h = self.R["def"]
        self.assertIn("2 commits", h)                     # dedup by hash, out-of-window dropped
        self.assertIn("3 pipeline runs", h)               # two current + one past in window
        self.assertIn("✓1 ✕1 ↺2", h)
        self.assertIn("3 gate runs · PASS 1 · FAIL 2", h)
        self.assertIn("last failure tests", h)            # first rc≠0 step of the newest FAIL row

    def test_more_adds_rows(self):
        h = self.R["more"]
        for k in ("Results", "Evidence", "Waited on you", "Outliers", "Cost"):
            self.assertIn("<i>" + k + "</i>", h)
        self.assertIn("2 prompts · 2m", h)
        self.assertIn("worker&lt;x>", h)
        self.assertIn("per commit K2520", h)              # (5000 + 40) / 2
        self.assertIn("Less ▴", h)

    def test_throwing_storage_still_renders(self):
        h = self.R["thr"]
        self.assertIn("<i>Results</i>", h)
        self.assertNotIn("<i>Cost</i>", h)
        self.assertTrue(self.R["setOk"])

    def test_removed_rows(self):
        for h in (self.R["def"], self.R["more"]):
            self.assertNotIn("Longest gap", h)
            self.assertNotIn("Running now", h)
            self.assertNotIn("<i>Total</i>", h)


if __name__ == "__main__":
    unittest.main()
