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


# archProvNote: «drawn by» badge from the /api/arch `prov` field
PROV_PRE = """
const I18N = { ko: {} }; let LANG = 'en';
const T = s => LANG === 'ko' && I18N.ko[s] ? I18N.ko[s] : s;
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const AILG = { cc: ['Claude', '<svg>CC</svg>'], cx: ['Codex', '<svg>CX</svg>'] };
"""
PROV_BODY = """
const P = (plat, model, stages) => ({ v: 1, plat, sid: 's1', model, stages, at: 1, vt: 2 });
process.stdout.write(JSON.stringify({
  one: archProvNote(P('cx', 'gpt-5', [])),
  multi: archProvNote(P('cc', 'opus', [{ t: 'Map <a>', model: 'opus' }, { t: 'Verify', model: 'haiku' }])),
  same: archProvNote(P('cc', 'opus', [{ t: 'Map', model: 'opus' }, { t: 'Verify', model: 'opus' }])),
  none: archProvNote(null), old: archProvNote(undefined), bad: archProvNote(P('zz', 'm', [])),
}));
"""


class ProvBadge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        js = "\n".join([PROV_PRE, js_fn("strHdBadge"), js_fn("aiLogo"), js_fn("archProvNote"), PROV_BODY])
        r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        if r.returncode != 0:
            raise AssertionError(r.stderr.decode())
        cls.o = json.loads(r.stdout)

    def test_r2_logo_and_model(self):
        """R2: platform logo + model name for a one-model map."""
        h = self.o["one"]
        self.assertIn("ailg-cx", h)
        self.assertIn("<span>gpt-5</span>", h)
        self.assertNotIn("Codex<", h.replace('title="Codex"', ""))   # vendor name only in the logo title

    def test_r2_per_stage_models(self):
        """R2: each stage's model when stages used different models."""
        h = self.o["multi"]
        self.assertIn("ailg-cc", h)
        self.assertIn("<span>opus · haiku</span>", h)   # distinct models inline; per-stage titles in the tooltip
        self.assertIn('title="Map &lt;a&gt;: opus\nVerify: haiku"', h)
        self.assertIn("<span>opus</span>", self.o["same"])   # one model across stages -> plain model

    def test_r3_unknown_without_claude_logo(self):
        """R3: null prov / unknown platform -> «unknown», no Claude fallback logo."""
        for k in ("none", "old", "bad"):
            self.assertIn("Drawn by: unknown", self.o[k])
            self.assertNotIn("ailg", self.o[k])

    def test_r3_ko_entry(self):
        """R3: the «unknown» label has a ko entry."""
        from tests._load import js_all
        self.assertIn("'Drawn by: unknown':", js_all())


if __name__ == "__main__":
    unittest.main()
