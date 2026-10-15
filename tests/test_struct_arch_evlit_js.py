"""84j5 edge-row highlight on the Architecture map (R1-R4): hovering a «Connections» row lights that edge + its two ends,
a click pins it (toggle / empty space clears), an edge in a multi-step flow lights the whole flow, nothing ever scrolls."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e
from tests.test_struct_arch_detail_js import CONSTS, DET_FNS, DOM, MAP, PRE, FNS, SEND, J, DET

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
with open(os.path.join(WEB, "js", "84j5-structure-arch-evlit.js"), encoding="utf-8") as fh:
    EVL = fh.read()
EVL_FNS = re.findall(r"^function (\w+)\(", EVL, re.M)
# Single-statement lines of the 84j click handler, run against a fake target.
ROW_CLICK = re.search(r"^  if\(\(b = t\.closest\('\[data-ae\]'\)\)\).*$", J, re.M).group(0)
EMPTY_CLICK = re.search(r"^  if\(ARCH\.op && t\.closest\('\.archmap,\.archel-list'\).*$", J, re.M).group(0)
SVG = "const svg = fakeSvg(['m0', 'm1', 'm2', 'm3'], [['m0', 'm1'], ['m1', 'm2'], ['m2', 'm3'], ['m1', 'm0'], ['m0', 'm3']]);"
LIT = ("const lit = s => [s.ns.filter(n => n.classList.contains('arlit')).map(n => n.dataset.p),"
       " s.es.filter(e => e.classList.contains('arlit')).map(e => e.dataset.f + '>' + e.dataset.t),"
       " s.es.filter(e => e.classList.contains('arevk')).map(e => e.dataset.f + '>' + e.dataset.t), s.classList.contains('arlitdim')];")


def run(body):
    fns = list(dict.fromkeys(FNS + DET_FNS + EVL_FNS))
    js = "\n".join([PRE, CONSTS, DOM, "var ARCH_EVL = null;", "\n".join(js_fn(n) for n in fns), SEND,
                    "const D = " + json.dumps(MAP) + "; ARCH.cache['/r'] = D; ARCH.lit = null; ARCH.scope = null;", SVG, LIT,
                    "(async () => {\n" + body + "\n})().catch(e => { console.error(e); process.exit(1); });"])
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchEvLit(unittest.TestCase):
    def test_R1_hover_lights_edge_and_ends_then_restores(self):
        r = run("ARCH.scope = {p: '/r', layer: 'api', group: null}; archLitPaint(svg, archLitSet(D, archLitQ('/r'))); const before = lit(svg);"
                "ARCH_EVL = {p: '/r', i: 5}; const q = archLitQ('/r'); archLitPaint(svg, archLitSet(D, q)); const on = lit(svg);"
                "ARCH_EVL = null; archLitPaint(svg, archLitSet(D, archLitQ('/r')));"
                "console.log(JSON.stringify([q, on, before, lit(svg)]));")
        q, on, before, after = r
        self.assertEqual(q, {"edge": 5, "tests": False})              # web -> db (import, no flow)
        self.assertEqual(on[0], ["m0", "m3"])                          # only its two end modules
        self.assertEqual(on[1], ["m0>m3"])                             # only that edge pair
        self.assertEqual(on[2], ["m0>m3"])
        self.assertTrue(on[3])                                         # rest dimmed
        self.assertEqual(after, before)                                # leaving the row restores the map exactly

    def test_R2_pin_toggle_empty_click_and_precedence(self):
        r = run("const T0 = sel => ({closest(q){ return q.split(',').some(x => sel.indexOf(x) >= 0) ? {dataset: {ae: '4'}} : null; }});"
                "const row = (t, p) => { let b; " + ROW_CLICK + " };"
                "const empty = (t, p) => { " + EMPTY_CLICK + " };"
                "const o = []; row(T0(['[data-ae]']), '/r'); o.push(ARCH.op, archLitQ('/r'));"
                "ARCH.lit = {p: '/r', flow: 'f2'}; o.push(archLitQ('/r').edge); ARCH_EVL = {p: '/r', i: 1}; o.push(archLitQ('/r').edge); ARCH_EVL = null;"
                "row(T0(['[data-ae]']), '/r'); o.push(ARCH.op, archLitQ('/r').flow);"
                "row(T0(['[data-ae]']), '/r'); empty(T0(['.archmap']), '/r'); o.push(ARCH.op);"
                "row(T0(['[data-ae]']), '/r'); empty(T0(['.archmap', '.mmdfe']), '/r'); o.push(ARCH.op); empty(T0(['.archel-list']), '/r'); o.push(ARCH.op);"
                "console.log(JSON.stringify(o));")
        self.assertEqual(r[0], "/r\t4")
        self.assertEqual(r[1], {"edge": 4, "tests": False})           # pinned row -> edge query
        self.assertEqual(r[2], 4)                                      # pin beats a lit flow
        self.assertEqual(r[3], 1)                                      # hover beats the pin
        self.assertEqual(r[4:6], ["", "f2"])                           # same row again unpins, the lit flow comes back
        self.assertEqual(r[6], "")                                     # empty map space clears
        self.assertEqual(r[7], "/r\t4")                                # a click on an edge is not empty space
        self.assertEqual(r[8], "")                                     # empty list padding clears

    def test_R2_stale_edge_index_falls_back(self):
        r = run("ARCH.op = '/r\\t99'; ARCH.scope = {p: '/r', layer: 'api', group: null}; const a = archLitQ('/r');"
                "ARCH.lit = {p: '/r', flow: 'f1'}; ARCH_EVL = {p: '/r', i: 42}; const b = archLitQ('/r');"
                "console.log(JSON.stringify([a, b]));")
        self.assertEqual(r[0], {"layer": "api", "group": None})       # stale pin -> scope
        self.assertEqual(r[1]["flow"], "f1")                           # stale hover + pin -> lit flow
        self.assertNotIn("edge", r[1])

    def test_R3_flow_path_lit_in_order(self):
        r = run("const a = archEvFlow(D, 0, null), b = archEvFlow(D, 4, null), c = archEvFlow(D, 2, null), d = archEvFlow(D, 2, ['f2']),"
                " e = archEvFlow(D, 99, null); ARCH_EVL = {p: '/r', i: 0}; const q = archLitQ('/r'), s = archLitSet(D, q); archLitPaint(svg, s);"
                "console.log(JSON.stringify([a, b, c, d, e, q, lit(svg), [...s.e].sort()]));")
        a, b, c, d, e, q, on, es = r
        self.assertEqual([a, b, c, e], ["f1", None, "f1", None])      # web->srv in f1; srv->web has no flow; f2 has one step only
        self.assertEqual(d, "f2")                                      # a lit flow holding the edge wins
        self.assertEqual(q, {"edge": 0, "flow": "f1", "tests": False})  # exactly one flow
        self.assertEqual(on[0], ["m0", "m1", "m2", "m3"])              # every step of the path
        self.assertEqual(on[1], ["m0>m1", "m1>m2", "m2>m3", "m1>m0"])
        self.assertEqual(on[2], ["m0>m1", "m1>m0"])                    # the row's own edge stands out (.arevk)
        self.assertEqual(len(es), 6)                                   # same set as lighting f1 itself
        with open(os.path.join(WEB, "css", "79-structure-arch.css"), encoding="utf-8") as fh:
            css = fh.read()
        self.assertIn(".mmdfe.arlit.arevk .mmde{stroke-width", css)

    def test_R4_off_marker_never_moves_view(self):
        r = run("const v = {left: 0, top: 40, right: 500, bottom: 400}, R = (l, t, w, h) => ({left: l, top: t, right: l + w, bottom: t + h});"
                "console.log(JSON.stringify([archOffPos(R(10, 50, 40, 20), v), archOffPos(R(480, 390, 40, 20), v), archOffPos(R(600, 100, 40, 20), v),"
                " archOffPos(R(-90, 900, 40, 20), v), archOffPos(R(200, 0, 40, 20), v), archOffPos(R(1000, 5000, 40, 20), v)]));")
        self.assertIsNone(r[0])
        self.assertIsNone(r[1])                                        # partly visible counts as visible
        self.assertEqual(r[2], {"side": "r", "x": 500, "y": 110})
        self.assertEqual(r[3], {"side": "l", "x": 0, "y": 380})        # clamped inside v
        self.assertEqual(r[4], {"side": "t", "x": 220, "y": 40})
        self.assertEqual(r[5], {"side": "r", "x": 500, "y": 380})
        for bad in ("scrollTo", "scrollIntoView", "archLitGo", "archScrollAt", "scrollTop", "scrollLeft", ".focus("):
            self.assertNotIn(bad, EVL)
        self.assertNotIn("innerHTML", EVL)                             # hover is class-only
        self.assertNotIn("paintStruct", EVL)
        self.assertIn("addEventListener('scroll'", EVL)
        self.assertIn("}, true);", EVL)                                # capture: scroll does not bubble

    def test_R4_marker_dom_and_stale_hover(self):
        r = run("const mk = []; const body = {getBoundingClientRect(){ return {left: 0, top: 0}; }, querySelector(){ return mk[0] || null; },"
                " appendChild(m){ mk.push(m); m.remove = () => mk.splice(mk.indexOf(m), 1); }};"
                "let er = {left: 900, top: 100, right: 950, bottom: 120}; const am = {scrollTop: 3, scrollLeft: 4, clientWidth: 500, clientHeight: 400,"
                " clientLeft: 0, clientTop: 0, getBoundingClientRect(){ return {left: 0, top: 0}; }, closest(){ return body; },"
                " querySelector(){ return null; }, querySelectorAll(){ return [{getBoundingClientRect(){ return er; }}]; }};"
                "const slot = {closest(){ return am; }}; globalThis.archViewRect = " + js_fn("archViewRect") + ";"
                "document.createElement = () => ({style: {}, setAttribute(){}}); archOffMark(slot); const a = mk.length && [mk[0].className, mk[0].textContent, mk[0].style.left];"
                "er = {left: 100, top: 100, right: 150, bottom: 120}; archOffMark(slot);"
                "ARCH_EVL = {p: '/r', i: 2}; document.querySelector = () => ({dataset: {ae: '2'}}); archEvlLive('/r'); const k1 = ARCH_EVL;"
                "document.querySelector = () => null; archEvlLive('/r');"
                "console.log(JSON.stringify([a, mk.length, am.scrollTop, am.scrollLeft, k1, ARCH_EVL]));")
        self.assertEqual(r[0], ["archoff r", "→ 화면 밖", "500px"])
        self.assertEqual(r[1], 0)                                      # back in view: marker removed
        self.assertEqual(r[2:4], [3, 4])                               # scroll untouched
        self.assertEqual(r[4], {"p": "/r", "i": 2})                    # row still under the pointer keeps the hover
        self.assertIsNone(r[5])                                        # a repaint that lost the row drops it

    def test_file_rules(self):
        self.assertNotRegex(EVL, r"[가-힣]")
        self.assertIsNone(re.search(r"^ARCH\.", EVL, re.M))
        self.assertNotRegex(EVL, r"\bARCH\.\w+\s*=[^=]")              # never writes ARCH: the hover lives in ARCH_EVL
        self.assertNotIn("T(nm", EVL)
        self.assertIn("archEvlLive", DET)
        self.assertIn("archOffMark", DET)
        self.assertLess(len(J.splitlines()), 700)
        names = sorted(os.listdir(os.path.join(WEB, "js")))
        self.assertLess(names.index("84j4-structure-arch-focus.js"), names.index("84j5-structure-arch-evlit.js"))
        self.assertLess(names.index("84j5-structure-arch-evlit.js"), names.index("84k-structure-arch-flow.js"))


if __name__ == "__main__":
    unittest.main()
