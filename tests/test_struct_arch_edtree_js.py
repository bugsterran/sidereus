"""84j6 «Connections» flow tree on the Architecture overview (R1-R4): one fold per flow with its ordered steps plus «Not on a
traced flow» (Wiring / Calls sub-folds), flow / step hover and pin highlight, step evidence, expand / collapse all, default folded, nothing ever scrolls."""
import json
import os
import re
import shutil
import subprocess
import unittest

from sidereus.demo_rel import demo_arch
from tests._load import js_fn
from tests._node import node_e
from tests.test_struct_arch_detail_js import CONSTS, DET_FNS, DOM, PRE, FNS, SEND, J
from tests.test_struct_arch_evlit_js import EVL, EVL_FNS, LIT

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
with open(os.path.join(WEB, "js", "84j6-structure-arch-edtree.js"), encoding="utf-8") as fh:
    ET = fh.read()
ET_FNS = re.findall(r"^function (\w+)\(", ET, re.M)
MAP = demo_arch(0)   # 2 flows; steps map to edges 0, 2, 0, 3; edges 1 (import), 4 (call, failed) are in no flow
# web m0 · order m1 · common m2 · pay m3 · app m4 · db m5; only passed edges are drawn
SVG = "const svg = fakeSvg(['m0', 'm1', 'm2', 'm3', 'm4', 'm5'], [['m0', 'm1'], ['m1', 'm2'], ['m1', 'm5'], ['m1', 'm3']]);"


def run(body):
    fns = list(dict.fromkeys(FNS + DET_FNS + EVL_FNS + ET_FNS))
    js = "\n".join([PRE, CONSTS, DOM, "var ARCH_EVL = null;", "\n".join(js_fn(n) for n in fns), SEND,
                    "const D = " + json.dumps(MAP) + "; ARCH.cache['/r'] = D; ARCH.lit = null; ARCH.scope = null; ARCH.et = {};",
                    "const NAMES = {}; D.modules.forEach(m => { NAMES[m.id] = m.name; });", SVG, LIT,
                    "const H = () => archEdTreeHtml(ARCH.cache['/r'], NAMES, '/r', {op: ARCH.op, et: ARCH.et, dv: {}, sn: ''});",
                    "(async () => {\n" + body + "\n})().catch(e => { console.error(e); process.exit(1); });"])
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchEdTree(unittest.TestCase):
    def test_R1_flows_steps_and_other(self):
        r = run("const t = archEdTree(D); archEdTreeClick('/r', {aetall: '1'});"
                "console.log(JSON.stringify([t.flows.map(f => [f.n, f.id, f.mods, f.steps.map(s => s.ei)]), t.other, H()]));")
        fl, other, h = r
        self.assertEqual(fl, [[0, "get-order", 3, [0, 2]], [1, "pay-order", 3, [0, 3]]])
        self.assertEqual(other, {"w": [1], "c": [4]})
        self.assertEqual(re.findall(r'data-aet="(\d+)"', h), ["0", "1"])
        self.assertEqual(re.findall(r'data-ats="([\d.]+)"', h), ["0.0", "0.1", "1.0", "1.1"])   # ordered steps
        self.assertEqual(re.findall(r'data-ae="(\d+)"', h), ["1", "4"])                         # Other: today's rows, passed first
        self.assertIn("추적된 흐름 밖 · 2 · 미검증 1", h)
        self.assertIn("배선 (1)", h)
        self.assertIn("호출 (1)", h)
        self.assertIn("(모듈 3개 · 2단계)", h)
        self.assertIn("<em class=archsk>2</em><b>order</b><i>→</i><b>PostgreSQL</b>", h)       # «k  from → to», 1-based

    def test_R1_all_verified_label(self):
        r = run("const D4 = JSON.parse(JSON.stringify(D)); D4.edges[4].ok = true;"
                "console.log(JSON.stringify(archEdTreeHtml(D4, NAMES, '/r', {op: '', et: {}})));")
        self.assertIn("추적된 흐름 밖 · 2 · 모두 검증됨", r)

    def test_R1_ok_preferred_and_duplicate_pair_credited(self):
        r = run("const D2 = JSON.parse(JSON.stringify(D)); D2.edges.unshift(Object.assign({}, D2.edges[0], {ok: false}));"
                "D2.flows[0].name = 'A <b>'; const t = archEdTree(D2);"
                "const D3 = JSON.parse(JSON.stringify(D)); D3.edges[3].ok = false; const u = archEdTree(D3);"
                "console.log(JSON.stringify([t.flows[0].steps.map(s => s.ei), t.other, u.flows[1].steps[1].ei,"
                " archEdTreeHtml(D2, NAMES, '/r', {op: '', et: {'/r\\t0': true}}), t.flows[0].steps[0].eis]));")
        self.assertEqual(r[0], [1, 3])                   # the passed web -> order edge, not the failed one before it
        self.assertEqual(r[1], {"w": [2], "c": [5]})     # both edges on the step's pair are credited to the flow
        self.assertEqual(r[4], [0, 1])
        self.assertIn("같은 쌍 +1", r[3])
        self.assertEqual(r[2], 3)                        # no passed edge: first one with the pair
        self.assertIn("<b>A &lt;b&gt;</b>", r[3])        # flow name escaped, not translated

    def test_R2_hover_flow_step_and_leave(self):
        r = run("ARCH.scope = {p: '/r', layer: 'x', group: null}; const P = () => { archLitPaint(svg, archLitSet(ARCH.cache['/r'], archLitQ('/r'))); return lit(svg); };"
                "const before = P(); const o = [];"
                "ARCH_EVL = {p: '/r', f: 0}; o.push(archLitQ('/r'), P());"
                "ARCH_EVL = {p: '/r', f: 1, s: 1}; o.push(archLitQ('/r'), P());"
                "ARCH_EVL = null; o.push(P(), before);"
                "const D3 = JSON.parse(JSON.stringify(D)); D3.flows[0].steps.push({from: 'app', to: 'common', ok: false, evidence: {}}); ARCH.cache['/r'] = D3;"
                "ARCH_EVL = {p: '/r', f: 0, s: 2}; o.push(archLitQ('/r'), P());"
                "o.push([archEvlKey('/r', {dataset: {aet: '1'}}), archEvlKey('/r', {dataset: {ats: '0.1'}}), archEvlKey('/r', {dataset: {ae: '3'}}), archEvlKey('/r', {dataset: {}})]);"
                "console.log(JSON.stringify(o));")
        self.assertEqual(r[0], {"flow": "get-order", "tests": False})
        self.assertEqual(r[1][0], ["m0", "m1", "m5"])                       # whole flow
        self.assertEqual(r[1][1], ["m0>m1", "m1>m5"])
        self.assertEqual(r[2], {"edge": 3, "tests": False})                 # step: its own edge, no flow widening
        self.assertEqual(r[3][0], ["m1", "m3"])
        self.assertEqual(r[3][1], ["m1>m3"])
        self.assertEqual(r[3][2], ["m1>m3"])                                # .arevk
        self.assertEqual(r[4], r[5])                                        # leaving restores
        self.assertEqual(r[6], {"mods": ["app", "common"], "tests": False})  # step with no edge
        self.assertEqual(r[7][0], ["m2", "m4"])
        self.assertEqual(r[8], [{"p": "/r", "f": 1}, {"p": "/r", "f": 0, "s": 1}, {"p": "/r", "i": 3}, None])

    def test_R3_pin_flow_and_step_evidence_stale(self):
        r = run("const o = []; archEdTreeClick('/r', {aet: '0'}); o.push(ARCH.op, ARCH.et['/r\\t0'], archLitQ('/r'));"
                "archEdTreeClick('/r', {aet: '0'}); o.push(ARCH.op);"
                "archEdTreeClick('/r', {aet: '1'}); archEdTreeClick('/r', {ats: '1.1'}); o.push(ARCH.op, archLitQ('/r'), H());"
                "ARCH_EVL = {p: '/r', f: 0}; o.push(archLitQ('/r').flow); ARCH_EVL = null;"   # hover beats the pin
                "archEdTreeClick('/r', {ats: '1.1'}); o.push(ARCH.op);"
                "ARCH.scope = {p: '/r', layer: 'x', group: null}; ARCH.op = '/r\\tf9'; o.push(archLitQ('/r')); ARCH.op = '/r\\tf0.9'; o.push(archLitQ('/r'));"
                "ARCH_EVL = {p: '/r', f: 7}; o.push(archLitQ('/r'));"
                "console.log(JSON.stringify(o));")
        self.assertEqual(r[0:3], ["/r\tf0", True, {"flow": "get-order", "tests": False}])   # pin opens the flow
        self.assertEqual(r[3], "")                                                          # same node again unpins
        self.assertEqual(r[4], "/r\tf1.1")
        self.assertEqual(r[5], {"edge": 3, "tests": False})
        self.assertIn('data-aev="f1.1"', r[6])                                              # pinned step shows its evidence
        self.assertIn("order/OrderService.java", r[6])
        self.assertEqual(r[7], "get-order")
        self.assertEqual(r[8], "")
        for q in r[9:12]:
            self.assertEqual(q, {"layer": "x", "group": None})                              # stale n / k falls back

    def test_R3_empty_space_clears_tree_pin(self):
        empty = re.search(r"^  if\(ARCH\.op && t\.closest\('\.archmap,\.archel-list'\).*$", J, re.M).group(0)
        r = run("const T0 = sel => ({closest(q){ return q.split(',').some(x => sel.indexOf(x) >= 0) ? {} : null; }});"
                "const empty = (t, p) => { " + empty + " }; ARCH.op = '/r\\tf0.1'; empty(T0(['.archel-list', 'button']), '/r'); const a = ARCH.op;"
                "empty(T0(['.archel-list']), '/r'); console.log(JSON.stringify([a, ARCH.op]));")
        self.assertEqual(r, ["/r\tf0.1", ""])

    def test_R4_default_folded_expand_collapse_caret(self):
        r = run("const o = [H()]; archEdTreeClick('/r', {aetall: '1'}); o.push(H(), Object.keys(ARCH.et).sort());"
                "archEdTreeClick('/r', {aetall: '0'}); o.push(H()); archEdTreeClick('/r', {aetf: '1'}); o.push(H(), ARCH.op);"
                "archEdTreeClick('/r', {aet: 'other'}); o.push(H()); archEdTreeClick('/r', {aet: 'other.c'}); o.push(H(), ARCH.op);"
                "console.log(JSON.stringify(o));")
        d0, all1, keys, all0, car, op, oth, othc, op2 = r
        self.assertNotIn("data-ats", d0)
        self.assertNotIn("data-ae=", d0)
        self.assertEqual(d0.count("aria-expanded=false"), 3)
        self.assertIn("data-aetall=1", d0)
        self.assertIn("data-aetall=0", d0)
        self.assertEqual(all1.count("data-ats"), 4)
        self.assertEqual(keys, ["/r\t0", "/r\t1", "/r\tother", "/r\tother.c", "/r\tother.w"])
        self.assertEqual(all0, d0)
        self.assertEqual(re.findall(r'data-ats="([\d.]+)"', car), ["1.0", "1.1"])   # caret folds only
        self.assertEqual(op, "")
        self.assertEqual(re.findall(r'data-ae="(\d+)"', oth), [])                      # sub-folds start folded
        self.assertEqual(re.findall(r'data-aet="(other[.\w]*)"', oth), ["other.w", "other.c"])
        self.assertEqual(re.findall(r'data-ae="(\d+)"', othc), ["4"])                 # only Calls opened
        self.assertEqual(op2, "")                                                     # a sub-fold toggle pins nothing

    def test_R4_fold_hiding_pinned_row_unpins(self):
        r = run("const o = []; archEdTreeClick('/r', {aetall: '1'}); archEdTreeClick('/r', {ats: '1.0'}); o.push(ARCH.op);"
                "archEdTreeClick('/r', {aetall: '0'}); o.push(ARCH.op);"
                "archEdTreeClick('/r', {aetall: '1'}); archEdTreeClick('/r', {ats: '1.0'}); archEdTreeClick('/r', {aetf: '1'}); o.push(ARCH.op);"
                "archEdTreeClick('/r', {aet: '1'}); archEdTreeClick('/r', {aetall: '0'}); o.push(ARCH.op);"
                "archEdTreeClick('/r', {aet: 'other'}); ARCH.op = '/r\\t4'; archEdTreeClick('/r', {aetf: '0'}); o.push(ARCH.op);"
                "archEdTreeClick('/r', {aet: 'other'}); o.push(ARCH.op);"
                "ARCH.op = '/r\\t4'; archEdTreeClick('/r', {aetf: '0'}); o.push(ARCH.op);"   # already folded: a map pin stays
                "archEdTreeClick('/r', {aetall: '1'}); ARCH.op = '/r\\t4'; archEdTreeClick('/r', {aet: 'other.w'}); o.push(ARCH.op);"
                "archEdTreeClick('/r', {aetf: 'other.c'}); o.push(ARCH.op);"
                "console.log(JSON.stringify(o));")
        self.assertEqual(r[0], "/r\tf1.0")
        self.assertEqual(r[1], "")                          # Collapse all hid the pinned step
        self.assertEqual(r[2], "")                          # its flow's caret hid it
        self.assertRegex(r[3], r"\tf1$")                    # a pinned flow node stays visible, stays pinned
        self.assertEqual(r[4], "/r\t4")
        self.assertEqual(r[5], "")                          # folding Other hid the pinned edge
        self.assertEqual(r[6], "/r\t4")
        self.assertEqual(r[7], "/r\t4")                    # folding Wiring does not hide a Calls row
        self.assertEqual(r[8], "")                          # folding its own Calls sub-fold does

    def test_file_rules(self):
        for bad in ("scrollTo", "scrollIntoView", "archLitGo", "archScrollAt", "scrollTop", "scrollLeft", ".focus("):
            self.assertNotIn(bad, ET)
            self.assertNotIn(bad, EVL)
        for attr in ("data-arnx", "data-arnall", "data-afs"):
            self.assertNotIn(attr, ET)
        self.assertNotRegex(ET, r"[가-힣]")
        self.assertNotIn("T(f.name", ET)
        self.assertIn("archEdTreeHtml", J)
        self.assertIn("ARCH.et", J)
        self.assertLess(len(J.splitlines()), 700)
        names = sorted(os.listdir(os.path.join(WEB, "js")))
        self.assertLess(names.index("84j5-structure-arch-evlit.js"), names.index("84j6-structure-arch-edtree.js"))
        self.assertLess(names.index("84j6-structure-arch-edtree.js"), names.index("84k-structure-arch-flow.js"))


if __name__ == "__main__":
    unittest.main()
