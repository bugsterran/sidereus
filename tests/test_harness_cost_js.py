"""Harness gate cost line (47j hnCost): absent cost, «not measured», lower bound, evidence list, fixed `by` labels."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import BASE, i18n, jconst
from tests._node import node_e

FNS = ("hnN", "hnWhen", "hnStg", "hnCostByTxt", "hnCostDur", "hnCostRows", "hnCostItem", "hnCostEv", "hnCost")
CONSTS = ("esc", "HN_COSTBY")

SCEN = r"""
var HN = {fold: {}};
const rep = {counts: {caught: 4}, since: 1761600000};
const row = (o) => Object.assign({code: 'jump', stage: 'implement', ts: 1761600000, dur_ms: 1500, by: 'stop'}, o);
const full = {period_s: 604800, blocked: 3, overridden: 2, unknown: 1, gate_ms: 125000, gate_lb: true, hook_ms: 800, pause_ms: null,
  ev: {blocked: [row({})], overridden: [row({}), row({by: 'strict', code: '<b>x</b>', stage: '<i>s</i>'}), row({by: '<script>', code: 'z'}), row({by: 'Stop'})],
       unknown: [row({by: 'pending'})], gate: [], pause: [], hook: [row({by: null})]}};
R.none = hnCost({report: rep});
R.arr = hnCost({cost: []});
R.nullc = hnCost({report: rep, cost: {blocked: null, overridden: null, unknown: null, gate_ms: null, hook_ms: null, pause_ms: null}});
R.nullcost = hnCost({report: rep, cost: null});
R.nulls = hnCost({report: rep, cost: {blocked: 0, overridden: 0, unknown: 0, gate_ms: null, hook_ms: null, pause_ms: null, ev: {}}});
R.full = hnCost({report: rep, cost: full});
HN.fold.cost = 'overridden';
R.open = hnCost({report: rep, cost: full});
HN.fold.cost = 'gate';   // no rows: the stale key is dropped
R.stale = hnCost({report: rep, cost: full});
R.staleKey = HN.fold.cost;
LANG = 'ko';
HN.fold.cost = 'overridden';
R.ko = hnCost({report: rep, cost: full});
"""


def run():
    src = (BASE + i18n() + "\n" + "\n".join(jconst(c) for c in CONSTS) + "\n" + "\n".join(js_fn(f) for f in FNS)
           + "\nconst R = {};\nLANG = 'en';\n" + SCEN + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"), encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class HarnessCostJs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run()

    def test_absent_cost_renders_nothing(self):
        self.assertEqual(self.R["none"], "")

    def test_r3_null_counts_not_measured(self):
        h = self.R["nullc"]
        for s in ("Blocked not measured", "Overridden not measured", "unknown not measured"):
            self.assertIn(s, h)
        self.assertNotIn("Blocked 0", h)

    def test_r3_null_cost_renders_not_measured_line(self):
        h = self.R["nullcost"]
        self.assertIn("hncl", h)
        for s in ("Blocked not measured", "Gate time not measured", "Hook overhead not measured", "Paused by a block not measured"):
            self.assertIn(s, h)
        self.assertIn("Caught 4", h)

    def test_null_times_read_not_measured(self):
        h = self.R["nulls"]
        for s in ("Gate time not measured", "Hook overhead not measured", "Paused by a block not measured"):
            self.assertIn(s, h)
        self.assertIn("Caught 4", h)
        self.assertIn("Blocked 0", h)
        self.assertIn("last 7 days", h)
        self.assertIn("Counts only — no combined score", h)
        self.assertNotIn("<button", h)   # no evidence rows = plain text, nothing to open

    def test_lower_bound_prefix_and_counts(self):
        h = self.R["full"]
        self.assertIn("Gate time ≥2m 5s", h)
        self.assertIn('title="lower bound"', h)
        self.assertIn("Hook overhead 800 ms", h)
        self.assertIn("all projects", h)
        self.assertIn("Overridden 2", h)
        self.assertIn("unknown 1", h)
        self.assertIn('data-hncost=overridden aria-expanded=false', h)
        self.assertNotIn("hncev", h)   # closed by default
        self.assertNotIn("-", h.split("Caught")[1].split("<")[0])   # no subtraction on the line

    def test_evidence_list_columns_and_escaping(self):
        h = self.R["open"]
        self.assertIn("data-hncev=overridden", h)
        for c in ("Reason", "Stage", "Time", "Duration", "Overridden by"):
            self.assertIn("<th>" + c + "</th>", h)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", h)
        self.assertIn("&lt;i&gt;s&lt;/i&gt;", h)
        self.assertNotIn("<b>x</b>", h)
        self.assertIn("<td class=brd>Stop</td>", h)
        self.assertIn("<td class=brd>Strict mode off</td>", h)
        self.assertIn("<td class=brv>2s</td>", h)

    def test_unknown_by_never_shown_raw(self):
        h = self.R["open"]
        self.assertNotIn("script", h)
        self.assertEqual(h.count("<td class=brd>Stop</td>"), 1)   # 'Stop' as raw `by` is not a key: shows nothing

    def test_stale_open_key_dropped(self):
        self.assertEqual(self.R["staleKey"], "")
        self.assertNotIn("hncev", self.R["stale"])

    def test_korean(self):
        h = self.R["ko"]
        self.assertIn("우회됨 2", h)
        self.assertIn("<td class=brd>정지</td>", h)
        self.assertIn("<th>우회 방법</th>", h)


if __name__ == "__main__":
    unittest.main()
