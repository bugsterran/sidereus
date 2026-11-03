"""84j8 Architecture zoom buttons (R1-R3): − / + step within the 81e wheel range, 100% label + reset, Fit to pane width,
viewport centre kept, minimap clone untouched, zoom re-applied before the scroll restore."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


def _read(*p):
    with open(os.path.join(WEB, *p), encoding="utf-8") as fh:
        return fh.read()


ZM = _read("js", "84j8-structure-arch-zoom.js")
MMD = _read("js", "81e-structure-mermaid.js")
ARCH = _read("js", "84j-structure-arch.js")
ZM_FNS = re.findall(r"^function (\w+)\(", ZM, re.M)
CONSTS = "\n".join(re.findall(r"^const ARCH_ZM.*$", ZM, re.M))

PRE = r"""
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const T = s => s;
const H = {};
const document = { addEventListener: (t, f) => { H[t] = f; } };
const CALLS = [];
function archMmKeep(){ CALLS.push('keep'); } function archMmView(){ CALLS.push('view'); } function archOffMark(){ CALLS.push('off'); }
// Fake .archmap: 1000x700 scroller, 100px sticky top; svg centred horizontally when narrower, at content y 50.
function fakeSvg(vbW, vbH, cls){
  const a = { viewBox: '0 0 ' + vbW + ' ' + vbH, width: String(vbW), height: String(vbH), class: cls || 'mmdsvg' };
  return { a, dataset: {}, getAttribute: k => (k in a ? a[k] : null), setAttribute: (k, v) => { a[k] = String(v); } };
}
function fakeMap(svg){
  const pct = { textContent: '100%' }, top = { offsetHeight: 100 }, bar = { offsetHeight: 25 };
  const slot = { dataset: { k: 'c1\tall\t\t0\t0\ten\t10\t20' }, querySelector: q => q === '.archdg .mmdv > svg.mmdsvg' ? svg : q === '.archdg .archzm-pct' ? pct : null };
  const am = { scrollLeft: 0, scrollTop: 0, clientWidth: 1000, clientHeight: 700, clientLeft: 0, clientTop: 0,
    get scrollWidth(){ return Math.max(1000, +svg.a.width + 20); }, get scrollHeight(){ return Math.max(700, +svg.a.height + 80); },
    getBoundingClientRect: () => ({ left: 0, top: 0 }),
    querySelector: q => q === '.archtop' ? top : q === '.archdg .mmdbar' ? bar : q === '.archdg' ? slot : slot.querySelector(q) };
  svg.getBoundingClientRect = () => { const w = +svg.a.width, h = +svg.a.height, x = 10 + Math.max(0, (980 - w) / 2);
    return { left: x - am.scrollLeft, top: 50 - am.scrollTop, width: w, height: h }; };
  slot.closest = () => am;
  return { am, slot, pct };
}
"""


def run(body):
    fns = ["archMmVM", "archMmId", "archMmVk"] + ZM_FNS
    js = "\n".join([PRE, CONSTS, "\n".join(js_fn(n) for n in fns), "\n".join(LISTENERS_SRC),
                    "(() => {\n" + body + "\n})();"])
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


LISTENERS_SRC = re.findall(r"^document\.addEventListener\(.*?^\}(?:, \{ passive: (?:true|false) \})?\);", ZM, re.M | re.S)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchZoom(unittest.TestCase):
    def test_R1_step_clamps_and_buttons_only_on_arch_map(self):
        r = run("console.log(JSON.stringify([archZmStep(1, 1), archZmStep(1, -1), archZmStep(2.9, 1), archZmStep(0.55, -1), archZmStep(3, 1), archZmStep(0.5, -1)]));")
        self.assertAlmostEqual(r[0], 1.25)
        self.assertAlmostEqual(r[1], 0.8)
        self.assertEqual(r[2:], [3, 0.5, 3, 0.5])
        mmd_html = re.search(r"^function archMmd\(.*?^}", ARCH, re.S | re.M).group(0)
        self.assertLess(mmd_html.index("archZmBar()"), mmd_html.index("class=mmdtg"))
        bar = run("console.log(JSON.stringify(archZmBar()));")
        self.assertEqual(re.findall(r'data-arz="([^"]+)"', bar), ["-1", "0", "1", "fit"])
        self.assertIn('class="archzm-b archzm-pct" data-arz="0" title="Reset to 100%" aria-label="Reset to 100%">100%<', bar)
        block = re.search(r"^function mmdBlock\(.*?^}", MMD, re.S | re.M).group(0)
        self.assertNotIn("archzm", block)
        self.assertNotIn("data-arz", MMD)

    def test_R1_range_matches_81e_wheel(self):
        wheel = re.search(r"Math\.max\(([\d.]+), Math\.min\(([\d.]+), \(\+s\.dataset\.z", MMD)
        r = run("console.log(JSON.stringify([ARCH_ZM_MIN, ARCH_ZM_MAX]));")
        self.assertEqual(r, [float(wheel.group(1)), float(wheel.group(2))])

    def test_R2_set_label_reset_and_wheel(self):
        r = run("const s = fakeSvg(800, 400), m = fakeMap(s); const o = [];"
                "archZmSet(m.am, 1.5); o.push(m.pct.textContent, s.a.width, s.a.height, s.dataset.z, CALLS.slice());"
                "archZmSet(m.am, 1); o.push(m.pct.textContent, s.a.width);"
                "s.dataset.z = '2'; const v = { closest: q => q === '.archdg .mmdv' ? v : q === '.archdg' ? m.slot : null, querySelector: q => q === ':scope > svg.mmdsvg' ? s : null };"
                "CALLS.length = 0; H.wheel({ ctrlKey: true, target: v }); o.push(m.pct.textContent, ARCH_ZM.z[archMmVk(m.slot.dataset.k)], CALLS.slice());"
                "s.dataset.z = '2.5'; H.wheel({ ctrlKey: false, target: v }); o.push(m.pct.textContent);"
                "console.log(JSON.stringify(o));")
        self.assertEqual(r[0:4], ["150%", "1200", "600", "1.5"])
        self.assertEqual(r[4], ["keep", "view", "off"])
        self.assertEqual(r[5:7], ["100%", "800"])
        self.assertEqual(r[7:10], ["200%", 2, ["view"]])                # wheel refreshes the minimap rect
        self.assertEqual(r[10], "200%")                                   # plain wheel scrolls, label untouched

    def test_R2_click_buttons(self):
        # .mmdv grows with the svg (max-content .mmd): only the .archdg pane width (1018 = 1000 + borders/paddings) counts.
        r = run("const s = fakeSvg(2000, 400), m = fakeMap(s); const v = { get clientWidth(){ return +s.a.width + 16; } }; m.slot.clientWidth = 1018;"
                "m.am.querySelector = (q => o => o === '.archdg .mmdv' ? v : q(o))(m.am.querySelector);"
                "const btn = a => ({ dataset: { arz: a }, closest: q => q === '.archmap' ? m.am : null });"
                "const click = a => H.click({ target: { closest: q => q === '.archdg [data-arz]' ? btn(a) : null } });"
                "const o = []; click('1'); o.push(m.pct.textContent); click('-1'); o.push(m.pct.textContent); click('fit'); o.push(m.pct.textContent, s.a.width);"
                "click('0'); o.push(m.pct.textContent, s.a.width); console.log(JSON.stringify(o));")
        self.assertEqual(r, ["125%", "100%", "50%", "1000", "100%", "2000"])

    def test_R3_fit(self):
        r = run("console.log(JSON.stringify([archZmFit(400, 2000), archZmFit(1200, 800), archZmFit(9000, 100), archZmFit(500, 0)]));")
        self.assertEqual(r, [0.5, 1.5, 3, 1])

    def test_centre_preserved(self):
        r = run("const s = fakeSvg(2000, 1500), m = fakeMap(s); m.am.scrollLeft = 300; m.am.scrollTop = 200;"
                "const pt = () => { const v = archMmVM(m.am, s); return [(v.view.sl + 500 - v.map.x) / v.map.w, (v.view.st + 100 + 300 - v.map.y) / v.map.h]; };"
                "const a = pt(); archZmSet(m.am, 1.5); const b = pt(), v = archMmVM(m.am, s);"
                "console.log(JSON.stringify([(b[0] - a[0]) * v.map.w, (b[1] - a[1]) * v.map.h]));")
        self.assertLessEqual(abs(r[0]), 1)
        self.assertLessEqual(abs(r[1]), 1)

    def test_minimap_svg_untouched_and_apply(self):
        r = run("const s = fakeSvg(800, 400), m = fakeMap(s), mini = fakeSvg(800, 400);"
                "archZmSet(m.am, 2); const o = [mini.a.width, mini.dataset.z === undefined];"
                "const s2 = fakeSvg(800, 400), m2 = fakeMap(s2); archZmApply(m2.slot); o.push(s2.a.width, m2.pct.textContent, m2.am.scrollLeft);"
                "const s3 = fakeSvg(800, 400), m3 = fakeMap(s3); m3.slot.dataset.k = 'c2\tall\t\t0\t0\ten\t1\t1'; archZmApply(m3.slot); o.push(s3.a.width, m3.pct.textContent);"
                "console.log(JSON.stringify(o));")
        self.assertEqual(r, ["800", True, "1600", "200%", 0, "800", "100%"])
        for sel in re.findall(r"querySelector\('([^']*mmdsvg[^']*)'\)", ZM):
            self.assertTrue(sel.startswith(".archdg .mmdv > ") or sel.startswith(":scope > "), sel)   # every svg selector skips the .archmm clone (:scope = .archdg .mmdv)

    def test_apply_runs_before_scroll_restore(self):
        paint = ARCH[ARCH.index("box.innerHTML = '<div class=\"strtab archtab\">' + head(archHeadNote(d, dvOn)"):]
        self.assertLess(paint.index("archZmApply("), paint.index("archScrollPut(box, sm, sl, sd)"))
        fill = re.search(r"slot\.innerHTML = ARCH\.svg\[k\];.*?archScrollPut\(box, pd", ARCH, re.S).group(0)
        self.assertIn("archZmApply(slot)", fill)

    def test_bar_pinned_below_sticky_top_on_vertical_scroll(self):
        css = _read("css", "79d-structure-arch-zoom.css")
        rule = re.search(r"^\.archdg \.mmdbar\{top:([^;]+);z-index:1;background:var\(--mmd-bg\)\}", css, re.M)
        self.assertIsNotNone(rule)   # opaque bar under .archtop (z 2), not top:0 (hidden behind .archtop)
        self.assertEqual(rule.group(1), "calc(var(--archtop-sh,0px) - 6px)")
        self.assertIn(".archtop{position:sticky;top:-6px;", _read("css", "79-structure-arch.css"))   # the 6px the calc cancels
        r = run("const s = fakeSvg(800, 400), m = fakeMap(s), P = {}; m.am.style = { setProperty: (k, v) => { P[k] = v; } };"
                "archZmApply(m.slot); console.log(JSON.stringify([P['--archtop-sh'], s.a.width]));")
        self.assertEqual(r, ["100px", "800"])   # set even with no stored zoom

    def test_source_text_in_flex_flow_never_over_zoom_group(self):
        css = _read("css", "79d-structure-arch-zoom.css")
        self.assertIn("\n.archdg .mmdtg{position:static;flex:0 0 auto}", css)   # overrides 79 sticky right:10px (offset ignores the flex sibling)
        self.assertIn(".archdg .mmdtg{position:sticky;right:10px}", _read("css", "79-structure-arch.css"))
        self.assertGreater(css.index(".archdg .mmdtg{position:static"), css.index(".archzm{display:inline-flex;flex:0 0 auto}"))

    def test_ko_entries(self):
        ko = _read("js", "06-i18n-zu-arch-zoom.js") + _read("js", "06-i18n-zm-b1.js")
        for s in ("Zoom out", "Zoom in", "Reset to 100%", "Fit to width", "Fit"):
            self.assertIn("'" + s + "':", ko)


if __name__ == "__main__":
    unittest.main()
