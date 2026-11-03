"""81e Ctrl/Cmd+wheel zoom keeps the diagram point under the cursor in place (mmdZoomAnchor scrolls the nearest scroller)."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
with open(os.path.join(WEB, "js", "81e-structure-mermaid.js"), encoding="utf-8") as fh:
    MMD = fh.read()
WHEEL = re.search(r"^document\.addEventListener\('wheel'.*?^\}, \{ passive: false \}\);", MMD, re.M | re.S).group(0)

PRE = r"""
const H = {};
const document = { addEventListener: (t, f) => { H[t] = f; } };
const getComputedStyle = el => el.cs;
// Scroller 1000x700 at viewport (0,0); svg sits at content (10,50), wrapped in a non-scrolling .mmdv.
function world(vbW, vbH){
  const a = { viewBox: '0 0 ' + vbW + ' ' + vbH, width: String(vbW), height: String(vbH) };
  const sc = { cs: { overflowX: 'auto', overflowY: 'auto' }, scrollLeft: 0, scrollTop: 0, clientWidth: 1000, clientHeight: 700, parentElement: null,
    get scrollWidth(){ return +a.width + 20; }, get scrollHeight(){ return +a.height + 60; } };
  const mv = { cs: { overflowX: 'visible', overflowY: 'visible' }, scrollWidth: 0, clientWidth: 0, scrollHeight: 0, clientHeight: 0, parentElement: sc };
  const s = { a, dataset: {}, parentElement: mv, getAttribute: k => (k in a ? a[k] : null), setAttribute: (k, v) => { a[k] = String(v); },
    getBoundingClientRect: () => ({ left: 10 - sc.scrollLeft, top: 50 - sc.scrollTop, width: +a.width, height: +a.height }) };
  const v = { querySelector: q => q === 'svg.mmdsvg' ? s : null };
  v.closest = q => q === '.mmdv' ? v : null;
  return { s, sc, v };
}
// Map point (fraction of the svg) under viewport pixel (cx, cy).
const at = (w, cx, cy) => { const r = w.s.getBoundingClientRect(); return [(cx - r.left) / r.width, (cy - r.top) / r.height]; };
"""


def run(body):
    js = "\n".join([PRE, js_fn("mmdZoomAnchor"), WHEEL, "(() => {\n" + body + "\n})();"])
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class WheelAnchor(unittest.TestCase):
    def test_point_under_cursor_stays(self):
        r = run("const w = world(2000, 1500); w.sc.scrollLeft = 300; w.sc.scrollTop = 200; const o = [];"
                "const ev = d => ({ ctrlKey: true, deltaY: d, clientX: 700, clientY: 450, target: w.v, preventDefault(){} });"
                "const a = at(w, 700, 450); H.wheel(ev(-200)); const b = at(w, 700, 450);"
                "o.push(w.s.a.width !== '2000', (b[0] - a[0]) * +w.s.a.width, (b[1] - a[1]) * +w.s.a.height);"
                "H.wheel(ev(300)); const c = at(w, 700, 450); o.push((c[0] - a[0]) * +w.s.a.width, (c[1] - a[1]) * +w.s.a.height);"
                "console.log(JSON.stringify(o));")
        self.assertTrue(r[0])   # the svg did resize
        for d in r[1:]:
            self.assertLessEqual(abs(d), 1)

    def test_plain_wheel_untouched(self):
        r = run("const w = world(2000, 1500); w.sc.scrollLeft = 300; let p = 0;"
                "H.wheel({ ctrlKey: false, deltaY: -200, clientX: 700, clientY: 450, target: w.v, preventDefault(){ p = 1; } });"
                "console.log(JSON.stringify([w.s.a.width, w.sc.scrollLeft, p]));")
        self.assertEqual(r, ["2000", 300, 0])


if __name__ == "__main__":
    unittest.main()
