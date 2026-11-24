"""«Check results» step (47b hnVdStep): the jumped-to row clears the view's sticky .wvh caption; Config map project label stays left."""
import os
import re
import unittest

from tests._load import ROOT
from tests.test_tools_cfgmap_js import _js

# One flagged row inside .brep whose direct-child caption is 28px tall; style records the scroll margin set before the scroll.
_VIEW = (" const ORD = []; const st = {set scrollMarginTop(v){ ORD.push(['m', v]); }};"
         " const el = {dataset: {hnvd: 'v1'}, style: st, closest(){ return null; }, classList: {add(){}},"
         " scrollIntoView(o){ ORD.push(['s', o.block]); }};"
         " const HD = {offsetHeight: %s}; const brep = {querySelector(s){ return s === ':scope > .wvh' ? HD : null; }};"
         " const w = {closest(s){ return s === '.brep' ? %s : null; }, querySelectorAll(s){ return s === '[data-hnvdl=\"bad\"]' ? [el] : []; }};"
         " QSEL = s => s === '.tvw' ? w : null; mainView = 'tools'; hnVdStep('bad'); console.log(JSON.stringify(ORD))")


class VdStepPad(unittest.TestCase):
    def test_margin_clears_sticky_caption_before_nearest_scroll(self):
        self.assertEqual(_js(_VIEW % ("28", "brep")), [["m", "34px"], ["s", "nearest"]])

    def test_no_caption_keeps_outline_pad_only(self):
        self.assertEqual(_js(_VIEW % ("28", "null")), [["m", "6px"], ["s", "nearest"]])

    def test_cfgmap_project_label_not_pushed_right(self):
        with open(os.path.join(ROOT, "web", "css", "40-tokens.css"), encoding="utf-8") as f:
            css = f.read()
        self.assertIn(".brh2 i{margin-left:auto", css)   # the verdict <i> still takes the auto margin
        self.assertRegex(css, re.compile(r"\.brh2 i\.hncfgp\{margin-left:0\}"))


if __name__ == "__main__":
    unittest.main()
