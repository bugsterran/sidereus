"""Status bar / «By platform» Copilot quota piece (extUsage.cp.quota). Runs the JS through node."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

STUBS = """
const T = s => s, esc = s => String(s).replace(/"/g, '&quot;');
const TV = j => String((j && j.msg) || '').replace(/\\{(\\w+)\\}/g, (m, k) => (j.vars && k in j.vars) ? String(j.vars[k]) : m);
const fmtTok = n => String(n);
const aiLogo = p => '<i class="ailg ailg-' + p + '" title="x">L</i>';
const platName = k => k === 'cp' ? 'Copilot' : k;
const hhmm = () => '11/01 09:00';
const agoAt = () => '5m ago';
"""
FNS = ("fmtMoney", "fmtPct", "extCostStr", "extRateStr", "extWinLbl", "extRateDetail", "extQuotaStr", "sbExt", "sbExtSeg")
Q = {"bucket": "premium_interactions", "used": 1, "ent": 200, "unl": False, "pct": 99, "reset": 1761955200, "at": 1761900000}


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SbarCopilot(unittest.TestCase):
    def run_js(self, extu):
        js = STUBS + "\n".join(js_fn(f) for f in FNS) \
            + "\nprocess.stdout.write(JSON.stringify(sbExt(" + json.dumps(extu) + ")));"
        r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        return json.loads(r.stdout)

    def test_quota_piece(self):
        h = self.run_js({"cp": {"tok": 10, "cost": None, "quota": Q}})
        self.assertIn("<small class=sbd9>· 1 / 200 · 99% left · resets 11/01 09:00 · seen 5m ago</small>", h)
        self.assertIn("refresh only when Copilot runs", h)

    def test_pct_floors(self):
        for pct, want in ((99.5, "99%"), (0.4, "0%"), (100, "100%")):
            h = self.run_js({"cp": {"tok": 10, "quota": dict(Q, pct=pct)}})
            self.assertIn("· " + want + " left", h)

    def test_quota_drops_before_claude_steps(self):
        src = js_all()
        steps = json.loads(re.search(r"^const SB_STEPS = (\[.*?\]);", src, re.M).group(1))
        self.assertEqual(steps[0], 9)                  # before Claude-only steps 1-3

    def test_unlimited(self):
        h = self.run_js({"cp": {"tok": 10, "quota": dict(Q, unl=True)}})
        self.assertIn("· unlimited · resets", h)
        self.assertNotIn("1 / 200", h)
        self.assertNotIn("left", h.split('">', 1)[1])

    def test_no_quota_no_piece(self):
        h = self.run_js({"cp": {"tok": 10}})
        self.assertNotIn("sbd9", h)
        self.assertNotIn("seen", h)
        self.assertIn("No limit data", h)              # tooltip only

    def test_quota_ignored_for_other_platforms(self):
        h = self.run_js({"gm": {"tok": 10, "quota": Q}})
        self.assertNotIn("1 / 200", h)


if __name__ == "__main__":
    unittest.main()
