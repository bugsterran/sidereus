"""84j3 module detail on the Architecture map (R1-R4): side panel fields and neighbour tree, flows through a module and their
highlight, path bar + one-level-up chain + Esc guards, no view movement; plus 84j archReduce keeping cross-layer pairs."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e
from tests.test_struct_arch_js import PRE, FNS, SEND

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
DET_P = os.path.join(WEB, "js", "84j3-structure-arch-detail.js")
with open(DET_P, encoding="utf-8") as fh:
    DET = fh.read()
with open(os.path.join(WEB, "js", "84j-structure-arch.js"), encoding="utf-8") as fh:
    J = fh.read()
DET_FNS = re.findall(r"^function (\w+)\(", DET, re.M)
CONSTS = "\n".join(re.findall(r"^const ARCH_NBR_\w+ = .*$", DET, re.M))
# Fake svg: nodes [data-p] and edge groups .mmdfe with a Set-backed classList (enough for archHovPaint / archLitPaint).
DOM = """
const cl = () => { const s = new Set(); return { s, toggle(k, on){ if(on) s.add(k); else s.delete(k); }, contains(k){ return s.has(k); } }; };
const el = ds => ({ dataset: ds, classList: cl() });
function fakeSvg(nodes, edges){ const ns = nodes.map(p => el({p})), es = edges.map(e => el({f: e[0], t: e[1]}));
  return { ns, es, classList: cl(), querySelectorAll(q){ return q === '[data-p]' ? ns : q === '.mmdfe' ? es : []; } }; }
"""

MODS = [{"id": "web", "name": "Web <b>", "path": "web/", "kind": "module", "layer": "ui", "group": "front", "summary": "Page <i>x</i>",
         "owns": ["db"]},
        {"id": "srv", "name": "Server", "path": "srv/", "kind": "module", "layer": "api", "group": "back"},
        {"id": "svc", "name": "Svc", "path": "svc/", "kind": "module", "layer": "service", "group": "back"},
        {"id": "db", "name": "DB", "path": "db/", "kind": "store", "ext": "db", "layer": "data", "group": "back"}]
GROUPS = [{"id": "front", "name": "Front <x>"}, {"id": "back", "name": "Back"}]
EDGES = [{"from": f, "to": t, "kind": k, "label": "", "ok": ok, "est": False, "evidence": []} for f, t, k, ok in
         [("web", "srv", "call", True), ("srv", "svc", "call", True), ("svc", "db", "read", True), ("svc", "db", "write", True),
          ("srv", "web", "event", True), ("web", "db", "import", False)]]
FLOWS = [{"id": "f1", "name": "Order <s>", "ok": True, "steps": [{"from": "web", "to": "srv", "ok": True}, {"from": "srv", "to": "svc", "ok": True},
                                                                  {"from": "svc", "to": "db", "ok": True}]},
         {"id": "f2", "name": "Other", "ok": False, "steps": [{"from": "svc", "to": "db", "ok": False}]}]
MAP = {"ok": True, "v": 2, "commit": "c1", "modules": MODS, "groups": GROUPS, "edges": EDGES, "flows": FLOWS}


def run(body, lang="ko"):
    pre = PRE if lang == "ko" else PRE.replace("const LANG = 'ko';", "const LANG = 'en';", 1)
    fns = list(dict.fromkeys(FNS + DET_FNS))
    js = "\n".join([pre, CONSTS, DOM, "\n".join(js_fn(n) for n in fns), SEND,
                    "const D = " + json.dumps(MAP) + "; const NAMES = {}; D.modules.forEach(m => { NAMES[m.id] = m.name; });",
                    "(async () => {\n" + body + "\n})().catch(e => { console.error(e); process.exit(1); });"])
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchDetail(unittest.TestCase):
    def test_r1_panel_fields_escaped(self):
        h = run("console.log(JSON.stringify(archDetHtml(D, 'web', NAMES, {}, {})));")
        self.assertIn("Web &lt;b&gt;", h)
        self.assertIn("Page &lt;i&gt;x&lt;/i&gt;", h)          # summary escaped, not translated
        self.assertIn("<dd>UI</dd>", h)                         # layer label through ARCH_LAYER_LBL
        self.assertIn("<dd>Front &lt;x&gt;</dd>", h)            # group id -> its name, escaped
        self.assertIn("<dd>DB</dd>", h)                         # owns ids -> module names
        self.assertNotIn("<b>Web <b>", h)
        self.assertIn('data-arnall=1', h)
        self.assertIn('data-arnall=0', h)

    def test_r1_neighbours_grouped(self):
        r = run("const h = archNbrTree(D, 'web', NAMES, {}, {}), f = archNbrTree(D, 'web', NAMES, {out: true}, {}),"
                " k = archNbrTree(D, 'web', NAMES, {'out:call': true}, {});"
                "console.log(JSON.stringify([h, f, k]));", lang="en")
        h, f, k = r
        self.assertEqual(re.findall(r'data-arnx="([^"]+)"', h), ["out", "out:call", "out:other", "in", "in:event"])   # import -> Other
        self.assertIn("Calls", h)
        self.assertIn("Events", h)
        self.assertEqual(h.count('data-ae='), 3)                # every touching edge once, existing evidence toggle
        self.assertNotIn('data-arnx="out:call"', f)             # folded Out hides its kinds
        self.assertIn('aria-expanded=false', f)
        self.assertIn('data-arnx="out:call"', k)
        self.assertEqual(k.count('data-ae='), 2)                # folded Calls hides its leaf only

    def test_r1_ko_labels(self):
        h = run("console.log(JSON.stringify(archDetHtml(D, 'svc', NAMES, {}, {})));")
        for s in ("이웃 모듈", "읽기", "쓰기", "이 모듈을 지나는 흐름", "층"):
            self.assertIn(s, h)

    def test_r2_flows_via_and_counts(self):
        r = run("const dr = archDrawn(D.modules, D.edges, false, 'web', false);"
                "console.log(JSON.stringify([archFlowsVia(D, 'web', dr).map(x => [x.f.id, x.on, x.n]), archFlowsVia(D, 'db', null).map(x => x.f.id),"
                " archDetHtml(D, 'web', NAMES, {}, {drawn: dr, lit: 'f1'})]));", lang="en")
        self.assertEqual(r[0], [["f1", 1, 3]])                  # only web->srv is on the focus view of web
        self.assertEqual(r[1], ["f1", "f2"])
        self.assertIn("1/3 steps on this view", r[2])
        self.assertIn('data-arfx="f1" aria-pressed=true', r[2])
        self.assertIn("Order &lt;s&gt;", r[2])

    def test_r2_lit_set_and_survives_hover(self):
        r = run("const s = archLitSet(D, {flow: 'f1'}), g = archLitSet(D, {layer: 'service', group: null}), b = archLitSet(D, {layer: 'api', group: 'back'});"
                "const svg = fakeSvg(['m0', 'm1', 'm2', 'm3'], [['m0', 'm1'], ['m1', 'm2'], ['m2', 'm3'], ['m1', 'm0']]);"
                "archLitPaint(svg, s); archHovPaint(svg, {node: 'm0'}); archHovPaint(svg, null);"
                "const lit = svg.ns.filter(n => n.classList.contains('arlit')).map(n => n.dataset.p), le = svg.es.filter(e => e.classList.contains('arlit')).length;"
                "const dim = svg.classList.contains('arlitdim'), hov = svg.classList.contains('archdim'); archLitPaint(svg, null);"
                "console.log(JSON.stringify([[...s.n].sort(), s.e.size, [...g.n], [...b.n], lit, le, dim, hov, svg.classList.contains('arlitdim'),"
                " svg.ns.some(n => n.classList.contains('arlit')), archLitSet(D, null), archLitSet(D, {layer: ''})]));")
        self.assertEqual(r[0], ["m0", "m1", "m2", "m3"])
        self.assertEqual(r[1], 6)                               # both directions of each of 3 steps
        self.assertEqual(r[2], ["m2"])
        self.assertEqual(r[3], ["m1"])
        self.assertEqual(r[4], ["m0", "m1", "m2", "m3"])        # hover in + out leaves .arlit alone
        self.assertEqual(r[5], 4)
        self.assertEqual(r[6:8], [True, False])
        self.assertEqual(r[8:10], [False, False])               # null clears
        self.assertIsNone(r[10])
        self.assertIsNone(r[11])

    def test_R2_litset_includes_entry_and_steps(self):
        fl = [dict(FLOWS[0], entry={"kind": "http", "label": "GET /o"}), dict(FLOWS[1], entry={"kind": "http", "label": "GET /o"})]
        r = run("globalThis.archFlowEntries = " + js_fn("archFlowEntries") + ";"
                "const D2 = Object.assign({}, D, {flows: " + json.dumps(fl) + "}), s = archLitSet(D2, {flow: 'f1'}), t = archLitSet(D2, {flow: 'f2'});"
                "console.log(JSON.stringify([[...s.n].sort(), s.e.has('en0\\u0001m0'), s.e.has('en0\\u0001m2'), [...t.n].sort(), t.e.has('en0\\u0001m2'),"
                " archLitSet(D, {flow: 'f1'}).n.has('en0')]));")
        self.assertEqual(r[0], ["en0", "m0", "m1", "m2", "m3"])   # entry node + path modules
        self.assertEqual(r[1:3], [True, False])                    # only the edge to this flow's first module
        self.assertEqual(r[3], ["en0", "m2", "m3"])                # shared entry node lights for either flow
        self.assertTrue(r[4])
        self.assertFalse(r[5])                                     # no entry on the flow: no entry node

    def test_R2_unproven_step_in_x(self):
        r = run("const s = archLitSet(D, {flow: 'f2'}), ok = archLitSet(D, {flow: 'f1'});"
                "const svg = fakeSvg(['m2', 'm3'], [['m2', 'm3'], ['m1', 'm2']]); archLitPaint(svg, s);"
                "const fx = svg.es.map(e => e.classList.contains('archfx')); archLitPaint(svg, null);"
                "console.log(JSON.stringify([[...s.x].sort(), ok.x.size, fx, svg.es.some(e => e.classList.contains('archfx'))]));")
        self.assertEqual(r[0], ["m2\u0001m3", "m3\u0001m2"])
        self.assertEqual(r[1], 0)
        self.assertEqual(r[2], [True, False])                      # unproven step keeps --nx-err inside the highlight
        self.assertFalse(r[3])
        with open(os.path.join(WEB, "css", "79-structure-arch.css"), encoding="utf-8") as fh:
            css = fh.read()
        self.assertIn(".mmdfe.arlit.archfx .mmde{stroke:var(--nx-err", css)

    def test_R3_esc_clears_lit_first(self):
        r = run("ARCH.cache['/r'] = D; ARCH.sel = {p: '/r', id: 'web'}; ARCH.scope = null; ARCH.lit = {p: '/r', flow: 'f1'}; ARCH.flow = {p: '/r', id: 'f1'};"
                "const o = []; for(let i = 0; i < 5; i++){ const h = archEscStep('/r'); o.push([h, ARCH.lit, ARCH.flow, ARCH.sel, ARCH.scope]); }"
                "console.log(JSON.stringify(o));")
        self.assertEqual(r[0], [True, None, None, {"p": "/r", "id": "web"}, None])   # first press: highlight + sequence view only
        self.assertEqual(r[1][0], True)
        self.assertIsNone(r[1][3])                                 # then one level up
        self.assertEqual(r[-1][0], False)                          # top: not handled, Esc passes on

    def test_r3_path_variants(self):
        r = run("console.log(JSON.stringify([archPathHtml(D.modules, D.groups, 'web', null), archPathHtml(D.modules, D.groups, '', {layer: 'api', group: 'back'}),"
                " archPathHtml(D.modules, D.groups, '', {layer: 'api', group: null}), archPathHtml(D.modules, D.groups, '', null),"
                " archPathHtml([{id: 'a', name: 'A'}], [], 'a', null)]));", lang="en")
        lv = [re.findall(r"data-arpath=(\w+)", h) for h in r]
        self.assertEqual(lv[0], ["all", "layer", "group", "mod"])
        self.assertIn("Front &lt;x&gt;", r[0])
        self.assertIn("Web &lt;b&gt;</button>", r[0])
        self.assertEqual(lv[1], ["all", "layer", "group"])
        self.assertEqual(lv[2], ["all", "layer"])
        self.assertEqual(r[3], "")
        self.assertEqual(lv[4], ["all", "mod"])                 # v1 module: no layer/group segments
        self.assertEqual(r[0].count("aria-current"), 1)

    def test_r3_up_chain(self):
        r = run("const M = D.modules, s = []; let st = {sel: 'web', scope: null};"
                "for(let i = 0; i < 5; i++){ const u = archUp(st, M); s.push(u); if(!u) break; st = {sel: '', scope: u.scope}; }"
                "console.log(JSON.stringify([s, archUp({sel: 'web', scope: null}, [{id: 'web'}])]));")
        self.assertEqual(r[0], [{"scope": {"layer": "ui", "group": "front"}}, {"scope": {"layer": "ui", "group": None}}, {"scope": None}, None])
        self.assertEqual(r[1], {"scope": None})                 # v1 module goes straight to All

    def test_r3_esc_guards(self):
        r = run("const st = {view: 'struct', mode: 'arch', pop: false, pal: false}, E = (o, t) => Object.assign({key: 'Escape', target: t || {tagName: 'DIV'}}, o);"
                "console.log(JSON.stringify([archEscOk(E({}), st), archEscOk(E({key: 'Enter'}), st), archEscOk(E({defaultPrevented: true}), st),"
                " archEscOk(E({isComposing: true}), st), archEscOk(E({}, {tagName: 'INPUT'}), st), archEscOk(E({}, {tagName: 'SELECT'}), st),"
                " archEscOk(E({}, {tagName: 'TEXTAREA'}), st), archEscOk(E({}, {tagName: 'DIV', isContentEditable: true}), st),"
                " archEscOk(E({}), Object.assign({}, st, {pop: true})), archEscOk(E({}), Object.assign({}, st, {pal: true})),"
                " archEscOk(E({}), Object.assign({}, st, {mode: 'size'})), archEscOk(E({}), Object.assign({}, st, {view: 'tl'}))]));")
        self.assertEqual(r, [True] + [False] * 11)
        self.assertRegex(DET, r"addEventListener\('keydown', e => \{[\s\S]*?\}, true\);")   # capture: before 35c closes the popup

    def test_r4_no_view_movement(self):
        for bad in ("scrollIntoView", "scrollTo(", "scrollBy(", ".focus("):
            self.assertNotIn(bad, DET)
        sig = re.search(r"const sig = \[.*$", J, re.M).group(0)
        self.assertIn("ARCH.scope", sig)
        self.assertIn("ARCH.lit", sig)
        self.assertIn("ARCH.nx", sig)
        self.assertIn("keep('.archdet')", J)
        self.assertIn("put('.archdet', sd)", J)

    def test_r4_paint_detail_and_scroll_kept(self):
        r = run("ARCH.scope = null; ARCH.lit = null; ARCH.nx = {}; ARCH.flow = null; ARCH.cache['/r'] = D;"
                "globalThis.archFlowAt = d => ({fls: d.flows, fi: -1}); globalThis.archFlowPick = () => ''; globalThis.archMmd = () => '';"
                "const sc = {'.archmap': {scrollTop: 40, scrollLeft: 7}, '.archdet': {scrollTop: 90, scrollLeft: 0}};"
                "const box = {innerHTML: '', querySelector(q){ return sc[q] || null; }}; box._arp = '/r';"
                "archPaint(box, head); const ov = box.innerHTML; ARCH.sel = {p: '/r', id: 'srv'}; sc['.archdet'].scrollTop = 0; sc['.archmap'].scrollTop = 0;"
                "sc['.archdet'].scrollTop = 90; sc['.archmap'].scrollTop = 40; archPaint(box, head); const fo = box.innerHTML;"
                "const k1 = box._arsig; ARCH.scope = {p: '/r', layer: 'api', group: null}; ARCH.sel = null; archPaint(box, head);"
                "console.log(JSON.stringify([ov, fo, box.innerHTML, k1 !== box._arsig, sc['.archdet'].scrollTop, sc['.archmap'].scrollTop]));", lang="en")
        ov, fo, sp, changed, sd, sm = r
        self.assertNotIn("archpath", ov)                        # overview with no level: no path bar
        self.assertIn("archel-list", ov)
        self.assertIn("class=archdet", fo)
        self.assertIn("data-arpath=mod", fo)
        self.assertLess(fo.index("archpath"), fo.index("archbar"))   # path bar first in .archtop
        self.assertNotIn("archel-list", fo.split("archside")[1].split("</aside>")[0].replace("archnxl", ""))
        self.assertIn("data-arpath=layer aria-current", sp)
        self.assertTrue(changed)
        self.assertEqual([sd, sm], [90, 40])

    def test_lit_classes_separate_css(self):
        with open(os.path.join(WEB, "css", "79-structure-arch.css"), encoding="utf-8") as fh:
            css = fh.read()
        lit = [ln for ln in css.splitlines() if "arlitdim" in ln and not ln.startswith("/*")]
        self.assertTrue(lit)
        for ln in lit:
            self.assertNotIn("opacity", ln)                     # always-on state: colour only
            self.assertNotIn(".arn", ln)

    def test_det_file_rules(self):
        self.assertNotRegex(DET, r"[가-힣]")
        self.assertIsNone(re.search(r"^ARCH\.", DET, re.M))      # ARCH fields only inside functions
        self.assertLess(len(J.splitlines()), 700)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchReduceLayers(unittest.TestCase):
    """The overview reduction may hide a cross-layer pair; the focused module's panel still lists it (and keeps every edge)."""

    def test_hidden_cross_layer_pair_in_panel(self):
        m = [{"id": i, "name": i, "kind": "module", "layer": ly, "group": "g"} for i, ly in
             (("u1", "ui"), ("u2", "ui"), ("u3", "ui"), ("ep", "api"))]
        es = [{"from": f, "to": t, "kind": "config", "label": "", "ok": True, "est": est, "evidence": []} for f, t, est in
              (("u1", "u2", False), ("u2", "u3", False), ("u3", "ep", False), ("u1", "ep", True))]
        r = run("const m = " + json.dumps(m) + ", es = " + json.dumps(es) + ", d = {modules: m, edges: es}, nm = {};"
                "m.forEach(x => { nm[x.id] = x.name; }); const k = ps => ps.map(p => p.from + '>' + p.to);"
                "console.log(JSON.stringify([k(archReduce(archPairs(m, es, false))), archNbrTree(d, 'u1', nm, {}, {})]));", lang="en")
        self.assertEqual(r[0], ["u1>u2", "u2>u3", "u3>ep"])     # reduction unchanged: the est shortcut u1->ep is hidden
        self.assertIn('data-ae="3"', r[1])                      # ...but u1's panel lists u1 -> ep
        self.assertIn("<b>ep</b>", r[1])
        self.assertNotIn("p.x", J)                              # no cross-layer exemption in archReduce


if __name__ == "__main__":
    unittest.main()
