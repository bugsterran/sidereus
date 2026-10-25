"""Status bar Gemini segment (sbExt): hidden without usage, separate label, tooltip split. Runs the JS through node."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests import _clock
from tests._load import sidereus, js_fn
from tests._node import node_e

ext = sidereus("ext")
pg = sidereus("plat_gemini")
JS = os.path.join(os.path.dirname(__file__), "..", "web", "js")


def _fn(fname, name):
    with open(os.path.join(JS, fname), encoding="utf-8") as fh:
        src = fh.read()
    return re.search(r"^function " + name + r"\(.*?^}", src, re.S | re.M).group(0)


STUBS = """
const T = s => s, esc = s => String(s).replace(/"/g, '&quot;');
const TV = j => String((j && j.msg) || '').replace(/\\{(\\w+)\\}/g, (m, k) => (j.vars && k in j.vars) ? String(j.vars[k]) : m);
const fmtTok = n => n >= 1e6 ? Math.round(n/1e6) + 'M' : n >= 1e3 ? Math.round(n/1e3) + 'K' : String(n);
const aiLogo = p => '<i class="ailg ailg-' + p + '" title="x">L</i>';
const AILG = {gm: ['Gemini', ''], cx: ['Codex', '']};
const platName = k => AILG[k] ? AILG[k][0] : k;   // real one (40b-sessions-list.js) is covered by test_plat_conflation
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SbarGemini(unittest.TestCase):
    def run_js(self, extu):
        js = STUBS + js_fn("fmtMoney") + "\n" + js_fn("fmtPct") + "\n" + js_fn("extCostStr") + "\n" + js_fn("extRateStr") + "\n" + js_fn("extWinLbl") + "\n" + js_fn("hhmm") + "\n" + js_fn("extRateDetail") + "\n" + _fn("60-statusbar.js", "sbExt") + "\n" \
            + _fn("60-statusbar.js", "sbExtSeg") \
            + "\nprocess.stdout.write(JSON.stringify(sbExt(" + json.dumps(extu) + ")));"
        r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        return json.loads(r.stdout)

    def test_hidden_without_usage(self):
        self.assertEqual(self.run_js({}), "")
        self.assertEqual(self.run_js(None), "")

    def test_session_without_tokens_shows_today_zero(self):
        h = self.run_js({"gm": {"tok": 0, "cost": None}})
        self.assertIn("<b>0</b>", h)
        self.assertNotIn("price table", h)              # nothing was priced, so no «not in the price table»

    def test_segment_and_tooltip(self):
        h = self.run_js({"gm": {"tok": 1200000, "in": 300000, "cache": 800000, "out": 90000, "thought": 10000,
                                "cost": 0.84, "costMiss": 0, "n_sessions": 2,
                                "models": ["gemini-2.5-flash", "gemini-2.5-pro"]}})
        self.assertIn("class=sbext", h)
        self.assertIn('<i class="ailg ailg-gm">L</i><small', h)
        self.assertNotIn("<b>Gemini</b>", h)                  # logo only — name stays in the tooltip
        self.assertIn("<b>1M</b>", h)
        self.assertIn("≈ $0.84", h)
        self.assertNotIn('title="x"', h)                 # logo title must not shadow the segment tooltip
        tip = re.search(r'title="([^"]*)"', h).group(1)
        for s in ("Input 300K", "Cache 800K", "Output 90K", "Thinking 10K", "gemini-2.5-flash, gemini-2.5-pro", "estimate"):
            self.assertIn(s, tip)

    def test_one_segment_per_platform_with_own_logo(self):
        h = self.run_js({"gm": {"tok": 2000, "cost": 0.01}, "cx": {"tok": 3000, "cost": None}, "cu": {"tok": 0}})
        self.assertEqual(h.count("class=sbext"), 3)
        self.assertLess(h.index("ailg-cx"), h.index("ailg-gm"))
        self.assertNotIn("<b>Codex</b>", h)
        self.assertIn("ailg-cu", h)                     # «Today 0» entry is shown too

    def test_unpriced_has_no_cost(self):
        h = self.run_js({"gm": {"tok": 5000, "in": 5000, "cost": None, "costMiss": 3}})
        self.assertNotIn("$", h)
        self.assertIn("Model not in the price table", h)


class UsageModels(unittest.TestCase):
    def setUp(self):
        self._tok = dict(ext._tok)
        ext._tok.clear()
        self._gc, pg.scan = pg.scan, (lambda since=0.0: [])     # never the live ~/.gemini
        fz = _clock.frozen(ext, pg)
        fz.__enter__()
        self.addCleanup(fz.__exit__, None, None, None)

    def tearDown(self):
        pg.scan = self._gc
        ext._tok.clear()
        ext._tok.update(self._tok)

    def test_models_listed_for_today_only(self):
        now = _clock.NOW
        ext._tok[("gemini", "a")] = {"msgs": {
            "1": (10, 1, 0, 0, now, "gemini-2.5-pro", None),
            "2": (10, 1, 0, 0, now - 3 * 86400, "gemini-old", None)}}
        ext._tok[("gemini", "b")] = {"msgs": {"3": (10, 1, 0, 0, now, "gemini-2.5-flash", None)}}
        self.assertEqual(ext.ext_usage_today(now)["gm"]["models"], ["gemini-2.5-flash", "gemini-2.5-pro"])

    def test_disk_scan_is_base_and_live_adds_only_new_ids(self):
        now = _clock.NOW
        disk = [{"sid": "a", "msgs": {"1": (100, 10, 50, 5, now, "gemini-2.5-pro", 0.5)}},
                {"sid": "ended", "msgs": {"9": (200, 20, 0, 0, now, "gemini-2.5-flash", 0.25)}}]
        saved, pg.scan = pg.scan, (lambda since=0.0: disk)
        try:
            self.assertEqual(ext.ext_usage_today(now)["gm"]["tok"], 165 + 220)     # empty `_tok` (after restart)
            ext._tok[("gemini", "a")] = {"msgs": {"1": (999, 0, 0, 0, now, "x", None),      # same id: disk wins
                                                   "2": (7, 0, 0, 0, now, "gemini-2.5-pro", None)}}
            g = ext.ext_usage_today(now)["gm"]
        finally:
            pg.scan = saved
        self.assertEqual((g["tok"], g["n_sessions"], g["costMiss"], g["cost"]), (165 + 220 + 7, 2, 1, 0.75))
        self.assertNotIn("x", g["models"])


if __name__ == "__main__":
    unittest.main()
