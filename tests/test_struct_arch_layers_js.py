"""84j2 layer bands on the Architecture map (R1-R4): band order and ranks, group/external boxes, edge kinds (data-k),
pass-through bands with no box hit, and the v1 path unchanged with its «No layers» notice. Real 81e/81f/81g0/81g renderer."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import js_fn, sidereus
from tests._node import node_e
from tests.test_struct_arch_js import run, MODS, EDGES
from tests.test_structure_mermaid_js import PRE as MPRE, FNS as MFNS, ROUTER

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
L2 = open(os.path.join(WEB, "js", "84j2-structure-arch-layers.js"), encoding="utf-8").read()
CSS = open(os.path.join(WEB, "css", "79-structure-arch.css"), encoding="utf-8").read()

# entry -> api -> service -> data with an entry -> data edge that skips two bands; two externals (db, api).
M = [{"id": "http", "name": "HTTP", "kind": "entry", "ext": "http", "layer": "entry", "group": "io"},
     {"id": "cli", "name": "CLI", "kind": "entry", "ext": "cli", "layer": "entry", "group": "io"},
     {"id": "routes", "name": "Routes", "kind": "module", "layer": "api", "group": "core"},
     {"id": "svc", "name": "Service", "kind": "module", "layer": "service", "group": "core"},
     {"id": "svc2", "name": "Jobs", "kind": "module", "layer": "service", "group": "evil"},
     {"id": "pg", "name": "Postgres", "kind": "store", "ext": "db", "layer": "data", "group": "io"},
     {"id": "x1", "name": "libpq", "kind": "external", "ext": "db", "layer": "data", "group": "io"},
     {"id": "x2", "name": "Stripe", "kind": "external", "ext": "api", "layer": "infra", "group": "io"}]
G = [{"id": "io", "name": "I/O"}, {"id": "core", "name": "Core"}, {"id": "evil", "name": "<b>Evil</b>"}]
E = [[f, t, k] for f, t, k in [("http", "routes", "serve"), ("cli", "pg", "write"), ("routes", "svc", "call"), ("svc", "pg", "read"),
                                ("svc", "pg", "write"), ("svc", "svc2", "event"), ("routes", "svc2", "event"), ("routes", "svc2", "call"),
                                ("routes", "pg", "read"), ("svc", "x1", "import"), ("svc2", "x2", "call")]]
E = [{"from": f, "to": t, "kind": k, "ok": True, "est": False, "label": ""} for f, t, k in E]


def render(body):
    js = "\n".join([MPRE, "const MMD_BUDGET = 1e9, MMD_UNCROSS = 1e9, ARCH_DIR = 'TB'; let ERR = null; function softErr(t, e){ ERR = String(e); }",
                    "function codeBlock(s){ return s; }", ROUTER] + [js_fn(f) for f in MFNS]
                   + [js_fn(n) for n in ("archIsTest", "archMq", "archPairs", "archReduce", "archSrc", "archRanks", "archMmd")] + [L2,
                   "const M = " + json.dumps(M) + ", E = " + json.dumps(E) + ", GR = " + json.dumps(G) + ";", body])
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


# 84k entry nodes without its dictionary const: archFlowKind falls back to the raw kind.
ENT = js_fn("archFlowEntries") + "\n"
BANDED = ("const src = archBandSrc(M, E, false, true, GR), g = mmdParse(src); archBandFix(g); const L = mmdLayout(g);"
          "const svg = archMmd(src, M, '', archKindMap(M, E, false));")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchLayers(unittest.TestCase):
    def test_layer_list_matches_schema(self):
        # drift: the page's band order covers exactly the schema's layers
        names = set(re.search(r"^const ARCH_LAYERS = \[(.*?)\];", L2, re.M).group(1).replace("'", "").replace(" ", "").split(","))
        self.assertEqual(names, set(sidereus("arch_schema").LAYERS))

    def test_r1_bands_ordered_by_layer(self):
        r = render(BANDED + "const bs = g.slist.filter(s => !g.sgs[s].parent);"
                   "process.stdout.write(JSON.stringify([ERR, bs, g.rankFix, bs.map(s => L.sgs[s].y), bs.map(s => g.sgs[s].pass), mmdQuality(g, L)]));")
        err, bands, fix, ys, passes, q = r
        self.assertIsNone(err)
        self.assertEqual(bands, ["L0", "L2", "L3", "L7", "Lx"])   # non-empty layers in ARCH_LAYERS order, externals last
        self.assertEqual(fix["L0"], 0)                                    # entry on top
        self.assertEqual(fix["L7"], max(v for k, v in fix.items() if k != "Lx"))   # data is the last layer band
        self.assertEqual(fix["Lx"], len(bands) - 1)
        self.assertEqual(ys, sorted(ys))                                  # bands drawn top to bottom in that order
        self.assertTrue(all(passes))
        self.assertEqual(q["boxHits"], 0)                                 # R3: cli -> pg skips two bands, never through a box

    def test_r2_groups_and_externals(self):
        r = render(BANDED + "const par = k => g.sgs[g.nodes[k].sg]; process.stdout.write(JSON.stringify(["
                   "par('m3').parent, par('m3').title, par('m4').title, par('m0').parent, g.slist.filter(s => g.sgs[s].parent === 'Lx').map(s => g.sgs[s].title),"
                   "par('m6').parent, svg.indexOf('<b>') < 0 && svg.indexOf('&lt;b&gt;Evil') >= 0, g.sgs[g.nodes.m3.sg].cls, g.sgs.L3.cls]));")
        self.assertEqual(r[0], "L3")                       # group box inside its layer band
        self.assertEqual(r[1:3], ["Core", "<b>Evil</b>"])  # group names as given (decoded), never translated
        self.assertEqual(r[3], "L0")
        self.assertEqual(r[4], ["db", "api"])              # one box per ext; the module's group is ignored
        self.assertEqual(r[5], "Lx")
        self.assertTrue(r[6])                              # escaped in the SVG
        self.assertEqual(r[7:], ["archgrp", "archband"])

    def test_r3_edge_kinds(self):
        r = render(BANDED + "const k = (a, b) => (svg.match(new RegExp('data-k=\"(\\\\w+)\" data-f=\"' + a + '\" data-t=\"' + b + '\"')) || [])[1] || '';"
                   "process.stdout.write(JSON.stringify([k('m3', 'm5'), k('m2', 'm5'), k('m3', 'm4'), k('m2', 'm4'), k('m0', 'm2'), k('m3', 'm6'), k('m1', 'm5')]));")
        # read+write -> write, read, event only, event+call -> call, serve/import -> call, write
        self.assertEqual(r, ["write", "read", "event", "call", "call", "call", "write"])
        for k in ("read", "write"):
            self.assertRegex(CSS, r"\.archmap \.mmdfe\[data-k=" + k + r"\] \.mmde\{stroke:var\(--(?!nx-ok|nx-info)")
        self.assertIn(".archmap .mmdfe[data-k=event] .mmde{stroke-dasharray:9 4}", CSS)
        # kind colours sit before the focus/hover rules, so in/out still win at equal specificity
        self.assertLess(CSS.index("[data-k=read]"), CSS.index(".archmap .mmdfe[data-c=in] .mmde"))

    def test_band_group_row_levels(self):
        # band / group / entry row each get their own fill; a 5% band fill measured 1.04:1 on the dark page
        pct = lambda cls: int(re.search(r"\.archmap \.mmdsg\." + cls + r">rect\{fill:color-mix\(in srgb,var\([^)]*\) (\d+)%", CSS).group(1))
        self.assertGreaterEqual(pct("archband"), 10)
        self.assertGreaterEqual(pct("archgrp"), 8)
        self.assertGreaterEqual(pct("archerow"), 6)
        self.assertRegex(CSS, r"\.archmap \.mmdsg\.archgrp>rect\{[^}]*stroke:color-mix\(in srgb,var\(--nx-info")

    def test_r3_legend(self):
        r = run("console.log(JSON.stringify([archLegHtml(), archLegHtml(true), archLegHtml(true, true)]));")
        self.assertNotIn("data-k", r[0])
        self.assertNotIn('data-k="uses"', r[1])                         # «Uses» only when a uses edge is drawn
        self.assertIn('data-k="uses"', r[2])
        self.assertIn("사용", r[2])
        for k, ko in (("call", "호출"), ("read", "읽기"), ("write", "쓰기"), ("event", "이벤트")):
            self.assertIn('data-k="' + k + '"', r[1])
            self.assertIn(ko, r[1])

    def test_r4_v1_unchanged_with_notice(self):
        v1 = {"ok": True, "commit": "c1", "modules": MODS, "edges": EDGES}
        v2 = {"ok": True, "commit": "c2", "v": 2, "groups": G, "modules": M, "edges": E}
        r = run("const S = []; globalThis.archMmd = (src, mods, si, kinds) => { S.push([src, kinds || null]); return '<M/>'; };"
                "const box = {innerHTML: '', querySelector(){ return null; }}, H = [];"
                "for(const d of [" + json.dumps(v1) + ", " + json.dumps(v2) + "]){ ARCH.cache['/r'] = d; ARCH.svg = {}; box._arsig = ''; archPaint(box, head); H.push(box.innerHTML); }"
                "await new Promise(f => setTimeout(f, 20));"
                "console.log(JSON.stringify([H, S, archSrc(" + json.dumps(MODS) + ", " + json.dumps(EDGES) + ", false, '', false), archHasLayers({v: 2, modules: [{id: 'a'}]})]));")
        html, calls, v1src, part = r
        self.assertIn("archnol", html[0])
        self.assertIn("층 정보 없음", html[0])
        self.assertNotIn("archnol", html[1])
        self.assertEqual(calls[0], [v1src, None])          # v1: same archSrc, no kinds -> no data-k
        self.assertIn("subgraph L0[", calls[1][0])
        self.assertTrue(calls[1][1])
        self.assertFalse(part)                             # v2 with a layerless module draws the v1 way

    def test_tag_mode_skips_mmdlabels_same_svg(self):
        # archMmd sets g.flLabels: mmdLabels is never called and the tag-mode SVG is byte-identical to running it.
        from tests.test_struct_arch_js import SELF_MODS, SELF_EDGES
        sm = [{"id": m, "name": n, "kind": "external" if m.startswith("ext.") else "module"} for m, n in SELF_MODS]
        se = [{"from": f, "to": t, "ok": bool(ok), "est": bool(est)} for f, t, ok, est in SELF_EDGES]
        r = render("const SM = " + json.dumps(sm) + ", SE = " + json.dumps(se) + ", _lab = mmdLabels, _lay = mmdLayout; let N = 0, keep = false;"
                   "mmdLabels = (g, L) => { N++; return _lab(g, L); }; mmdLayout = g => { if(keep) delete g.flLabels; return _lay(g); };"
                   "const both = f => { keep = false; N = 0; const a = f(), n = N; keep = true; const b = f(); return [a === b, n, N > 0]; };"
                   "process.stdout.write(JSON.stringify([both(() => archMmd(archBandSrc(M, E, false, true, GR), M, '', archKindMap(M, E, false))),"
                   " both(() => archMmd(archSrc(SM, SE, false, '', true), SM, '')), both(() => archMmd(archSrc(SM, SE, true, 'routes'), SM, 1)), ERR,"
                   " (() => { N = 0; mmdBlock('flowchart TB\\n a -->|x| b'); return N; })()]));")
        self.assertEqual(r[:3], [[True, 0, True]] * 3)    # same bytes, 0 calls in tag mode (and the check really ran it)
        self.assertIsNone(r[3])
        self.assertEqual(r[4], 1)                         # md preview (non-tag) still places labels

    def test_R1_entry_nodes_in_L0_with_edge(self):
        fl = [{"id": "f1", "entry": {"kind": "http", "label": "GET /x"}, "steps": [{"from": "routes", "to": "svc"}]},
              {"id": "f2", "entry": {"kind": "mcp", "label": "<tool>"}, "steps": [{"from": "svc", "to": "pg"}]}]
        r = render(ENT + "const D = {flows: " + json.dumps(fl) + "}, en = archFlowEntries(D, M, false), src = archBandSrc(M, E, false, true, GR, en);"
                   "const km = archKindMap(M, E, false, en), g = mmdParse(src); archBandFix(g); const L = mmdLayout(g), svg = archMmd(src, M, '', km);"
                   "process.stdout.write(JSON.stringify([ERR, en.map(e => [e.k, e.kind, e.label, [...e.to], e.flows]), g.sgs[g.nodes.en0.sg].parent + '/' + g.nodes.en0.sg, g.sgs[g.nodes.en1.sg].parent + '/' + g.nodes.en1.sg, g.nodes.en0.shape,"
                   " g.nodes.en1.label, g.edges.filter(e => e.from.startsWith('en')).map(e => [e.from, e.to]), km['en0\\u0001m2'], svg.indexOf('data-p=\"en0\"') >= 0,"
                   " /data-k=\"entry\" data-f=\"en1\" data-t=\"m3\"/.test(svg), svg.indexOf('&lt;tool&gt;') >= 0 && svg.indexOf('<tool>') < 0, mmdQuality(g, L)]));")
        err, ents, sg0, sg1, shape, lab1, eds, kind, drawn, kedge, escd, q = r
        self.assertIsNone(err)
        self.assertEqual(ents, [["en0", "http", "GET /x", [2], ["f1"]], ["en1", "mcp", "<tool>", [3], ["f2"]]])
        self.assertEqual([sg0, sg1, shape], ["L0/Ek0r0", "L0/Ek5r0", "hex"])   # entry band, one row per kind (http 0, mcp 5)
        self.assertEqual(lab1, "<tool>")                            # the row names the kind; label decoded, never T()
        self.assertEqual(eds, [["en0", "m2"], ["en1", "m3"]])
        self.assertEqual(kind, "entry")
        self.assertTrue(drawn and kedge and escd)
        self.assertEqual(q["boxHits"], 0)                           # normal router path: no box crossings

    def test_entry_paired_with_entry_module_draws_once(self):
        # f1 starts at the http entry module (same way in): one hexagon m0, no en0 node, no en0 -> m0 edge; f2 stays a hexagon en1
        fl = [{"id": "f1", "entry": {"kind": "http", "label": "GET /x (Ctl)"}, "steps": [{"from": "http", "to": "routes"}]},
              {"id": "f2", "entry": {"kind": "job", "label": "nightly"}, "steps": [{"from": "svc", "to": "pg"}]}]
        r = render(ENT + "const en = archFlowEntries({flows: " + json.dumps(fl) + "}, M, false), src = archBandSrc(M, E, false, true, GR, en);"
                   "const g = mmdParse(src); archBandFix(g); const L = mmdLayout(g), svg = archMmd(src, M, '', archKindMap(M, E, false, en));"
                   "process.stdout.write(JSON.stringify([ERR, g.nlist.filter(k => /^en/.test(k)), g.nodes.m0.shape, g.nodes.m0.label, g.nodes.m0.sg, g.nodes.m1.shape,"
                   " g.nodes.en1.shape, g.edges.filter(e => /^en/.test(e.from)).map(e => [e.from, e.to]), g.edges.some(e => e.from === 'm0' && e.to === 'm2'),"
                   " svg.indexOf('data-p=\"m0\"') >= 0, mmdQuality(g, L).boxHits]));")
        err, ens, shape, lab, sg, shape1, shape_en, eds, serve, click, hits = r
        self.assertIsNone(err)
        self.assertEqual(ens, ["en1"])                       # paired entry: no separate node
        self.assertEqual([shape, lab, sg, shape1], ["hex", "HTTP", "Ek0r0", "rect"])   # module takes the hexagon, keeps its name and kind row
        self.assertEqual(shape_en, "hex")                    # unpaired entry unchanged
        self.assertEqual(eds, [["en1", "m3"]])               # no hexagon -> box edge for the pair
        self.assertTrue(serve and click)                     # serve edge from the single node, module click target kept
        self.assertEqual(hits, 0)

    def test_R1_same_kind_label_dedupes(self):
        nm = [m for m in M if m["layer"] != "entry"] + [{"id": "t1", "name": "tests", "kind": "test", "layer": "shared"}]
        fl = [{"id": "a", "entry": {"kind": "http", "label": "GET /x"}, "steps": [{"from": "routes", "to": "svc"}]},
              {"id": "b", "entry": {"kind": "http", "label": "GET /x"}, "steps": [{"from": "svc", "to": "pg"}]},
              {"id": "c", "entry": {"kind": "http", "label": "GET /y"}, "steps": [{"from": "gone", "to": "svc"}]},
              {"id": "d", "entry": {"kind": "cli", "label": "run"}, "steps": [{"from": "t1", "to": "svc"}]},
              {"id": "e", "entry": {}, "steps": [{"from": "svc", "to": "pg"}]}, {"id": "f", "entry": {"kind": "job", "label": "j"}, "steps": []}]
        r = render(ENT + "const N = " + json.dumps(nm) + ", D = {flows: " + json.dumps(fl) + "}, en = archFlowEntries(D, N, false), et = archFlowEntries(D, N, true);"
                   "const src = archBandSrc(N, E, false, true, GR, en);"
                   "process.stdout.write(JSON.stringify([en.map(e => [e.k, e.label, [...e.to], e.flows]), et.map(e => e.flows), src.indexOf('subgraph L0[') >= 0]));")
        self.assertEqual(r[0], [["en0", "GET /x", [0, 1], ["a", "b"]]])   # one node, two first modules; missing / hidden / no entry skipped
        self.assertEqual(r[1], [["a", "b"], ["d"]])                       # tests on: the test module's flow counts
        self.assertTrue(r[2])                                             # no entry-layer module: L0 made for the entry nodes

    def test_R1_long_entry_label_cut(self):
        long = "hooks/invite_notice.py (SessionStart/UserPromptSubmit)"
        fl = [{"id": "a", "entry": {"kind": "event", "label": long}, "steps": [{"from": "routes", "to": "svc"}]},
              {"id": "b", "entry": {"kind": "http", "label": "x" * 24}, "steps": [{"from": "svc", "to": "pg"}]}]
        r = render(ENT + "const en = archFlowEntries({flows: " + json.dumps(fl) + "}, M, false), g = mmdParse(archBandSrc(M, E, false, true, GR, en));"
                   "process.stdout.write(JSON.stringify([g.nodes.en0.label, g.nodes.en1.label, en[0].label]));")
        self.assertEqual(r[0], long[:23].rstrip() + "…")       # 24 chars max in the node
        self.assertEqual(r[1], "x" * 24)                       # exactly 24: kept whole
        self.assertEqual(r[2], long)                            # entry data keeps the full label

    def test_R5_no_flows_bytes_unchanged(self):
        r = render(ENT + "const a = archBandSrc(M, E, false, true, GR), k = JSON.stringify(archKindMap(M, E, false));"
                   "process.stdout.write(JSON.stringify([a === archBandSrc(M, E, false, true, GR, null), a === archBandSrc(M, E, false, true, GR, []),"
                   " k === JSON.stringify(archKindMap(M, E, false, [])), archFlowEntries({}, M, false).length, archFlowEntries({flows: []}, M, false).length, a.indexOf('{{') < 0]));")
        self.assertEqual(r, [True, True, True, 0, 0, True])

    def _flows(self, n):
        return [{"id": "f%d" % i, "entry": {"kind": "http", "label": "GET /p%d" % i}, "steps": [{"from": ("routes", "svc", "pg")[i % 3], "to": "svc"}]}
                for i in range(n)]

    def _kinds(self, n_http, via=0):
        # http x n + job + hook entries; M keeps its two entry modules (http, cli exts) in group «io»
        # via: that many extra http entries start at the http entry module, an edge between two L0 rows
        fl = self._flows(n_http) + [{"id": "v%d" % i, "entry": {"kind": "http", "label": "POST /v%d" % i}, "steps": [{"from": "http", "to": "routes"}]}
                                    for i in range(via)] + [{"id": "j", "entry": {"kind": "job", "label": "nightly"}, "steps": [{"from": "svc", "to": "pg"}]},
                                    {"id": "k", "entry": {"kind": "hook", "label": "pre-commit"}, "steps": [{"from": "routes", "to": "svc"}]}]
        return render(ENT + "const en = archFlowEntries({flows: " + json.dumps(fl) + "}, M, false), src = archBandSrc(M, E, false, true, GR, en);"
                      "const g = mmdParse(src); archBandFix(g); const L = mmdLayout(g), rows = g.slist.filter(s => /^Ek/.test(s));"
                      "process.stdout.write(JSON.stringify([ERR, rows, rows.map(s => [g.sgs[s].parent, g.sgs[s].pass, g.sgs[s].cls, !!g.sgs[s].oneLayer, g.sgs[s].title]),"
                      " rows.map(s => g.nlist.filter(k => g.nodes[k].sg === s)), g.slist.filter(s => g.sgs[s].parent === 'L0' && !/^Ek/.test(s)), g.nodes.en0.label,"
                      " mmdQuality(g, L), L.sgs.L0.y + L.sgs.L0.h <= Math.min(...['L2', 'L3', 'L7'].map(s => L.sgs[s].y)),"
                      " rows.map(s => [L.sgs[s].x + L.sgs[s].w / 2, L.sgs[s].y, L.sgs[s].h, L.sgs[s].tr ? L.sgs[s].tr.x + L.sgs[s].tr.w / 2 : null]), L.sgs.L0.x + L.sgs.L0.w / 2]));")

    def _geo(self, rows, geo, mid):
        self.assertTrue(all(abs(c - mid) <= 2 for c, _, _, _ in geo))   # every row centred in the entry band (81f one)
        span = {}
        for r, (_, y, h, _) in zip(rows, geo):
            k = r.split("r")[0]
            a, b = span.get(k, (y, y + h))
            span[k] = (min(a, y), max(b, y + h))
        sp = sorted(span.values())
        self.assertTrue(all(sp[i][1] <= sp[i + 1][0] for i in range(len(sp) - 1)))   # kind blocks never overlap vertically
        self.assertEqual([k for k, _ in sorted(span.items(), key=lambda kv: kv[1])], [r.split("r")[0] for r in rows if r.endswith("r0")])   # kind order top down

    def test_entry_rows_per_kind(self):
        err, rows, meta, members, boxes, lab0, q, above, geo, mid = self._kinds(3)
        self.assertIsNone(err)
        self.assertEqual(rows, ["Ek0r0", "Ek1r0", "Ek3r0", "Ek4r0"])   # http, hook, job, cli in kind order
        self.assertEqual([m[:4] for m in meta], [["L0", True, "archerow", True]] * 4)
        self.assertEqual(members[0], ["en0", "en1", "en2", "m0"])        # entry module joins its ext row
        self.assertEqual(members[3], ["m1"])                             # cli entry module: own row though no cli entry
        self.assertEqual(boxes, [])                                      # no inset G group box in L0
        self.assertEqual(lab0, "GET /p0")                                # no «HTTP · » prefix
        self.assertEqual(q["boxHits"], 0)
        self.assertTrue(above)
        self._geo(rows, geo, mid)
        self.assertTrue(all(abs(t - c) <= 1 for c, _, _, t in geo))      # titled rows: title centred like other band titles

    def test_entry_rows_wrap_within_kind(self):
        err, rows, meta, members, boxes, _, q, _, geo, mid = self._kinds(9)
        self.assertIsNone(err)
        self.assertEqual(rows, ["Ek0r0", "Ek0r1", "Ek1r0", "Ek3r0", "Ek4r0"])
        self.assertEqual([len(m) for m in members[:2]], [8, 2])          # 9 http + 1 module: wraps only inside the kind
        self.assertEqual(meta[1][4], "")                                  # only a kind's first row is titled
        self.assertTrue(meta[0][4] and meta[2][4])
        self.assertEqual(q["boxHits"], 0)
        self._geo(rows, geo, mid)

    def test_entry_rows_one_column_with_row_edges(self):
        # 33 http (5 rows) with entries pointing at the entry module in the last row: rows still stack in one column
        err, rows, meta, members, boxes, _, q, _, geo, mid = self._kinds(30, via=3)
        self.assertIsNone(err)
        self.assertEqual(rows, ["Ek0r0", "Ek0r1", "Ek0r2", "Ek0r3", "Ek0r4", "Ek1r0", "Ek3r0", "Ek4r0"])
        self.assertIn("m0", members[4])
        self._geo(rows, geo, mid)
        ys = [(y, y + h) for _, y, h, _ in geo]
        self.assertTrue(all(ys[i][1] <= ys[i + 1][0] for i in range(len(ys) - 1)))   # strictly top to bottom in row order
        self.assertEqual(q["boxHits"], 0)

    def test_place_one_layer_opt_in(self):
        # 81f one: flagged items share one layer, centred, in source order; without one the placement is unchanged
        r = render("const sz = {a: {w: 300, h: 40}, b: {w: 100, h: 40}, c: {w: 200, h: 40}}, it = ['a', 'b', 'c'], h = {a: 3, b: 1, c: 2};"
                   "const P = one => mmdPlace(it, [], v => sz[v], 'LR', h, null, null, one), n = P(), y = P(v => true), u = P(null);"
                   "process.stdout.write(JSON.stringify([it.map(v => n.pos[v].x), it.map(v => y.pos[v].x), it.map(v => y.pos[v].y), JSON.stringify(n) === JSON.stringify(u)]));")
        cx, lx, ly, same = r
        self.assertEqual(cx, [0, 100, 50])                                # default: centred in the layer
        self.assertEqual(lx, [0, 100, 50])                                # one: centred in the one layer
        self.assertEqual(ly, sorted(ly))                                  # one: source order, hint ignored
        self.assertTrue(same)

    # front modules: entry serves sec and f1; f1, f2 call sec (a request filter every controller depends on)
    FR_M = [{"id": "web", "name": "Web", "kind": "entry", "ext": "http", "layer": "entry"},
            {"id": "f1", "name": "Orders", "kind": "module", "layer": "api"},
            {"id": "f2", "name": "Users", "kind": "module", "layer": "api"},
            {"id": "sec", "name": "Security", "kind": "module", "layer": "infra"}]
    FR_E = [{"from": f, "to": t, "kind": k, "ok": True, "est": False, "label": ""}
            for f, t, k in [("web", "sec", "serve"), ("web", "f1", "serve"), ("f1", "sec", "call"), ("f2", "sec", "call")]]

    def _front(self, style, edges):
        foc = open(os.path.join(WEB, "js", "84j4-structure-arch-focus.js"), encoding="utf-8").read()
        return render(foc + "\nconst FM = " + json.dumps(self.FR_M) + ", FE = " + json.dumps(edges) + ", D = {v: 2, style: {style: '" + style + "'}, edges: FE};"
                      "const bp = archBandPlan(D, FM, false), src = archBandSrc(FM, FE, false, true, [], null, bp), g = mmdParse(src); archBandFix(g, bp);"
                      "const L = mmdLayout(g), km = archKindMap(FM, FE, false, null, bp), y = k => L.nodes[k].y, q = mmdQuality(g, L);"
                      "const fk = archFocusKinds(FM, FE, false, 'f1', null, false, null, bp);"   # focus: same front set as the overview
                      "if(fk['m1\\u0001m3'] !== km['m1\\u0001m3'] || archKindMap(FM, FE, false)['m1\\u0001m3'] !== 'call') ERR = 'front sets disagree';"
                      "const svg = archMmd(src, FM, '', km, null, bp), svg0 = archMmd(src, FM, '', km, null, Object.assign({}, bp, {fk: {}}));"
                      "process.stdout.write(JSON.stringify([ERR, Object.keys(bp.front).sort(), [y('m3'), y('m1'), y('m2')], g.nodes.m3.sg, km['m1\\u0001m3'], km['m0\\u0001m3'],"
                      " !!g.front, svg === svg0, q.boxHits]));")

    def test_front_module_first_and_uses(self):
        for style in ("feature-pkgs", "layered"):
            err, front, (ys, y1, y2), sg, uses, serve, has, same, hits = self._front(style, self.FR_E)
            self.assertIsNone(err)
            self.assertEqual(front, ["f1", "sec"])                        # served by an entry, entry module itself excluded
            self.assertEqual(ys, y1)                                       # both front: one shared first row though f1 calls sec
            self.assertLess(ys, y2)                                        # sec drawn above its non-front caller
            self.assertEqual(uses, "uses")                                 # module -> front: a dependency, dashed
            self.assertEqual(serve, "call")                                # entry -> front keeps its kind
            self.assertTrue(has)
            self.assertEqual(hits, 0)
            if style == "layered":
                self.assertEqual(sg, "L2")                                 # layer mode: infra front module lifted to the api band

    def test_centre_axis_overview(self):
        # every band block and every entry row centred on one vertical axis; same input twice -> same x
        body = ("const en = archFlowEntries({flows: " + json.dumps(self._flows(9)) + "}, M, false), lay = () => { const g = mmdParse(archBandSrc(M, E, false, true, GR, en));"
                " archBandFix(g); const L = mmdLayout(g), c = s => L.sgs[s].x + L.sgs[s].w / 2;"
                " return [g.slist.filter(s => !g.sgs[s].parent).map(c), g.slist.filter(s => /^Ek/.test(s)).map(c), Object.keys(L.nodes).map(k => L.nodes[k].x), mmdQuality(g, L).boxHits]; };"
                "process.stdout.write(JSON.stringify([ERR, lay(), lay()]));")
        err, a, b = render(ENT + body)
        self.assertIsNone(err)
        bands, rows, xs, hits = a
        self.assertGreaterEqual(len(bands), 4)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(abs(c - bands[0]) <= 2 for c in bands + rows), (bands, rows))
        self.assertEqual(a, b)
        self.assertEqual(hits, 0)

    def test_centre_axis_focus(self):
        # focus: hub on the axis, every other band centred on it
        foc = open(os.path.join(WEB, "js", "84j4-structure-arch-focus.js"), encoding="utf-8").read()
        # svc3 beside the hub in its group (no edge between them): the hub is off its band's centre
        m2 = M + [{"id": "svc3", "name": "Billing service", "kind": "module", "layer": "service", "group": "core"}]
        e2 = E + [{"from": "svc", "to": "svc3", "kind": "call", "ok": True, "est": False, "label": ""},
                  {"from": "svc3", "to": "pg", "kind": "read", "ok": True, "est": False, "label": ""}]
        r = render(ENT + foc + "\nconst M2 = " + json.dumps(m2) + ", E2 = " + json.dumps(e2) + ";"
                   "const ents = archFlowEntries({flows: " + json.dumps(self._flows(3)) + "}, M2, false), src = archFocusSrc(M2, E2, false, 'routes', GR, ents, false, null, null, null);"
                   "const g = mmdParse(src), hub = 'm' + M2.findIndex(m => m.id === 'routes'); archBandFix(g, null, hub); const L = mmdLayout(g), c = R => R.x + R.w / 2;"
                   "const hb = g.nodes[hub].sg ? (s => { while(g.sgs[s].parent) s = g.sgs[s].parent; return s; })(g.nodes[hub].sg) : hub;"
                   "process.stdout.write(JSON.stringify([ERR, c(L.nodes[hub]), g.slist.filter(s => !g.sgs[s].parent && s !== hb).map(s => c(L.sgs[s]))]));")
        err, h, others = r
        self.assertIsNone(err)
        self.assertGreaterEqual(len(others), 2)
        self.assertTrue(all(abs(c - h) <= 2 for c in others), (h, others))
        # 81e axisHub: a hub beside a sibling sits on the axis, not its band's centre; without g.axis the bytes are the old ones
        src = "flowchart TB\\n  subgraph A[A]\\n    a1[Hub]\\n    a2[A sibling with a long name]\\n  end\\n  subgraph B[B]\\n    b1[B]\\n  end\\n  a1 --> b1\\n  a2 --> b1"
        r = render("const lay = (ax, hub) => { const g = mmdParse('" + src + "'); g.axis = ax; if(hub) g.axisHub = hub; return mmdLayout(g); };"
                   "const a = lay(true, 'a1'), b = lay(true, null), n = lay(false, null), c = R => R.x + R.w / 2;"
                   "process.stdout.write(JSON.stringify([c(a.nodes.a1), c(a.sgs.B), c(b.sgs.A), c(b.sgs.B), c(n.nodes.a1), c(n.sgs.B)]));")
        self.assertLessEqual(abs(r[0] - r[1]), 2)                          # hub on the axis
        self.assertLessEqual(abs(r[2] - r[3]), 2)                          # no hub: band centres on the axis
        self.assertGreater(abs(r[4] - r[5]), 2)                            # fixture: the hub is off-axis without it

    def test_front_none_bytes_unchanged(self):
        # no serve into a non-entry module: no g.front, no «uses», same drawing as with front cleared; 81f without front unchanged
        err, front, _, sg, uses, _, has, same, _ = self._front("feature-pkgs", [e for e in self.FR_E if e["kind"] != "serve"])
        self.assertIsNone(err)
        self.assertEqual((front, has, uses, same), ([], False, "call", True))
        r = render("const sz = {a: {w: 300, h: 40}, b: {w: 100, h: 40}, c: {w: 200, h: 40}}, it = ['a', 'b', 'c'], es = [{a: 'a', b: 'c'}, {a: 'b', b: 'c'}];"
                   "const P = f => JSON.stringify(mmdPlace(it, es, v => sz[v], 'TB', null, null, null, null, f)), F = mmdPlace(it, es, v => sz[v], 'TB', null, null, null, null, v => v === 'c');"
                   "process.stdout.write(JSON.stringify([P(null) === P(v => false), P(null) === JSON.stringify(mmdPlace(it, es, v => sz[v], 'TB')), F.pos.c.y < F.pos.a.y]));")
        self.assertEqual(r, [True, True, True])

    # feature-package map shaped like a web + api repo: entry, a ui-only «web» group, an «api» group, a store, one external
    LOC_M = [{"id": "e1", "name": "Routes", "kind": "entry", "ext": "http", "layer": "entry", "group": "api"},
             {"id": "w1", "name": "Page", "kind": "module", "layer": "ui", "group": "web"},
             {"id": "w2", "name": "Hooks", "kind": "module", "layer": "shared", "group": "web"},
             {"id": "a1", "name": "Ctrl", "kind": "module", "layer": "api", "group": "api"},
             {"id": "a2", "name": "Svc", "kind": "module", "layer": "service", "group": "api"},
             {"id": "c1", "name": "Util", "kind": "module", "layer": "shared", "group": "common"},
             {"id": "s1", "name": "Mongo", "kind": "store", "ext": "db", "layer": "data", "group": "api"},
             {"id": "x1", "name": "axios", "kind": "external", "ext": "npm", "layer": "infra"}]
    LOC_G = [{"id": "web", "name": "Web app"}, {"id": "api", "name": "API server"}, {"id": "common", "name": "Common"}]
    LOC_E = [{"from": f, "to": t, "kind": "call", "ok": True, "est": False, "label": ""}
             for f, t in [("e1", "a1"), ("w1", "w2"), ("w2", "x1"), ("w1", "a1"), ("a1", "a2"), ("a2", "c1"), ("a2", "s1")]]

    def _loc(self, body, mods=None):
        return render("const LM = " + json.dumps(mods or self.LOC_M) + ", LE = " + json.dumps(self.LOC_E) + ", LG = " + json.dumps(self.LOC_G) + ";"
                      "const LD = {v: 2, style: {style: 'feature-pkgs'}, groups: LG}, bp = archBandPlan(LD, LM, false);" + body)

    def test_loc_bands_by_location(self):
        r = self._loc("const src = archBandSrc(LM, LE, false, true, LG, null, bp), g = mmdParse(src); archBandFix(g, bp); const L = mmdLayout(g);"
                      "const band = k => { let s = g.nodes[k].sg; while(g.sgs[s].parent) s = g.sgs[s].parent; return s; };"
                      "process.stdout.write(JSON.stringify([ERR, bp.loc, LM.map(m => bp.of(m)), g.slist.filter(s => !g.sgs[s].parent),"
                      " LM.map((m, i) => band('m' + i)), g.slist.filter(s => g.sgs[s].parent).map(s => g.sgs[s].parent + ':' + g.sgs[s].title),"
                      " ['L0', 'L1', 'L2', 'L3', 'Lx'].map(s => g.sgs[s].title), ['L0', 'L1', 'L2', 'L3', 'Lx'].map(s => g.sgs[s].tip), mmdQuality(g, L).boxHits,"
                      " archMmd(src, LM, '', archKindMap(LM, LE, false), null, bp).indexOf('<title>브라우저에서 실행되는 코드') >= 0]));")
        err, loc, of, roots, member, boxes, titles, tips, hits, svgtip = r
        self.assertIsNone(err)
        self.assertTrue(loc)
        self.assertEqual(of, [0, 1, 1, 2, 2, 2, 3, 4])                   # web group (ui, no api/service/domain/data) -> L1, api -> L2
        self.assertEqual(roots, ["L0", "L1", "L2", "L3", "Lx"])
        self.assertEqual(member, ["L0", "L1", "L1", "L2", "L2", "L2", "L3", "Lx"])
        self.assertEqual(boxes, ["L2:API server", "L2:Common", "Lx:npm"])  # single-group bands draw no G box
        self.assertEqual(titles, ["진입 · 요청이 시작되는 곳", "클라이언트 · 브라우저에서 실행", "서버 · 백엔드 코드",
                                  "저장소 · DB, 파일, 큐", "외부"])   # ko dictionary (LANG ko)
        self.assertTrue(all(len(t) <= 28 for t in titles))
        self.assertIn("Web app", tips[1])                                 # solo group name goes to the band tip
        self.assertIn("API server", tips[0])
        self.assertNotIn("\n", tips[2])                                   # two groups: no group line
        self.assertTrue(all(tips))
        self.assertEqual(hits, 0)
        self.assertTrue(svgtip)                                           # archMmd passes the plan: <title> on the band

    def test_loc_no_client_is_code(self):
        nm = [m for m in self.LOC_M if m.get("group") != "web"]
        r = self._loc("process.stdout.write(JSON.stringify([bp.lbl(2), bp.lbl(1), archBandSrc(LM, LE, false, true, LG, null, bp).indexOf('subgraph L1[') < 0]));", nm)
        self.assertEqual(r[0], "코드 · 프로젝트 코드")
        self.assertEqual(r[1], "클라이언트 · 브라우저에서 실행")
        self.assertTrue(r[2])

    def test_layer_and_null_style_bytes_unchanged(self):
        r = render("const out = []; for(const st of ['layered', 'hexagonal', null]){ const d = {v: 2, style: st ? {style: st} : null, groups: GR}, b = archBandPlan(d, M, false);"
                   " out.push([b.loc, archBandSrc(M, E, false, true, GR, null, b) === archBandSrc(M, E, false, true, GR), b.tip(3)]); }"
                   " const g = mmdParse(archBandSrc(M, E, false, true, GR)); archBandFix(g);"
                   " process.stdout.write(JSON.stringify([out, g.slist.some(s => g.sgs[s].tip != null)]));")
        out, anytip = r
        self.assertEqual([o[:2] for o in out], [[False, True]] * 3)
        self.assertEqual(out[0][2], "서비스 · 업무 로직")          # layer mode: meaning in the tip only
        self.assertFalse(anytip)                                          # no plan: no tips (old SVG bytes)

    def test_key_carries_band_mode(self):
        r = render(js_fn("archKey") + "const LANG = 'en', d = {commit: 'c', modules: M, edges: E};"
                   "process.stdout.write(JSON.stringify([archKey(d, '', false, false), archKey(Object.assign({style: {style: 'layered'}}, d), '', false, false),"
                   " archKey(Object.assign({style: {style: 'apps'}}, d), '', false, false)]));")
        self.assertEqual(r[0], r[1])
        self.assertEqual(r[2], r[0] + "\tloc")

    def test_r4_v1_svg_has_no_kind(self):
        r = render("const s = archSrc(M, E, false, '', false); process.stdout.write(JSON.stringify([archMmd(s, M, '').indexOf('data-k') < 0, ERR]));")
        self.assertEqual(r, [True, None])


if __name__ == "__main__":
    unittest.main()
