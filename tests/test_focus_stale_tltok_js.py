"""Cmd+K returns focus to its opener; stale dimming has no grayscale;
timeline summary adds external-platform tokens per logo (tlExtTok). One node run with stub DOM; no clock."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def src(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


STUB = r"""
const mk = id => ({id, cls: new Set(), isConnected: true, focus(){ document.activeElement = this; },
  classList: {add(c){}, remove(c){}}, contains(x){ return x === this; }});
const opener = mk('opener'), q = mk('cmdkq'), box = mk('cmdk');
var document = {body: mk('body'), activeElement: null, getElementById: id => id === 'cmdk' ? box : id === 'cmdkq' ? q : null};
var ISPOP = false, ISWP = false, ISBP = false, cpOn = false, cpSel = 0;
function cpPaint(){}
let cpRet = null;
"""


def run(body):
    code = (STUB + js_fn("cpOpen") + "\n" + js_fn("cpClose") + "\n" + js_fn("tlExtTok")
            + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(code), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class FocusStaleTlTok(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
document.activeElement = opener; cpOpen();
R.open = document.activeElement.id;
cpClose(); R.back = document.activeElement.id;
document.activeElement = opener; cpOpen(); opener.isConnected = false; cpClose();
R.gone = document.activeElement.id;
const rows = [
  {kind: 'sess', tk: 900},
  {kind: 'sess', plat: 'cx', tk: 12000, segs: [[50, 60], [120, 130]], tks: [2000, 10000]},
  {kind: 'sess', plat: 'gm', tk: 13000, start: 200},
  {plat: 'cx', tk: 500, start: 10}];
R.all = tlExtTok(rows, null);
R.win = tlExtTok(rows, 100);
""")

    def test_cmdk_focus_returns_to_opener(self):
        self.assertEqual(self.R["open"], "cmdkq")
        self.assertEqual(self.R["back"], "opener")

    def test_cmdk_detached_opener_is_skipped(self):
        self.assertEqual(self.R["gone"], "cmdkq")

    def test_ext_tokens_whole_window(self):
        self.assertEqual(self.R["all"], {"cx": 12500, "gm": 13000})

    def test_ext_tokens_drop_pieces_before_window(self):
        self.assertEqual(self.R["win"], {"cx": 10000, "gm": 13000})

    def test_stale_dim_no_grayscale(self):
        rule = [l for l in src("web/css/90-main-ui.css").splitlines() if l.startswith("html.agstale ")]
        self.assertTrue(rule)
        self.assertFalse(any("grayscale" in l for l in rule))
        op = float(re.search(r"opacity:([.\d]+)", rule[0]).group(1))
        self.assertGreaterEqual(op, 0.8)   # measured: .7 left light .sbok at 2.89:1

    def test_no_platform_name_in_timeline_token_label(self):
        self.assertNotIn("'Claude '", src("web/js/74b-timeline-rows.js"))
        self.assertNotIn("'Claude '", src("web/js/74-timeline.js"))


if __name__ == "__main__":
    unittest.main()
