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
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def drag(saved):
    """Load the file with pref `saved`, drag the grip to x=400 then x=900, release, double-click. Returns the event log."""
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
           "const grip = {setPointerCapture(){}}, tgt = {closest: s => s === '#tlnmg' ? grip : null};\n"
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


if __name__ == "__main__":
    unittest.main()
