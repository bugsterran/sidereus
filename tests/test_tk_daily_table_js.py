"""Tokens tab «Daily» table (web/js/46-tokens-tab.js tkDailyTable/tkTot/tkRange): newest first, one row per day,
zero day «–», today's tokens equal the trend's last point (live share included), names escaped, redrawn per WKR."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import i18n, jconst
from tests._node import node_e

FNS = ("fmtTok", "fmtMoney", "fmtPct", "tkTot", "tkDailyTable", "tkTrend", "tkRange")

STUBS = r"""
var document = {getElementById: () => null, addEventListener: () => {}};
const thc = (a, b) => a, wkc = i => '#c' + i, tkBar = () => '', tkMix = () => '', tkModels = () => '';
const loadWkRange = () => {}, WKRANGE = '7', WKR_DESC = {'7': 'Last 7 days'}, SCOPE_PC_TIP = 'tip';
let WKR = null, WKU = null, TKTR = null;
"""


def run(body):
    src = (STUBS + i18n() + "\n" + jconst("esc") + "\n" + jconst("WKDN_EN") + "\n"
           + "\n".join(js_fn(f) for f in FNS)
           + "\nconst R = {};\nLANG = 'en';\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"), encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class DailyTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
const mk = (today, last) => ({at: 100, today: today, days: 3, liveAdd: 1200, rows: [], total: 0,
  daily: [{d: '2026-10-13', tok: 2000, cost: 1.5, top: [{name: 'a<b>', tok: 1500}, {name: 'c', tok: 400}, {name: 'z', tok: 100}]},
          {d: '2026-10-14', tok: 0, cost: 0},
          {d: today, tok: last, cost: 3, top: [{name: 'c', tok: last}]}]});
WKR = mk('2026-10-15', 7000);
WKU = {at: 100, liveAdd: 2000};          // same `at` -> the WKU live share wins (as in tkRange)
const h = tkRange();
R.h = h;
R.rows = (h.match(/<tbody>[\s\S]*?<\/tbody>/g) || []).filter(x => x.includes('<s>Thu</s>') || x.includes('<s>Wed</s>') || x.includes('<s>Tue</s>'))[0];
R.tot = TKTR.tot;
WKU = null;
R.h2 = tkRange();
WKR = mk('2026-10-16', 7000); WKR.daily.unshift({d: '2026-10-12', tok: 10, cost: 0});
R.h3 = tkRange();
""")

    def test_order_and_count(self):
        rows = self.R["rows"]
        trs = rows.split("<tr")[1:]
        self.assertEqual(len(trs), 3)
        self.assertIn("10/15", trs[0])
        self.assertIn("10/14", trs[1])
        self.assertIn("10/13", trs[2])
        self.assertIn("<s>Thu</s>", trs[0])
        self.assertIn('class="brt tkdt"', self.R["h"])
        self.assertIn("class=today", trs[0])

    def test_zero_day(self):
        tr = self.R["rows"].split("<tr")[1:][1]
        self.assertIn("<td class=brv>0</td>", tr)
        self.assertIn("<td class=tkdtp>–</td>", tr)

    def test_today_matches_chart(self):
        tot = self.R["tot"]
        self.assertEqual(tot[-1], 9000)
        tr = self.R["rows"].split("<tr")[1:][0]
        self.assertIn("<td class=brv>9K</td>", tr)
        self.assertIn('title="Cost excludes the live share since the last count"', tr)
        self.assertNotIn("title=", self.R["rows"].split("<tr")[1:][2])

    def test_wkr_live_when_at_differs(self):
        self.assertIn("<td class=brv>8K</td>", self.R["h2"])
        self.assertNotIn("<td class=brv>9K</td>", self.R["h2"])

    def test_names_escaped_top_two(self):
        tr = self.R["rows"].split("<tr")[1:][2]
        self.assertIn("a&lt;b&gt; <s>2K</s> · c <s>400</s>", tr)
        self.assertNotIn("a<b>", self.R["h"])
        self.assertNotIn(">z <s>", tr)

    def test_redraws_with_range(self):
        self.assertNotEqual(self.R["h"], self.R["h3"])
        self.assertIn("10/12", self.R["h3"])
        self.assertNotIn("10/12", self.R["h"])
