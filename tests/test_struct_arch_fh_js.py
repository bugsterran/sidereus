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
    (r.sp || [r.ks]).forEach((grp, gi2) => { if(gi2){ subs.push([]); used = 0; }   // r.sp: hub band parts each start a line
      grp.forEach(k => { const w = Math.min(220, mmdTw(k) + 26); if(subs[subs.length - 1].length && used + 24 + w > room){ subs.push([]); used = 0; }
      used += (subs[subs.length - 1].length ? 24 : 0) + w; subs[subs.length - 1].push([k, w]); }); });
    subs.forEach((s, si) => { if(si) y += Math.max(C.SUB, need[g] || 0);
      const tw = s.reduce((a, q) => a + q[1], 0) + 24 * (s.length - 1); let x = x0 + (room - tw) / 2;
      s.forEach(([k, w]) => { rects[k] = { x, y, w, h: 30 }; x += w + 24; }); rows.push(s.map(q => q[0])); y += 30; g++; }); });
  return { rects, rows }; };
const route = (F, W) => { let need = [], gw = [16, 16], L = null, R = null;
  for(let i = 0; i < 3; i++){ L = lay(F, W, need, gw); R = archFhPaths(L.rects, L.rows, F.edges.map(e => ({ a: e.a, b: e.b }))); need = R.need; gw = R.gw; }
  return { L, R, q: archFhQuality(R.paths, L.rects) }; };
"""

# Vertical runs of different paths sharing > 0.5px of height: [count closer than 1px, min x gap]; routeB = route with badged links.
SAME = r"""
const same = P => { const V = P.paths.filter(p => p.pts).map(p => p.pts.slice(1).map((q, j) => [p.pts[j], q]).filter(s => s[0][0] === s[1][0]));
  let n = 0, md = 1e9; for(let i = 0; i < V.length; i++) for(let j = i + 1; j < V.length; j++) V[i].forEach(a => V[j].forEach(b => {
    const lo = Math.max(Math.min(a[0][1], a[1][1]), Math.min(b[0][1], b[1][1])), hi = Math.min(Math.max(a[0][1], a[1][1]), Math.max(b[0][1], b[1][1]));
    if(hi - lo > 0.5){ const d = Math.abs(a[0][0] - b[0][0]); md = Math.min(md, d); if(d < 1) n++; } })); return [n, md]; };
const routeB = (F, W) => { let need = [], gw = [16, 16], L = null, R = null;
  for(let i = 0; i < 3; i++){ L = lay(F, W, need, gw); R = archFhPaths(L.rects, L.rows, F.edges.map(e => ({ a: e.a, b: e.b, k: e.kind, lab: true }))); need = R.need; gw = R.gw; }
  return [archFhQuality(R.paths, L.rects), same(R)]; };
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
        E[1]["label"] = "call hostLinkMode, navigateToPath, apiConfigured"
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
        self.assertIn('<g class="mmdel mmdfl"><title>', h)
        self.assertIn("markerUnits=userSpaceOnUse", h)                         # arrow heads keep their size when lines thicken
        # long step label: badge text cut at 28 chars, the full label stays in the <title>
        self.assertIn("<title>call hostLinkMode, navigateToPath, apiConfigured</title>", h)
        self.assertIn(">call hostLinkMode, navigate…</text>", h)
        self.assertIn("class=archfh-row data-b=", h)

    def test_free_height_spreads_gaps(self):
        # Free height under a short map is split over its row gaps; little room or no gaps keeps the tight layout; capped per gap.
        r = run("console.log(JSON.stringify([archFhGap(0, 3), archFhGap(24, 3), archFhGap(300, 3), archFhGap(900, 3), archFhGap(500, 0)]));", [], [], [])
        self.assertEqual(r, [0, 0, 100, 120, 0])

    def test_badge_steps_off_adjacent_boxes(self):
        # A wide badge on the short link between two neighbours in one row overlapped both boxes; it now ends clear of every box.
        # A badge with room on its run keeps the spot it had before.
        r = run("const A = {x: 100, y: 50, w: 80, h: 30}, B = {x: 204, y: 50, w: 80, h: 30}, w = 44;"
                "const ov = (p, R) => p.lx - w / 2 < R.x + R.w && p.lx + w / 2 > R.x && p.ly - 9 < R.y + R.h && p.ly + 9 > R.y;"
                "const p = {pts: [[180, 65], [204, 65]], lx: 192, ly: 65, bs: [180, 204]}; archFhBadge(p, w, [], [A, B]);"
                "const q = {pts: [[0, 200], [300, 200]], lx: 150, ly: 200, bs: [0, 300]}; archFhBadge(q, w, [], [A, B]);"
                "console.log(JSON.stringify([ov(p, A) || ov(p, B), p.lx, q.lx, q.ly]));", [], [], [])
        self.assertEqual(r, [False, 192, 150, 200])

    def test_css_hit_and_open_arrowhead(self):
        # The no-layers focus (.archly) hit paths and the open arrowhead rendered filled black without these rules.
        css = _rd("css", "79-structure-arch.css")
        self.assertRegex(css, r"\.archly \.mmdhit[^{]*\{fill:none")
        self.assertRegex(css, r"\.mmdaho\{fill:none;stroke:var\(--mmd-ln\)")

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

    def test_hub_band_splits_callers_hub_callees(self):
        # one band holding hub, callers, callees and a two-way neighbour: three lines, callers above, hub alone, the rest below
        L = ["hub", "c0", "c1", "c2", "e0", "e1", "e2", "t0"]
        M = [{"id": i, "name": "%s wizard" % i, "kind": "module", "layer": "service", "group": "g"} for i in L]
        E = [("c0", "hub"), ("c1", "hub"), ("c2", "hub"), ("hub", "e0"), ("hub", "e1"), ("hub", "e2"), ("hub", "t0"), ("t0", "hub"), ("c0", "e2")]
        E = [{"from": f, "to": t, "kind": "call", "ok": True, "est": False, "label": "%s.%s" % (f, t)} for f, t in E]
        r = run("const F = plan('hub', null, BP), U1 = { rows: F.rows.map(r => ({ b: r.b, ks: r.ks })), edges: F.edges };"
                "const s = route(F, 1100), u = route(U1, 1100), hr = F.rows.find(r => r.sp);"
                "process.stdout.write(JSON.stringify([hr.sp, ['hub', 'c0', 'c1', 'c2', 'e0', 'e1', 'e2', 't0'].map(ix), s.q, u.q, archFhHtml(M, E, false, 'hub', [], [], null, null, BP).includes('archfh-bx sp')]));",
                M, E, [{"id": "g", "name": "G"}], [])
        sp, (hub, c0, c1, c2, e0, e1, e2, t0), q, q1, html_sp = r
        self.assertEqual(sorted(sp[0]), sorted([c0, c1, c2]))                 # callers only above (c0 also calls e2: still a caller)
        self.assertEqual(sp[1], [hub])
        self.assertEqual(sorted(sp[2]), sorted([e0, e1, e2, t0]))             # callees and two-way below
        self.assertEqual((q["overlaps"], q["boxHits"]), (0, 0))
        self.assertLessEqual(q["crossings"], q1["crossings"])                 # never worse than the single line
        self.assertTrue(html_sp)

    def test_stacked_boxes_link_straight(self):
        # a sits over h (adjacent rows): a straight vertical, no bend; f is off to the side and still bends
        r = run(r"""const R = { a: { x: 100, y: 0, w: 100, h: 30 }, f: { x: 400, y: 0, w: 100, h: 30 }, h: { x: 80, y: 100, w: 160, h: 30 } };
const P = archFhPaths(R, [['a', 'f'], ['h']], [{ a: 'a', b: 'h' }, { a: 'f', b: 'h' }]);
process.stdout.write(JSON.stringify([archFhQuality(P.paths, R), P.paths.map(p => p.pts)]));""", [], [], [])
        q, (pa, pf) = r
        self.assertEqual(len(pa), 2)
        self.assertEqual(pa[0][0], pa[1][0])
        self.assertEqual(len(pf), 4)
        self.assertEqual((q["overlaps"], q["boxHits"]), (0, 0))

    def test_bundle_three_plus_same_kind(self):
        # 4 calls into the hub top merge on one run into one trunk; 2 reads stay separate (fewer than 3, other kind)
        r = run(r"""const R = { h: { x: 400, y: 100, w: 160, h: 30 } }, ks = ['c0', 'c1', 'c2', 'c3', 'r0', 'r1'];
ks.forEach((k, i) => { R[k] = { x: i * 150, y: 0, w: 120, h: 30 }; });
const es = ks.map(k => ({ a: k, b: 'h', k: k[0] === 'c' ? 'call' : 'read' })), P = archFhPaths(R, [ks, ['h']], es);
process.stdout.write(JSON.stringify([archFhQuality(P.paths, R), P.paths.map(p => [p.pts[p.pts.length - 1], p.pts.length > 2 ? p.pts[p.pts.length - 2][1] : null, p.bd || null])]));""", [], [], [])
        q, ends = r
        calls, reads = ends[:4], ends[4:]
        self.assertEqual(len({tuple(e[0]) for e in calls}), 1)                 # one trunk, one arrow head
        self.assertEqual(len({e[1] for e in calls if e[1] is not None}), 1)     # one shared run
        self.assertTrue(all(e[2] for e in calls))
        self.assertEqual(len({tuple(e[0]) for e in reads}), 2)                 # not bundled
        self.assertFalse(any(e[2] for e in reads))
        self.assertEqual((q["overlaps"], q["boxHits"]), (0, 0))               # a bundle's own shared run is not an overlap

    def test_badged_hub_ends_get_own_vertical_runs(self):
        # a lit flow badges every link: a bundle trunk at the hub stacked its badges in pairs beside the trunk. Badged links never bundle,
        # each end has its own port inside its box, and no two paths share (or nearly share) a vertical run.
        r = run(SAME + r"""const R = { h: { x: 400, y: 100, w: 160, h: 30 } }, up = ['a0', 'a1'], dn = ['b0', 'b1', 'b2', 'b3', 'b4', 'b5', 'b6', 'b7'];
up.forEach((k, i) => { R[k] = { x: 250 + i * 300, y: 0, w: 120, h: 30 }; });
dn.forEach((k, i) => { R[k] = { x: 20 + i * 130, y: 200, w: 110, h: 30 }; });
const es = up.map(k => ({ a: k, b: 'h', k: 'call' })).concat(dn.map(k => ({ a: 'h', b: k, k: 'call' })), [{ a: 'b2', b: 'h', k: 'call' }]);
const P = archFhPaths(R, [up, ['h'], dn], es.map(e => Object.assign({ lab: true }, e))), B = archFhPaths(R, [up, ['h'], dn], es);
const inside = P.paths.every(p => { const s = p.pts[0], t = p.pts[p.pts.length - 1];
  return s[0] >= R[p.a].x && s[0] <= R[p.a].x + R[p.a].w && t[0] >= R[p.b].x && t[0] <= R[p.b].x + R[p.b].w; });
process.stdout.write(JSON.stringify([archFhQuality(P.paths, R), same(P), inside, P.paths.some(p => p.bd), same(B)]));""", [], [], [])
        q, (n, md), inside, bundled, (nb, _) = r
        print("\n  badged hub: crossings %d, shared vertical runs %d (bundled: %d), min gap %.1fpx" % (q["crossings"], n, nb, md))
        self.assertEqual(n, 0)
        self.assertGreaterEqual(md, 6)
        self.assertTrue(inside)
        self.assertFalse(bundled)
        self.assertGreater(nb, 0)                                              # unbadged links still bundle into one trunk
        self.assertEqual((q["boxHits"], q["overlaps"]), (0, 0))

    def test_badged_shapes_no_more_crossings(self):
        # ★before (bundles + sibling-blind nudge): fixed 1 crossing / 9 shared runs, dbuser 30 / 0 (min gap 3.6px), real lit 31 / 67
        r = run(SAME + r"""const R = {}, rows = [], put = (ks, y) => { rows.push(ks); ks.forEach((k, i) => { R[k] = { x: 120 + i * 130, y, w: 100, h: 30 }; }); };
put(['c0', 'c1', 'c2'], 20); put(['s0', 'h', 's1'], 100); put(['o0', 'o1', 'o2', 'o3'], 180); put(['o4', 'o5'], 240);
const es = [['c0','h'],['c1','h'],['c2','h'],['s0','h'],['h','s1'],['h','o0'],['h','o1'],['h','o2'],['h','o3'],['h','o4'],['h','o5'],['c0','o5']].map(([a, b]) => ({ a, b, lab: true }));
const P = archFhPaths(R, rows, es); process.stdout.write(JSON.stringify([archFhQuality(P.paths, R), same(P)]));""", [], [], [])
        M, E, G, F = _dbuser()
        d = run(SAME + "const F = archFhPlan(archFocusPlanM(M, E, false, 's0', archFlowEntries(D, M, false), false, { flows: D.flows, fs: ['f.screen.dbuser'] }, BP), false);"
                "process.stdout.write(JSON.stringify([1100, 900].map(W => routeB(F, W))));", M, E, G, F)
        M, E, G, F = _real()
        e = run(SAME + "process.stdout.write(JSON.stringify(routeB(plan('hub', ['f4', 'f6'], BP), 1100)));", M, E, G, F)
        print("\n  after: fixed %s · dbuser %s · real lit %s" % (r, d, e))
        self.assertLessEqual(r[0]["crossings"], 1)
        self.assertEqual(r[1][0], 0)
        for q, (n, md) in d:
            self.assertLessEqual(q["crossings"], 30)
            self.assertEqual((n, q["boxHits"], q["overlaps"]), (0, 0, 0))
            self.assertGreaterEqual(md, 3)
        self.assertLessEqual(e[0]["crossings"], 31)
        self.assertEqual((e[1][0], e[0]["boxHits"]), (0, 0))

    def test_two_way_edges_draw_two_lines(self):
        # h <-> b (rows apart) and h <-> n (neighbours): each direction is its own line, never drawn on its reverse
        r = run(r"""const R = { b: { x: 260, y: 0, w: 100, h: 30 }, h: { x: 130, y: 100, w: 100, h: 30 }, n: { x: 260, y: 100, w: 100, h: 30 } };
const P = archFhPaths(R, [['b'], ['h', 'n']], [{ a: 'h', b: 'b' }, { a: 'b', b: 'h' }, { a: 'h', b: 'n' }, { a: 'n', b: 'h' }]);
process.stdout.write(JSON.stringify([archFhQuality(P.paths, R), P.paths.map(p => p.pts)]));""", [], [], [])
        q, pts = r
        self.assertEqual(q["overlaps"], 0)
        self.assertNotEqual(pts[0], list(reversed(pts[1])))
        self.assertNotEqual(pts[2], list(reversed(pts[3])))
        self.assertEqual(pts[2][0][1] + 10, pts[3][0][1])                      # neighbours split by 2 * RV

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
