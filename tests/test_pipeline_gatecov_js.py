"""Gate coverage: plGateCov counts, «Unverified» pill on gateless stage cards, «Gates n/m» in the pipeline bar.
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
const ago = s => s + 's', PL_JUDGED = [], PL_LOW = [];
function plLabTip(x){ return x; }
const I18N = { ko: {} };
"""


def _run(body, lang="en"):
    with open(os.path.join(ROOT, "web", "js", "06-i18n-zs-pl.js"), encoding="utf-8") as fh:
        ko = fh.read()
    src = js_all()
    consts = re.search(r"^const PLG_FAM = [\s\S]*?\};$", src, re.M).group(0)
    consts += "\n" + re.search(r"^const PLG_GFAM[^\n]*$", src, re.M).group(0)
    consts += "\n" + re.search(r"^const PLG_NAMES = [\s\S]*?^PLG_NAMES\.ko = \{\};", src, re.M).group(0)
    fns = "\n".join(js_fn(f) for f in ("T", "TV", "plgShow", "plgBase", "plgFam", "plgColor", "plgHue", "plFlagChips", "plGateCov", "plNodeHtml"))
    code = "let LANG = %s;\n" % json.dumps(lang) + STUBS + ko + "\n" + consts + "\n" + fns + "\n" + body
    r = subprocess.run(node_e(code), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


G = ("{ defaults: { model: 'opus' }, loops: [], nodes: ["
     "{ id: 'a', title: '설계', agent: 'x', ui: { x: 0, y: 0 } },"
     "{ id: 'b', title: '구현', agent: 'x', gate: 'scripts/check.sh --fast', ui: { x: 0, y: 0 } },"
     "{ id: 'c', title: '검증', agent: 'x', gate: 'bash t.sh', ui: { x: 0, y: 0 } },"
     "{ id: 'd', title: '리뷰', agent: 'x', gate: '  ', ui: { x: 0, y: 0 } }] }")


def _bar_expr():
    body = js_fn("plBody")
    cov = re.search(r"^\s*const cov = [^\n]*$", body, re.M).group(0)
    span = "'" + re.search(r"""'</b>(<span class="plcov'.*?'</span>')""", body).group(1)
    return cov, span


@unittest.skipUnless(shutil.which("node"), "node not installed")
class GateCoverage(unittest.TestCase):
    def test_counts(self):
        r = _run("const G = %s; console.log(JSON.stringify([plGateCov(G), plGateCov({nodes: []}), plGateCov(null)]));" % G)
        self.assertEqual(r, [{"n": 2, "m": 4}, {"n": 0, "m": 0}, {"n": 0, "m": 0}])

    def test_unverified_pill_only_without_gate(self):
        r = _run("const E = { G: %s }; console.log(JSON.stringify(E.G.nodes.map(n => plNodeHtml(E, n, false, null))));" % G)
        self.assertIn("class=plunv", r[0])
        self.assertIn("Unverified", r[0])
        self.assertIn("No gate command", r[0])
        self.assertIn('aria-label="Unverified — No gate command — nothing machine-checks this stage"', r[0])   # screen readers hear why
        self.assertIn("class=plnc", r[0])   # row shows even with no other chips
        self.assertNotIn("plunv", r[1])
        self.assertNotIn("plunv", r[2])
        self.assertIn("class=plunv", r[3])   # whitespace-only gate is no gate

    def test_unverified_korean(self):
        r = _run("const E = { G: %s }; console.log(JSON.stringify(plNodeHtml(E, E.G.nodes[0], false, null)));" % G, lang="ko")
        self.assertIn("검증 없음", r)

    def test_bar_text(self):
        cov, span = _bar_expr()
        self.assertIn("plEnt(p).G", cov)
        js = "const p = {}; function plEnt(){ return { G: %s }; }\n%s\nconsole.log(JSON.stringify(%s));" % (G, cov, span)
        en = _run(js)
        self.assertIn("Gates 2/4", en)
        self.assertIn("machine-checked by a gate command: 2 of 4", en)   # meaning kept in the tooltip
        self.assertIn("plcovlo", en)   # amber while n < m
        self.assertIn("게이트 2/4", _run(js, lang="ko"))


if __name__ == "__main__":
    unittest.main()
