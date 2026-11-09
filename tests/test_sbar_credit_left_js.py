"""Status bar «left ≈» at a rounded 100%, credit-seat layer rows, exact credit «left» (sweep 20 quota)."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e
from tests.test_saver_quota_js import i18n, jconst

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STUBS = """
var document = {getElementById: () => null};
let QLAST = null, ACCTS = [], CONN = {}, MAIN = '';
const UIS = {getItem: () => MAIN};
const fmtTok = n => (n / 1e6).toFixed(1) + 'M';
const gauge = p => '<g>', qcls = p => 'ok';
"""
FNS = ("fmtPct", "fmtMoney", "ageU", "acctList", "mainAcct", "mainAcctOk", "sblAccRows", "estLeftTxt",
       "creditMoney", "creditExact", "creditPct", "creditRow", "creditInfo")


def read(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return f.read()


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SbarCreditLeft(unittest.TestCase):
    def run_js(self, body):
        src = STUBS + i18n() + "\nLANG = 'en';\n" + jconst("esc") + "\n" + "\n".join(js_fn(f) for f in FNS) + "\n" + body
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        return json.loads(r.stdout)

    def test_left_zero_reads_under_one_pct(self):
        out = self.run_js("process.stdout.write(JSON.stringify([estLeftTxt({left: 0}), estLeftTxt({left: 2e6})]));")
        self.assertEqual(out, ["< 1%", "2.0M"])
        # Bar body and both tooltips go through estLeftTxt, never a raw fmtTok of the estimate.
        src = read("web/js/60-statusbar.js")
        self.assertNotRegex(src, r"sbt\(T\('left ≈'\), e\.left\)")
        self.assertNotIn("fmtTok(e5.left)", src)
        self.assertNotIn("fmtTok(est0.wk_left)", src)
        self.assertEqual(len(re.findall(r"estLeftTxt\(", src)), 3)

    def test_credit_seat_rows_have_no_100pct(self):
        rows = self.run_js("""
ACCTS = [{label: 'me', primary: true}];
const cq = {five_hour: {pct: 0, resets_at: null}, seven_day: {pct: 0, resets_at: null},
           extra: {seat: 'enterprise_usage_based', used: 10013, limit: 60000, pct: 16.69}};
process.stdout.write(JSON.stringify(sblAccRows(cq, acctList(), '')));
""")
        self.assertEqual(len(rows), 1)
        self.assertNotIn("100%", json.dumps(rows))
        self.assertEqual((rows[0]["l5"], rows[0]["l7"], rows[0]["u5"], rows[0]["u7"]), ("$100.13/$600.00", "—", None, None))

    def test_credit_left_is_exact(self):
        h = self.run_js("process.stdout.write(JSON.stringify(creditRow({extra: {pct: 16.69, used: 10013, limit: 60000}})));")
        self.assertIn("$499.87 left", h)
        self.assertIn("$100.13/$600.00", h)
        ci = self.run_js("process.stdout.write(JSON.stringify(creditInfo({extra: {seat: 'x_usage_based', used: 10013, limit: 60000}})));")
        self.assertEqual((ci["left"], ci["usedOf"]), ("$499.87 left", "$100.13/$600.00"))
        self.assertIn("$100.13 used of the $600.00 monthly limit", ci["tip"])
        ap = self.run_js("process.stdout.write(JSON.stringify(creditInfo({extra: {seat: 'x_usage_based', used: 10013, limit: 60000, approx: true}})));")
        self.assertIn("≈$100.13 used of the ≈$600.00 monthly limit", ap["tip"])

    def test_credit_segment_shows_local_used_tokens(self):
        # The credit comes only in money (cents): used/limit are converted to tokens at this week's local $/token, «≈».
        tk = js_fn("sbCreditTok")
        u = "{block: {tokens: 25084941}, week: {tokens: 600000000, cost: 240}}"   # $0.40 per 1M tokens
        ex = "{used: 20000, limit: 60000}"                                       # $200 of $600
        out = self.run_js(tk + "\nprocess.stdout.write(JSON.stringify([sbCreditTok(" + u + ", " + ex + "),"
                          " sbCreditTok({week: {tokens: 9, cost: 0}}, " + ex + "), sbCreditTok(" + u + ", {used: 1}),"
                          " sbCreditTok(null, null)]));")
        full, nocost, nolimit, nul = out
        self.assertEqual(full["html"], " <small class=sbd8>· Tokens</small> <b class=sbd8>≈500.0M/1500.0M</b>")
        self.assertIn("$0.40 per 1M tokens", full["tip"])
        self.assertNotIn("25.1M", full["html"])
        for e in (nocost, nolimit, nul):
            self.assertEqual(e, {"html": "", "tip": ""})
        src = read("web/js/60-statusbar.js")
        self.assertIn("sbCreditTok(USG, QLAST && QLAST.q && QLAST.q.extra)", src)
        self.assertIn("esc(cs.tip + ctk.tip)", src)


if __name__ == "__main__":
    unittest.main()
