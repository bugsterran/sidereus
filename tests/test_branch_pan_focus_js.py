"""brPanPaint keeps keyboard focus on work-unit rows and id'd controls across a poll repaint (web/js/88-branch.js)."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all
from tests._node import node_e


def _fn(src, name):
    return re.search(r"^function " + name + r"\(.*?^}", src, re.S | re.M).group(0)


def _run(active):
    src = js_all()
    js = "\n".join([
        "const CSS = {escape: s => String(s).replace(/[\"\\\\]/g, m => '\\\\' + m)};",
        "let brDet = null, brWu = '', brSel = '', brPanLast = '', foc = '';",
        "const ae = " + json.dumps(active) + ";",
        "const p = {scrollTop: 0, className: '', innerHTML: '', contains: () => true};",
        "const document = {activeElement: ae, getElementById: () => p, querySelectorAll: () => []};",
        "function brPanBody(){ return 'x'; } function brWire(){} function paintBr(){}",
        "function brTreeFocus(s){ foc = s; }",
        _fn(src, "brFocusKey"), _fn(src, "brPanPaint"),
        "brPanPaint(); console.log(JSON.stringify(foc));",
    ])
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class BranchPanFocus(unittest.TestCase):
    def test_work_unit_row(self):
        self.assertEqual(_run({"dataset": {"bw": "/r/wt-a"}, "id": ""}), '[data-bw="/r/wt-a"]')

    def test_id_controls(self):
        self.assertEqual(_run({"dataset": {}, "id": "brmg"}), "#brmg")
        self.assertEqual(_run({"dataset": {}, "id": "brwuall"}), "#brwuall")

    def test_tree_rows_still_first(self):
        self.assertEqual(_run({"dataset": {"bt": "L/fix"}, "id": "x"}), '[data-bt="L/fix"]')
        self.assertEqual(_run({"dataset": {"bn": "main"}, "id": ""}), '[data-bn="main"]')

    def test_plain_element_no_key(self):
        self.assertEqual(_run({"dataset": {}, "id": ""}), "")


if __name__ == "__main__":
    unittest.main()
