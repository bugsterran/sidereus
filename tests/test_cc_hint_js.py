"""«Saver mode» compact-threshold hint (web/js/90b-mypref.js mpCcHint): on / off / unknown, en and ko. Stubbed keys only."""
import json
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_switch
from tests._load import js_fn
from tests._node import node_e

SRC = i18n_switch(("T",)) + "\n" + js_fn("fmtTok") + "\n" + js_fn("mpCcHint") + r"""
let LANG = 'en';
const k = (a, w) => ({cc_auto_compact: {value: a}, cc_compact_window: {value: w}});
const cases = [k(true, 450000), k(null, 450000), k(false, 450000), k(true, null), k(false, null), null, {cc_auto_compact: {value: true}}];
const R = {en: cases.map(mpCcHint)};
LANG = 'ko'; R.ko = cases.map(mpCcHint);
process.stdout.write(JSON.stringify(R));
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class CcHint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r = subprocess.run(node_e(SRC), capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        cls.R = json.loads(r.stdout)

    def test_en(self):
        self.assertEqual(self.R["en"], ["Compact threshold: 450K", "Compact threshold: 450K", "Auto-compact off",
                                        "", "Auto-compact off", "", ""])

    def test_ko(self):
        self.assertEqual(self.R["ko"][:3], ["컴팩트 기준: 450K", "컴팩트 기준: 450K", "자동 컴팩트 꺼짐"])
        self.assertEqual(self.R["ko"][3], "")


if __name__ == "__main__":
    unittest.main()
