"""«Fit to view» is zoom/pan only (48d), the folded «Working now» class does not reuse the node chip class (48j/43),
and the narrow run status line keeps Korean words whole (43). Source + node checks; no live files."""
import os
import re
import unittest

import tests.test_pipeline_run as tpr
from tests._load import ROOT


def _read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


class FitToViewKeepsNodes(unittest.TestCase):
    def _handler(self):
        m = re.search(r"^\s*if\(e\.target\.closest\('\[data-plfitv\]'\)\)\{[^\n]*$", _read("web", "js", "48d-pipeline-cv-input.js"), re.M)
        self.assertIsNotNone(m)
        return m.group(0)

    def test_handler_never_reflows(self):
        h = self._handler()
        for bad in ("plWrapBest", "plgLayout", "plTouch"):   # a re-flow moved ui.x/y -> dirty draft -> «Run» disabled
            self.assertNotIn(bad, h)
        self.assertIn("plFit(E, w && w.querySelector('.plcv'), false, false, true)", h)

    def test_fit_call_leaves_positions_and_centres(self):
        r = tpr.CanvasFit._run(self, tpr.CanvasFit.DOM + " plGwFit(); plFit(E, cv, false); E.touched = true; E.view.x = 300; E.view.y = -90; const k0 = plgKey(E.G);"
                               " plFit(E, cv, false, false, true); return [k0 === plgKey(E.G), off()];",
                               ids="abc", extra=("plGwFit", "plPanH"))
        self.assertTrue(r[0])                                            # node positions untouched: draft stays clean
        self.assertLessEqual(max(abs(r[1][0]), abs(r[1][1])), 1)         # drawn graph centred


class FoldedClass(unittest.TestCase):
    def test_folded_class_is_not_node_chip(self):
        js = _read("web", "js", "48j-pipeline-now.js")
        self.assertIn("plNowFolded() ? ' plmdf' : ''", js)
        self.assertNotIn("' plnc'", js)
        css = _read("web", "css", "43-pipeline.css")
        self.assertNotIn(".plmd.plnc", css)
        self.assertIn(".plmd.plmdf{grid-template-columns", css)
        self.assertIn(".plmd.plmdf>.strspg{display:none}", css)


class RunStatusWrap(unittest.TestCase):
    def test_narrow_status_keeps_ko_words(self):
        css = _read("web", "css", "43-pipeline.css")
        m = re.search(r"@media \(max-width:1439px\)\{[^\n]*\.plbar>\.plrunst>span[^{]*\{([^}]*)\}\}", css)
        self.assertIsNotNone(m)
        self.assertIn("word-break:keep-all", m.group(1))
        self.assertIn("overflow-wrap:anywhere", m.group(1))   # long ASCII tokens still split


if __name__ == "__main__":
    unittest.main()
