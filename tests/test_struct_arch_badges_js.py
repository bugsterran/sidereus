"""81e mmdFlPlace number badges (R1/R2/R3): when no candidate spot is free the badge slides along its edge
before the anchor fallback, so it covers no node box or placed label; the candidate-first order is unchanged."""
import json
import math
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e
from tests.test_structure_mermaid_js import PRE as MPRE, FNS as MFNS

# one horizontal edge (0,100)->(400,100); label "xxxxxxxxxx" is 80px wide, badge 21x18 (circled digit 13px + 8), anchor (16,100)
BODY = """
const blk = bs => { const n = {}; bs.forEach((b, i) => { n['b' + i] = { x: b[0], y: 60, w: b[1] - b[0], h: 80 }; }); return n; };
const run = bs => { const L = { nodes: blk(bs), sgs: {}, w: 400, h: 200,
  edges: [{ from: 'p', to: 'q', label: 'xxxxxxxxxx', pts: [[0, 100], [400, 100]] }] };
  const P = mmdFlPlace({}, L); return { lab: P.labs[0], nodes: L.nodes, leg: P.leg.length }; };
process.stdout.write(JSON.stringify([
  run([[0, 70], [180, 220], [330, 370]]),
  run([[0, 30], [150, 185], [330, 370]]),
  run([[0, 400]])]));
"""


def place():
    js = "\n".join([MPRE] + [js_fn(f) for f in MFNS] + [BODY])
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


def overlap(a, b):
    return a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"]


class BadgeSlide(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a, cls.b, cls.c = place()

    def test_r1_r2_blocked_spots_slide_along_edge(self):
        # (a) every candidate spot and the anchor are blocked, the edge has a free stretch
        lab = self.a["lab"]
        self.assertTrue(lab["num"])
        R = lab["R"]
        for n in self.a["nodes"].values():
            self.assertFalse(overlap(R, n), (R, n))
        self.assertLessEqual(abs(R["y"] + R["h"] / 2 - 100), 0.5)
        self.assertTrue(0 <= R["x"] + R["w"] / 2 <= 400)
        # R3: nearest free stretch, not the far end
        self.assertEqual(R, {"x": 73.5, "y": 91, "w": 21, "h": 18})

    def test_r3_free_candidate_unchanged(self):
        # (b) a candidate spot is free -> same rect as before the slide fallback existed
        lab = self.b["lab"]
        self.assertTrue(lab["num"])
        R = lab["R"]
        self.assertAlmostEqual(R["x"], 37.5)
        self.assertEqual([R["y"], R["w"], R["h"]], [78, 21, 18])

    def test_fully_blocked_keeps_anchor(self):
        # (c) the whole edge is covered -> old anchor rect, finite numbers
        R = self.c["lab"]["R"]
        self.assertEqual(R, {"x": 5.5, "y": 91, "w": 21, "h": 18})
        self.assertTrue(all(math.isfinite(v) for v in R.values()))
        self.assertEqual(self.c["leg"], 1)


if __name__ == "__main__":
    unittest.main()
