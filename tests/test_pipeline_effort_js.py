"""R3 stage reasoning effort on the Pipelines screen: card model line (48d plNodeHtml), stage-editor select
(48d plEffOpts/plPanel), check (48c plgCheck), «session runs it» request (48b plDmDirect) and the new-pipeline
schema hint (48e). Pure functions under node; no live files."""
import json
import re
import shutil
import unittest

from tests._load import js_all, js_fn
from tests.test_pipeline_gatecov_js import _run as _card
from tests.test_pipeline_graph import _js as _graph
from tests.test_pipeline_run import _js as _run_js

EFFORTS = ["low", "medium", "high", "xhigh", "max"]
G = ("{ defaults: { model: 'opus' }, loops: [], nodes: ["
     "{ id: 'a', title: '설계', agent: 'x', ui: { x: 0, y: 0 } },"
     "{ id: 'b', title: '구현', agent: 'x', model: 'sonnet', effort: 'high', ui: { x: 0, y: 0 } }] }")


def _efforts():
    return re.search(r"^const PLG_EFFORTS[^\n]*$", js_all(), re.M).group(0)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class StageEffort(unittest.TestCase):
    def test_r3_card_shows_level_only_when_set(self):
        js = "const E = { G: %s }; console.log(JSON.stringify(E.G.nodes.map(n => plNodeHtml(E, n, false, null).match(/<div class=plnm[^>]*>.*?<\\/div>/)[0])));" % G
        en, ko = _card(js), _card(js, lang="ko")
        self.assertNotIn("effort", en[0].lower())                    # no effort key: the session's effort, nothing shown
        self.assertNotIn("pleff", en[0])
        self.assertIn('<span class=pleff title="Reasoning effort: high" aria-label="Reasoning effort: high"> · high</span>', en[1])
        self.assertTrue(en[1].startswith("<div class=plnm>sonnet<span class=pleff"), en[1])   # right after the model
        self.assertIn('title="추론 강도: high"', ko[1])

    def test_r3_panel_select_lists_session_plus_levels(self):
        src = "const esc = s => String(s), T = s => s;\n" + _efforts() + "\n" + js_fn("plOpt") + "\n" + js_fn("plEffOpts")
        r = _graph(src + "\nconsole.log(JSON.stringify([plEffOpts(''), plEffOpts('xhigh')]));")
        vals = re.findall(r'<option value="([^"]*)"', r[0])
        self.assertEqual(vals, [""] + EFFORTS)
        self.assertIn('<option value="" selected>Session effort</option>', r[0])
        self.assertIn('<option value="xhigh" selected>xhigh</option>', r[1])
        self.assertNotIn('value="" selected', r[1])
        pan = js_fn("plPanel")
        # right after «Model», through the generic data-plf path ('' deletes the key; Save -> diff -> Confirm)
        self.assertIn("+ plRow('Effort', '<select data-plf=effort>' + plEffOpts(n.effort || '') + '</select>')", pan)
        self.assertLess(pan.index("data-plf=model"), pan.index("data-plf=effort"))
        self.assertLess(pan.index("data-plf=effort"), pan.index("data-plf=skill"))
        self.assertIn("else if(val === '') delete n[f];", js_fn("plField"))

    def test_r3_effort_saved_and_checked(self):
        # plgCheck runs outside the test block: publish the list on the global object
        r = _graph(_efforts().replace("const PLG_EFFORTS", "globalThis.PLG_EFFORTS") + "\nconst G = plgFrom({name: 'p', defaults: {model: 'inherit', retry: 0}, stages: ["
                   "{title: '구현', agent: 'impl', effort: 'max'}, {title: '검증', agent: 'v'}]});"
                   "const ok = plgCheck(G).errs.length; const st = plgStages(G, plgOrder(G).order);"
                   "G.nodes[1].effort = 'turbo'; const bad = plgCheck(G).errs.map(e => e.msg);"
                   "console.log(JSON.stringify([ok, st.map(s => s.effort || null), Object.keys(st[0]), bad]));")
        self.assertEqual(r[0], 0)
        self.assertEqual(r[1], ["max", None])                         # round-trips; no key when unset
        self.assertEqual(r[2][:3], ["title", "agent", "effort"])
        self.assertEqual(r[3], ["Verify: the effort is not valid"])
        self.assertIn("'model', 'effort', 'skill'", re.search(r"^const PLG_KEYS[^\n]*$", js_all(), re.M).group(0))
        self.assertEqual(json.loads(_efforts().split("=", 1)[1].strip().rstrip(";").replace("'", '"')), EFFORTS)

    def test_r3_direct_request_names_effort(self):
        p = {"name": "bf", "defaults": {"model": "sonnet"}, "stages": [
            {"title": "원인", "agent": "o-dev", "model": "opus", "effort": "high"}, {"title": "수정", "agent": "o-dev"}]}
        t = _run_js("plDmDirect(%s, 'fix it', {}, {})" % json.dumps(p), "plDmDirect")
        self.assertIn("1. 원인 — agent o-dev · model opus · effort high\n", t)
        self.assertIn("2. 수정 — agent o-dev · model sonnet\n", t)
        self.assertIn("model unless inherit, effort when the stage sets one, description", t)
        p["stages"][0].pop("effort")
        t = _run_js("plDmDirect(%s, 'fix it', {}, {})" % json.dumps(p), "plDmDirect")
        self.assertNotIn("effort", t)                                # unchanged request when no stage sets one

    def test_r2_r3_defaults_effort_is_the_effective_level(self):
        # hooks/pl_flow.py fills a valid defaults.effort into every stage without one and enforces it: the screen and request name it too.
        g = ("{ defaults: { model: 'opus', effort: 'high' }, loops: [], nodes: [{ id: 'a', title: '설계', agent: 'x', ui: { x: 0, y: 0 } },"
             " { id: 'b', title: '구현', agent: 'x', effort: 'low', ui: { x: 0, y: 0 } }] }")
        js = _efforts() + "\nconst E = { G: %s }; console.log(JSON.stringify(E.G.nodes.map(n => plNodeHtml(E, n, false, null).match(/<div class=plnm[^>]*>.*?<\\/div>/)[0])));" % g
        en = _card(js)
        self.assertIn('<span class=pleff title="Reasoning effort: high" aria-label="Reasoning effort: high"> · default (high)</span>', en[0])
        self.assertIn("> · low</span>", en[1])                       # the stage's own level wins
        bad = _card(_efforts() + "\nconst E = { G: { defaults: { model: 'opus', effort: 'turbo' }, loops: [], nodes: [{ id: 'a', title: 's', agent: 'x', ui: { x: 0, y: 0 } }] } };"
                    " console.log(JSON.stringify(plNodeHtml(E, E.G.nodes[0], false, null)));")
        self.assertNotIn("pleff", bad)                               # the hook ignores an invalid default: so does the card
        p = {"name": "bf", "defaults": {"model": "sonnet", "effort": "high"}, "stages": [{"title": "원인", "agent": "o-dev"}]}
        pub = "globalThis.PLG_EFFORTS = " + json.dumps(EFFORTS) + ";"
        t = _run_js("(() => { %s return plDmDirect(%s, 'fix it', {}, {}); })()" % (pub, json.dumps(p)), "plDmDirect")
        self.assertIn("1. 원인 — agent o-dev · model sonnet · effort high\n", t)
        self.assertIn("effort when the stage sets one, ", t)
        r = _graph("const G = plgFrom(%s); console.log(JSON.stringify(G.defaults));" % json.dumps(p))
        self.assertEqual(r, {"model": "sonnet", "effort": "high"})   # Save posts G.defaults: the canvas keeps defaults.effort

    def test_r3_schema_hint(self):
        self.assertIn('"model"?,"effort"?:"low|medium|high|xhigh|max","retry"?', js_all())


if __name__ == "__main__":
    unittest.main()
