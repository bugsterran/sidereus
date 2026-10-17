"""Quota drawer Esc (web/js/60-statusbar.js): one Esc closes one layer — skipped when already handled or the Cmd+K palette is open."""
import json
import os
import re
import shutil
import subprocess
import unittest
from tests._node import node_e

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "js", "60-statusbar.js")


def _handler():
    with open(SRC, encoding="utf-8") as fh:
        src = fh.read()
    m = re.search(r"document\.addEventListener\('keydown', (e => \{ if\(e\.key === 'Escape' && SDRW_OPEN[^\n]*\})\);", src)
    assert m, "drawer Esc handler not found"
    return m.group(1)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class DrawerEsc(unittest.TestCase):
    def run_case(self, prevented, palette):
        js = ("let SDRW_OPEN = true, cpOn = %s, closed = 0; const sdrwSet = v => { if(!v) closed++; };\n"
              "const h = %s;\nh({key: 'Escape', defaultPrevented: %s});\nprocess.stdout.write(JSON.stringify(closed));"
              % (json.dumps(palette), _handler(), json.dumps(prevented)))
        r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_closes_when_top(self):
        self.assertEqual(self.run_case(False, False), 1)

    def test_skips_when_handled(self):
        self.assertEqual(self.run_case(True, False), 0)

    def test_skips_when_palette_open(self):
        self.assertEqual(self.run_case(False, True), 0)


if __name__ == "__main__":
    unittest.main()
