"""«Show in bar» account (55a kpiAcct/kpiQ, 60b select): the bar's 5h/7d equal the picked account's popover row;
a missing/errored row falls back to main with kmiss; one account = no select; picking never touches mbMainAcct."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import i18n, jconst
from tests._node import node_e

FNS = ("fmtPct", "acctList", "mainAcct", "mainAcctOk", "knQ", "knQFor", "kpiAcct", "kpiQ",
       "sblAccRows", "sblHtml", "sbPctCls")

STUBS = """
var document = {getElementById: () => null};
let QLAST = null, ACCTS = [], CONN = {}, STORE = {};
const UIS = {getItem: k => k in STORE ? STORE[k] : null};
const connStaleNote = () => '';
const acctCls = l => 'acc-' + l;
const sesCount = () => ({open: 1, work: 0, need: 0, idle: 1});
function CLK(d){ return 'clk'; }
"""


def run(body):
    src = (STUBS + i18n() + "\n" + jconst("esc") + "\n" + "\n".join(js_fn(f) for f in FNS)
           + "\nconst R = {};\nLANG = 'en';\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"))
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class KpiAcct(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
ACCTS = [{label: 'me', primary: true}, {label: 'work'}, {label: '<x>&'}];
QLAST = {q: {five_hour: {pct: 10}, seven_day: {pct: 20},
  accounts: [{label: 'work', five_hour: {pct: 33}, seven_day: {pct: 44}}, {label: '<x>&', err: 'http', five_hour: {pct: 99}}]}};
const kq = k => { const r = kpiQ(k); return [r.w && r.w.pct, r.kpi, r.kmiss]; };
const row = l => { const r = sblAccRows(QLAST.q, acctList(), mainAcct()).find(x => x.label === l); return [r.u5, r.u7]; };
R.none = [kq('5h'), kq('7d')];
STORE.mbKpiAcct = 'work'; R.work = [kq('5h')[0], kq('7d')[0]]; R.workRow = row('work'); R.workTag = kq('5h');
STORE.mbMainAcct = 'work'; STORE.mbKpiAcct = 'me'; R.prim = [kq('5h')[0], kq('7d')[0]]; R.primRow = row('me'); R.primTag = kq('5h');
STORE.mbKpiAcct = 'work'; R.same = kq('5h');
STORE.mbKpiAcct = '<x>&'; R.miss = kq('5h'); R.mainKept = mainAcct();
STORE.mbKpiAcct = 'gone'; R.stale = [kpiAcct(), kq('5h')];
STORE.mbKpiAcct = 'work'; R.html = sblHtml(0);
ACCTS = [{label: 'me', primary: true}]; QLAST.q.accounts = []; R.oneHtml = sblHtml(0); R.oneK = kpiAcct();
""")

    def test_r3_bar_equals_popover_row(self):
        self.assertEqual(self.R["work"], self.R["workRow"])
        self.assertEqual(self.R["work"], [33, 44])
        self.assertEqual(self.R["workTag"], [33, "work", False])
        self.assertEqual(self.R["prim"], self.R["primRow"])   # primary picked while main is another account
        self.assertEqual(self.R["primTag"], [10, "me", False])

    def test_unset_and_same_as_main_follow_main(self):
        self.assertEqual(self.R["none"], [[10, "", False], [20, "", False]])
        self.assertEqual(self.R["same"], [33, "", False])
        self.assertEqual(self.R["stale"], ["", [33, "", False]])

    def test_missing_row_falls_back_to_main(self):
        self.assertEqual(self.R["miss"], [33, "<x>&", True])   # errored row's stale 99 never shown; main's 33 is
        self.assertEqual(self.R["mainKept"], "work")

    def test_select_escaped_outside_grid(self):
        h = self.R["html"]
        self.assertIn("<select data-kpi>", h)
        self.assertIn('<option value="work" selected>work</option>', h)
        self.assertIn("&lt;x&gt;&amp;", h)
        self.assertNotIn("<x>&", h)
        self.assertLess(h.index("data-kpi"), h.index("sbl-tbl"))   # shared subgrid keeps only its rows

    def test_one_account_no_select(self):
        self.assertNotIn("data-kpi", self.R["oneHtml"])
        self.assertEqual(self.R["oneK"], "")


if __name__ == "__main__":
    unittest.main()
