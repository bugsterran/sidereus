"""History/retro tab details (85-history.js, 86-retro.js): filtered day totals, live span clamp, OTel «since» label, grade chip."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_fn
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SRC = i18n_prelude("'ko'", ("T", "KE", "srvEn")) + r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
// Fixed clock: 2026-10-05 10:40 local — `new Date()` / `Date.now()` never read the real time.
const FIX = new Date(2026, 9, 5, 10, 40, 0).getTime();
class FD extends Date { constructor(...a){ if(a.length) super(...a); else super(FIX); } static now(){ return FIX; } }
const c = {LANG: 'ko', T, KE, srvEn, thc: a => a, Math, Date: FD, JSON, SESS: []};
Date = FD;
vm.createContext(c);
vm.runInContext(HELP + '\n' + fs.readFileSync(path.join(ROOT, 'web', 'js', '86-retro.js'), 'utf8')
  + ';this.X = {rtRank, rtSigs};', c);
const X = c.X, R = {};
const now = Math.floor(Date.now() / 1000);
// histDayTot
const d = {date: '2026-10-02', n: 5, tok: 1000, cost: 9, rows: [], gm: {tok: 70, estCost: 1.5, rows: []}};
const shown = [{plat: 'cc', tok: 100, cost: 1}, {tok: 50, cost: 0.5}, {plat: 'gm', tok: 30, estCost: 0.2}];
R.tot = c.histDayTot(d, shown, true);
R.raw = c.histDayTot(d, shown, false);
R.totNoGm = c.histDayTot(d, shown.slice(0, 1), true);
// histSpan: end in the future is clamped; live badge only for a session the poll lists as open
const t0 = new Date(); t0.setMinutes(0, 0, 0);
const from = Math.floor(t0.getTime() / 1000) - 3600, to = Math.floor(t0.getTime() / 1000) + 3600;
const ymd = x => x.getFullYear() + '-' + String(x.getMonth() + 1).padStart(2, '0') + '-' + String(x.getDate()).padStart(2, '0');
const row = {date: ymd(new Date(from * 1000)), sid: 'S1', from, to};
c.SESS = [{sid: 'S1', state: 'wait'}];
R.live = c.histSpan(row);
c.SESS = [{sid: 'S1', state: 'done'}];
R.ended = c.histSpan(row);
R.past = c.histSpan(Object.assign({}, row, {to: from + 1800}));
R.hhmm = new Date(now * 1000).toTimeString().slice(0, 5);
// rtRank: collection started inside the range vs before it
const today = ymd(new Date());
const rank = {calls: 3, restN: 0, rest: [], top: [{n: 'Bash', calls: 3, ok: 100, ms: 5}]};
R.inside = X.rtRank({days: 30, rank: Object.assign({from: today}, rank)});
R.before = X.rtRank({days: 7, rank: Object.assign({from: '2020-01-01'}, rank)});
R.sigs = X.rtSigs({sigs: [{sig: 'A', kind: 'tool', grade: 'noise', n: 3, last: now},
                          {sig: 'B', kind: 'agent', grade: 'check', n: 1, last: now, chk: 1}]});
process.stdout.write(JSON.stringify(R));
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class HistRetroUx(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        core = open(os.path.join(ROOT, "web", "js", "00-core.js"), encoding="utf-8").read()
        esc = re.search(r"^const esc = .*?;$", core, re.S | re.M).group(0)
        help_ = "\n".join([esc, js_fn("fmtPct"), js_fn("histExtKeys"), js_fn("histDayTot"), js_fn("histSpan"),
                           js_fn("histLive"), "function stamp(t){ return String(t); }", "function agoAt(t){ return 'ago'; }"])
        r = subprocess.run(node_e("const ROOT = %s;\nconst HELP = %s;\n" % (json.dumps(ROOT), json.dumps(help_)) + SRC),
                           capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        cls.R = json.loads(r.stdout)

    def test_day_totals_follow_filter(self):
        t = self.R["tot"]
        self.assertEqual((t["n"], t["tok"], t["cost"]), (2, 150, 1.5))
        self.assertEqual(t["ext"]["gm"]["tok"], 30)
        self.assertEqual((self.R["raw"]["n"], self.R["raw"]["tok"], self.R["raw"]["ext"]["gm"]["tok"]), (5, 1000, 70))
        self.assertEqual(self.R["totNoGm"]["ext"], {})      # a platform with no shown rows drops out of the header

    def test_live_span_never_in_future(self):
        hhmm = self.R["hhmm"]
        self.assertIn("~" + hhmm, self.R["live"])
        self.assertIn("진행 중", self.R["live"])
        self.assertIn("~" + hhmm, self.R["ended"])        # clamped even when closed
        self.assertNotIn("진행 중", self.R["ended"])
        self.assertNotIn("진행 중", self.R["past"])

    def test_rank_since_label(self):
        self.assertIn("부터 (수집 시작)", self.R["inside"])
        self.assertNotIn("최근 30일", self.R["inside"])
        self.assertIn("최근 7일", self.R["before"])
        self.assertNotIn("수집 시작", self.R["before"])

    def test_grade_chip(self):
        s = self.R["sigs"]
        self.assertIn('class="rtgc rtg-noise"', s)
        self.assertIn("잡음", s)
        self.assertEqual(s.count("rtgc"), 1)               # the «봐야 할 것» row keeps its own mark instead
        self.assertIn("rtchkt", s)


if __name__ == "__main__":
    unittest.main()
