"""R4: pipeline verdict line of the «Evaluation» popover's «Result layer» (48i plEvalVerdict / PLE_VD) + 47g «Next step» fold.
Node-run with stubs; no live files."""
import json
import os
import re
import subprocess
import unittest

from tests._load import ROOT, js_all, js_fn
from tests._node import node_e
from tests import test_harness_next_js as thn   # module import: its test class must not be collected twice

_PIPE = {"pl_broke": {"meaning": "m-pb", "why": "w-pb", "who": "ai", "next": "n-pb"},
         "pl_loopback": {"meaning": "m-pl", "why": "w-pl", "who": "ai", "next": "n-pl"},
         "pl_too_few": {"meaning": "m-pt", "why": "w-pt", "who": "owner", "next": "n-pt", "ignore": "i-pt"}}
_EN = {"pl_broke": "A pass from this pipeline broke later.",
       "pl_too_few": "Fewer than 5 runs in the last 30 days, too few to judge.",
       "pl_loopback": "Review loop-backs rose sharply against the 30 days before.",
       "healthy": "No pass broke, enough runs, loop-backs steady."}


def _src48i():
    src = js_all()
    out = [re.search(r"^const PLE_OC = [\s\S]*?\};$", src, re.M).group(0),
           re.search(r"^const plOcPct[^\n]*$", src, re.M).group(0),
           re.search(r"^const PLE_VD = [\s\S]*?\};$", src, re.M).group(0)]
    return "\n".join(out + [js_fn(f) for f in ("plEvalVerdict", "plEvalOutcome", "plEvalEff")]) + "\n"


def _js(body, lang="en"):
    return thn._js("LANG = %s; Object.assign(HN_NXS.guide.ko, %s); HN_NXS.guide.en = HN_NXS.guide.ko;\n%s%s"
                   % (json.dumps(lang), json.dumps(_PIPE), _src48i(), body))


def _ev(vd):
    return {"outcome": {"verdict": vd, "proc": {"runs": 7, "jump": 0}, "result": {"n": 3, "broke": 1, "fixed": 0}, "lb": {}}, "graded": {}}


class PlVerdict(unittest.TestCase):
    def test_r4_first_li_is_verdict(self):
        for vd, s in _EN.items():
            h = _js("console.log(JSON.stringify(plEvalOutcome(%s, 'demo-pipe')))" % json.dumps(_ev(vd)))
            first = h.split("<ul>", 1)[1].split("<li", 2)[1]
            self.assertIn(s, first, vd)

    def test_r4_fold_for_not_healthy_only(self):
        r = _js("console.log(JSON.stringify(['pl_broke', 'healthy', 'pl_too_few'].map(v => plEvalOutcome(%s(v), 'demo-pipe'))))"
                % ("(v => Object.assign(%s, {outcome: Object.assign(%s.outcome, {verdict: v})}))" % (json.dumps(_ev("")), json.dumps(_ev("")))))
        broke, healthy, few = r
        self.assertIn("<details class=hnnx", broke)
        self.assertIn("data-hnnxd=", broke)                 # ai: «Draft instruction»
        self.assertNotIn("hnnx", healthy)
        self.assertIn("Safe to ignore when", few)          # owner: no draft button
        self.assertNotIn("data-hnnxd=", few)

    def test_r4_unknown_or_absent_no_line(self):
        r = _js("console.log(JSON.stringify([plEvalOutcome(%s, 'p'), plEvalOutcome(%s, 'p')]))"
                % (json.dumps(_ev("<b>x")), json.dumps(dict(_ev(""), outcome={"proc": {"runs": 2}}))))
        for h in r:
            self.assertNotIn("plevd", h)

    def test_r4_draft_body_names_the_pipeline(self):
        r = _js("""
const k = hnNxKey('pl_broke', {name: 'demo-pipe'}); plEvalOutcome(%s, 'demo-pipe');
hnNxDraft(k); console.log(JSON.stringify([HN_NXS.dr.body, POSTS.length]));
""" % json.dumps(_ev("pl_broke")))
        body, n = r
        self.assertEqual(n, 0)                               # drafting never sends
        for s in ("Harness verdict: pl_broke", "File: .claude/pipelines/demo-pipe.json", "runs 7", "docs/verdicts/pl_broke.md"):
            self.assertIn(s, body)

    def test_r4_ple_vd_matches_server_ids(self):
        keys = _js("console.log(JSON.stringify(Object.keys(PLE_VD).sort()))")
        self.assertEqual(keys, sorted(_EN))
        self.assertEqual(_js("console.log(JSON.stringify(PLE_VD))"), _EN)
        with open(os.path.join(ROOT, "sidereus", "pl_outcome.py"), encoding="utf-8") as f:
            py = f.read()
        if "OC_VERDICT" not in py:
            self.skipTest("pl_outcome.OC_VERDICT not landed yet")
        from tests._load import sidereus
        ids = getattr(sidereus("pl_outcome"), "OC_VERDICT")
        self.assertEqual(sorted(ids), sorted(_EN))

    def test_r4_every_sentence_has_ko(self):
        r = _js("console.log(JSON.stringify(Object.values(PLE_VD).map(s => T(s))))", lang="ko")
        self.assertEqual(len(r), 4)
        for en, ko in zip(_EN.values(), r):
            self.assertNotEqual(en, ko)

    def test_node_check(self):
        subprocess.run(["node", "--check", os.path.join(ROOT, "web", "js", "06-i18n-zzs-plverdict.js")], check=True)


if __name__ == "__main__":
    unittest.main()
