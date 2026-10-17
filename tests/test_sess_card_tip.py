"""sessCardTip (web/js/40b) adds a «권한: <pmode>» line only when pmode is set; sessRowHtml escapes it."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._node import node_e

WEB = os.path.join(os.path.dirname(__file__), "..", "web", "js")


def _fn(src, name):
    return re.search(r"^function " + name + r"\(.*?^}", src, re.S | re.M).group(0)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SessCardTipTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(WEB, "40b-sessions-list.js"), encoding="utf-8") as fh:
            self.src = fh.read()

    def run_js(self, rows):
        js = "\n".join(["const NL = String.fromCharCode(10);", i18n_prelude("'ko'", ("T", "TV")),
                        _fn(self.src, "sessCardTip"),
                        "console.log(JSON.stringify(%s.map(sessCardTip)));" % json.dumps(rows)])
        r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_pmode_line(self):
        out = self.run_js([{"cwd": "/w", "id": "s1", "model": "opus", "pmode": "auto"},
                           {"cwd": "/w", "id": "s1", "model": "opus", "pmode": ""},
                           {"cwd": "/w", "id": "s1"}])
        self.assertEqual(out[0], "/w · s1 · opus\n권한: auto")
        self.assertEqual(out[1], "/w · s1 · opus")
        self.assertEqual(out[2], "/w · s1")

    def test_row_escapes_tip(self):
        self.assertIn("tip = esc(sessCardTip(x) + (at ? NL + at : ''));", _fn(self.src, "sessRowHtml"))


if __name__ == "__main__":
    unittest.main()
