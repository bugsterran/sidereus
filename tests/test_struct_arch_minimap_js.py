"""84j7 Architecture minimap: viewport geometry + click mapping, lit classes copied by index, pref default on, T() labels."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

FNS = ["archMmOn", "archMmHtml", "archMmGeom", "archMmLit", "archMmId", "archMmAnchor", "archMmVM", "archMmFirst"]
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
                "archMmFirst(am, sv, F('c1')); o.push([am.scrollLeft, am.scrollTop]);"            # same map, focus key: no move
                "am.scrollLeft = 0; am.scrollTop = 0; archMmFirst(am, sv, F('c2')); archMmFirst(am, sv, K('c2')); o.push([am.scrollLeft, am.scrollTop]);"
                "am.scrollLeft = 7; archMmFirst(am, sv, K('c3')); o.push([am.scrollLeft, am.scrollTop]);"
                "console.log(JSON.stringify(o));")
        self.assertEqual(r[0], [10, 300 - 100])                            # wide map: left edge, top under the sticky bar (Entry visible)
        self.assertEqual(r[1], [123, 45])                                   # manual scroll kept on the next sync
        self.assertEqual(r[2], [123, 45])                                   # a click to focus never centres
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
