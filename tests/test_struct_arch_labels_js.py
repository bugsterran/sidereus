"""Arch focus view edge labels: out-edges all share the hub as tail, so 84j sets g.flHead and 81e mmdFlPlace anchors
their labels at the head end (not piled up at the hub). In-edge labels and the overview stay as before."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e
from tests.test_structure_mermaid_js import PRE as MPRE, FNS as MFNS

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "js")
with open(os.path.join(WEB, "81g0-structure-grid-router.js"), encoding="utf-8") as fh:
    ROUTER = fh.read()
ARCH_FNS = ("archIsTest", "archMq", "archPairs", "archReduce", "archSrc", "archRanks", "archMmd")

MODS = [{"id": "in", "name": "Caller"}, {"id": "hub", "name": "Hub"}] + [{"id": "o%d" % i, "name": "Target %d" % i} for i in range(6)]
EDGES = [{"from": "in", "to": "hub", "label": "handle", "ok": True}] + [
    {"from": "hub", "to": "o%d" % i, "label": "call_%d" % i, "ok": True} for i in range(6)]

BODY = """
const M = %s, E = %s, _L = mmdLayout, _P = mmdFlPlace; let S = null, P = null, DROP = false;
mmdLayout = g => { if(DROP) delete g.flHead; S = _L(g); return S; };
mmdFlPlace = (g, L) => { P = _P(g, L); return P; };
const focus = drop => { DROP = drop; archMmd(archSrc(M, E, false, 'hub'), M, 1, null, null);
  return S.edges.map((e, i) => ({from: e.from, to: e.to, pts: e.pts, R: P.labs[i] && P.labs[i].R, num: P.labs[i] && P.labs[i].num || null})); };
const hubR = () => S.nodes.m1;
const a = focus(false), hub = hubR(), b = focus(true);
DROP = false; const o1 = archMmd(archSrc(M, E, false, ''), M, '', null, null); DROP = true; const o2 = archMmd(archSrc(M, E, false, ''), M, '', null, null);
process.stdout.write(JSON.stringify([ERR, a, hub, b, o1 === o2, o1.length]));
"""


def run(body):
    js = "\n".join([MPRE, "const MMD_BUDGET = 1e9, MMD_UNCROSS = 1e9, ARCH_DIR = 'TB'; let ERR = null; function softErr(t, e){ ERR = String(e); }", ROUTER]
                   + [js_fn(f) for f in MFNS] + [js_fn(n) for n in ARCH_FNS] + [body])
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


def overlap(a, b):
    return a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"]


def crosses(R, p, q):
    # axis-aligned segment p-q against the open interior of rect R
    x0, x1, y0, y1 = min(p[0], q[0]), max(p[0], q[0]), min(p[1], q[1]), max(p[1], q[1])
    return x1 > R["x"] and x0 < R["x"] + R["w"] and y1 > R["y"] and y0 < R["y"] + R["h"]


def centre(R):
    return R["x"] + R["w"] / 2, R["y"] + R["h"] / 2


def dist_rect(px, py, R):
    dx = max(R["x"] - px, 0, px - R["x"] - R["w"])
    dy = max(R["y"] - py, 0, py - R["y"] - R["h"])
    return (dx * dx + dy * dy) ** 0.5


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchFocusLabels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.err, cls.a, cls.hub, cls.b, cls.ov_same, cls.ov_len = run(BODY % (json.dumps(MODS), json.dumps(EDGES)))

    def test_r1_out_labels_spread(self):
        self.assertIsNone(self.err)
        outs = [e for e in self.a if e["from"] == "m1"]
        self.assertEqual(len(outs), 6)
        rs = [e["R"] for e in self.a if e["R"]]
        self.assertEqual(len(rs), len(self.a))
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                self.assertFalse(overlap(rs[i], rs[j]), (i, j))
        for e in outs:
            if e["num"]:
                continue   # a legend badge is allowed to sit anywhere free
            cx, cy = centre(e["R"])
            end = e["pts"][-1]
            self.assertLess(((cx - end[0]) ** 2 + (cy - end[1]) ** 2) ** 0.5, dist_rect(cx, cy, self.hub), e["to"])

    def test_r1_labels_off_other_lines(self):
        for i, e in enumerate(self.a):
            for j, f in enumerate(self.a):
                if i == j:
                    continue
                for k in range(1, len(f["pts"])):
                    self.assertFalse(crosses(e["R"], f["pts"][k - 1], f["pts"][k]), (e["to"], f["to"]))

    def test_r2_in_labels_and_overview_unchanged(self):
        ins = lambda r: [e["R"] for e in r if e["from"] != "m1"]
        self.assertEqual(ins(self.a), ins(self.b))
        self.assertGreater(len(ins(self.a)), 0)
        self.assertTrue(self.ov_same)
        self.assertGreater(self.ov_len, 0)


def in_stats(r, me):
    """In-edge labels: overlaps among themselves, ones crossing another edge's line, ones demoted to a number badge."""
    ins = [i for i, e in enumerate(r) if e["to"] == me and e["R"]]
    ov = sum(1 for i in ins for j in ins if i < j and overlap(r[i]["R"], r[j]["R"]))
    cr = sum(1 for i in ins if any(crosses(r[i]["R"], f["pts"][k - 1], f["pts"][k])
                                   for j, f in enumerate(r) if j != i for k in range(1, len(f["pts"]))))
    return ov, cr, sum(1 for i in ins if r[i]["num"]), len(ins)


# Hub calling and called by the same six peers: head-anchored out-labels land by each peer, right where that peer's
# tail-anchored in-label wants to sit. ★Placed in edge order: in-labels on other lines 3 -> 4; in-labels first: 2.
MODS2 = [{"id": "hub", "name": "Hub"}] + [{"id": "x%d" % i, "name": "Peer module %d" % i} for i in range(6)]
EDGES2 = [x for i in range(6) for x in ({"from": "x%d" % i, "to": "hub", "label": "inbound_call_%d" % i, "ok": True},
                                        {"from": "hub", "to": "x%d" % i, "label": "outbound_call_%d" % i, "ok": True})]
BODY2 = BODY.replace("'hub'), M, 1,", "'hub'), M, 0,").replace("S.nodes.m1", "S.nodes.m0")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchFocusInLabels(unittest.TestCase):
    def test_r2_in_labels_not_worse(self):
        err, a, _, b, _, _ = run(BODY2 % (json.dumps(MODS2), json.dumps(EDGES2)))
        self.assertIsNone(err)
        ov_a, cr_a, bd_a, n_a = in_stats(a, "m0")
        ov_b, cr_b, bd_b, n_b = in_stats(b, "m0")
        self.assertEqual((n_a, n_b), (6, 6))
        self.assertEqual(ov_a, 0)
        self.assertLessEqual(cr_a, cr_b)
        self.assertLessEqual(bd_a, bd_b)


if __name__ == "__main__":
    unittest.main()
