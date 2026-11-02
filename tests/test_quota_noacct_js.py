"""Quota details modal: a no-window zero account is unknown, not 0% (55a buildQuota); «Who is using the 5h» marks a
window that is not the shown account's as approximate (60-statusbar qwhoApprox)."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import i18n, jconst
from tests._node import node_e

STUBS = """
let OUT = '', QLAST = null, QERR = null, BURN = null;
const EL = {title: ''};
var document = {getElementById: id => EL};
const setHtml = (el, h) => { OUT = h; return true; };
const gauge = p => '<g' + p + '>', qcls = () => 'q', ageU = s => s + 's', fmtTok = n => n + 'T';
const creditRow = () => '', sbPrimNote = () => '', curWinTok = () => null, buildQuotaLocal = () => {};
const UIS = {getItem: () => null};
let ACCTS = [];
"""


def _run(body, fns):
    src = STUBS + i18n() + "\n" + jconst("esc") + "\n" + "\n".join(js_fn(f) for f in fns) + "\n" + body
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"), encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class QuotaNoAcct(unittest.TestCase):
    FNS = ("fmtPct", "qErrText", "buildQuota", "acctList", "mainAcct", "mainAcctOk", "knQ", "qwhoApprox")

    def test_no_login_row_is_not_zero(self):
        h = _run("""
buildQuota({}, {five_hour: {pct: 0, resets_at: null}, seven_day: {pct: 0, resets_at: null}, age: 0});
process.stdout.write(JSON.stringify(OUT));
""", self.FNS)
        self.assertNotIn("0%", h)
        self.assertIn("알 수 없음", h)

    def test_live_row_keeps_pct(self):
        h = _run("""
buildQuota({}, {five_hour: {pct: 0, resets_at: new Date(Date.now() + 3600e3).toISOString(), leftSec: 3600}, age: 0});
process.stdout.write(JSON.stringify(OUT));
""", self.FNS)
        self.assertIn("0%", h)          # a live window at 0% is a real 0%

    def test_qwho_approx(self):
        out = _run("""
const R = Date.parse('2030-01-01T05:00:00Z');
QLAST = {q: {five_hour: {pct: 40, resets_at: new Date(R).toISOString()}}};
const st = R / 1000 - 5 * 3600;
process.stdout.write(JSON.stringify([qwhoApprox({exact: true, start: st}), qwhoApprox({exact: false, start: st}),
                                     qwhoApprox({exact: true, start: st - 3600})]));
""", self.FNS)
        self.assertEqual(out, [False, True, True])


if __name__ == "__main__":
    unittest.main()
