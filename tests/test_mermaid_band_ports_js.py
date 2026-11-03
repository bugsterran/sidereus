"""81g pass-band ports (84j2 layered view): cross-band lines leave the source bottom and enter the target top, same-row pairs
use sides, no caller enters a hub sideways; graphs without `pass` route exactly as before. Real 81e/81f/81g0/81g renderer."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e
from tests.test_structure_mermaid_js import PRE, FNS, ROUTER

# Hub between two siblings in L2: with free ports the callers bussed into the hub's left/right sides (side entry < turn cost).
SRC = ("flowchart TB\n  subgraph L1[One]\n    direction LR\n" + "".join("    c%d[caller number %d]\n" % (i, i) for i in range(8))
       + "  end\n  subgraph L2[Two]\n    direction LR\n    m1[mid one]\n    hub[shared hub]\n    m2[mid two]\n  end\n"
       + "  subgraph L3[Three]\n    direction LR\n    d1[callee one]\n    d2[callee two]\n    p1[pair one] --> p2[pair two]\n  end\n"
       + "".join("  c%d --> hub\n" % i for i in range(8)) + "  hub --> d1\n  hub --> d2\n  m1 --> d1\n  m2 --> d2\n")
OLD = js_fn("mmdRouteAll").replace("bp = bandPens(e.from, e.to)", "bp = null")


def run(body, old=False):
    fns = [js_fn(f) for f in FNS if f != "mmdRouteAll"] + [OLD if old else js_fn("mmdRouteAll")]
    js = "\n".join([PRE, "const MMD_BUDGET = 1e9, MMD_UNCROSS = 1e9; let ERR = null; function softErr(t, e){ ERR = String(e); }",
                    ROUTER] + fns + ["const SRC = " + json.dumps(SRC) + ";", body])
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


LAY = ("const g = mmdParse(SRC); if(PASS) ['L1', 'L2', 'L3'].forEach(s => { g.sgs[s].pass = true; }); const L = mmdLayout(g);"
       "process.stdout.write(JSON.stringify([ERR, L.nodes, L.edges]));")


def side(R, p):
    x, y = p
    return ("top" if abs(y - R["y"]) < 1 else "bottom" if abs(y - R["y"] - R["h"]) < 1
            else "left" if abs(x - R["x"]) < 1 else "right" if abs(x - R["x"] - R["w"]) < 1 else "?")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class BandPorts(unittest.TestCase):
    def test_cross_band_top_in_bottom_out(self):
        err, nodes, edges = run("const PASS = true;" + LAY)
        self.assertIsNone(err)
        cross = [e for e in edges if e["from"] != "p1"]
        self.assertEqual(len(cross), 12)
        for e in cross:
            p = e["pts"]
            self.assertEqual(side(nodes[e["to"]], p[-1]), "top", e)
            self.assertLess(p[-2][1], p[-1][1], e)           # last run comes down onto the top edge
            self.assertEqual(side(nodes[e["from"]], p[0]), "bottom", e)
        self.assertFalse([e for e in edges if e["to"] == "hub" and side(nodes["hub"], e["pts"][-1]) in ("left", "right")])
        pair = [e for e in edges if e["from"] == "p1"][0]
        self.assertLess(abs(nodes["p1"]["y"] - nodes["p2"]["y"]), 1)   # fixture: the pair shares a row
        self.assertIn(side(nodes["p2"], pair["pts"][-1]), ("left", "right"))
        self.assertIn(side(nodes["p1"], pair["pts"][0]), ("left", "right"))

    def test_no_pass_routes_as_before(self):
        self.assertNotEqual(OLD, js_fn("mmdRouteAll"))   # the band hook was found and switched off
        new = run("const PASS = false;" + LAY)
        old = run("const PASS = false;" + LAY, old=True)
        self.assertEqual(new, old)

    def test_focus_store_under_group_title_enters_top(self):
        # 84j4 focus shape of a real map: infra hub -> store inside a group box whose title is wider than the store.
        # ⚠With 8px under the group title the store had no top port: the line fell back to its left side.
        from tests.test_struct_arch_focus_js import render
        M = ([{"id": "sec", "name": "Security / auth", "kind": "module", "layer": "infra", "group": "g.api"},
              {"id": "rdb", "name": "Main RDB (MyBatis)", "kind": "store", "layer": "data", "group": "g.api", "ext": "db"}]
             + [{"id": "s%d" % i, "name": n, "kind": "module", "layer": "service", "group": "g.api"}
                for i, n in enumerate(["Dashboard", "DBSafer", "SQL gateway", "System admin"])])
        E = [{"from": f, "to": t, "kind": k, "ok": True, "est": False, "label": ""} for f, t, k in
             [("sec", "rdb", "read"), ("sec", "rdb", "write")] + [("s%d" % i, "sec", "call") for i in range(4)]]
        G = [{"id": "g.api", "name": "Spring Boot API (api container)"}]
        a, b, nodes, edges = render("const src = archFocusSrc(M, E, false, 'sec', GR, null, false, null, {w: 680, h: 600}), g = mmdParse(src);"
                                    " archBandFix(g); g.flLabels = true; archFocusStrip(g); const L = mmdLayout(g);"
                                    "const ix = id => 'm' + M.findIndex(m => m.id === id);"
                                    "process.stdout.write(JSON.stringify([ix('sec'), ix('rdb'), L.nodes, L.edges]));", M, E, G, flows=[])
        p = [e for e in edges if e["from"] == a and e["to"] == b][0]["pts"]
        self.assertEqual(side(nodes[a], p[0]), "bottom", p)
        self.assertEqual(side(nodes[b], p[-1]), "top", p)
        self.assertLess(p[-2][1], p[-1][1], p)


if __name__ == "__main__":
    unittest.main()


# Demo shop shape: order -> db runs past narrower boxes into a wider lone node under a centred band title.
COL = ("flowchart TB\n  subgraph L1[Service]\n    o[order]\n  end\n  subgraph L2[Domain]\n    c[common]\n  end\n"
       "  subgraph L3[Infra]\n    p[pay]\n  end\n  subgraph L4[External]\n    db[PostgreSQL database]\n  end\n"
       "  o --> c\n  o -.-> db\n  o -.-> p\n")

DEMO = ("flowchart TB\n  subgraph L0[\"Entry\"]\n    direction LR\n    subgraph Ek0r0[\"HTTP\"]\n      direction TB\n"
        "      en0{{\"GET /orders/{id}\"}}\n      en1{{\"POST /orders/{id}/pay\"}}\n    end\n  end\n"
        "  subgraph L2[\"API\"]\n    m0[\"web\"]\n    m4[\"app (py)\"]\n  end\n  subgraph L3[\"Service\"]\n    m1[\"order\"]\n  end\n"
        "  subgraph L4[\"Domain\"]\n    m2[\"common\"]\n  end\n  subgraph L6[\"Infra\"]\n    m3[\"pay\"]\n  end\n"
        "  subgraph Lx[\"External\"]\n    m5([\"PostgreSQL\"])\n  end\n"
        "  m0 --> m1\n  m1 --> m2\n  m1 -.-> m5\n  m1 -.-> m3\n  en0 --> m0\n  en1 --> m0\n")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class BandCentre(unittest.TestCase):
    def test_lone_node_entered_at_top_centre_clear_of_title(self):
        err, nodes, edges, tr = run("const g = mmdParse(" + json.dumps(COL) + "); ['L1', 'L2', 'L3', 'L4'].forEach(s => { g.sgs[s].pass = true; });"
                                    " const L = mmdLayout(g); process.stdout.write(JSON.stringify([ERR, L.nodes, L.edges, L.sgs.L4.tr]));")
        self.assertIsNone(err)
        R, p = nodes["db"], [e for e in edges if e["to"] == "db"][0]["pts"]
        self.assertEqual(side(R, p[-1]), "top")
        self.assertLessEqual(abs(p[-1][0] - (R["x"] + R["w"] / 2)), 2)   # was 39px off before the title moved
        self.assertTrue(p[-1][0] > tr["x"] + tr["w"] + 2 or p[-1][0] < tr["x"] - 2)   # last run clear of the title wall

    def test_demo_map_db_jogs_onto_top_centre(self):
        # Demo layered map (84j2 archBandSrc output, bands set up like archBandFix): the trunk past common/pay reached db's top
        # one column right of centre; 81g0 relSmooth jogs a one-side end onto the centre port.
        err, nodes, edges, tr = run("const g = mmdParse(" + json.dumps(DEMO) + "); g.slist.forEach(s => { g.sgs[s].pass = true; });"
                                    " g.sgs.Ek0r0.oneLayer = true; g.rankFix = {L0: 0, L2: 1, L3: 2, L4: 3, L6: 4, Lx: 5}; g.axis = true;"
                                    " const L = mmdLayout(g); process.stdout.write(JSON.stringify([ERR, L.nodes, L.edges, L.sgs.Lx.tr]));")
        self.assertIsNone(err)
        R, p = nodes["m5"], [e for e in edges if e["to"] == "m5"][0]["pts"]
        self.assertEqual(side(R, p[-1]), "top")
        self.assertLessEqual(abs(p[-1][0] - (R["x"] + R["w"] / 2)), 2)
        self.assertTrue(p[-1][0] > tr["x"] + tr["w"] + 2 or p[-1][0] < tr["x"] - 2)


# Band-wide non-pass group (real map shape): relRoute runs out of pops on every pass, and the elbow fallback ignored all walls.
WALL = ("flowchart TB\n  subgraph LA[Top]\n    direction LR\n    subgraph GA[group a]\n      a[alpha]\n    end\n  end\n"
        "  subgraph LB[Middle]\n    direction LR\n    subgraph GB[wide group]\n      direction TB\n"
        + "".join("      b%d[member number %d]\n" % (i, i) for i in range(1, 5)) + "    end\n  end\n"
        "  subgraph LC[Bottom]\n    direction LR\n    d[box in the way]\n    subgraph GC[a very long group title here]\n      c[c]\n    end\n  end\n"
        "  a --> c\n")
OPEN = "if(!p && bp){ blk.set(base);"


def hits(p, R, m=0):
    for (x0, y0), (x1, y1) in zip(p, p[1:]):
        if (min(x0, x1) < R["x"] + R["w"] - m and max(x0, x1) > R["x"] + m
                and min(y0, y1) < R["y"] + R["h"] - m and max(y0, y1) > R["y"] + m):
            return True
    return False


@unittest.skipUnless(shutil.which("node"), "node not installed")
class BandWall(unittest.TestCase):
    def wall(self, old):
        # Small search budget so this fixture exhausts relRoute the way the real map does at full budget.
        router = ROUTER.replace("RR_POPS = 20000", "RR_POPS = 400")
        self.assertNotEqual(router, ROUTER)
        fn = js_fn("mmdRouteAll")
        self.assertIn(OPEN, fn)
        fns = [js_fn(f) for f in FNS if f != "mmdRouteAll"] + [fn.replace(OPEN, "if(false){") if old else fn]
        js = "\n".join([PRE, "const MMD_BUDGET = 1e9, MMD_UNCROSS = 1e9; let ERR = null; function softErr(t, e){ ERR = String(e); }", router] + fns
                       + ["const g = mmdParse(%s); ['LA', 'LB', 'LC'].forEach(s => { g.sgs[s].pass = true; });"
                          " g.rankFix = {LA: 0, LB: 1, LC: 2}; g.axis = true; const L = mmdLayout(g);"
                          " process.stdout.write(JSON.stringify([ERR, L.nodes, L.edges[0].pts,"
                          " Object.keys(L.sgs).map(k => L.sgs[k].tr).filter(Boolean)]));" % json.dumps(WALL)])
        r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        if r.returncode != 0:
            raise AssertionError(r.stderr.decode())
        return json.loads(r.stdout)

    def bad(self, nodes, p, trs):
        return [k for k, R in nodes.items() if k not in ("a", "c") and hits(p, R)] + [t["x"] for t in trs if hits(p, t)]

    def test_band_wide_group_routes_clear_of_titles_and_boxes(self):
        err, nodes, p, trs = self.wall(False)
        self.assertIsNone(err)
        self.assertEqual(self.bad(nodes, p, trs), [], p)
        self.assertEqual(side(nodes["c"], p[-1]), "top", p)
        self.assertLess(p[-2][1], p[-1][1], p)
        _, nodes, p, trs = self.wall(True)   # fixture check: without the open-interior retry the elbow ran through them
        self.assertTrue(self.bad(nodes, p, trs), p)
