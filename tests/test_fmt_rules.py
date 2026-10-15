"""Shared number formatters (fmtPct/fmtMoney/fmtTok/fmtChars in web/js/00-core.js): runs fmtSelfTest() through node."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

def _units():
    """UNIT_KO table from 05-i18n.js (U() looks English units up there)."""
    return re.search(r"^const UNIT_KO = \{.*?\};", js_all(), re.S | re.M).group(0) + "\n"


NAMES = ("fmtTok", "fmtPct", "fmtMoney", "fmtChars", "U", "ago", "fmtSelfTest")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class FmtRules(unittest.TestCase):
    def test_selftest_passes(self):
        for lang in ("ko", "en"):
            js = ("var LANG = %r;\n" % lang + _units()
                  + "\n".join(js_fn(n) for n in NAMES) + "\nprocess.stdout.write(JSON.stringify(fmtSelfTest()));")
            r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout), [], lang)

    def test_ago_floors(self):
        # 59s / 90s / 119s: the same age must read the same on every screen (was «2분» on round() sites).
        js = ("var LANG = 'ko';\n" + _units() + js_fn("U") + "\n" + js_fn("ago")
              + "\nprocess.stdout.write(JSON.stringify([59, 90, 119].map(ago)));")
        r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), ["59초", "1분", "1분"])

    def test_no_lowercase_k_suffix(self):
        # fmtTok ignores the old o.k option, so callers passing k:'k' still get 'K'.
        js = js_fn("fmtTok") + "\nprocess.stdout.write(fmtTok(2500, {k: 'k'}));"
        r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20)
        self.assertEqual(r.stdout, "3K")

    def test_tok_unit_rollover(self):
        # A value that rounds to 1000 in one unit is printed in the next unit, never «1000K»/«1000M».
        cases = {999: "999", 999.5: "1K", 999499: "999K", 999600: "1M", 999.4e6: "999M", 999.6e6: "1.0B"}
        js = js_fn("fmtTok") + "\nprocess.stdout.write(JSON.stringify(" + json.dumps(list(cases)) + ".map(n => fmtTok(n))));"
        r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), list(cases.values()))


if __name__ == "__main__":
    unittest.main()
