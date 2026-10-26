"""84j7 Architecture minimap: viewport geometry + click mapping, lit classes copied by index, pref default on, T() labels."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

FNS = ["archMmOn", "archMmHtml", "archMmAt", "archMmStay", "archMmPadCss", "archMmGeom", "archMmLit", "archMmId", "archMmAnchor", "archMmHub", "archMmVM", "archMmFirst", "archMmVk", "archMmKeep", "archMmPos", "archMmPick"]
PRE = """
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const T = s => 'T[' + s + ']';
let STORE = {}, THROW = false;
function lsGet(k, d){ if(THROW) throw new Error('x'); return k in STORE ? STORE[k] : d; }
function cl(){ const s = new Set(); return { contains: c => s.has(c), toggle: (c, on) => { if(on) s.add(c); else s.delete(c); }, has: s }; }
function el(lit){ const e = { classList: cl() }; if(lit) e.classList.toggle('arlit', true); return e; }
function svg(ps, es, dim){ const s = { classList: cl(), ps, es, querySelectorAll: q => q === '[data-p]' ? ps : es }; s.classList.toggle('arlitdim', !!dim); return s; }
"""


def run(body):
    js = "\n".join([PRE, "\n".join(js_fn(n) for n in FNS), body])
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchMinimap(unittest.TestCase):
    def test_geom_scaled_and_clamped(self):
        # 15000x6000 map at content (10, 40); 1000x700 scroller with a 100px sticky top; 180x140 minimap box.
        r = run("const v = {sl: 2000, st: 1000, cw: 1000, ch: 700, sw: 15020, sh: 6080, top: 100}, m = {x: 10, y: 40, w: 15000, h: 6000};"
                "const g = archMmGeom(v, m, {w: 180, h: 140});"
                "const e = archMmGeom({sl: 14500, st: 0, cw: 1000, ch: 700, sw: 15020, sh: 6080, top: 100}, m, {w: 180, h: 140});"
                "console.log(JSON.stringify([g.s, g.w, g.h, g.r, e.f, g.to(0, 0), g.to(180, 140), g.to(90, 70 - 0), archMmGeom(v, {x: 0, y: 0, w: 0, h: 0}, {w: 1, h: 1})]));")
        s, w, h, rect, edge, lo, hi, mid, bad = r
        self.assertAlmostEqual(s, 180 / 15000)                         # width-bound scale
        self.assertAlmostEqual(w, 180)
        self.assertAlmostEqual(h, 72)
        oy = (140 - 72) / 2                                            # content centred vertically
        self.assertAlmostEqual(rect["x"], (2000 - 10) * s)
        self.assertAlmostEqual(rect["y"], oy + (1000 + 100 - 40) * s)
        self.assertAlmostEqual(rect["w"], 1000 * s)
        self.assertAlmostEqual(rect["h"], 600 * s)
        self.assertAlmostEqual(edge["x"] + edge["w"], 1.0)             # right edge clamped to the map
        self.assertEqual(lo, {"left": 0, "top": 0})                    # top-left corner clamps to 0
        self.assertEqual(hi, {"left": 15020 - 1000, "top": 6080 - 700})   # bottom-right clamps to max
        self.assertEqual(mid, {"left": round(10 + 7500 - 500), "top": round(40 + 3000 - 100 - 300)})   # centred on the map middle
        self.assertIsNone(bad)

    def test_lit_copied_by_index(self):
        r = run("const a = svg([el(1), el(0), el(1)], [el(0), el(1)], true), b = svg([el(0), el(1), el(0)], [el(1), el(0)], false);"
                "archMmLit(a, b); const o = [b.classList.contains('arlitdim'), b.ps.map(x => x.classList.contains('arlit')), b.es.map(x => x.classList.contains('arlit'))];"
                "archMmLit(svg([el(0), el(0), el(0)], [el(0), el(0)], false), b); o.push(b.classList.contains('arlitdim'), b.ps.concat(b.es).some(x => x.classList.contains('arlit')));"
                "console.log(JSON.stringify(o));")
        self.assertEqual(r, [True, [True, False, True], [False, True], False, False])

    def test_first_sync_anchors_once(self):
        # 6000x2000 content, 1000x700 scroller, 100px sticky top; map spans x 10..5990, y 300..2000 (wider than the view).
        r = run("const ARCH_MM = {seen: {}};"
                "const am = {scrollLeft: 0, scrollTop: 0, clientWidth: 1000, clientHeight: 700, scrollWidth: 6000, scrollHeight: 2000,"
                " getBoundingClientRect: () => ({left: 0, top: 0}), querySelector: q => q === '.archtop' ? {offsetHeight: 100} : null};"
                "const sv = {getBoundingClientRect: () => ({left: 10 - am.scrollLeft, top: 300 - am.scrollTop, width: 5980, height: 1700})};"
                "const K = c => [c, 'all', '', 0, 0, 'en', 40, 90].join('\\t'), F = c => ['fv0|', c, 'focus', 'm', 0, 0, 'en', 40, 90].join('\\t');"
                "archMmFirst(am, sv, K('c1')); const o = [[am.scrollLeft, am.scrollTop]];"
                "am.scrollLeft = 123; am.scrollTop = 45; archMmFirst(am, sv, K('c1')); o.push([am.scrollLeft, am.scrollTop]);"
                "archMmFirst(am, sv, F('c1')); o.push([am.scrollLeft, am.scrollTop]);"            # same map, first focus sight: anchored (no hub)
                "archMmFirst(am, sv, F('c2')); am.scrollLeft = 0; am.scrollTop = 0; archMmFirst(am, sv, K('c2')); o.push([am.scrollLeft, am.scrollTop]);"
                "am.scrollLeft = 7; archMmFirst(am, sv, K('c3')); o.push([am.scrollLeft, am.scrollTop]);"
                "console.log(JSON.stringify(o));")
        self.assertEqual(r[0], [10 + 2990 - 500, 300 - 100])               # wide, tall map: centred horizontally, top under the sticky bar (Entry visible)
        self.assertEqual(r[1], [123, 45])                                   # manual scroll kept on the next sync
        self.assertEqual(r[2], r[0])                                        # focus first sight anchors whatever the inherited scroll
        self.assertEqual(r[3], [0, 0])                                      # first seen as focus: overview later does not centre
        self.assertEqual(r[4], [7, 0])                                      # already scrolled new map: not moved

    def test_first_sync_narrow_map_centred_horizontally(self):
        # 2000x1500 content, 1000x700 scroller, 100px sticky top; 600px-wide map at x 500, y 250 fits the width.
        r = run("const ARCH_MM = {seen: {}};"
                "const am = {scrollLeft: 0, scrollTop: 0, clientWidth: 1000, clientHeight: 700, scrollWidth: 2000, scrollHeight: 1500,"
                " getBoundingClientRect: () => ({left: 0, top: 0}), querySelector: q => q === '.archtop' ? {offsetHeight: 100} : null};"
                "const sv = {getBoundingClientRect: () => ({left: 500 - am.scrollLeft, top: 250 - am.scrollTop, width: 600, height: 1200})};"
                "archMmFirst(am, sv, ['c1', 'all', '', 0, 0, 'en', 40, 90].join('\\t')); console.log(JSON.stringify([am.scrollLeft, am.scrollTop]));")
        self.assertEqual(r, [500 + 300 - 500, 250 - 100])                  # centred horizontally, top under the sticky bar

    def test_focus_first_sight_centres_hub_once(self):
        # 6000x2000 content, 1000x700 scroller, 100px sticky top; focus map x 10..5990, y 300..700 (fits); hub m5 at x 4000, 200 wide.
        r = run("const ARCH_MM = {seen: {}};"
                "const am = {scrollLeft: 0, scrollTop: 0, clientWidth: 1000, clientHeight: 700, scrollWidth: 6000, scrollHeight: 2000,"
                " getBoundingClientRect: () => ({left: 0, top: 0}), querySelector: q => q === '.archtop' ? {offsetHeight: 100} : null};"
                "const hub = {getBoundingClientRect: () => ({left: 4000 - am.scrollLeft, top: 400 - am.scrollTop, width: 200, height: 40})};"
                "const sv = {getBoundingClientRect: () => ({left: 10 - am.scrollLeft, top: 300 - am.scrollTop, width: 5980, height: 400}),"
                " querySelector: q => q === '[data-p=\"m5\"]' ? hub : null};"
                "const F = (fx, id) => [fx, 'c1', 'focus', id, 0, 0, 'en', 40, 90].join('\\t'), K = ['c1', 'all', '', 0, 0, 'en', 40, 90].join('\\t');"
                "am.scrollLeft = 300; am.scrollTop = 900; archMmFirst(am, sv, F('fv0|', 'a'), 'm5'); const o = [[am.scrollLeft, am.scrollTop]];"
                "archMmFirst(am, sv, F('fv1|3', 'a'), 'm5'); o.push([am.scrollLeft, am.scrollTop]);"            # same focus, new svg key
                "am.scrollLeft = 77; am.scrollTop = 11; archMmFirst(am, sv, F('fv0|', 'a'), 'm5'); o.push([am.scrollLeft, am.scrollTop]);"
                "archMmFirst(am, sv, K); o.push([am.scrollLeft, am.scrollTop]);"                              # back to the overview
                "archMmFirst(am, sv, F('fv0|', 'b'), 'm9'); o.push([am.scrollLeft, am.scrollTop]);"            # other focus, hub not found
                "console.log(JSON.stringify(o));")
        self.assertEqual(r[0], [4000 + 100 - 500, 300 + 200 - 100 - 300])  # hub centred horizontally, fitting map centred vertically
        self.assertEqual(r[1], r[0])                                        # re-paint of the same focus view does not move
        self.assertEqual(r[2], [77, 11])                                    # manual scroll kept
        self.assertEqual(r[3], [77, 11])                                    # overview seen with the focus: not centred
        self.assertEqual(r[4], [10 + 2990 - 500, 100])                      # no hub element: archMmAnchor on the map rect

    def test_scroll_kept_per_view_across_rebuild(self):
        # #feed is shared by every main tab: coming back rebuilds .archmap at 0,0; archPaint restores the view's last scroll.
        r = run("const ARCH_MM = {seen: {}, pos: {}};"
                "const K = (c, s) => [c, s ? 'focus' : 'all', s || '', 0, 0, 'en', 40, 90].join('\\t');"
                "const am = (k, t, l) => ({scrollTop: t, scrollLeft: l, querySelector: q => q === '.archdg' ? {dataset: {k}} : null});"
                "archMmKeep(am(K('c1'), 300, 1200)); archMmKeep(am('fv1|3\\t' + K('c1', 'a'), 50, 900));"
                "const o = [archMmPos(K('c1')), archMmPos('fv0|\\t' + K('c1', 'a')), archMmPos(K('c2')), archMmPos(K('c1', 'b'))];"
                "archMmKeep(am(K('c1'), 10, 20)); o.push(archMmPos(K('c1'))); archMmKeep(am('', 1, 1)); o.push(Object.keys(ARCH_MM.pos).length);"
                "console.log(JSON.stringify(o));")
        self.assertEqual(r[0], [300, 1200])           # overview: last scroll
        self.assertEqual(r[1], [50, 900])             # focus view: own entry, svg-key prefix (lit/flows) ignored
        self.assertIsNone(r[2])                       # new map identity: none (first-sight anchor applies)
        self.assertIsNone(r[3])                       # other focused module: none
        self.assertEqual(r[4], [10, 20])              # latest scroll wins
        self.assertEqual(r[5], 2)                     # unparsable key not stored

    def test_paint_restores_saved_scroll_before_diagram(self):
        src = js_fn("archPaint")
        i = src.find("archMmPick(sm, ")
        self.assertGreater(i, 0)
        self.assertLess(i, src.find("archDiagram(box"))   # archDiagram copies box._arsm for a cache-miss fill
        self.assertIn("box._arsm = [sm, sl, sd]", src[i:i + 120])

    def test_pick_on_view_key_change(self):
        # Back to the overview from a focus view: the overview's own saved scroll, not the focus view's carried one.
        r = run("const ARCH_MM = {seen: {}, pos: {}};"
                "const K = (c, s) => [c, s ? 'focus' : 'all', s || '', 0, 0, 'en', 40, 90].join('\\t');"
                "ARCH_MM.pos[archMmVk(K('c1'))] = [95, 1347];"
                "console.log(JSON.stringify([archMmPick([26, 144], 'fv0|\\t' + K('c1', 'a'), K('c1')),"   # focus -> overview
                " archMmPick([26, 144], K('c1'), K('c1')),"                                             # same view (click / poll): carried
                " archMmPick([95, 1347], K('c1'), 'fv0|\\t' + K('c1', 'b')),"                        # overview -> unseen focus: carried
                " archMmPick(null, null, K('c1')), archMmPick(null, null, K('c2')), archMmPick([5, 6], null, K('c2'))]));")
        self.assertEqual(r, [[95, 1347], [26, 144], [95, 1347], [95, 1347], None, [5, 6]])

    def test_hub_left_clamped(self):
        r = run("const v = {cw: 1000, ch: 700, sw: 3000, sh: 2000, top: 100}, m = {x: 0, y: 0, w: 3000, h: 300};"
                "console.log(JSON.stringify([archMmHub(v, m, {x: 2900, w: 100}), archMmHub(v, m, {x: 10, w: 20}), archMmHub(v, m, null)]));")
        self.assertEqual([x["left"] for x in r], [2000, 0, 1000])

    def test_pref_default_on(self):
        r = run("const o = [archMmOn()]; STORE['sidereus.archmm'] = '0'; o.push(archMmOn()); STORE['sidereus.archmm'] = '1'; o.push(archMmOn());"
                "THROW = true; o.push(archMmOn()); console.log(JSON.stringify(o));")
        self.assertEqual(r, [True, False, True, True])

    def test_html_labels_through_T(self):
        r = run("console.log(JSON.stringify([archMmHtml(true), archMmHtml(false)]));")
        on, off = r
        self.assertIn('class="archmm"', on)
        self.assertIn("T[Minimap]", on)
        self.assertIn("T[Hide minimap]", on)
        self.assertIn('class="archmm off"', off)
        self.assertIn("T[Show minimap]", off)
        self.assertIn("data-armm", off)
        self.assertIn('title="T[Hide minimap]" aria-label="T[Hide minimap]"', on)   # icon chip: label only in title/aria
        self.assertNotIn(">T[", on.split("<button", 1)[1])

class AnchorShortMap(unittest.TestCase):
    def test_short_map_centred_both_ways(self):
        # 1000x700 scroller, 100px sticky top (600px visible); 400x300 map at x 1000, y 500 in 3000x2000 content.
        r = run("const v = {cw: 1000, ch: 700, sw: 3000, sh: 2000, top: 100}, m = {x: 1000, y: 500, w: 400, h: 300};"
                "console.log(JSON.stringify(archMmAnchor(v, m)));")
        self.assertEqual(r, {"left": 1000 + 200 - 500, "top": 500 + 150 - 100 - 300})


@unittest.skipUnless(shutil.which("node"), "node not installed")
class DrillDownKeepsClickedNode(unittest.TestCase):
    """A drill-down click opens the focus view with the clicked node where it was on screen (no auto-centre)."""

    def test_clicked_node_stays_under_pointer(self):
        # 1000x700 scroller at client (50, 100), 6000x3000 content; node m5 clicked at client (450, 650);
        # the focus view draws hub m5 at content (4000, 900).
        r = run("const ARCH_MM = {seen: {}, pos: {}, at: null, pad: {}};"
                "const am = {scrollLeft: 300, scrollTop: 200, clientWidth: 1000, clientHeight: 700, scrollWidth: 6000, scrollHeight: 3000,"
                " getBoundingClientRect: () => ({left: 50, top: 100}), querySelector: q => q === '.archtop' ? {offsetHeight: 100} : null};"
                "const old = {dataset: {p: 'm5'}, closest: q => q === '.archmap' ? am : null, getBoundingClientRect: () => ({left: 450, top: 650, width: 120, height: 40})};"
                "const hub = {getBoundingClientRect: () => ({left: 50 + 4000 - am.scrollLeft, top: 100 + 900 - am.scrollTop, width: 120, height: 40})};"
                "const sv = {getBoundingClientRect: () => ({left: 50 + 10 - am.scrollLeft, top: 100 + 300 - am.scrollTop, width: 5980, height: 2000}),"
                " querySelector: q => q === '[data-p=\"m5\"]' ? hub : null};"
                "const F = id => ['fv0|', 'c1', 'focus', id, 0, 0, 'en', 40, 90].join('\\t');"
                "archMmAt(old); archMmFirst(am, sv, F('a'), 'm5'); const h = hub.getBoundingClientRect(), o = [[h.left, h.top], ARCH_MM.at];"
                "am.scrollLeft = 10; am.scrollTop = 20; archMmFirst(am, sv, F('a'), 'm5'); o.push([am.scrollLeft, am.scrollTop]);"   # repaint: not moved
                "archMmAt(old); am.scrollLeft = 0; am.scrollTop = 0; archMmFirst(am, sv, F('a'), 'm5'); const h2 = hub.getBoundingClientRect(); o.push([h2.left, h2.top]);"   # seen focus re-opened by a click
                "archMmAt({dataset: {p: 'm7'}, closest: () => am, getBoundingClientRect: () => ({left: 60, top: 110})}); am.scrollLeft = 5; am.scrollTop = 6;"
                "archMmFirst(am, sv, F('b'), 'm5'); o.push([am.scrollLeft, am.scrollTop], ARCH_MM.at);"   # anchor for another node: not moved, dropped
                "archMmAt({dataset: {p: 'm5'}, closest: () => am, getBoundingClientRect: () => ({left: 5000, top: 5000})}); archMmFirst(am, sv, F('c'), 'm5'); o.push([am.scrollLeft, am.scrollTop]);"   # clamped
                "console.log(JSON.stringify(o));")
        self.assertEqual(r[0], [450, 650])            # the clicked node did not move on screen
        self.assertIsNone(r[1])                       # anchor consumed once
        self.assertEqual(r[2], [10, 20])              # later repaints of the same focus never move the view
        self.assertEqual(r[3], [450, 650])
        self.assertEqual(r[4], [5, 6])
        self.assertIsNone(r[5])
        self.assertEqual(r[6], [0, 0])                # scroll clamped to [0, max]

    def test_click_records_anchor_before_paint(self):
        src = js_fn("archDgClick")
        i = src.find("archMmAt(b)")
        self.assertGreater(i, 0)
        self.assertLess(i, src.find("paintStruct()", i))

    def test_short_focus_content_gets_spacer(self):
        # Focus content shorter than the viewport (scrollHeight == clientHeight): clamping scrollTop to 0 moved the node up.
        # The .archdg slot grows a top / bottom spacer so the clicked node keeps its screen y; the spacer is kept for repaints of that view.
        r = run("const ARCH_MM = {seen: {}, pos: {}, at: null, pad: {}};"
                "const dg = {style: {}}, px = v => parseFloat(v) || 0;"
                "const am = {scrollLeft: 0, scrollTop: 0, clientWidth: 1000, clientHeight: 700, scrollWidth: 1000,"
                " get scrollHeight(){ return 700 + px(dg.style.paddingTop) + px(dg.style.paddingBottom); },"
                " getBoundingClientRect: () => ({left: 0, top: 100}), querySelector: q => q === '.archtop' ? {offsetHeight: 100} : null};"
                "let HY = 300; const hub = {getBoundingClientRect: () => ({left: 400, top: 100 + HY + px(dg.style.paddingTop) - am.scrollTop, width: 120, height: 40})};"
                "const sv = {closest: q => q === '.archdg' ? dg : null, getBoundingClientRect: () => ({left: 0, top: 100 + px(dg.style.paddingTop) - am.scrollTop, width: 1000, height: 600}),"
                " querySelector: q => q === '[data-p=\"m5\"]' ? hub : null};"
                "const F = id => ['fv0|', 'c1', 'focus', id, 0, 0, 'en', 40, 90].join('\\t'), at = y => archMmAt({dataset: {p: 'm5'}, closest: () => am, getBoundingClientRect: () => ({left: 400, top: y})});"
                "at(650); archMmFirst(am, sv, F('a'), 'm5'); const o = [hub.getBoundingClientRect().top, archMmPadCss(F('a')), archMmPadCss(F('z'))];"
                "dg.style = {}; HY = 650; am.scrollTop = 0; at(200); archMmFirst(am, sv, F('b'), 'm5'); o.push(hub.getBoundingClientRect().top, am.scrollTop);"   # node lower than it was: bottom spacer
                "console.log(JSON.stringify(o));")
        self.assertEqual(r[0], 650)                                   # top spacer: the node did not move up
        self.assertIn("padding-top:250px", r[1])                      # kept for repaints of the same view
        self.assertEqual(r[2], "")                                    # other views: no spacer
        self.assertEqual(r[3], 200)                                   # bottom spacer lets scrollTop reach it
        self.assertEqual(r[4], 550)
