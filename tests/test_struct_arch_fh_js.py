"""84j9 focus view as HTML rows (R5/R6): only hub edges (plus a lit flow's numbered steps) are drawn, rows by band and step order,
orthogonal connectors in row gaps / side gutters with no box hits, every agent string through esc(). No live data, no DOM."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e
from tests.test_structure_mermaid_js import PRE as MPRE, FNS as MFNS, ROUTER
from tests.test_struct_arch_focus_js import _hub, _real, FLOWS

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
_rd = lambda *p: open(os.path.join(WEB, *p), encoding="utf-8").read()
L2, FOC, FH = _rd("js", "84j2-structure-arch-layers.js"), _rd("js", "84j4-structure-arch-focus.js"), _rd("js", "84j9-structure-arch-focus-html.js")

# Flex-wrap stand-in for the 79f CSS: label column 92, side gutters gw, boxes mmdTw + 26 wide (cap 220) x 30, column gap 24,
# band gap max(28, need), sub-row gap max(14, need); laid out twice so the gaps follow archFhPaths need (as archFhRoute does).
LAY = r"""
const lay = (F, W, need, gw) => { const rects = {}, rows = [], C = ARCH_FH; let y = Math.max(C.SUB, need[0] || 0), g = 0;
  F.rows.forEach((r, bi) => { const x0 = 92 + gw[0], room = W - x0 - gw[1], subs = [[]]; let used = 0;
    if(bi) y += Math.max(C.ROW, need[g] || 0);
    r.ks.forEach(k => { const w = Math.min(220, mmdTw(k) + 26); if(subs[subs.length - 1].length && used + 24 + w > room){ subs.push([]); used = 0; }
      used += (subs[subs.length - 1].length ? 24 : 0) + w; subs[subs.length - 1].push([k, w]); });
    subs.forEach((s, si) => { if(si) y += Math.max(C.SUB, need[g] || 0);
      const tw = s.reduce((a, q) => a + q[1], 0) + 24 * (s.length - 1); let x = x0 + (room - tw) / 2;
      s.forEach(([k, w]) => { rects[k] = { x, y, w, h: 30 }; x += w + 24; }); rows.push(s.map(q => q[0])); y += 30; g++; }); });
  return { rects, rows }; };
const route = (F, W) => { let need = [], gw = [16, 16], L = null, R = null;
  for(let i = 0; i < 3; i++){ L = lay(F, W, need, gw); R = archFhPaths(L.rects, L.rows, F.edges.map(e => ({ a: e.a, b: e.b }))); need = R.need; gw = R.gw; }
  return { L, R, q: archFhQuality(R.paths, L.rects) }; };
"""


def run(body, M, E, G, flows=None):
    js = "\n".join([MPRE, "const document = { addEventListener(){} };", "function codeBlock(s){ return s; }", ROUTER] + [js_fn(f) for f in MFNS]
                   + [js_fn(n) for n in ("archIsTest", "archMq", "archPairs", "archReduce", "archRanks", "archFlowEntries")]
                   + [L2, FOC, FH, "const M = " + json.dumps(M) + ", E = " + json.dumps(E) + ", GR = " + json.dumps(G) + ", D = {modules: M, edges: E, flows: "
                      + json.dumps(FLOWS if flows is None else flows) + "};",
                      "const ix = id => 'm' + M.findIndex(m => m.id === id), BP = archBandPlan(D, M, false);"
                      "const plan = (sel, fs, bp) => archFhPlan(archFocusPlanM(M, E, false, sel, archFlowEntries(D, M, false), false, { flows: D.flows, fs }, bp), !bp);",
                      LAY, body])
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


def _dbuser():
    """dbuser-screens shape: 14 modules over 4 bands (api · service · domain · data), hub = service s0, one lit flow of 32 steps."""
    L = [("u%d" % i, "api") for i in range(2)] + [("s%d" % i, "service") for i in range(4)] + [("d%d" % i, "domain") for i in range(4)] \
        + [("t%d" % i, "data") for i in range(4)]
    M = [{"id": i, "name": "%s %s" % (i, "screen-module"), "kind": "store" if l == "data" else "module", "layer": l, "group": "g"} for i, l in L]
    ids, seq, x = [i for i, _ in L], ["u0"], 7
    while len(seq) < 33:   # deterministic walk, never a self step
        x = (x * 1103515245 + 12345) % 2147483648
        n = ids[x % len(ids)]
        if n != seq[-1]:
            seq.append(n)
    st = list(zip(seq, seq[1:]))
    E = [{"from": a, "to": b, "kind": "read" if b.startswith("t") else "call", "ok": True, "est": False, "label": "%s>%s" % (a, b)} for a, b in sorted(set(st))]
    F = [{"id": "f.screen.dbuser", "name": "dbuser", "entry": {"kind": "http", "label": "GET /dbuser"}, "steps": [{"from": a, "to": b, "ok": True} for a, b in st]}]
    return M, E, [{"id": "g", "name": "G"}], F


class ArchFocusHtmlOneZoom(unittest.TestCase):
    def test_no_second_layer_zoom_or_hover(self):
        # Layer zoom is 84j3 archLyZoom only; a 84j9 [data-arz] listener scaled .archfh a second time (compounded zoom).
        self.assertNotIn("data-arz", FH)
        self.assertNotRegex(FH, r"transform\s*[:=]|scale\(")
        self.assertNotIn("ARCH_ZM", FH)
        self.assertNotIn("archZmKeep", FH)
        self.assertNotIn("addEventListener", FH)                               # hover/click handled by 84j

    def test_hex_hub_has_no_clipped_border(self):
        # The [data-on] hub border is cut by the .hx clip-path into slivers at the slanted corners; the hexagon hub drops it.
        import re
        css = _rd("css", "79f-structure-arch-focus-html.css")
        m = re.search(r"\.archfh \.archfh-n\.hx\[data-on\]\{([^}]*)\}", css)
        self.assertIsNotNone(m)
        self.assertIn("border:0", m.group(1))


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchFocusHtml(unittest.TestCase):
    def test_r5_no_flow_only_hub_edges(self):
        M, E, G = _hub()
        r = run("const F = plan('hub', null, BP), ks = [].concat(...F.rows.map(r => r.ks));"
                "process.stdout.write(JSON.stringify([ks, ['far', 'far2', 'pg', 'a0', 'd0'].map(ix), F.edges.every(e => e.a === ix('hub') || e.b === ix('hub'))]));", M, E, G)
        ks, (far, far2, pg, a0, d0), hub_only = r
        for k in (far, far2, pg):
            self.assertNotIn(k, ks)
        self.assertTrue({a0, d0, "ifx"} <= set(ks))
        self.assertTrue(hub_only)

    def test_r5_lit_flow_keeps_its_modules(self):
        M, E, G = _hub()
        r = run("const F = plan('hub', ['f1'], BP), ks = [].concat(...F.rows.map(r => r.ks));"
                "process.stdout.write(JSON.stringify([ks, ['far', 'far2', 'pg'].map(ix), F.rows.map(r => r.ks)]));", M, E, G)
        ks, (far, far2, pg), rows = r
        self.assertIn(far, ks)                                                 # d0 -> far -> pg are numbered steps 3, 4
        self.assertIn(pg, ks)
        self.assertNotIn(far2, ks)                                             # not on the flow, not a neighbour
        self.assertTrue(any(k.startswith("en") for k in rows[0]))              # the flow's entry on the top row

    def test_rows_by_band_then_step_order(self):
        M, E, G = _hub()
        r = run("const F = plan('hub', ['f1'], BP), V = plan('hub', null, null);"
                "process.stdout.write(JSON.stringify([F.rows.map(r => r.b), F.rows.map(r => r.ks), ['a0', 'd0', 'far', 'hub'].map(ix),"
                " V.rows.map(r => [r.b, r.lbl, r.ks.length]), V.rows[1].ks]));", M, E, G)
        bands, rows, (a0, d0, far, hub), v1rows, v1hub = r
        self.assertEqual(bands, sorted(bands))
        dom = next(r for r in rows if d0 in r)
        self.assertEqual(dom[:2], [d0, far])                                   # step 2 before step 3, then the rest
        self.assertEqual(next(r for r in rows if a0 in r)[0], a0)              # step 1 first in its row
        self.assertEqual([x[0] for x in v1rows], [0, 1, 2])                    # v1: callers / hub / callees
        self.assertEqual(v1hub, [hub])
        self.assertEqual(v1rows[0][2], 7)

    def test_html_contract_and_esc(self):
        M, E, G = _hub(n_in=2, n_out=3, n_infra=0)
        M[1]["name"] = '<b>x</b>&"'
        E[0]["label"] = "<img src=x>"
        r = run("const h = archFhHtml(M, E, false, 'hub', GR, archFlowEntries(D, M, false), false, { flows: D.flows, fs: null }, BP);"
                "process.stdout.write(JSON.stringify([h, ix('hub'), ARCH_FOCUS_MEMO.P && ARCH_FOCUS_MEMO.P.sk]));", M, E, G)
        h, hub, memo = r
        self.assertEqual(memo, hub)                                            # archFocusHx reads the memo plan
        self.assertNotIn("<b>x", h)
        self.assertNotIn("<img", h)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", h)
        self.assertIn('data-p="%s" data-kd="module" data-on=1' % hub, h)
        self.assertRegex(h, r'<g class=mmdfe data-f="m\d+" data-t="%s" data-k="call" data-c="in"' % hub)
        self.assertRegex(h, r'data-f="%s" data-t="m\d+" data-k="call" data-c="out"' % hub)
        self.assertIn('<g class="mmdel mmdfl"><rect', h)
        self.assertIn("class=archfh-row data-b=", h)

    def test_paths_fixed_rects(self):
        # row 0: 3 callers · row 1: sibling, hub, sibling · row 2/3: callees wrapped into two sub-rows · far edge row 0 -> row 3 uses a gutter
        r = run(r"""const R = {}, rows = [], put = (ks, y) => { rows.push(ks); ks.forEach((k, i) => { R[k] = { x: 120 + i * 130, y, w: 100, h: 30 }; }); };
put(['c0', 'c1', 'c2'], 20); put(['s0', 'h', 's1'], 100); put(['o0', 'o1', 'o2', 'o3'], 180); put(['o4', 'o5'], 240);
const es = [['c0','h'],['c1','h'],['c2','h'],['s0','h'],['h','s1'],['h','o0'],['h','o1'],['h','o2'],['h','o3'],['h','o4'],['h','o5'],['c0','o5']].map(([a, b]) => ({ a, b }));
let P = archFhPaths(R, rows, es);
const xs = R => Object.keys(R).map(k => R[k]), x0 = Math.min(...xs(R).map(r => r.x)), x1 = Math.max(...xs(R).map(r => r.x + r.w));
const far = P.paths[11].pts, gut = far.some(q => q[0] < x0 || q[0] > x1);
process.stdout.write(JSON.stringify([archFhQuality(P.paths, R), gut, P.paths.every(p => p.pts && p.pts.length >= 2), P.need, P.gw]));""", [], [], [])
        q, gut, all_drawn, need, gw = r
        self.assertEqual(q["boxHits"], 0)
        self.assertEqual(q["overlaps"], 0)
        self.assertLessEqual(q["crossings"], 1)
        self.assertTrue(gut)                                                   # 3 rows apart: side gutter, not through rows 1/2
        self.assertTrue(all_drawn)
        self.assertGreater(need[2], 0)
        self.assertGreater(gw[0] + gw[1], 32)

    def test_lanes_order_a_fan(self):
        # hub fans out to 4 callees right of it: the farther target takes the lane nearer the hub, so no run crosses a stub
        r = run(r"""const R = { h: { x: 0, y: 0, w: 100, h: 30 } }, t = ['a', 'b', 'c', 'd'];
t.forEach((k, i) => { R[k] = { x: 120 + i * 130, y: 100, w: 100, h: 30 }; });
const P = archFhPaths(R, [['h'], t], t.map(b => ({ a: 'h', b })));
process.stdout.write(JSON.stringify([archFhQuality(P.paths, R), P.paths.map(p => p.pts[1][1])]));""", [], [], [])
        q, ys = r
        self.assertEqual(q, {"crossings": 0, "boxHits": 0, "overlaps": 0})
        self.assertEqual(ys, sorted(ys, reverse=True))

    def test_in_and_out_ends_on_one_side_get_own_ports(self):
        # hub's in-edge from s and out-edge to b both end on the hub top: at its centre the shorter stub lay on the longer one
        r = run(r"""const R = { s: { x: 0, y: 0, w: 100, h: 30 }, b: { x: 260, y: 0, w: 100, h: 30 }, h: { x: 130, y: 100, w: 100, h: 30 } };
const P = archFhPaths(R, [['s', 'b'], ['h']], [{ a: 's', b: 'h' }, { a: 'h', b: 'b' }]);
process.stdout.write(JSON.stringify([archFhQuality(P.paths, R), P.paths[0].pts[P.paths[0].pts.length - 1], P.paths[1].pts[0]]));""", [], [], [])
        q, s_end, b_start = r
        self.assertEqual(q, {"crossings": 0, "boxHits": 0, "overlaps": 0})
        self.assertEqual(s_end[1], 100)                                        # both on the hub top
        self.assertEqual(b_start[1], 100)
        self.assertLess(s_end[0], b_start[0])                                  # own ports, ordered by the far end's x

    def test_real_and_dbuser_shapes(self):
        M, E, G, F = _real()
        r = run("const a = route(plan('hub', null, BP), 1100), b = route(plan('hub', ['f4', 'f6'], BP), 1100);"
                "process.stdout.write(JSON.stringify([a.q, b.q, a.L.rows.length]));", M, E, G, F)
        qa, qb, nrows = r
        self.assertEqual(qa["boxHits"], 0)
        self.assertEqual(qb["boxHits"], 0)
        self.assertEqual((qa["overlaps"], qb["overlaps"]), (0, 0))             # one port per end: no stub drawn over another
        self.assertGreater(nrows, 2)
        M, E, G, F = _dbuser()
        r = run("const P = archFocusPlanM(M, E, false, 's0', archFlowEntries(D, M, false), false, { flows: D.flows, fs: ['f.screen.dbuser'] }, BP), F = archFhPlan(P, false);"
                "const n = [].concat(...F.rows.map(r => r.ks)).filter(k => /^m/.test(k)).length, s = route(F, 1100), w = route(F, 900);"
                "process.stdout.write(JSON.stringify([n, F.rows.length, F.edges.length, s.q, w.q, F.rows.map(r => r.ks.length)]));", M, E, G, F)
        n, nb, ne, q1100, q900, per = r
        print("\n  dbuser shape: %d modules, %d rows %s, %d edges -> 1100: %s · 900: %s" % (n, nb, per, ne, q1100, q900))
        self.assertEqual(n, 14)
        self.assertEqual(q1100["boxHits"], 0)
        self.assertEqual(q900["boxHits"], 0)
        self.assertEqual((q1100["overlaps"], q900["overlaps"]), (0, 0))
        self.assertLess(q1100["crossings"], 49)                                # Mermaid on the live case: 49


if __name__ == "__main__":
    unittest.main()
