"""«Result layer» block of the «Evaluation» panel (48i plEvalOutcome): fact sentences from counts, ko entries for every key.
Pure functions under node; no live files."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import ROOT, js_all, js_fn
from tests._node import node_e

STUBS = """
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const I18N = { ko: {} };
"""

SENT = [
    "Gate: {g} of {m} gates confirmed able to fail",
    "Procedure: {runs} runs, {jump} order violations blocked",
    "Result: {broke} of {n} passes broke later, fix followed {fixed}",
    "Review loop-backs: {cur}% of runs (last 30 days) vs {prev}% (30 days before)",
    "Review loop-backs: {cur}% of runs (last 30 days), no earlier data",
    "Latest report {date} · {path}",
    "No report yet",
]


def _ko():
    with open(os.path.join(ROOT, "web", "js", "06-i18n-zx-eval.js"), encoding="utf-8") as fh:
        return fh.read()


def _run(body, lang="en"):
    src = js_all()
    consts = re.search(r"^const PLE_OC = [\s\S]*?\};$", src, re.M).group(0)
    consts += "\n" + re.search(r"^const plOcPct[^\n]*$", src, re.M).group(0)
    fns = "\n".join(js_fn(f) for f in ("T", "TV", "plEvalOutcome"))
    code = "let LANG = %s;\n" % json.dumps(lang) + STUBS + _ko() + "\n" + consts + "\n" + fns + "\n" + body
    r = subprocess.run(node_e(code), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


EV = ("{ graded: { n: 2, m: 3 }, outcome: { proc: { runs: 9, jump: 1 }, lb: { cur: { n: 8, k: 2 }, prev: { n: 4, k: 2 } },"
      " result: { n: 6, broke: 1, fixed: 2 } }, rep: { date: '2026-10-11', path: '/d/eval/k/reports/2026-10-11.md' } }")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ResultLayer(unittest.TestCase):
    def test_keys_in_js_and_ko(self):
        with open(os.path.join(ROOT, "web", "js", "48i-pipeline-eval.js"), encoding="utf-8") as fh:
            src = fh.read()
        ko = _ko()
        for s in SENT:
            self.assertIn("'" + s + "'", src, s)
            self.assertIn("'" + s + "':", ko, s)

    def test_sentences_en(self):
        h = _run("console.log(JSON.stringify(plEvalOutcome(%s)));" % EV)
        for s in ("Gate: 2 of 3 gates confirmed able to fail", "Procedure: 9 runs, 1 order violations blocked",
                  "Result: 1 of 6 passes broke later, fix followed 2",
                  "Review loop-backs: 25% of runs (last 30 days) vs 50% (30 days before)",
                  "Latest report 2026-10-11 · /d/eval/k/reports/2026-10-11.md"):
            self.assertIn(s, h)

    def test_ko_and_fallbacks(self):
        h = _run("console.log(JSON.stringify(plEvalOutcome(%s)));" % EV, "ko")
        self.assertIn("결과 층", h)
        self.assertIn("실행 9회", h)
        r = _run("console.log(JSON.stringify([plEvalOutcome({ outcome: { proc: { runs: 3 }, lb: { cur: { n: 3, k: 1 }, prev: { n: 0, k: 0 } } } }),"
                 " plEvalOutcome({ outcome: { proc: { runs: 2 } } }), plEvalOutcome({}), plEvalOutcome(null),"
                 " plEvalOutcome({ outcome: { proc: { runs: 0 }, result: { n: 0 } } })]));")
        self.assertIn("33% of runs (last 30 days), no earlier data", r[0])
        self.assertIn("No report yet", r[0])
        self.assertNotIn("loop-backs", r[1])   # no runs in either window
        self.assertEqual(r[2:], ["", "", ""])   # no runs and no passes: block hidden

    def test_escapes_report_path(self):
        h = _run("console.log(JSON.stringify(plEvalOutcome({ outcome: { result: { n: 1 } }, rep: { date: '<b>', path: '<i>' } })));")
        self.assertNotIn("<i>", h)
        self.assertIn("&lt;i", h)


if __name__ == "__main__":
    unittest.main()
