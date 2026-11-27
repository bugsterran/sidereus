"""«Stage cost» budget lines (48i plEvalEff, cost.bud): share of budget, «Over budget» mark, over-budget run count.
Pure functions under node; no live files."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import ROOT, js_fn
from tests._node import node_e

STUBS = """
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const I18N = { ko: {} };
"""

KEYS = ["of budget {b} ({p}%)", "of budget {b}", "Over budget", "Over budget in {k} of {m} runs"]
EFF = "{ impl: { sec: 60, tok: 1000, n: 3 } }"
# plEvalEff output without cost.bud, computed from the function before budgets existed (R3: byte-identical).
NO_BUD = ("<table class=pleeff><caption>Stage cost (last 30 days)</caption><tr><th>Stage</th><th>Median time</th>"
          "<th>Median tokens</th><th>Share</th><th>Runs</th></tr><tr><td>impl</td><td>60s</td><td>1000</td><td>100%</td>"
          "<td>3</td></tr></table><div class=pleeffs><div>Median per run: 1500 tokens (3 runs)</div>"
          "<div>Last run: 318000 · 61s</div></div>")


def _ko():
    with open(os.path.join(ROOT, "web", "js", "06-i18n-zx-eval.js"), encoding="utf-8") as fh:
        return fh.read()


def _eff(bud, last="{ tok: 318000, sec: 61 }", lang="en"):
    fns = "\n".join(js_fn(f) for f in ("T", "TV", "plEvalEff"))
    cost = "{ share: { impl: 100 }, med: 1500, mn: 3, last: %s%s }" % (last, ", bud: " + bud if bud else "")
    code = ("let LANG = %s;\n" % json.dumps(lang) + STUBS + _ko() + "\n" + fns
            + "\nprocess.stdout.write(JSON.stringify(plEvalEff(%s, %s)));" % (EFF, cost))
    r = subprocess.run(node_e(code), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


def _last(html):
    return [x for x in html.split("<div>") if x.startswith("Last run")][0]


@unittest.skipUnless(shutil.which("node"), "node not installed")
class StageCostBudget(unittest.TestCase):
    def test_r2_over_budget(self):
        h = _eff("{ tok: 300000, over: 7, m: 12 }")
        self.assertIn("Last run: 318K · 61s · of budget 300K (106%)", _last(h))
        self.assertIn("<span class=pleover>Over budget</span>", _last(h))
        self.assertIn("<div>Over budget in 7 of 12 runs</div>", h)

    def test_r2_within_budget_no_mark(self):
        h = _eff("{ tok: 400000, over: 0, m: 5 }")
        self.assertIn("of budget 400K (79%)", h)   # 79.5 rounds down while within budget
        self.assertNotIn("pleover", h)
        self.assertIn("Over budget in 0 of 5 runs", h)

    def test_r2_percent_agrees_with_mark_near_budget(self):
        # Just over reads above 100 with the mark; just under reads below 100 without it.
        h = _eff("{ tok: 300000, over: 1, m: 2 }", last="{ tok: 300001, sec: 61 }")
        self.assertIn("(101%)", _last(h))
        self.assertIn("pleover", _last(h))
        h = _eff("{ tok: 300000, over: 0, m: 2 }", last="{ tok: 299999, sec: 61 }")
        self.assertIn("(99%)", _last(h))
        self.assertNotIn("pleover", h)
        h = _eff("{ tok: 300000, over: 0, m: 2 }", last="{ tok: 300000, sec: 61 }")
        self.assertIn("(100%)", _last(h))
        self.assertNotIn("pleover", h)

    def test_r4_unknown_tokens_not_judged(self):
        h = _eff("{ tok: 300000, over: 1, m: 2 }", last="{ tok: null, sec: 30 }")
        line = _last(h)
        self.assertIn("of budget 300K", line)
        self.assertNotIn("%", line.split("of budget")[1])
        self.assertNotIn("pleover", h)

    def test_r2_no_runs_no_count_line(self):
        h = _eff("{ tok: 300000, over: 0, m: 0 }")
        self.assertIn("of budget", h)
        self.assertNotIn("Over budget in", h)

    def test_r3_no_budget_identical(self):
        for bud in ("", "null", "{ tok: 0, over: 1, m: 2 }"):
            h = _eff(bud)
            self.assertEqual(h, NO_BUD, bud)
            self.assertNotIn("budget", h.lower())

    def test_budget_line_one_decimal(self):
        # Whole K/M read «1K of budget 1K (125%)»: both numbers on the budget line keep one decimal, «.0» dropped.
        h = _eff("{ tok: 1000, over: 1, m: 1 }", last="{ tok: 1250, sec: 61 }")
        self.assertIn("Last run: 1.3K · 61s · of budget 1K (125%)", _last(h))
        h = _eff("{ tok: 1200000, over: 1, m: 1 }", last="{ tok: 1400000, sec: 61 }")
        self.assertIn("Last run: 1.4M · 61s · of budget 1.2M (117%)", _last(h))
        h = _eff("{ tok: 999960, over: 0, m: 1 }", last="{ tok: 999, sec: 61 }")
        self.assertIn("Last run: 999 · 61s · of budget 1M (0%)", _last(h))   # never «1000K»

    def test_r2_values_escaped(self):
        h = _eff("{ tok: 300000, over: '<b>', m: 3 }")
        self.assertNotIn("<b>", h)

    def test_r2_ko(self):
        h = _eff("{ tok: 300000, over: 7, m: 12 }", lang="ko")
        self.assertIn("예산 300K 대비 106%", h)
        self.assertIn("예산 초과", h)
        self.assertIn("실행 12회 중 7회 예산 초과", h)

    def test_keys_in_js_and_ko(self):
        with open(os.path.join(ROOT, "web", "js", "48i-pipeline-eval.js"), encoding="utf-8") as fh:
            src = fh.read()
        ko = _ko()
        for s in KEYS:
            self.assertIn("'" + s + "'", src, s)
            self.assertIn("'" + s + "':", ko, s)


if __name__ == "__main__":
    unittest.main()
