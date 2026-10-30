"""Harness hook-cost reasons (47h hnVdTxtHook via 47b hnVdTxt): #28 R1 slow text · R2 «k hooks combined» only for k >= 2 · R3 limit sentence · R4 «time and effect not measured yet» hint."""
import json
import os
import subprocess
import unittest

from tests._load import ROOT
from tests._node import node_e
from tests import test_harness_js as thj   # module import: the Harness class must not be collected twice
from tests._i18n_js import i18n_switch

_FS = [os.path.join(ROOT, "web", "js", f) for f in ("47b-harness.js", "47h-harness-hookcost.js")]


def _js(body):
    src = thj._STUB + i18n_switch() + "const document = {addEventListener(){}};\n"
    for p in _FS:
        with open(p, encoding="utf-8") as f:
            src += f.read() + "\n"
    return json.loads(subprocess.run(node_e(src + body), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


def _txt(vds, lang="en"):
    return _js("LANG = '%s'; console.log(JSON.stringify(%s.map(v => hnVdTxt(v))))" % (lang, json.dumps(vds)))


class HarnessHookCost(unittest.TestCase):
    def test_node_check(self):
        subprocess.run(["node", "--check", _FS[1]], check=True, capture_output=True)

    def test_r1_r2_slow_text(self):
        one, two, three = _txt([{"lvl": "check", "why": "slow", "vp": {"avg": 1450, "runs": 220, "k": 1}},
                                {"lvl": "check", "why": "slow", "vp": {"avg": 1450, "runs": 220, "k": 2}},
                                {"lvl": "check", "why": "slow", "vp": {"avg": 1450.4, "runs": 220}}])
        self.assertEqual(one, "Slow — avg 1450 ms over 220 runs")   # R1
        self.assertNotIn("combined", one)   # R2: a single hook is not «combined»
        self.assertEqual(two, "Slow — avg 1450 ms over 220 runs · 2 hooks combined")   # R2
        self.assertEqual(three, "Slow — avg 1450 ms over 220 runs")
        ko = _txt([{"lvl": "check", "why": "slow", "vp": {"avg": 1450, "runs": 220, "k": 2}}], "ko")[0]
        self.assertIn("1450 ms", ko)
        self.assertIn("훅 2개 합산", ko)

    def test_r3_no_effect_with_limit(self):
        vd = {"lvl": "check", "why": "no_effect", "vp": {"runs": 80, "min": 70}}
        en, ko, dflt = _txt([vd])[0], _txt([vd], "ko")[0], _txt([{"lvl": "check", "why": "no_effect", "vp": {"runs": 60}}])[0]
        self.assertIn("No visible effect — 70+ runs, never blocked, never printed", en)   # R3: threshold from the server
        self.assertIn("side effects such as file writes are not visible here", en)   # R3 limit
        self.assertIn("70회 이상", ko)
        self.assertIn("부수 효과", ko)
        self.assertIn("— 50+ runs", dflt)   # no min sent = default threshold

    def test_r4_hint_only_when_otel_counted_without_cost(self):
        base = {"cmd": "a.py", "eff": "log", "scope": "user", "src": "settings.json", "matcher": "", "ch": "a"}
        rows = [dict(base, n=12, nsrc="otel", cost=None), dict(base, n=12, nsrc="otel", cost={"runs": 12, "avg": 5, "blk": 0, "out": 1, "k": 1}),
                dict(base, n=12, nsrc="", cost=None), dict(base, n=0, nsrc="otel", cost=None)]
        h = _js("LANG = 'en'; console.log(JSON.stringify(%s.map(h => hnChip(h, false))))" % json.dumps(rows))
        self.assertIn("time and effect not measured yet", h[0])   # R4: OTel saw it fire, cost unknown
        self.assertNotIn('class="hnvdr', h[0])   # a hint, not a verdict row
        for x in h[1:]:
            self.assertNotIn("not measured yet", x)   # measured · no OTel data · never fired

    def test_other_ids_fall_back(self):
        self.assertEqual(_js("console.log(JSON.stringify([hnVdTxtHook({why: 'zz'}), hnVdTxtHook({why: 'dup'})]))"), [None, None])
        self.assertEqual(_txt([{"lvl": "check", "why": "zz"}])[0], "to check")

    def test_row_is_escaped(self):
        h = _js("LANG = 'en'; console.log(JSON.stringify(hnVdRow({vd: {lvl: 'check', why: 'slow', id: 'v1', vp: {avg: 1, runs: 3, k: '<b>2'}}})))")
        self.assertNotIn("<b>", h)

    def test_demo_rows(self):
        from sidereus import demo
        d = demo._demo_harness(1e9, "/api/harness")[1]
        hooks = {h["cmd"]: h for e in d["events"] for h in e["hooks"]}
        self.assertEqual(hooks["load-context.py"]["cost"], {"runs": 220, "avg": 1450, "blk": 0, "out": 220, "k": 2})
        self.assertEqual(hooks["audit-log.py"]["cost"]["runs"], 60)
        self.assertIsNone(hooks["guard.py"]["cost"])   # R4: no record = None, not zeros


if __name__ == "__main__":
    unittest.main()
