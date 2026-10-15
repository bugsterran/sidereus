"""Arch map focus view fits the visible map box: 81f mmdPlace `room` (spacing only, never text/box size),
84j archFitOf (room from the .archmap box) and archMmd(…, fit) (focus only; the overview ignores it)."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e
from tests.test_structure_mermaid_js import PRE as MPRE, FNS as MFNS
from tests.test_struct_arch_js import SELF_MODS, SELF_EDGES

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "js")
with open(os.path.join(WEB, "81g0-structure-grid-router.js"), encoding="utf-8") as fh:
    ROUTER = fh.read()
ARCH_FNS = ("archIsTest", "archMq", "archPairs", "archReduce", "archSrc", "archRanks", "archMmd", "archFitOf")


def run(body):
    js = "\n".join([MPRE, "const MMD_BUDGET = 1e9, MMD_UNCROSS = 1e9, ARCH_DIR = 'TB'; let ERR = null; function softErr(t, e){ ERR = String(e); }", ROUTER]
                   + [js_fn(f) for f in MFNS] + [js_fn(n) for n in ARCH_FNS] + [body])
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


# One input, the focused hub, four outputs: the focus view's LR shape.
PLACE = """
const ids = ['i', 'f', 'o1', 'o2', 'o3', 'o4'], es = [{a: 'i', b: 'f', w: 1, lw: 0, lh: 0}].concat(['o1', 'o2', 'o3', 'o4'].map(o => ({a: 'f', b: o, w: 1, lw: 0, lh: 0})));
const sz = () => ({w: 90, h: 30}), P = room => mmdPlace(ids, es, sz, 'LR', null, null, room);
const a = P(null), b = P({w: 900, h: 500}), c = P({w: 100, h: 60}), gaps = p => ['o2', 'o3', 'o4'].map((k, i) => p.pos[k].y - p.pos[['o1', 'o2', 'o3'][i]].y);
process.stdout.write(JSON.stringify([[a.w, a.h], [b.w, b.h], JSON.stringify(a) === JSON.stringify(c), gaps(a), gaps(b)]));
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchFocusFit(unittest.TestCase):
    def test_place_room_spreads_spacing(self):
        (aw, ah), (bw, bh), same, ga, gb = run(PLACE)
        self.assertTrue(same)                                   # a room smaller than the natural drawing changes nothing
        self.assertGreater(bh, ah * 2)                          # rows spread down to the room height
        self.assertLessEqual(bh, 500)
        self.assertGreater(bw, aw)                              # layer gaps widen toward the room width
        self.assertLessEqual(bw, 900)
        self.assertEqual(len({round(g, 3) for g in gb}), 1)                     # even row gap, boxes keep their size
        self.assertGreater(gb[0], ga[0])

    def test_fit_of_box(self):
        body = """
const el = (ow, oh, kids) => ({offsetWidth: ow, offsetHeight: oh, clientWidth: 1, clientHeight: 1, querySelector: s => kids[s] || null});
const top = el(900, 120, {}), bar = el(900, 25, {}), am = el(1000, 700, {'.archtop': top, '.archdg .mmdbar': bar});
const box = el(0, 0, {'.archmap': am}), tiny = el(0, 0, {'.archmap': el(300, 200, {'.archtop': top})});
process.stdout.write(JSON.stringify([archFitOf(box), archFitOf(tiny), archFitOf(el(0, 0, {})), archFitOf(null)]));
"""
        fit, tiny, none, nul = run(body)
        self.assertEqual(fit, {"w": 940, "h": 480})             # offset sizes minus chrome, 20px buckets (scrollbars ignored)
        self.assertIsNone(tiny)
        self.assertIsNone(none)
        self.assertIsNone(nul)

    def test_focus_fit_quality(self):
        # Hub of the self map at the three desktop room sizes: grows to the room, boxHits 0, no new label overlaps.
        mods = [{"id": m, "name": n, "kind": "external" if m.startswith("ext.") else "module"} for m, n in SELF_MODS]
        edges = [{"from": f, "to": t, "ok": bool(ok), "est": bool(est)} for f, t, ok, est in SELF_EDGES]
        body = ("const M = " + json.dumps(mods) + ", E = " + json.dumps(edges) + ", _L = mmdLayout; let Q = null, S = null;\n"
                "mmdLayout = g => { const L = _L(g); Q = g; S = L; return L; };\n"
                "const deg = {}; E.forEach(e => { deg[e.from] = (deg[e.from] || 0) + 1; deg[e.to] = (deg[e.to] || 0) + 1; });\n"
                "const si = M.reduce((b, m, i) => (deg[m.id] || 0) > (deg[M[b].id] || 0) ? i : b, 0), sel = M[si].id;\n"
                "const one = fit => { const h = archMmd(archSrc(M, E, false, sel), M, si, null, fit); return {w: S.w, h: S.h, q: mmdQuality(Q, S), fit: !!Q.fit, h1: h.length > 0, rf: JSON.stringify(Q.rankFix || null), rk: rk()}; };\n"
                "const rk = () => { const c = k => Math.round(S.nodes[k].x + S.nodes[k].w / 2), xs = [...new Set(Object.keys(S.nodes).map(c))].sort((a, b) => a - b);"
                " const o = {}; Object.keys(S.nodes).sort().forEach(k => { o[k] = xs.indexOf(c(k)); }); return o; };\n"
                "const ov = fit => { archMmd(archSrc(M, E, false, ''), M, '', null, fit); return [S.w, S.h, !!Q.fit]; };\n"
                "process.stdout.write(JSON.stringify([ERR, one(null), [[560, 260], [900, 800], [1400, 1100]].map(([w, h]) => [w, h, one({w, h})]), ov(null), ov({w: 3000, h: 3000})]));\n")
        err, base, fits, o0, o1 = run(body)
        self.assertIsNone(err)
        self.assertEqual(base["q"]["boxHits"], 0)
        for w, h, r in fits:
            self.assertTrue(r["fit"])
            self.assertEqual(r["q"]["boxHits"], 0, (w, h))
            self.assertLessEqual(r["q"]["labelOverlaps"], base["q"]["labelOverlaps"], (w, h))
            self.assertGreaterEqual(r["h"], base["h"])
            self.assertEqual([r["rf"], r["rk"]], [base["rf"], base["rk"]], (w, h))   # same ranks with and without fit
            self.assertLessEqual(r["h"], max(base["h"], h + 16) + 24, (w, h))   # room + RP margins; never far past the box
        self.assertGreater(fits[2][2]["h"], base["h"])
        self.assertEqual(o0, o1[:2] + [False])                  # overview ignores fit


if __name__ == "__main__":
    unittest.main()
