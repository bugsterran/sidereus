"""Pipelines canvas row height (web/js/48d-pipeline-canvas.js plCvNeed): follows the graph, capped at 62vh.

The fixed 62vh row pushed the stage panel below the fold at 1440x900. Pure function run under node."""
import json
import os
import re
import unittest

from tests._load import ROOT, js_all, js_fn
from tests.test_pipeline_graph import P, _js

FNS = "\n".join(js_fn(f) for f in ("plZFloor", "plFitRaw", "plCvNeed", "plWSizes", "plFit", "plFitKey", "plSizeKey", "plWatchLay", "plWrapCols"))
_ALL = js_all()
WATCH = "\n".join(re.search(r"^const %s[^\n]*$" % c, _ALL, re.M).group(0) for c in ("PLW_MIN", "PL_ZFIT", "PL_ZWATCH")) + "\n"


def src(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class CanvasHeight(unittest.TestCase):
    def need(self, body):
        return _js(FNS + "\n" + body)

    def test_one_row_chain_is_short(self):
        # demo chain (5 stages, 2 loop-backs) on one row, 1100px canvas, 900px window
        out = self.need("const G = plgFrom(%s); plgLayout(G, 28, 5); console.log(JSON.stringify(plCvNeed(G, 1100, 900)));" % json.dumps(P))
        self.assertLess(out, 0.62 * 900)
        self.assertGreaterEqual(out, 200)

    def test_tall_graph_capped(self):
        mk = "plgFrom({name: 'x', defaults: {model: 'inherit', retry: 0}, stages: Array.from({length: 7}, (_, i) => ({title: 's' + i, agent: 'a'}))})"
        out = self.need("const G = %s; plgLayout(G, 28, 1); console.log(JSON.stringify([plCvNeed(G, 1100, 900), plCvNeed(G, 0, 900), plCvNeed({nodes: [], loops: []}, 1100, 900)]));" % mk)
        self.assertEqual(out, [558, 558, 200])

    def test_watch_canvas_shows_every_wrapped_row(self):
        # ★1100x900 Watch stack ~591px (A = 591 - 2 grips = 543): shares alone gave the canvas 304 for a 2-row need of 488 (+42 strip).
        # The need is this paint's canvas minimum (capped at A - pane min - card min = 379); the rest is a Watch-only zoom below plZFloor.
        out = self.need(WATCH + "const G = plgFrom(%s); plgLayout(G, 28, 3); const F = [0.5585, 0.2473, 0.1941];"
                        " const row = plCvNeed(G, 760, 900) + 42, s = plWSizes(543, F, row), big = plWSizes(800, F, row), plain = plWSizes(543, F);"
                        " const ch = s[0] - 42, E = {G: G}, cv = {clientWidth: 760, clientHeight: ch, closest: q => q === '.plgw.plwt' ? {} : null};"
                        " plFit(E, cv, false); const bot = Math.max(...G.nodes.map(n => n.ui.y + plgH(G, n.id)));"
                        " const E2 = {G: G}; plFit(E2, {clientWidth: 760, clientHeight: ch}, false);"
                        " console.log(JSON.stringify({row, s, big, plain, ch, z: E.view.z, bottom: E.view.y + bot * E.view.z, hz: plFitRaw(G, Infinity, ch), edit: E2.view.z}));" % json.dumps(P))
        self.assertEqual(out["row"], 530)
        self.assertEqual(out["s"], [379, 80, 84])                     # min(need row, A - 164): card then pane give way
        self.assertEqual(out["big"][0], 530)                          # room enough: exactly the need row
        self.assertEqual(sum(out["big"]), 800)
        self.assertEqual(out["plain"], [304, 134, 105])               # no need passed: shares as before
        self.assertLess(out["z"], 1)                                  # below the 100% floor ...
        self.assertAlmostEqual(out["z"], out["hz"])                   # ... just far enough to fit the height
        self.assertLessEqual(out["bottom"], out["ch"])                # last row bottom inside the canvas
        self.assertEqual(out["edit"], 1)                              # outside Watch the floor still holds

    def test_watch_grip_resize_wins_over_the_need(self):
        # After a grip resize on this page load the person's canvas stands (no snap back to the need); the Watch zoom still fits every row.
        lets = "\n".join(re.search(r"^(?:const|let) %s[^\n]*$" % c, _ALL, re.M).group(0) for c in ("PLWDRAG", "PLWUSER", "PLW_STEP", "PLW_SNAP_MAX"))
        fns = "\n".join(js_fn(f) for f in ("plWShares", "plWApply", "plWStep", "plWNow", "plWSave", "plWReset", "plWKey", "plWSnap", "plWatchFit"))
        dom = ("const SAVED = {}; function lsJson(k, d){ return k in SAVED ? SAVED[k] : d; } function lsSetJson(k, v){ SAVED[k] = v; } function lsDel(k){ delete SAVED[k]; }"
               " const ST = {}, gs = {style: {setProperty(k, v){ ST[k] = v; }, getPropertyValue(k){ return ST[k] || ''; }}, querySelector: () => null};"
               " const OC = {style: {}, get offsetHeight(){ return parseFloat(this.style.height); }, getBoundingClientRect: () => ({bottom: 0})};"
               " const fd = {scrollHeight: 0, clientHeight: 0, getBoundingClientRect: () => ({bottom: 0})};"
               " var document = {querySelector(q){ return q.includes('plwov') ? OC : q.includes('plnl') ? null : gs; }, querySelectorAll: () => []};"
               " var getComputedStyle = () => ({paddingBottom: '0'});"
               " const GP = {dataset: {plwg: 'p'}}, key = k => plWKey({key: k, target: {closest: () => GP}, preventDefault(){}});")
        out = self.need(WATCH + lets + "\n" + fns + "\n" + dom + " const G = plgFrom(%s); plgLayout(G, 28, 3); const row = R => 42 + plWatchLay(G, 760, R - 42, false).need;"
                        " plWatchFit(gs, fd, 700, row); const a = ST['--plcvh']; key('ArrowUp');"
                        " plWatchFit(gs, fd, 700, row); const b = ST['--plcvh'], ch = parseFloat(b) - 42;"
                        " const E = {G: G}; plFit(E, {clientWidth: 760, clientHeight: ch, closest: q => q === '.plgw.plwt' ? {} : null}, false);"
                        " const bot = Math.max(...G.nodes.map(n => n.ui.y + plgH(G, n.id)));"
                        " plWReset(); plWatchFit(gs, fd, 700, row);"
                        " console.log(JSON.stringify({a, b, ch, bottom: E.view.y + bot * E.view.z, hh: plFitRaw(G, Infinity, ch), z: E.view.z, reset: ST['--plcvh']}));" % json.dumps(P))
        # A = 700 - 48 = 652: need row 530 capped at A - 164 = 488; one ArrowUp (24px) leaves 464 < 530, still >= 0.7 for the 2 rows.
        self.assertEqual(out["a"], "488px")                          # first paint: the need minimum (capped at A - 164)
        self.assertEqual(out["b"], "464px")                          # resized below the need: kept on the next paint
        self.assertLessEqual(out["z"], out["hh"])                    # zoom x graph height <= canvas height
        self.assertLessEqual(out["bottom"], out["ch"])
        self.assertEqual(out["reset"], "488px")                      # Home / double-click default: the need minimum again

    def test_watch_zoom_floor_and_column_pick(self):
        # ★1440x900 change in Watch (938x419) wrapped to 3 columns at 39%: Watch never fits under PL_ZWATCH (the rest pans)
        # and, when nothing fits at plZFloor, takes the max-zoom column count instead of the floor-width one.
        mk = "n => plgFrom({name: 'x', defaults: {model: 'inherit', retry: 0}, stages: Array.from({length: n}, (_, i) => ({title: 's' + i, agent: 'a'}))})"
        out = self.need(WATCH + "const mk = %s; const G = plgFrom(%s); plgLayout(G, 28, 3); const wt = {closest: q => q === '.plgw.plwt' ? {} : null};"
                        " const E = {G: G}; plFit(E, Object.assign({clientWidth: 760, clientHeight: 289}, wt), false);"
                        " const E2 = {G: G}; plFit(E2, {clientWidth: 760, clientHeight: 289}, false);"
                        " const G7 = mk(7); console.log(JSON.stringify({z: E.view.z, raw: plFitRaw(G, Infinity, 289), edit: E2.view.z,"
                        " cols: [plWrapCols(G7, 760, 300), plWrapCols(G7, 760, 300, true)]}));" % (mk, json.dumps(P)))
        self.assertLess(out["raw"], 0.7)                              # the full height fit would be 60%
        self.assertEqual(out["z"], 0.7)                               # Watch floor: the last row pans
        self.assertEqual(out["edit"], 1)                              # outside Watch: plZFloor as before
        self.assertEqual(out["cols"], [3, 4])                         # 7 stages, 760x300: floor-width 3 cols (52%) vs Watch best 4 cols (79%)

    def test_watch_fixtures_fit_both_axes(self):
        # ★Live 1440/1100x900: bugfix (4) stayed one row at 100% with 2 cards 53/279px past the right edge in a 598x281 canvas;
        # change (8) at 70% left a card 173px past the edge at 938x419. Columns, zoom and need now come from one pass over the largest canvas.
        S = lambda t, **k: dict({"title": t, "agent": "a"}, **k)
        fx = {"bugfix": [S("a1"), S("a2"), S("a3", onFail={"goto": "a2", "max": 2}), S("a4")],
              "verify": [S("b1"), S("b2", fanout="slices"), S("b3"), S("b4", fanout="slices"), S("b5", onFail={"goto": "b4", "max": 2}), S("b6")],
              "change": [S("c1"), S("c2"), S("c3", fanout="slices"), S("c4", onFail={"goto": "c3", "max": 2}), S("c5", onFail={"goto": "c3", "max": 1, "then": "c7"}),
                         S("c6", onFail={"goto": "c3", "max": 1, "then": "c7"}), S("c7", onFail={"goto": "c3", "max": 1}, onlyOnJump=True), S("c8")]}
        out = self.need(WATCH + "const FX = %s, out = {}, wt = {closest: q => q === '.plgw.plwt' ? {} : null};"
                        " for(const wd of [0, 252]) for(const k in FX) for(const [cw, H] of [[938, 419], [598, 385]]){"
                        "  const G = plgFrom({name: k, defaults: {model: 'inherit', retry: 0}, stages: FX[k]}); G.wd = {}; if(wd) G.nodes.forEach(n => G.wd[n.id] = wd);"
                        "  const p = plWatchLay(G, cw, H, true), c2 = plWrapCols(G, cw, p.need, true); plgLayout(G, 28, c2);"
                        "  const E = {G: G}; plFit(E, Object.assign({clientWidth: cw, clientHeight: p.need}, wt), false);"
                        "  const r = Math.max(...G.nodes.map(n => n.ui.x + plgW(G, n.id))) * E.view.z + E.view.x;"
                        "  out[k + cw + (wd ? 'w' : '')] = {c: p.c, c2, z: E.view.z, pz: p.z, need: p.need, r, full: plFitRaw(G, cw, p.need)};"
                        " } console.log(JSON.stringify(out));" % json.dumps(fx))
        for k, o in out.items():
            cw = 938 if "938" in k else 598
            self.assertLessEqual(o["r"], cw, k)                          # no card past the right edge
            self.assertGreaterEqual(o["z"], 0.7 - 1e-9, k)
            self.assertEqual(o["c2"], o["c"], k)                         # the pick at the granted need = the pick at the largest canvas
            self.assertAlmostEqual(o["z"], o["pz"], msg=k)
            self.assertLessEqual(o["need"], 419 if cw == 938 else 385, k)
        got = {k: (o["c"], round(o["z"], 3)) for k, o in out.items() if not k.endswith("w")}
        self.assertEqual(got, {"bugfix938": (4, 1), "bugfix598": (2, 0.934), "verify938": (4, 1), "verify598": (3, 0.859), "change938": (6, 0.7), "change598": (3, 0.7)})
        for k in ("bugfix598", "verify938", "verify598"):
            self.assertLessEqual(out[k]["z"], out[k]["full"] + 1e-9, k)   # fully visible: zoom x graph height <= canvas height

    def test_wired_into_fit_and_css(self):
        js = src("web/js/48d-pipeline-canvas.js")
        self.assertIn("plCvNeed(E.G, cv.clientWidth, innerHeight)", js)
        self.assertIn("placeholder=\"' + esc(T('Stage name')) + '\"", js)
        self.assertIn("var(--plcvh,", src("web/css/43-pipeline.css"))


if __name__ == "__main__":
    unittest.main()
