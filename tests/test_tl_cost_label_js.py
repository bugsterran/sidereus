"""Timeline drawer «Cost» row: the this-window token label says it covers all accounts, and its tooltip says the status
bar «5h used» counts the primary account only. The tkTxt line from 76-timeline-drawer.js runs with the real dictionaries."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "web", "js", "76-timeline-drawer.js"), encoding="utf-8") as fh:
    SRC = fh.read()
LINE = re.search(r"^ *const tkTxt = .*$", SRC, re.M).group(0)


def run(lang):
    js = (i18n_prelude(json.dumps(lang), ("T",))
          + "const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\"/g, '&quot;');"
          + "const fmtTok = n => String(n), cl = '', cc = 1200, xs = '';"
          + "const out = [];"
          + "{ const _w = 1200;\n" + LINE + "\nout.push(tkTxt); }"
          + "{ const _w = null;\n" + LINE + "\nout.push(tkTxt); }"
          + "process.stdout.write(JSON.stringify(out));")
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TlCostLabel(unittest.TestCase):
    def test_en(self):
        w, nw = run("en")
        self.assertEqual(w, '<span title="The status bar «5h used» counts the primary account only">'
                            'this-window tokens · all accounts</span> 1200')
        self.assertEqual(nw, "tokens 1200")    # no window measured: plain total, no account claim

    def test_ko(self):
        w, _ = run("ko")
        self.assertEqual(w, '<span title="상태바 «5h 사용»은 주 계정만 셉니다">이번 창 토큰 · 모든 계정</span> 1200')


if __name__ == "__main__":
    unittest.main()
