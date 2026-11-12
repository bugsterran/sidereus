"""Pipelines canvas view survives Save (new sha) and «Undo» (web/js/48d-pipeline-canvas.js plEnt/plViewCarry, 48-pipeline.js plResetEnt).

⚠plEnt rebuilt the entry copying only `view`: without touched/fitK plGwFit re-fitted (x snapped to 0), and «Undo» deleted
the entry so plAfterPaint ran the first-open fit + centre after a click. Run under node with DOM stubs."""
import json
import os
import unittest

from tests._load import ROOT, js_fn
from tests.test_pipeline_graph import P, _js

FNS = ("plEntKey", "plEnt", "plCurEnt", "plViewCarry", "plResetEnt", "plFit", "plFitKey", "plSizeKey", "plFitRaw", "plCvNeed", "plWrapCols",
       "plWrapBest", "plWrapFirst", "plCentre", "plDrawBox", "plVisY", "plApplyView", "plZoomLabel", "plPanH", "plGwFit", "plAfterPaint",
       "plNowPickApply", "plZFloor")

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

    # Six stages with two loop-backs, saved in one row: too wide for a 560x300 canvas, so the first open wraps and fits.
    SIX = "const six = Object.assign(JSON.parse(%s), { ok: true, sha: 's6' }); PLS.file = six; cv.clientWidth = 560; cv.clientHeight = 300;" % json.dumps(json.dumps(
        dict(P, stages=[dict(s, ui={"x": 44 + 248 * i, "y": 24}) for i, s in enumerate(P["stages"] + [{"title": "배포", "agent": "ops"}])])))
    # Drawn box (cards + status pill + loop lanes) placed by the view, against the canvas: [fitsW, fitsH, inside].
    FITS = """const fit = E => { const B = plDrawBox(plVG(E)), v = E.view, z = v.z;
          return [(B.r - B.l) * z <= cv.clientWidth + 0.5, (B.b - B.t) * z <= cv.clientHeight + 0.5,
                  v.x + B.l * z >= -0.5 && v.x + B.r * z <= cv.clientWidth + 0.5 && v.y + B.t * z >= -0.5 && v.y + B.b * z <= cv.clientHeight + 0.5]; };"""

    def test_first_open_fits_drawn_box(self):
        out = run(self.SIX + self.FITS + """
          plAfterPaint(box); const E = plCurEnt();
          console.log(JSON.stringify([E.G.nodes.length, E.G.loops.length > 1, fit(E)[0], E.view.z]));""")
        self.assertEqual(out, [6, True, True, 1])   # wraps to the canvas width at the 100% floor; the rows pan vertically

    def test_cards_grow_on_later_paint_refit_while_first(self):
        # ⚠the live run arrives on a later paint and widens cards; fitK (canvas size, count) alone kept the stale zoom clipped
        out = run(self.SIX + self.FITS + """
          plAfterPaint(box); const E = plCurEnt(), z0 = E.view.z;
          E.G.wd = {}; E.G.ht = {}; E.G.nodes.forEach(n => { E.G.wd[n.id] = 320; E.G.ht[n.id] = 150; });
          const x0 = E.G.nodes.map(n => n.ui.x).join(); plGwFit();
          console.log(JSON.stringify([E.view.z === z0, E.G.nodes.map(n => n.ui.x).join() !== x0, fit(E)[0]]));""")
        self.assertEqual(out, [True, True, True])   # floored zoom kept; re-wrapped for the wider cards

    def test_select_and_now_pick_never_move_view(self):
        out = run(self.SIX + """
          plAfterPaint(box); const E = plCurEnt(), v0 = JSON.stringify(E.view);
          E.sel = { k: 'n', id: E.G.nodes[2].id }; plAfterPaint(box); const a = JSON.stringify(E.view);
          PLS.data = { '/p': {} }; PLS.nowPick = { name: PLS.file.name, title: E.G.nodes[4].title }; plNowPickApply();
          E.G.wd = {}; E.G.nodes.forEach(n => { E.G.wd[n.id] = 300; });   // a later poll grows the cards after the pick
          plAfterPaint(box); plGwFit();
          console.log(JSON.stringify([a === v0, JSON.stringify(E.view) === v0, E.first, E.sel.id === E.G.nodes[4].id]));""")
        self.assertEqual(out, [True, True, False, True])

    # Four unplaced stages (auto layout = our own wrap) on a 560x300 canvas: a 300px card wraps 1 column, 184px cards 2x2.
    FOUR = "PLS.file = Object.assign(JSON.parse(%s), { ok: true, sha: 'f4' }); cv.clientWidth = 560; cv.clientHeight = 300;" % json.dumps(json.dumps(
        dict(P, stages=P["stages"][:4])))

    def test_cards_shrink_after_click_rewrap_our_layout(self):
        # ⚠plgPush only pushes right: without a re-flow the chain kept the 1-column pitch of the wide card after any click
        fresh = run(self.FOUR + """
          const E = plEnt(PLS.file); E.G.wd = { n1: 184 }; plAfterPaint(box);
          console.log(JSON.stringify(E.G.nodes.map(n => n.ui.x)));""")
        shrink = """
          const E = plEnt(PLS.file); E.G.wd = { n1: 300 }; plAfterPaint(box); const a = E.G.nodes.map(n => n.ui.x);
          E.first = %s; E.G.wd = { n1: 184 }; plGwFit();
          console.log(JSON.stringify([a, E.G.nodes.map(n => n.ui.x), E.laid, plgKey(E.G) === E.base]));"""
        first, out = run(self.FOUR + shrink % "true"), run(self.FOUR + shrink % "false")
        self.assertEqual(out[0], [44, 44, 44, 44])
        self.assertEqual(len(set(out[1])), len(set(fresh)))   # 2 columns, like a fresh 184px layout
        self.assertEqual(out[1:], [first[1], True, True])   # same re-flow as before the click; the draft stays clean
        # a selected node defers it (a poll never moves what the person picked); the next fit after deselect re-flows
        sel = run(self.FOUR + """
          const E = plEnt(PLS.file); E.G.wd = { n1: 300 }; plAfterPaint(box);
          E.first = false; E.sel = { k: 'n', id: 'n2' }; E.G.wd = { n1: 184 }; plGwFit(); const a = E.G.nodes.map(n => n.ui.x);
          E.sel = null; plGwFit();
          console.log(JSON.stringify([a, E.G.nodes.map(n => n.ui.x), plgKey(E.G) === E.base]));""")
        self.assertEqual(sel, [[44, 44, 44, 44], first[1], True])

    def test_touched_view_not_refitted(self):
        out = run(self.SIX + """
          plAfterPaint(box); const E = plCurEnt();
          E.view = { x: 12, y: -40, z: 1.2 }; E.touched = true; E.first = false;
          cv.clientWidth = 900; cv.clientHeight = 500; E.G.wd = {}; E.G.nodes.forEach(n => { E.G.wd[n.id] = 300; });
          plGwFit(); plAfterPaint(box);
          console.log(JSON.stringify(E.view));""")
        self.assertEqual(out, {"x": 12, "y": -40, "z": 1.2})

    def test_reset_click_uses_helper(self):
        with open(os.path.join(ROOT, "web/js/48-pipeline.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("[data-plreset]')){ plResetEnt(plCur());", js)
        self.assertNotIn("if(p) delete PLS.g[plEntKey(p.name)]; PLS.diff = null", js)


if __name__ == "__main__":
    unittest.main()
