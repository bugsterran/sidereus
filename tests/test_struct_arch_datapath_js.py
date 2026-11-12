"""84jb store «Data path» (R1-R4): which flow entry points write or read a store, from the verified map, flows and verdicts only."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e
from tests.test_struct_arch_js import PRE

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
DP_P = os.path.join(WEB, "js", "84jb-structure-arch-datapath.js")
with open(DP_P, encoding="utf-8") as fh:
    DP = fh.read()
FNS = ["archDataPath", "archDataPathHtml", "archDataPathClick", "archFlowKind"]
KIND = "const ARCH_FLOW_KIND = {http: 'HTTP'};"
# Fake DOM for the click handler: closest() walks a one-level parent chain.
DOM = """
let HOLD = null; function kbHold(...s){ HOLD = s; }
const tab = { closest(q){ return q === '.archtab' ? tab : null; } };
function btn(id){ const b = { dataset: { ardp: id }, closest(q){ return q === '[data-ardp]' ? b : q === '.archtab' ? tab : null; } }; return b; }
document.activeElement = null;
"""


def mod(i, kind="module"):
    return {"id": i, "name": i.upper(), "path": i + "/", "kind": kind}


def edge(f, t, k, ok=True, est=False):
    return {"from": f, "to": t, "kind": k, "label": "", "ok": ok, "est": est, "evidence": []}


def step(f, t, ok=True, est=0):
    return {"from": f, "to": t, "ok": ok, "est": est}


def flow(i, steps, label="GET /", name=None):
    return {"id": i, "name": name or ("Flow " + i), "ok": True, "entry": {"kind": "http", "label": label}, "steps": steps}


MODS = [mod("web"), mod("srv"), mod("svc"), mod("db", "store"), mod("cache", "store"), mod("idle", "store")]


def run(body, d, lang="en"):
    pre = PRE if lang == "ko" else PRE.replace("const LANG = 'ko';", "const LANG = 'en';", 1)
    js = "\n".join([pre, KIND, DOM, "\n".join(js_fn(n) for n in FNS),
                    "const D = " + json.dumps(d) + ";",
                    "(async () => {\n" + body + "\n})().catch(e => { console.error(e); process.exit(1); });"])
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


def dp(d, sid):
    return run("const x = archDataPath(D, " + json.dumps(sid) + ");"
               "console.log(JSON.stringify(x && {w: x.w.map(r => [r.f.id, r.est]), r: x.r.map(r => [r.f.id, r.est])}));", d)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchDataPath(unittest.TestCase):
    def test_R1_write_through_steps_and_read_side(self):
        d = {"modules": MODS, "edges": [edge("svc", "db", "write"), edge("svc", "cache", "read")],
             "flows": [flow("f1", [step("web", "srv"), step("srv", "svc")])]}
        self.assertEqual(dp(d, "db"), {"w": [["f1", False]], "r": []})
        self.assertEqual(dp(d, "cache"), {"w": [], "r": [["f1", False]]})

    def test_R1_row_and_click(self):
        d = {"modules": MODS, "edges": [edge("svc", "db", "write")], "flows": [flow("f1", [step("srv", "svc")], label="POST /o")]}
        r = run("const h = archDataPathHtml(D, D.modules[3], null), on = archDataPathHtml(D, D.modules[3], 'f1');"
                "ARCH.flow = null; ARCH.lit = null; const b = btn('f1'); document.activeElement = b;"
                "const hit = archDataPathClick(b), a = [ARCH.flow, ARCH.lit, PAINTS, HOLD];"
                "const again = archDataPathClick(b);"
                "console.log(JSON.stringify([h, on, hit, a, again, ARCH.flow, ARCH.lit]));", d)
        h, on, hit, a, again, fl2, lit2 = r
        self.assertIn('data-ardp="f1"', h)
        self.assertIn("Written by", h)
        self.assertNotIn("Read by", h)                         # empty side omitted
        self.assertIn("<em class=archk>HTTP</em> POST /o", h)
        self.assertIn("aria-pressed=true class=on", on)
        self.assertTrue(hit)
        self.assertEqual(a[0], {"p": "/r", "id": "f1"})         # opens the existing sequence view of that flow
        self.assertEqual(a[1], {"p": "/r", "flow": "f1"})
        self.assertEqual(a[2], 1)
        self.assertIn('.archdet [data-ardp="f1"]', a[3])        # keyboard focus kept across the repaint
        self.assertTrue(again)
        self.assertIsNone(fl2)                                  # second press on the same flow closes the view
        self.assertEqual(lit2, {"p": "/r", "flow": "f1"})

    def test_R1_ko_labels(self):
        d = {"modules": MODS, "edges": [edge("svc", "db", "write"), edge("svc", "db", "read")], "flows": [flow("f1", [step("srv", "svc")])]}
        h = run("console.log(JSON.stringify([archDataPathHtml(D, D.modules[3], null), archDataPathHtml(D, D.modules[5], null)]));", d, lang="ko")
        for s in ("데이터 경로", "쓰는 곳", "읽는 곳"):
            self.assertIn(s, h[0])
        self.assertIn("이 저장소에 닿는 진입점 없음", h[1])

    def test_R2_direct_step_both_kinds(self):
        d = {"modules": MODS, "edges": [edge("svc", "db", "read"), edge("svc", "db", "write")], "flows": [flow("f1", [step("svc", "db")])]}
        self.assertEqual(dp(d, "db"), {"w": [["f1", False]], "r": [["f1", False]]})

    def test_R2_failed_edge_or_step_left_out(self):
        d = {"modules": MODS, "edges": [edge("svc", "db", "write", ok=False), edge("srv", "db", "read")],
             "flows": [flow("f1", [step("web", "svc")]), flow("f2", [step("web", "srv", ok=False)]),
                       flow("f3", [step("web", "srv", ok=False), step("srv", "svc")])]}
        self.assertEqual(dp(d, "db"), {"w": [], "r": [["f3", False]]})   # f3 reaches srv through its ok step only

    def test_R2_estimate_rule(self):
        d = {"modules": MODS, "edges": [edge("svc", "db", "write"), edge("srv", "db", "write", est=True)],
             "flows": [flow("f1", [step("web", "svc", est=1)]),                          # only route via an est step
                       flow("f2", [step("web", "svc", est=1), step("svc", "x")]),         # a second non-est route wins
                       flow("f3", [step("web", "srv")]),                                  # est edge
                       flow("f4", [step("web", "srv"), step("srv", "svc")])]}             # est edge + non-est route
        self.assertEqual(dp(d, "db"), {"w": [["f1", True], ["f2", False], ["f3", True], ["f4", False]], "r": []})
        h = run("console.log(JSON.stringify(archDataPathHtml(D, D.modules[3], null)));", d)
        self.assertEqual(h.count("archbg archest"), 2)

    def test_R3_unreached_store_and_hidden_cases(self):
        d = {"modules": MODS, "edges": [edge("svc", "db", "write")], "flows": [flow("f1", [step("web", "srv")])]}
        r = run("console.log(JSON.stringify([archDataPathHtml(D, D.modules[5], null), archDataPathHtml(D, D.modules[3], null),"
                " archDataPathHtml(D, D.modules[2], null), archDataPathHtml(Object.assign({}, D, {flows: []}), D.modules[3], null),"
                " archDataPathHtml({modules: D.modules, edges: D.edges}, D.modules[3], null), archDataPathHtml(D, null, null),"
                " archDataPath(D, 'nope')]));", d)
        self.assertIn("No entry point reaches this store", r[0])
        self.assertIn("No entry point reaches this store", r[1])    # svc is not named in f1's steps
        self.assertEqual(r[2:6], ["", "", "", ""])                # non-store · flows [] · no flows key · no module
        self.assertIsNone(r[6])

    def test_R4_pure_and_escaped(self):
        for s in ("fetch(", "XMLHttpRequest", "postJSON(", "archFetch("):
            self.assertNotIn(s, DP)
        d = {"modules": MODS, "edges": [edge("svc", "db", "write")],
             "flows": [flow("<i>f</i>", [step("srv", "svc")], label="<b>L</b>", name="<b>N</b>")]}
        h = run("console.log(JSON.stringify(archDataPathHtml(D, D.modules[3], null)));", d)
        self.assertIn("&lt;b&gt;L&lt;/b&gt;", h)
        self.assertIn("&lt;b&gt;N&lt;/b&gt;", h)
        self.assertIn('data-ardp="&lt;i&gt;f&lt;/i&gt;"', h)
        self.assertNotIn("<b>L", h)
        self.assertNotIn("<b>N", h)

    def test_R4_detail_panel_calls_it_guarded(self):
        with open(os.path.join(WEB, "js", "84j3-structure-arch-detail.js"), encoding="utf-8") as fh:
            det = fh.read()
        self.assertIn("typeof archDataPathHtml === 'function' ? archDataPathHtml(d, m, o.lit) : ''", det)


if __name__ == "__main__":
    unittest.main()
