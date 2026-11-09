"""«Who is using the 5h» header (60-statusbar.js buildQwho): names the account whose window is shown, escaped, never via T()."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import i18n, jconst
from tests._node import node_e

STUBS = """
const EL = {};
var document = {getElementById: id => EL};
let OUT = '';
const setHtml = (el, h) => { OUT = h; return true; };
const connStaleNote = () => '';
let CONN = null;
const fmtTok = n => String(n);
const qwhoApprox = () => false;
const wkc = () => '#000';
"""

BODY = """
const R = {};
const W = {start: 1900000000, exact: true, total: 10, rows: [{name: 'p', n: 1, share: 100, tok: 10, sids: []}]};
QWHO = Object.assign({}, W, {acct: '<b>work</b>'}); buildQwho(); R.acct = OUT;
QWHO = Object.assign({}, W, {acct: ''}); buildQwho(); R.primary = OUT;
process.stdout.write(JSON.stringify(R));
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class QwhoAcct(unittest.TestCase):
    def test_header_names_account(self):
        src = (STUBS + i18n() + "\n" + jconst("esc") + "\n" + js_fn("fmtPct") + "\nlet QWHO = null;\n" + js_fn("buildQwho") + "\n" + BODY)
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"), encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        R = json.loads(r.stdout)
        head = R["acct"].split("</div>")[0]
        self.assertIn("<small class=qwa>&lt;b&gt;work&lt;/b&gt;</small>", head)
        self.assertNotIn("<b>work</b>", R["acct"])
        self.assertNotIn("qwa", R["primary"])

    def test_credit_seat_hides_5h_section(self):
        # A usage-billed seat has no 5h cycle: the «Who is using the 5h» section is not drawn.
        body = """
let QLAST = {q: {}}, METER = true;
const creditInfo = q => METER ? {meter: true} : null;
const R = {};
QWHO = {start: 1900000000, exact: true, total: 10, rows: [{name: 'p', n: 1, share: 100, tok: 10, sids: []}]};
buildQwho(); R.meter = OUT;
METER = false; buildQwho(); R.sub = OUT;
METER = true; QWHO = Object.assign({}, QWHO, {acct: 'work'}); buildQwho(); R.extra = OUT;
process.stdout.write(JSON.stringify(R));
"""
        src = (STUBS + i18n() + "\n" + jconst("esc") + "\n" + js_fn("fmtPct") + "\nlet QWHO = null;\n" + js_fn("buildQwho") + "\n" + body)
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"), encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        R = json.loads(r.stdout)
        self.assertEqual(R["meter"], "")
        self.assertIn("<div class=qwh", R["sub"])
        self.assertIn("<div class=qwr", R["sub"])
        # An extra account in use keeps its own 5h window even when the primary is a credit seat.
        self.assertIn("<div class=qwr", R["extra"])

    def test_pi_row_logo_and_tip(self):
        # A pi row carries the pi logo, an account-in-use tooltip and the escaped folder name; other plat values get no logo.
        body = """
const aiLogo = p => '<i class=ailg-' + p + '></i>';
const R = {};
QWHO = {start: 1900000000, exact: true, total: 10, rows: [
  {plat: 'pi', name: '<x>', n: 1, share: 60, tok: 6, sids: [{sid: 's1', tok: 6}]},
  {plat: '<evil>', name: 'q', n: 1, share: 40, tok: 4, sids: []}]};
buildQwho(); R.out = OUT;
process.stdout.write(JSON.stringify(R));
"""
        src = (STUBS + i18n() + "\n" + jconst("esc") + "\n" + js_fn("fmtPct") + "\nlet QWHO = null;\n" + js_fn("buildQwho") + "\n" + body)
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"), encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        out = json.loads(r.stdout)["out"]
        pi, other = out.split("<div class=qwr")[1:3]
        self.assertIn("<i class=ailg-pi></i> &lt;x&gt;", pi)
        self.assertIn("이 계정이라고 가정합니다", pi.split('">')[0])
        self.assertIn("s1 6", pi.split('">')[0])
        self.assertNotIn("<x>", out)
        self.assertNotIn("ailg", other)
        self.assertNotIn("주 계정", other)


if __name__ == "__main__":
    unittest.main()
