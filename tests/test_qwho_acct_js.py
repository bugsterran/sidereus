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


if __name__ == "__main__":
    unittest.main()
