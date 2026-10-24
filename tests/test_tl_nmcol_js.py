"""Timeline name column (web/js/74d-timeline-nmcol.js): width clamp, pref sidereus.tlnmW on drag/dblclick. Fake DOM."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

SRC = os.path.join(os.path.dirname(__file__), "..", "web", "js", "74d-timeline-nmcol.js")


def node(src):
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def drag(saved, cls="tlnmg"):
    """Load the file with pref `saved`, drag a target with classes `cls` to x=400 then x=900, release, double-click. Returns the event log."""
    src = ("const log = [], L = {}, prefs = {'sidereus.tlnmW': " + json.dumps(saved) + "};\n"
           "function lsGet(k, d){ return k in prefs ? prefs[k] : d; }\n"
           "function lsSet(k, v){ log.push(['set', k, v]); prefs[k] = v; return true; }\n"
           "function lsDel(k){ log.push(['del', k]); delete prefs[k]; return true; }\n"
           "const esc = s => s, KE = (k, e) => k;\n"
           "const c = {getBoundingClientRect: () => ({left: 0})}, ax = {clientWidth: 1000, querySelector: () => c};\n"
           "const feed = {querySelector: () => ax, style: {setProperty: (k, v) => log.push(['css', v]), removeProperty: () => log.push(['css', ''])}};\n"
           "const document = {documentElement: {classList: {add(){}, remove(){}}},\n"
           "  addEventListener: (t, f) => { (L[t] = L[t] || []).push(f); }, removeEventListener: (t, f) => { L[t] = (L[t] || []).filter(x => x !== f); },\n"
           "  getElementById: () => feed, querySelector: () => ax};\n"
           "const fire = (t, e) => (L[t] || []).slice().forEach(f => f(e));\n"
           "const grip = {setPointerCapture(){}}, cls = " + json.dumps(cls) + ".split(' ');\n"
           # closest() honours class selectors only ('.a.b', comma lists), so an id selector or a non-grip target misses
           "const tgt = {closest: sel => sel.split(',').some(q => (q = q.trim())[0] === '.' && q.slice(1).split('.').every(k => cls.includes(k))) ? grip : null};\n"
           + js_fn("dragTrack") + "\n"   # shared drag lifecycle (08-ui-kit.js)
           + open(SRC, encoding="utf-8").read() + "\n"
           "log.push(['w0', tlNmW]);\n"
           "fire('pointerdown', {target: tgt, button: 0, pointerId: 1, preventDefault(){}, stopPropagation(){}});\n"
           "fire('pointermove', {clientX: 400, buttons: 1}); fire('pointermove', {clientX: 900, buttons: 1}); fire('pointerup', {});\n"
           "fire('dblclick', {target: tgt, stopPropagation(){}}); log.push(['w1', tlNmW]);\n"
           "process.stdout.write(JSON.stringify(log));")
    return node(src)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TlNmCol(unittest.TestCase):
    def test_clamp(self):
        out = node(js_fn("tlNmWClamp") + "\nconst TLNM_MIN = 220;\n"
                   "process.stdout.write(JSON.stringify([tlNmWClamp(100, 1000), tlNmWClamp(333.4, 1000), tlNmWClamp(900, 1000), tlNmWClamp(300, 300)]));")
        self.assertEqual(out, [220, 333, 500, 220])

    def test_drag_persists_clamped_and_dblclick_resets(self):
        log = drag("300")
        self.assertEqual(log[0], ["w0", 300])
        self.assertIn(["css", "400px"], log)
        self.assertIn(["css", "500px"], log)                       # 900 > half of the 1000px column
        self.assertIn(["set", "sidereus.tlnmW", "500"], log)
        self.assertEqual([x for x in log if x[0] in ("set", "del")], [["set", "sidereus.tlnmW", "500"], ["del", "sidereus.tlnmW"]])
        self.assertEqual(log[-2:], [["css", ""], ["w1", 0]])

    def test_saved_below_min_is_default(self):
        self.assertEqual(drag("100")[0], ["w0", 0])

    def test_row_grip_drags_too(self):
        log = drag("300", "tlnmg tlnmgl")                       # full-height grip matches the same class
        self.assertIn(["set", "sidereus.tlnmW", "500"], log)
        self.assertEqual(log[-1], ["w1", 0])

    def test_non_grip_target_does_not_drag(self):
        log = drag("300", "tlt")
        self.assertEqual(log, [["w0", 300], ["w1", 300]])       # no css, no set, no del

    def test_wire_inserts_one_row_grip(self):
        src = ("const lsGet = (k, d) => d, lsSet = () => true, lsDel = () => true, esc = s => s, T = s => s;\n"
               "const mk = () => ({html: [], querySelector(s){ return this.html.some(h => h.includes(s.slice(1))) ? {} : null; },\n"
               "  insertAdjacentHTML(p, h){ this.html.push(h); }});\n"
               "const cell = mk(), wrap = mk(), box = {querySelector: s => s === '.tlwrap' ? wrap : cell};\n"
               "const document = {addEventListener(){}, getElementById: () => null}, window = {};\n"
               + open(SRC, encoding="utf-8").read() + "\n"
               "tlNmColWire(box); tlNmColWire(box);\n"
               "process.stdout.write(JSON.stringify([cell.html.length, wrap.html]));")
        n_cell, wrap_html = node(src)
        self.assertEqual(n_cell, 1)
        self.assertEqual(len(wrap_html), 1)
        self.assertIn('class="tlnmg tlnmgl"', wrap_html[0])


class TlNmColCss(unittest.TestCase):
    def test_fallback_clamp_identical(self):
        css = open(os.path.join(os.path.dirname(__file__), "..", "web", "css", "20-timeline.css"), encoding="utf-8").read()
        fb = "var(--tlnm-w,clamp(260px,24vw,340px))"
        for sel in (".tlnm{", ".tlaxr .tlnm{", ".tlnmgl{"):
            i = css.index("\n" + sel) + 1
            self.assertIn(fb, css[i:css.index("}", i)], sel)

    def test_row_line_hidden_by_opacity_not_background(self):
        # the #nxcss twin copies background-color with higher specificity, which would beat :hover
        css = open(os.path.join(os.path.dirname(__file__), "..", "web", "css", "20-timeline.css"), encoding="utf-8").read()
        i = css.index("\n.tlnmgl::after{") + 1
        rule = css[i:css.index("}", i)]
        self.assertNotIn("background", rule)
        self.assertIn("opacity:0", rule)
        self.assertIn("html.tlnmdrag .tlnmgl::after{opacity:1}", css)


if __name__ == "__main__":
    unittest.main()
