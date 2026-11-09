"""Saver badge (55-saver-quota.js buildSaver) is not drawn on a usage-billed seat: its 5h verdict has no meaning there."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STUBS = """
const EL = {className: '', removeAttribute: () => {}};
var document = {getElementById: () => EL, body: {classList: {toggle: () => {}}}};
let OUT = null;
const setHtml = (el, h) => { OUT = h; return true; };
const esc = s => String(s), T = s => s, KE = (a, b) => b, TV = o => o.msg;
const svLive = () => null, svChip = () => '', svCapTip = () => '', svAsOf = () => '';
const SV = {};
const svParts = () => ({main: 'No throttle', sub: 'Goal 100%', cls: 'svfree', stage: 0, mode: 'auto', old: false, head: ''});
let QLAST = {q: {}}, METER = true;
const creditInfo = q => METER ? {meter: true} : null;
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SaverCreditHide(unittest.TestCase):
    def test_credit_seat_hides_saver_badge(self):
        body = ("const R = {}; buildSaver(null); R.meter = OUT;"
                " METER = false; buildSaver(null); R.sub = OUT;"
                " process.stdout.write(JSON.stringify(R));")
        r = subprocess.run(node_e(STUBS + js_fn("buildSaver") + "\n" + body), capture_output=True, text=True,
                           timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        R = json.loads(r.stdout)
        self.assertEqual(R["meter"], "")
        self.assertIn("No throttle", R["sub"])

    def test_status_bar_drops_5h_verdict_on_credit_seat(self):
        # The status bar's 5h pace word («No throttle») is skipped on a metered seat unless a manual switch is set.
        with open(os.path.join(ROOT, "web/js/60-statusbar.js"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("const sbMeter = !(SVSW && /^(on|off)$/.test(SVSW.mode)) && typeof creditInfo === 'function'", src)
        self.assertIn("if(r && !sbMeter){", src)


if __name__ == "__main__":
    unittest.main()
