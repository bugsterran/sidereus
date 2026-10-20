"""84j4 v2 focus view on the Architecture map (R1-R5): layer bands and group boxes kept with only the clicked module +
direct neighbours, infra/shared neighbours folded into one chip, edge labels on hover only, entry click lights its flows
with step numbers, and a 20+ neighbour hub fits a 1440 map box. Real 81e/81f/81g0/81g renderer."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e
from tests.test_structure_mermaid_js import PRE as MPRE, FNS as MFNS, ROUTER
from tests.test_struct_arch_js import SELF_MODS

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
_rd = lambda *p: open(os.path.join(WEB, *p), encoding="utf-8").read()
L2, FOC, J = _rd("js", "84j2-structure-arch-layers.js"), _rd("js", "84j4-structure-arch-focus.js"), _rd("js", "84j-structure-arch.js")
CSS = _rd("css", "79-structure-arch.css")
NAMES = [n for m, n in SELF_MODS if not m.startswith("ext.") and "test" not in n]   # a test-like name would hide the module


def _hub(n_in=7, n_out=20, n_infra=8):
    """hub (service) with n_in api callers, n_out domain callees in three groups, n_infra infra/shared neighbours, plus far modules."""
    nm = lambda i: NAMES[i % len(NAMES)]
    M = [{"id": "hub", "name": "Hub service", "kind": "module", "layer": "service", "group": "core"}]
    M += [{"id": "a%d" % i, "name": nm(i), "kind": "module", "layer": "api", "group": "web"} for i in range(n_in)]
    M += [{"id": "d%d" % i, "name": nm(i + 3), "kind": "module", "layer": "domain", "group": "g%d" % (i % 3)} for i in range(n_out)]
    M += [{"id": "i%d" % i, "name": nm(i + 5), "kind": "module", "layer": "infra" if i % 2 else "shared", "group": "base"} for i in range(n_infra)]
    M += [{"id": "far", "name": "Far away", "kind": "module", "layer": "domain", "group": "g0"},
          {"id": "far2", "name": "Not a neighbour", "kind": "module", "layer": "api", "group": "web"},
          {"id": "pg", "name": "Postgres", "kind": "store", "layer": "data", "group": "io"}]
    E = [("a%d" % i, "hub", "call") for i in range(n_in)] + [("hub", "d%d" % i, "call") for i in range(n_out)]
    E += [("hub", "i%d" % i, "read" if i % 2 else "write") for i in range(n_infra)]
    E += [("d0", "far", "call"), ("far", "pg", "write"), ("far2", "d1", "call")]
    E = [{"from": f, "to": t, "kind": k, "ok": True, "est": False, "label": "%s.%s" % (f, t)} for f, t, k in E]
    G = [{"id": "web", "name": "Web"}, {"id": "core", "name": "Core"}, {"id": "base", "name": "Base"}, {"id": "io", "name": "I/O"}] \
        + [{"id": "g%d" % i, "name": "Group %d" % i} for i in range(3)]
    return M, E, G


FLOWS = [{"id": "f1", "name": "get", "entry": {"kind": "http", "label": "GET /x"}, "steps": [
    {"from": "a0", "to": "hub", "ok": True}, {"from": "hub", "to": "d0", "ok": True},
    {"from": "d0", "to": "far", "ok": True}, {"from": "far", "to": "pg", "ok": True}]},
    {"id": "f2", "name": "cli", "entry": {"kind": "cli", "label": "sync"}, "steps": [{"from": "a1", "to": "hub", "ok": True}]}]


# Shape of a real v2 map (56 modules, hub 13 in / 17 out, 8 flows with 7 entries, one group holding most modules):
# ids anonymised, names/labels replaced by padding of the real length, only layers/groups/kinds/steps kept.
REAL_M = [('n00', 12, 'service', 'app', 'module'), ('n01', 17, 'api', 'app', 'module'), ('n02', 15, 'infra', 'app', 'module'), ('n03', 17, 'infra',
    'app', 'module'), ('n04', 16, 'service', 'app', 'module'), ('n05', 16, 'service', 'app', 'module'), ('n06', 7, 'api', 'app', 'module'), ('n07',
    17, 'shared', 'app', 'module'), ('n08', 21, 'infra', 'app', 'module'), ('n09', 17, 'infra', 'app', 'module'), ('n10', 20, 'shared', 'app',
    'module'), ('hub', 20, 'service', 'app', 'module'), ('n12', 18, 'data', 'app', 'module'), ('n13', 14, 'service', 'app', 'module'), ('n14', 19,
    'infra', 'app', 'module'), ('n15', 18, 'service', 'app', 'module'), ('n16', 20, 'infra', 'app', 'module'), ('n17', 18, 'service', 'app',
    'module'), ('n18', 12, 'service', 'app', 'module'), ('n19', 7, 'service', 'app', 'module'), ('n20', 9, 'shared', 'app', 'module'), ('n21', 22,
    'infra', 'app', 'module'), ('n22', 21, 'infra', 'app', 'module'), ('n23', 17, 'data', 'app', 'module'), ('n24', 18, 'data', 'app', 'module'),
    ('n25', 13, 'infra', 'app', 'module'), ('n26', 18, 'ui', 'app', 'module'), ('n27', 24, 'infra', 'compose', 'module'), ('n28', 11, 'infra',
    'nginx', 'module'), ('n29', 8, 'entry', 'app', 'entry'), ('n30', 14, 'entry', 'app', 'entry'), ('n31', 11, 'entry', 'app', 'entry'), ('n32', 13,
    'entry', 'app', 'entry'), ('n33', 11, 'entry', 'app', 'entry'), ('n34', 10, 'entry', 'app', 'entry'), ('n35', 12, 'entry', 'app', 'entry'),
    ('n36', 15, 'entry', 'app', 'entry'), ('n37', 11, 'entry', 'app', 'entry'), ('n38', 11, 'entry', 'app', 'entry'), ('n39', 8, 'entry', 'app',
    'entry'), ('n40', 13, 'entry', 'app', 'entry'), ('n41', 8, 'entry', 'app', 'entry'), ('n42', 12, 'entry', 'app', 'entry'), ('n43', 13, 'entry',
    'app', 'entry'), ('n44', 18, 'entry', 'app', 'entry'), ('n45', 22, 'entry', 'app', 'entry'), ('n46', 10, 'entry', 'compose', 'entry'), ('n47', 11,
    'entry', 'compose', 'entry'), ('n48', 7, 'data', 'app', 'store'), ('n49', 10, 'data', 'app', 'store'), ('n50', 8, 'data', 'app', 'store'), ('n51',
    16, 'data', 'app', 'store'), ('n52', 10, 'data', 'app', 'store'), ('n53', 11, 'data', 'redis', 'store'), ('n54', 11, 'data', 'app', 'store'),
    ('n55', 11, 'data', 'app', 'store')]
REAL_E = [('n00', 'n14', 'import', 16, 0), ('n00', 'n18', 'import', 22, 0), ('n00', 'n20', 'import', 46, 0), ('n00', 'n12', 'import', 15, 0), ('n00',
    'n10', 'import', 36, 0), ('n00', 'n19', 'import', 57, 0), ('n00', 'n03', 'import', 49, 0), ('n00', 'n15', 'import', 56, 0), ('n00', 'n21',
    'import', 26, 0), ('n00', 'n05', 'import', 21, 0), ('n00', 'n07', 'import', 24, 0), ('n00', 'n08', 'import', 29, 0), ('n00', 'hub', 'import', 30,
    0), ('n01', 'n10', 'import', 20, 0), ('n01', 'n17', 'import', 28, 0), ('n02', 'n21', 'import', 28, 0), ('n03', 'n02', 'import', 29, 0), ('n03',
    'n20', 'import', 19, 0), ('n04', 'n14', 'import', 16, 0), ('n04', 'n18', 'import', 19, 0), ('n04', 'n12', 'import', 15, 0), ('n04', 'n00',
    'import', 60, 0), ('n04', 'hub', 'import', 33, 0), ('n04', 'n13', 'import', 26, 0), ('n04', 'n17', 'import', 37, 0), ('n04', 'n05', 'import', 27,
    0), ('n04', 'n19', 'import', 26, 0), ('n05', 'n12', 'import', 15, 0), ('n05', 'n21', 'import', 26, 0), ('n05', 'n10', 'import', 36, 0), ('n05',
    'n18', 'import', 34, 0), ('n05', 'n19', 'import', 49, 0), ('n05', 'n00', 'import', 42, 0), ('n05', 'n14', 'import', 16, 0), ('n05', 'n15',
    'import', 19, 0), ('n05', 'n03', 'import', 25, 0), ('n05', 'n08', 'import', 32, 0), ('n06', 'n08', 'import', 34, 0), ('n06', 'n15', 'import', 44,
    0), ('n07', 'n10', 'import', 20, 0), ('n07', 'n17', 'import', 27, 0), ('n08', 'n12', 'import', 37, 0), ('n08', 'n03', 'import', 51, 0), ('n08',
    'n14', 'import', 16, 0), ('n08', 'n18', 'import', 58, 0), ('n08', 'n17', 'import', 39, 0), ('n08', 'n00', 'import', 15, 0), ('n08', 'n10',
    'import', 36, 0), ('n08', 'n15', 'import', 40, 0), ('n08', 'n19', 'import', 48, 0), ('n08', 'n20', 'import', 24, 0), ('n08', 'n05', 'import', 40,
    0), ('n08', 'hub', 'import', 59, 0), ('n08', 'n13', 'import', 31, 0), ('n08', 'n07', 'import', 26, 0), ('n09', 'n03', 'import', 25, 0), ('hub',
    'n14', 'import', 16, 0), ('hub', 'n20', 'import', 52, 0), ('hub', 'n21', 'import', 52, 0), ('hub', 'n18', 'import', 31, 0), ('hub', 'n15',
    'import', 52, 0), ('hub', 'n10', 'import', 36, 0), ('hub', 'n03', 'import', 43, 0), ('hub', 'n12', 'import', 15, 0), ('hub', 'n00', 'import', 13,
    0), ('hub', 'n07', 'import', 32, 0), ('hub', 'n08', 'import', 50, 0), ('hub', 'n13', 'import', 36, 0), ('hub', 'n19', 'import', 48, 0), ('n12',
    'hub', 'import', 50, 0), ('n12', 'n15', 'import', 18, 0), ('n13', 'n03', 'import', 25, 0), ('n13', 'n10', 'import', 20, 0), ('n13', 'n14',
    'import', 16, 0), ('n13', 'n21', 'import', 52, 0), ('n13', 'n20', 'import', 19, 0), ('n13', 'n15', 'import', 44, 0), ('n13', 'n18', 'import', 33,
    0), ('n13', 'n19', 'import', 57, 0), ('n13', 'n08', 'import', 31, 0), ('n13', 'n12', 'import', 15, 0), ('n14', 'n21', 'import', 24, 0), ('n15',
    'n14', 'import', 16, 0), ('n15', 'n20', 'import', 47, 0), ('n15', 'n21', 'import', 26, 0), ('n15', 'n18', 'import', 22, 0), ('n15', 'hub',
    'import', 59, 0), ('n15', 'n03', 'import', 43, 0), ('n15', 'n07', 'import', 58, 0), ('n15', 'n08', 'import', 22, 0), ('n15', 'n10', 'import', 20,
    0), ('n15', 'n00', 'import', 35, 0), ('n15', 'n05', 'import', 24, 0), ('n15', 'n12', 'import', 15, 0), ('n15', 'n17', 'import', 54, 0), ('n17',
    'n14', 'import', 16, 0), ('n17', 'n18', 'import', 34, 0), ('n17', 'n20', 'import', 38, 0), ('n17', 'n03', 'import', 51, 0), ('n17', 'n15',
    'import', 39, 0), ('n17', 'n21', 'import', 26, 0), ('n17', 'n12', 'import', 15, 0), ('n17', 'n08', 'import', 42, 0), ('n17', 'n10', 'import', 36,
    0), ('n17', 'n19', 'import', 57, 0), ('n17', 'n07', 'import', 57, 0), ('n17', 'hub', 'import', 30, 0), ('n18', 'n02', 'import', 32, 0), ('n18',
    'hub', 'import', 55, 0), ('n18', 'n20', 'import', 29, 0), ('n18', 'n08', 'import', 51, 0), ('n18', 'n00', 'import', 33, 0), ('n18', 'n14',
    'import', 16, 0), ('n18', 'n19', 'import', 11, 0), ('n18', 'n05', 'import', 18, 0), ('n18', 'n13', 'import', 36, 0), ('n18', 'n17', 'import', 59,
    0), ('n18', 'n15', 'import', 31, 0), ('n18', 'n03', 'import', 19, 0), ('n19', 'n14', 'import', 16, 0), ('n19', 'n15', 'import', 16, 0), ('n19',
    'n18', 'import', 26, 0), ('n19', 'n10', 'import', 20, 0), ('n19', 'n21', 'import', 26, 0), ('n19', 'n12', 'import', 15, 0), ('n19', 'n20',
    'import', 42, 0), ('n19', 'n00', 'import', 15, 0), ('n19', 'n05', 'import', 39, 0), ('n19', 'n08', 'import', 29, 0), ('n19', 'hub', 'import', 52,
    0), ('n19', 'n13', 'import', 31, 0), ('n19', 'n17', 'import', 28, 0), ('n20', 'n10', 'import', 20, 0), ('n20', 'hub', 'import', 32, 0), ('n20',
    'n07', 'import', 24, 0), ('n21', 'n03', 'import', 51, 0), ('n21', 'n14', 'import', 29, 0), ('n21', 'n10', 'import', 20, 0), ('n21', 'hub',
    'import', 21, 0), ('n21', 'n18', 'import', 51, 0), ('n21', 'n08', 'import', 38, 0), ('n21', 'n15', 'import', 48, 0), ('n00', 'n48', 'read', 22,
    0), ('n00', 'n48', 'write', 18, 0), ('n04', 'n48', 'read', 22, 0), ('n05', 'n48', 'read', 22, 0), ('n05', 'n48', 'write', 18, 0), ('n08', 'n48',
    'read', 22, 0), ('hub', 'n48', 'read', 22, 0), ('hub', 'n48', 'write', 18, 0), ('n13', 'n48', 'read', 22, 0), ('n13', 'n48', 'write', 18, 0),
    ('n15', 'n48', 'read', 22, 0), ('n15', 'n48', 'write', 18, 0), ('n17', 'n48', 'read', 22, 0), ('n17', 'n48', 'write', 18, 0), ('n19', 'n48',
    'read', 22, 0), ('n19', 'n48', 'write', 18, 0), ('hub', 'n49', 'read', 20, 0), ('hub', 'n50', 'read', 20, 0), ('n08', 'n51', 'read', 26, 0),
    ('n08', 'n52', 'read', 29, 0), ('n02', 'n53', 'write', 23, 0), ('n02', 'n53', 'read', 23, 0), ('n14', 'n53', 'write', 20, 0), ('n14', 'n53',
    'read', 20, 0), ('n09', 'n54', 'write', 21, 0), ('n13', 'n55', 'write', 27, 0), ('n12', 'n25', 'config', 25, 0), ('n25', 'n23', 'config', 27, 0),
    ('n25', 'n24', 'config', 28, 0), ('n23', 'hub', 'config', 30, 0), ('n21', 'n26', 'config', 27, 0), ('n27', 'n28', 'config', 16, 0), ('n27', 'n22',
    'config', 14, 0), ('n28', 'n22', 'config', 27, 1), ('n12', 'n16', 'di', 35, 1), ('n29', 'n00', 'serve', 27, 0), ('n30', 'n04', 'serve', 33, 0),
    ('n31', 'n05', 'serve', 29, 0), ('n32', 'n08', 'serve', 30, 0), ('n33', 'hub', 'serve', 41, 0), ('n34', 'n13', 'serve', 27, 0), ('n35', 'n15',
    'serve', 39, 0), ('n36', 'n17', 'serve', 40, 0), ('n37', 'n18', 'serve', 25, 0), ('n38', 'n19', 'serve', 24, 0), ('n39', 'n21', 'serve', 28, 0),
    ('n40', 'n01', 'serve', 39, 0), ('n41', 'n06', 'serve', 24, 0), ('n42', 'n21', 'serve', 20, 0), ('n43', 'n14', 'serve', 28, 0), ('n44', 'hub',
    'serve', 33, 0), ('n45', 'n17', 'serve', 37, 0), ('n46', 'n27', 'serve', 14, 0), ('n47', 'n27', 'serve', 27, 0)]
REAL_F = [('f0', 'http', 25, [('n38', 'n19'), ('n19', 'n14'), ('n19', 'n19'), ('n19', 'n48'), ('n19', 'n18'), ('n18', 'n00'), ('n19', 'n08'), ('n19',
    'n08')]), ('f1', 'http', 22, [('n29', 'n00'), ('n00', 'n18'), ('n18', 'n00'), ('n00', 'n00'), ('n00', 'n48')]), ('f2', 'http', 40, [('n40',
    'n01'), ('n01', 'n17'), ('n17', 'n48')]), ('f3', 'http', 22, [('n41', 'n06'), ('n06', 'n08'), ('n08', 'n51')]), ('f4', 'http', 32, [('n33',
    'hub'), ('hub', 'n18'), ('hub', 'n14'), ('hub', 'hub'), ('hub', 'n48')]), ('f5', 'event', 67, [('n45', 'n17'), ('n17', 'n08'), ('n17', 'n08'),
    ('n08', 'n18'), ('n18', 'n17')]), ('f6', 'event', 47, [('n44', 'hub'), ('hub', 'n48')]), ('f7', 'cli', 30, [('n46', 'n27'), ('n27', 'n22'),
    ('n27', 'n28'), ('n28', 'n22')])]
REAL_G = [('app', 38), ('nginx', 29), ('redis', 33), ('compose', 26)]



def _real():
    pad = lambda k, n: (k + " " + "x" * n)[:max(n, 1)]
    M = [{"id": i, "name": pad(i, n), "kind": k, "layer": l, "group": g} for i, n, l, g, k in REAL_M]
    E = [{"from": f, "to": t, "kind": k, "ok": True, "est": bool(e), "label": "y" * n} for f, t, k, n, e in REAL_E]
    G = [{"id": g, "name": "z" * n} for g, n in REAL_G]
    F = [{"id": i, "name": i, "entry": {"kind": k, "label": "/" + "p" * (n - 1)}, "steps": [{"from": a, "to": b, "ok": True} for a, b in st]}
         for i, k, n, st in REAL_F]
    return M, E, G, F


def render(body, M, E, G, flows=None):
    js = "\n".join([MPRE, "const MMD_BUDGET = 1e9, MMD_UNCROSS = 1e9, ARCH_DIR = 'TB'; let ERR = null; function softErr(t, e){ ERR = String(e); }",
                    "function codeBlock(s){ return s; }", ROUTER] + [js_fn(f) for f in MFNS]
                   + [js_fn(n) for n in ("archIsTest", "archMq", "archPairs", "archReduce", "archSrc", "archRanks", "archMmd", "archFlowEntries")]
                   + [L2, FOC, "\n".join(js_fn(n) for n in ("archOwn", "archLitSet")),
                      "const M = " + json.dumps(M) + ", E = " + json.dumps(E) + ", GR = " + json.dumps(G) + ", D = {modules: M, edges: E, flows: "
                      + json.dumps(FLOWS if flows is None else flows) + "};", body])
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


# Focus source -> parsed graph -> layout, as 84j archMmd draws it (bands ranked by 84j2 archBandFix).
LAY = ("const run = (open, lit, fit, ents) => { const src = archFocusSrc(M, E, false, 'hub', GR, ents || null, open, lit || null, fit || null), g = mmdParse(src);"
       " archBandFix(g); g.flLabels = true; const lab = archFocusStrip(g), L = mmdLayout(g);"   # as 84j archMmd: labels off the layout
       " g.edges.forEach(e => { const x = lab[e.from + '\\u0001' + e.to]; if(x) e.label = x; }); return {src, g, L}; };"
       "const ix = id => 'm' + M.findIndex(m => m.id === id), roots = g => g.slist.filter(s => !g.sgs[s].parent);")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchFocus(unittest.TestCase):
    def setUp(self):
        self.M, self.E, self.G = _hub()

    def test_r1_bands_and_groups_kept(self):
        r = render(LAY + "const {g, L} = run(false); const bs = roots(g);"
                   "process.stdout.write(JSON.stringify([ERR, bs, bs.map(s => L.sgs[s].y), g.nlist, ix('hub'), ix('far'), ix('far2'), ix('pg'),"
                   " g.slist.filter(s => g.sgs[s].parent).map(s => g.sgs[s].title), g.nodes[ix('hub')].sg, g.sgs[g.nodes[ix('a0')].sg].parent]));",
                   self.M, self.E, self.G)
        err, bands, ys, nodes, hub, far, far2, pg, grps, hubBand, aBand = r
        self.assertIsNone(err)
        self.assertEqual([b.split(".")[0] for b in bands][:1], ["L2"])        # api callers on top, layer order kept
        self.assertEqual(ys, sorted(ys))
        self.assertIn(hub, nodes)
        for k in (far, far2, pg):                                             # non-neighbours removed
            self.assertNotIn(k, nodes)
        self.assertEqual(hubBand, "L3")
        self.assertEqual(aBand, "L2")
        self.assertTrue({"Web", "Group 0", "Group 1", "Group 2"} <= set(grps))   # group boxes kept
        self.assertNotIn("Core", grps)                                         # hub's group alone in its band: no box (path bar names it)
        self.assertNotIn("I/O", grps)                                          # empty groups dropped

    def test_r2_infra_folded(self):
        r = render(LAY + "const a = run(false), b = run(true);"
                   "const ins = x => M.filter(m => /^i/.test(m.id)).map(m => ix(m.id)).filter(k => x.g.nodes[k]).length;"
                   "process.stdout.write(JSON.stringify([a.g.nodes.ifx && a.g.nodes.ifx.label, ins(a), a.g.edges.filter(e => e.to === 'ifx' || e.from === 'ifx').length,"
                   " roots(a.g).find(s => a.g.nodes.ifx.sg === s || a.g.sgs[a.g.nodes.ifx.sg] && a.g.sgs[a.g.nodes.ifx.sg].parent === s),"
                   " archFocusKinds(M, E, false, 'hub', null, false, null)[ix('hub') + '\\u0001ifx'], !!b.g.nodes.ifx, ins(b)]));", self.M, self.E, self.G)
        label, folded_left, ifx_edges, band, kind, open_ifx, open_n = r
        self.assertRegex(label, r"(?<!\d)8(?!\d)")                                    # T('Infrastructure {n}') with the folded count
        self.assertEqual(folded_left, 0)
        self.assertEqual(ifx_edges, 1)                                         # 8 out pairs merge into one edge
        self.assertTrue(band.startswith("L5"))                                 # band of the topmost folded layer (shared)
        self.assertEqual(kind, "write")                                        # strongest kind of the merged pairs
        self.assertFalse(open_ifx)                                             # expanded: every neighbour its own box
        self.assertEqual(open_n, 8)

    def test_r2_infra_expand(self):
        M, E, G = _hub(n_infra=1)
        r = render(LAY + "const a = run(false); process.stdout.write(JSON.stringify([!!a.g.nodes.ifx, !!a.g.nodes[ix('i0')]]));", M, E, G)
        self.assertEqual(r, [False, True])                                     # a single infra neighbour is not folded

    def test_r3_labels_hover_only(self):
        r = render("const src = archFocusSrc(M, E, false, 'hub', GR, null, false, null, null), si = M.findIndex(m => m.id === 'hub');"
                   "const svg = archMmd(src, M, si, archFocusKinds(M, E, false, 'hub', null, false, null));"
                   "process.stdout.write(JSON.stringify([ERR, svg]));", self.M, self.E, self.G)
        self.assertIsNone(r[0])
        self.assertRegex(r[1], r'<g class=mmdfe[^>]*><g class="mmdel mmdfl')   # pair labels still in the svg for hover
        self.assertIn("a0.hub", r[1])
        self.assertIn("(fv ? ' data-fv' : '')", J)                             # focus slot marked for the CSS
        self.assertIn(".archdg[data-fv] .mmdfe .mmdfl{visibility:hidden}", CSS)
        self.assertIn(".archdg[data-fv] svg.archdim .mmdfe.arhe .mmdfl{visibility:visible}", CSS)
        self.assertNotRegex(CSS, r"data-fv\][^{]*\.arn[^{]*\.mmdfl")              # box hover must not reveal its edges' text

    def test_r3_hover_shows_one_label(self):
        # 84j archHovPaint on a fake svg: a pill is visible when its .mmdfe has arhe (79 rule). Idle 0, box hover 0, edge hover 1.
        js = "\n".join([js_fn("archHov"), js_fn("archHovPaint"), '''
const cl = () => { const s = new Set(); return {toggle: (c, on) => { if(on) s.add(c); else s.delete(c); }, has: c => s.has(c)}; };
const E = [['m1', 'm0'], ['m0', 'm2'], ['m0', 'm3'], ['m3', 'm0']], es = [];
E.forEach(([f, t]) => { es.push({dataset: {f, t}, classList: cl(), pill: false}, {dataset: {f, t}, classList: cl(), pill: true}); });
const ns = ['m0', 'm1', 'm2', 'm3'].map(p => ({dataset: {p}, classList: cl()}));
const svg = {classList: cl(), querySelectorAll: q => q === '.mmdfe' ? es : ns};
const vis = () => es.filter(g => g.pill && svg.classList.has('archdim') && g.classList.has('arhe')).length;
const lit = () => es.filter(g => !g.pill && g.classList.has('arn')).length;
const out = [vis()]; archHovPaint(svg, {node: 'm0'}); out.push(vis(), lit()); archHovPaint(svg, {edge: {f: 'm0', t: 'm3'}}); out.push(vis()); archHovPaint(svg, null); out.push(vis());
process.stdout.write(JSON.stringify(out));
'''])
        p = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr.decode())
        self.assertEqual(json.loads(p.stdout), [0, 0, 4, 1, 0])   # idle · box hover (4 edges lit, no text) · edge hover · out

    def test_r4_entry_lights_flow(self):
        r = render(LAY + "const ents = archFlowEntries(D, M, false), en = ents.find(e => e.flows.indexOf('f1') >= 0), lit = {flows: D.flows, fs: en.flows};"
                   "const a = run(false, {flows: D.flows, fs: null}, null, ents), b = run(false, lit, null, ents), S = archLitSet(D, {fs: en.flows, tests: false});"
                   "const lab = x => x.g.edges.filter(e => e.label).map(e => [e.from, e.to, e.label]);"
                   "process.stdout.write(JSON.stringify([ERR, en.k, !!a.g.nodes[en.k], !!a.g.nodes[ix('far')], !!b.g.nodes[ix('far')], !!b.g.nodes[ix('pg')],"
                   " lab(b), [ix('a0'), ix('hub'), ix('d0'), ix('far'), ix('pg')], Array.from(S.n).sort(), ents.find(e => e.flows.indexOf('f2') >= 0).k,"
                   " b.g.edges.some(e => e.from === en.k && e.to === ix('a0'))]));", self.M, self.E, self.G)
        err, ek, ent_drawn, far_a, far_b, pg_b, labs, ks, lit_n, ek2, ent_edge = r
        self.assertIsNone(err)
        self.assertTrue(ent_drawn)                                             # entry of a flow through the hub shows in focus
        self.assertFalse(far_a)
        self.assertTrue(far_b and pg_b)                                        # lit: step modules added in their bands
        a0, hub, d0, far, pg = ks
        nums = {(f, t): l for f, t, l in labs}
        self.assertEqual([nums.get((a0, hub)), nums.get((hub, d0)), nums.get((d0, far)), nums.get((far, pg))], ["1", "2", "3", "4"])
        self.assertTrue(ent_edge)
        self.assertEqual(sorted(lit_n), sorted([ek, a0, hub, d0, far, pg]))     # only flows starting at the clicked entry
        self.assertNotIn(ek2, lit_n)

    def test_paired_entry_one_hexagon_lights_flows(self):
        # fx starts at entry module «ent» (same way in): one hexagon m<ent> with the module name, no en node / en -> m edge;
        # f1 (starts at a0, not an entry module) keeps its en hexagon. Clicking the pair lights fx like an en node.
        M = self.M + [{"id": "ent", "name": "/api/** (Key)", "kind": "entry", "ext": "http", "layer": "entry", "group": "io"}]
        E = self.E + [{"from": "ent", "to": "hub", "kind": "call", "ok": True, "est": False, "label": "serve"}]
        fl = FLOWS + [{"id": "fx", "name": "x", "entry": {"kind": "http", "label": "/api/** Key (Filter)"}, "steps": [{"from": "ent", "to": "hub", "ok": True}]}]
        r = render(LAY + "let lit = null; const ARCH = {sel: {p: '/r', id: 'hub'}, tests: false, lit: null}; function paintStruct(){ lit = ARCH.lit; }"
                   "const ents = archFlowEntries(D, M, false), {g} = run(false, {flows: D.flows, fs: null}, null, ents), k = ix('ent'), ex = ents.find(e => e.flows[0] === 'fx').k;"
                   "archFocusClick('/r', D, k);"
                   "process.stdout.write(JSON.stringify([ERR, !!g.nodes[ex], g.nodes[k].shape, g.nodes[k].label, g.edges.filter(e => /^en/.test(e.from)).map(e => [e.from, e.to]),"
                    " g.edges.some(e => e.from === k && e.to === ix('hub')), ents.find(e => e.flows[0] === 'f1').k, lit && lit.fs, archFocusHx(ix('hub')), k]));",
                   M, E, self.G, fl)
        err, en_drawn, shape, lab, eds, serve, ek1, lit, hub, k_ent = r
        self.assertIsNone(err)
        self.assertFalse(en_drawn)                                            # no separate entry node for the pair
        self.assertEqual([shape, lab], ["hex", "/api/** (Key)"])
        self.assertEqual(eds[0], [ek1, "m1"])                                 # unpaired f1 entry unchanged
        self.assertEqual([x for x in eds if x[1] == k_ent], [])               # no hexagon -> box edge for the pair
        self.assertTrue(serve)                                                # module edge from the single node
        self.assertEqual(lit, ["fx"])                                         # click lights its flows
        self.assertIsNone(hub)                                                # the hub keeps its own click
        self.assertNotIn("addEventListener", FOC)                            # no global listener: 84j archDgClick routes the click
        self.assertIn("archFocusHx(b.dataset.p)", J)

    def test_r5_hub_fits_1440(self):
        r = render(LAY + "const {g, L, src} = run(false, null, {w: 680, h: 600}), q = mmdQuality(g, L), hub = ix('hub');"
                   "const odd = g.nlist.filter(k => k !== hub && (L.nodes[k].w !== mmdBox(g.nodes[k].label, g.nodes[k].shape).w || L.nodes[k].h !== mmdBox(g.nodes[k].label, g.nodes[k].shape).h));"
                   "const wide = run(false, null, null);"
                   "process.stdout.write(JSON.stringify([ERR, L.w, q.boxHits, odd, g.nlist.length, wide.L.w, roots(g)]));", self.M, self.E, self.G)
        err, w, hits, odd, n, w0, bands = r
        self.assertIsNone(err)
        self.assertGreaterEqual(n, 28)                                         # hub + 7 in + 20 out + ifx chip
        self.assertGreater(w0, 680)                                            # without the room the hub row is wider
        self.assertLessEqual(w, 680)                                           # no horizontal scroll in the 1440 map box
        self.assertEqual(hits, 0)
        self.assertEqual(odd, [])                                              # text and box sizes unchanged
        self.assertEqual(len(bands), len(set(bands)))                           # wrapped rows stay inside one box per layer

    def test_r5_real_shape_fits(self):
        # ★Before: 1157px layout (svg 1602px live) for an 860px room; after: 759 at 860, 645 at 680.
        M, E, G, F = _real()
        r = render(LAY + "const ents = archFlowEntries(D, M, false), lit = {flows: D.flows, fs: null};"
                   "const one = w => { const {g, L} = run(false, lit, {w, h: 600}, ents), q = mmdQuality(g, L), hub = ix('hub');"
                   " const odd = g.nlist.filter(k => k !== hub && (L.nodes[k].w !== mmdBox(g.nodes[k].label, g.nodes[k].shape).w || L.nodes[k].h !== mmdBox(g.nodes[k].label, g.nodes[k].shape).h));"
                   " return [w, L.w, q.boxHits, odd, roots(g)]; };"
                   "const si = M.findIndex(m => m.id === 'hub'), src = archFocusSrc(M, E, false, 'hub', GR, ents, false, lit, {w: 860, h: 600});"
                   "const svg = archMmd(src, M, si, archFocusKinds(M, E, false, 'hub', ents, false, lit)), sw = +/<svg[^>]* width=\"(\\d+)\"/.exec(svg)[1];"
                   "process.stdout.write(JSON.stringify([ERR, one(860), one(680), sw, (svg.match(/class=\"mmdel mmdfl/g) || []).length, /mmdflg/.test(svg)]));", M, E, G, F)
        err, a, b, sw, pills, legend = r
        self.assertIsNone(err)
        for w, lw, hits, odd, bands in (a, b):
            self.assertLessEqual(lw, w, w)
            self.assertEqual(hits, 0, w)
            self.assertEqual(odd, [], w)
            self.assertEqual(bands, ["L0", "L3", "L5", "L7"], w)
        self.assertLessEqual(sw, 860)                                          # the rendered svg too: no legend column
        self.assertGreater(pills, 10)                                          # labels kept as hover pills
        self.assertFalse(legend)

    def test_r1_hub_on_first_screen(self):
        # ★Real shape in the 1440 pane (fit 660): hub top 854 in the svg before (stair of one-member chunks), 434 after.
        M, E, G, F = _real()
        r = render(LAY + "const ents = archFlowEntries(D, M, false), {g, L} = run(false, {flows: D.flows, fs: null}, {w: 660, h: 600}, ents);"
                   "process.stdout.write(JSON.stringify([L.nodes[ix('hub')].y, g.slist.filter(s => g.sgs[s].parent).map(s => g.sgs[s].parent + '/' + g.sgs[s].title)]));", M, E, G, F)
        y, grps = r
        self.assertLess(y, 500)
        self.assertEqual(len(grps), len(set(grps)))                            # one box per (band, group), no repeated chunks

    def test_r1_hub_on_first_screen_narrow(self):
        # ★1100 pane: .archmap 543px wide -> archFitOf w = floor((543 - 52) / 20) * 20 = 480. Hub top 644 in the svg before
        #  (963 live, first screen ends at 860), 496 after; the two entries share one row (were y 48 / 122).
        M, E, G, F = _real()
        r = render(LAY + "const ents = archFlowEntries(D, M, false), {g, L} = run(false, {flows: D.flows, fs: null}, {w: 480, h: 600}, ents), q = mmdQuality(g, L);"
                   "process.stdout.write(JSON.stringify([L.nodes[ix('hub')].y, L.w, q.boxHits, g.nlist.filter(k => g.nodes[k].shape === 'hex').map(k => L.nodes[k].y),"
                   " g.edges.filter(e => e.to === ix('hub') && g.nodes[e.from].sg === g.nodes[ix('hub')].sg && e.style !== 'invis').map(e => L.nodes[e.from].y)]));", M, E, G, F)
        y, w, hits, ey, cy = r
        up = [c for c in cy if c < y]                                          # callers drawn above the hub (mutual pairs may sit below)
        self.assertTrue(up)
        self.assertEqual(len(set(up)), 1)                                      # callers keep the full room; the mutual one moves below the hub
        self.assertLess(y, 400)                                                # ★456 (live box 851-881 > 860) before; 382 = the 1440 pane's
        self.assertLessEqual(w, 480)
        self.assertEqual(hits, 0)
        self.assertEqual(len(set(ey)), 1)                                      # no entry step (entries paired with their module are hexagons too)

    def test_r1_entries_one_band(self):
        fl = [{"id": "e%d" % i, "name": "e", "entry": {"kind": "http", "label": "GET /entry/%d" % i}, "steps": [{"from": "a%d" % i, "to": "hub", "ok": True}]}
              for i in range(7)]
        r = render(LAY + "const ents = archFlowEntries(D, M, false), {g, L} = run(false, {flows: D.flows, fs: null}, {w: 860, h: 600}, ents);"
                   "const en = g.nlist.filter(k => /^en/.test(k));"
                   "process.stdout.write(JSON.stringify([roots(g).filter(s => /^L0/.test(s)), en.map(k => g.nodes[k].sg), Math.max(...Object.values(en.reduce((o, k) => { const y = Math.round(L.nodes[k].y); o[y] = (o[y] || 0) + 1; return o; }, {}))), L.w]));",
                   self.M, self.E, self.G, fl)
        l0, sgs, per_row, w = r
        self.assertEqual(l0, ["L0"])                                           # one entry band box
        self.assertEqual(sgs, ["L0"] * 7)
        self.assertGreaterEqual(per_row, 2)                                    # packed side by side, wrapped inside the band (not one per row)
        self.assertLessEqual(w, 860)

    def test_r1_unlinked_entries_dropped(self):
        fl = FLOWS + [{"id": "f3", "name": "x", "entry": {"kind": "http", "label": "POST /far"}, "steps": [{"from": "far2", "to": "d1", "ok": True}]}]
        r = render(LAY + "const ents = archFlowEntries(D, M, false), {g} = run(false, {flows: D.flows, fs: null}, null, ents), lit = run(false, {flows: D.flows, fs: ['f3']}, null, ents);"
                   "const k = ents.find(e => e.flows.indexOf('f3') >= 0).k;"
                   "process.stdout.write(JSON.stringify([!!g.nodes[k], !!lit.g.nodes[k], g.nlist.filter(x => /^en/.test(x)).every(x => g.edges.some(e => e.from === x))]));",
                   self.M, self.E, self.G, fl)
        self.assertEqual(r, [False, True, True])                               # no edge to a drawn module: dropped unless its flow is lit

    def test_r2_click_keeps_scroll(self):
        # A focus click (ifx / entry / Esc) changes the paint key: the diagram fills a frame later, onto a map that was
        # clamped to scroll 0 under the loading line. fill() must put the saved scroll back.
        js = "\n".join(["const ARCH = {svg: {}, cache: {}}; let strOn = ['/r'];", "function archWaitHtml(){ return 'wait'; }",
                         "function archMmd(){ return '<svg>'; }"] + [js_fn(n) for n in ("archDiagram", "archScrollPut")] + ["""
const am = {scrollTop: 0, scrollLeft: 0}, slot = {dataset: {k: 'K'}, innerHTML: ''};
const box = {_arsm: [[1094, 12], null, null], querySelector: s => s === '.archdg' ? slot : s === '.archmap' ? am : null};
const h = archDiagram(box, 'K', 'src', [], 0, null, null);
setTimeout(() => process.stdout.write(JSON.stringify([h, slot.innerHTML, am.scrollTop, am.scrollLeft])), 5);
"""])
        p = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr.decode())
        self.assertEqual(json.loads(p.stdout), ["wait", "<svg>", 1094, 12])
        self.assertIn("box._arsm = [sm, sl, sd];", J)                                    # archPaint saves the scroll it read before innerHTML

    def test_r2_refit_keeps_scroll(self):
        # «Fold infrastructure» appearing changes the bar height, so archPaint refits and paints twice; the second pass must not
        # read the scroll from the DOM the first pass just rebuilt (clamped to 0 under the loading line).
        from tests.test_struct_arch_js import run as arun, MODS, EDGES
        r = arun("const D2 = {ok: true, commit: 'c', modules: " + json.dumps(MODS) + ", edges: " + json.dumps(EDGES) + "};"
                 "ARCH.cache['/r'] = D2; ARCH.sel = {p: '/r', id: 'a'}; let tall = 120, sets = 0;"
                 "const top = {get offsetHeight(){ return tall; }};"
                 "const am = {scrollTop: 1110, scrollLeft: 30, offsetWidth: 900, offsetHeight: 900, querySelector: q => q === '.archtop' ? top : null};"
                 "const box = {_arp: '/r', _h: '', get innerHTML(){ return this._h; }, set innerHTML(v){ this._h = v; sets++; am.scrollTop = 0; am.scrollLeft = 0; tall += 30; },"
                 " querySelector: q => q === '.archmap' ? am : null};"
                 "archPaint(box, head); await new Promise(res => setTimeout(res, 20));"
                 "console.log(JSON.stringify([sets, am.scrollTop, am.scrollLeft]));")
        sets, top, left = r
        self.assertEqual(sets, 2)                                              # the refit pass ran (bar height changed)
        self.assertEqual([top, left], [1110, 30])

    def test_r2_entry_click_keeps_scroll(self):
        # Entry click lights a flow: its «n lit · m off-screen» line resizes the bar while the diagram is still loading, so the
        # next poll repaints before the fill. That paint must use the pending scroll, not the DOM clamped to 0.
        from tests.test_struct_arch_js import run as arun, MODS, EDGES
        r = arun("const D2 = {ok: true, commit: 'c', modules: " + json.dumps(MODS) + ", edges: " + json.dumps(EDGES) + "};"
                 "ARCH.cache['/r'] = D2; ARCH.sel = {p: '/r', id: 'a'}; let tall = 120, sets = 0;"
                 "const top = {get offsetHeight(){ return tall; }};"
                 "const am = {scrollTop: 152, scrollLeft: 4, offsetWidth: 900, offsetHeight: 900, querySelector: q => q === '.archtop' ? top : null};"
                 "const box = {_arp: '/r', _h: '', get innerHTML(){ return this._h; }, set innerHTML(v){ this._h = v; sets++; am.scrollTop = 0; am.scrollLeft = 0; },"
                 " querySelector: q => q === '.archmap' ? am : null};"
                 "archPaint(box, head); tall = 160; archPaint(box, head); await new Promise(res => setTimeout(res, 20));"
                 "console.log(JSON.stringify([sets, am.scrollTop, am.scrollLeft]));")
        sets, top, left = r
        self.assertGreaterEqual(sets, 2)                                       # the second paint ran before the fill
        self.assertEqual([top, left], [152, 4])

    def test_back_button_first_and_accent(self):
        from tests.test_struct_arch_js import run as arun, MODS, EDGES
        body = ("console.log(JSON.stringify(archBarHtml(" + json.dumps(MODS) + ", " + json.dumps(EDGES) + ", 'a', false, false, '<PICK>', '', false)));")
        en, ko = arun(body, lang="en"), arun(body)
        self.assertTrue(en.startswith('<div class="archbar on"><button type=button class=archall data-arall title="Back (Esc)">← Back to full diagram</button><PICK>'), en)
        self.assertIn('title="돌아가기 (Esc)">← 전체 구조도로</button>', ko)
        self.assertRegex(CSS, r"\.archall\{[^}]*background:var\(--nx-info-bg")     # filled accent, not plain text
        self.assertIn("html[data-ui=next][data-ui] .archall{color:#fff}", CSS)   # light theme keeps white (5.4:1)

    def test_chrome_above_focus_map_stays_short(self):
        # ★Live 1100x860 (pane bottom ~819): hub box 824-854 with a 2-line path and the «Source text» row; 771-801 without them.
        self.assertRegex(CSS, r"\.archpath\{[^}]*flex-wrap:nowrap")                 # path stays one line
        self.assertRegex(CSS, r"\.archpath button\[data-arpath=group\]\{flex-shrink:1\}")   # only the group crumb gets «…»
        self.assertRegex(CSS, r"\.archdg\[data-fv\] \.mmdbar\{[^}]*height:0[^}]*align-items:flex-start")   # floats; button not stretched to 0

    def test_memo_hits_with_new_ents_arrays(self):
        # 84j rebuilds archFlowEntries every paint: equal-but-new ents must reuse the source without another layout.
        r = render("const _L = mmdLayout; let n = 0; mmdLayout = g => { n++; return _L(g); }; const fit = {w: 680, h: 600}, lit = {flows: D.flows, fs: null};"
                   "const s1 = archFocusSrc(M, E, false, 'hub', GR, archFlowEntries(D, M, false), false, lit, fit), n1 = n;"
                   "const k1 = archFocusKinds(M, E, false, 'hub', archFlowEntries(D, M, false), false, lit);"
                   "const s2 = archFocusSrc(M, E, false, 'hub', GR, archFlowEntries(D, M, false), false, {flows: D.flows, fs: null}, fit);"
                   "process.stdout.write(JSON.stringify([n1 > 0, n - n1, s1 === s2, Object.keys(k1).length > 0]));", self.M, self.E, self.G)
        self.assertEqual(r, [True, 0, True, True])

    def test_loc_mode_uses_plan_bands(self):
        # «apps» style: location bands; the hub (service) sits in band 2, a ui caller in band 1, folded infra in band 2
        M = self.M + [{"id": "u0", "name": "Screen", "kind": "module", "layer": "ui", "group": "fe"}]
        E = self.E + [{"from": "u0", "to": "hub", "kind": "call", "ok": True, "est": False, "label": ""}]
        r = render("const bp = archBandPlan({v: 2, style: {style: 'apps'}, groups: GR}, M, false), lb = archBandPlan({style: {style: 'layered'}}, M, false);"
                   "const P = archFocusPlan(M, E, false, 'hub', null, false, null, bp), Q = archFocusPlan(M, E, false, 'hub', null, false, null, lb);"
                   "const src = archFocusSrc(M, E, false, 'hub', GR, null, false, null, null, bp), g = mmdParse(src); archBandFix(g, bp);"
                   "const roots = g.slist.filter(s => !g.sgs[s].parent), ix = id => 'm' + M.findIndex(m => m.id === id);"
                   "const band = k => { let s = g.nodes[k].sg; while(g.sgs[s].parent) s = g.sgs[s].parent; return s; };"
                   "ARCH_FOCUS_MEMO.pa = null; ARCH_FOCUS_MEMO.a = null; const s0 = archFocusSrc(M, E, false, 'hub', GR, null, false, null, null);"
                   "ARCH_FOCUS_MEMO.pa = null; ARCH_FOCUS_MEMO.a = null; const s1 = archFocusSrc(M, E, false, 'hub', GR, null, false, null, null, lb);"
                   "process.stdout.write(JSON.stringify([P.sb, P.fl, Q.sb, roots, band(ix('hub')), band(ix('u0')), !!g.sgs.L1.tip, s0 === s1]));", M, E, self.G)
        sb, fl, qsb, roots, hub, u0, tip, same = r
        self.assertEqual([sb, fl, qsb], [2, 2, 3])                       # plan index, not ARCH_LAYERS.indexOf (service = 3)
        self.assertEqual(roots, ["L1", "L2"])
        self.assertEqual([hub, u0], ["L2", "L1"])
        self.assertTrue(tip)
        self.assertTrue(same)                                             # no plan = layer plan, same bytes


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchFocusPillClamp(unittest.TestCase):
    def test_pill_near_right_edge_stays_inside(self):
        # Badge at the right edge (x 290..300 of a 300px SVG) with a 150px pill: the pill must not run past L.w.
        js = "\n".join(["function esc(s){ return String(s); }", "function mmdTw(t){ return t.length * 7; }",
                        "function mmdFlPlace(g, L){ return {labs: L.edges.map((e, i) => ({R: L.R[i]}))}; }",
                        js_fn("archFocusPills"),
                        "const g = {edges: [{from: 'a', to: 'b'}, {from: 'c', to: 'd'}]};"
                        "const lab = {'a\\u0001b': 'x'.repeat(20), 'c\\u0001d': 'y'.repeat(60)};"
                        "const L = {w: 300, edges: [{from: 'a', to: 'b'}, {from: 'c', to: 'd'}], R: [{x: 290, y: 40, w: 10, h: 10}, {x: 150, y: 80, w: 10, h: 10}]};"
                        "const o = archFocusPills(g, L, lab);"
                        "process.stdout.write(JSON.stringify(Array.from(o.matchAll(/<rect x=\"([\\d.-]+)\" y=\"[\\d.-]+\" width=\"([\\d.]+)\"/g)).map(m => [+m[1], +m[2]])));"])
        p = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr.decode())
        (x1, w1), (x2, w2) = json.loads(p.stdout)
        self.assertGreaterEqual(x1, 0)
        self.assertLessEqual(x1 + w1, 300)                                # clamped inside the SVG
        self.assertEqual(x2, 2)                                           # wider than the SVG: left-aligned at 2


if __name__ == "__main__":
    unittest.main()
