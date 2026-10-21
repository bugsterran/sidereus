"""Pipelines canvas view survives Save (new sha) and «Undo» (web/js/48d-pipeline-canvas.js plEnt/plViewCarry, 48-pipeline.js plResetEnt).

⚠plEnt rebuilt the entry copying only `view`: without touched/fitK plGwFit re-fitted (x snapped to 0), and «Undo» deleted
the entry so plAfterPaint ran the first-open fit + centre after a click. Run under node with DOM stubs."""
import json
import os
import unittest

from tests._load import ROOT, js_fn
from tests.test_pipeline_graph import P, _js

FNS = ("plEntKey", "plEnt", "plCurEnt", "plViewCarry", "plResetEnt", "plFit", "plFitKey", "plFitRaw", "plCvNeed", "plWrapCols",
       "plWrapBest", "plWrapFirst", "plCentre", "plDrawBox", "plVisY", "plApplyView", "plZoomLabel", "plPanH", "plGwFit", "plAfterPaint")

STUBS = r"""
const PL_ZMIN = 0.8, PL_ZFIT = 0.4, PL_SPLIT = { v: '--plpanh', key: 'sidereus.plpanh', min: 200, cv: 200 };
let PLDRAG = null, PLRO = null, mainView = 'pipe', innerHeight = 900, CENTRES = 0, FITS = 0;
const PLS = { proj: '/p', g: {}, file: null };
function plCur(){ return PLS.file; }
function lsGet(){ return 0; }
function plMeasure(){ return false; }
function plPaintEdgesNodes(){}
function plFitPills(){}
function getComputedStyle(){ return { paddingBottom: '0' }; }
const ST = () => ({ setProperty(){}, removeProperty(){}, height: '' });
const cv = { clientWidth: 1100, clientHeight: 400, querySelector(){ return null; }, closest(){ return null; } };
cv.parentNode = { clientHeight: 440 };
const g = { style: ST(), classList: { contains: () => false }, getBoundingClientRect(){ return { top: 100 }; }, querySelector(s){ return s === '.plcv' ? cv : null; } };
const fd = { clientTop: 0, scrollTop: 0, clientHeight: 900, scrollHeight: 900, getBoundingClientRect(){ return { top: 0, bottom: 900 }; } };
const document = { querySelector(s){ return s === '.plw .plgw' ? g : null; }, getElementById(id){ return id === 'feed' ? fd : null; } };
const box = { querySelector(s){ return s === '.plcv' ? cv : null; } };
"""


def run(body):
    src = "\n".join(js_fn(f) for f in FNS)
    # count centre/fit calls without changing what they do
    spy = ("const _c = plCentre; plCentre = function(){ CENTRES++; return _c.apply(null, arguments); };"
           "const _f = plFit; plFit = function(){ FITS++; return _f.apply(null, arguments); };")
    return _js(STUBS + src + "\n" + spy + "\n" + body)


FILE = "const mk = sha => Object.assign(JSON.parse(%s), { ok: true, sha }); PLS.file = mk('a');" % json.dumps(json.dumps(
    dict(P, stages=[dict(s, ui={"x": 44 + 248 * i, "y": 24}) for i, s in enumerate(P["stages"])])))


class ViewKeep(unittest.TestCase):
    def test_save_keeps_panned_view(self):
        out = run(FILE + """
          const E = plEnt(PLS.file); E.view = { x: 272, y: -19, z: 0.966 }; E.touched = true; E.ctrd = false; E.fitK = 'old';
          PLS.file = mk('b');   // saved: new file sha
          plGwFit();
          const N = plCurEnt();
          console.log(JSON.stringify([N !== E, N.view, N.touched]));""")
        self.assertEqual(out, [True, {"x": 272, "y": -19, "z": 0.966}, True])

    def test_undo_keeps_view_and_never_centres(self):
        out = run(FILE + """
          const E = plEnt(PLS.file); E.view = { x: 442, y: -19, z: 0.9 }; E.touched = true; E.ctrd = false; E.G.nodes[0].title = 'x';
          plResetEnt(PLS.file);
          CENTRES = 0; FITS = 0;
          plAfterPaint(box);
          const N = plCurEnt();
          console.log(JSON.stringify([N !== E, N.G.nodes[0].title !== 'x', N.view, CENTRES, FITS]));""")
        self.assertEqual(out, [True, True, {"x": 442, "y": -19, "z": 0.9}, 0, 0])

    def test_first_open_still_fits_and_centres(self):
        out = run(FILE + """
          plAfterPaint(box);
          const E = plCurEnt();
          console.log(JSON.stringify([!!E.view, E.first, E.ctrd, FITS > 0, CENTRES > 0]));""")
        self.assertEqual(out, [True, True, True, True, True])

    def test_reset_click_uses_helper(self):
        with open(os.path.join(ROOT, "web/js/48-pipeline.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("[data-plreset]')){ plResetEnt(plCur());", js)
        self.assertNotIn("if(p) delete PLS.g[plEntKey(p.name)]; PLS.diff = null", js)


if __name__ == "__main__":
    unittest.main()
