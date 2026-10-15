"""Stage agent/skill pickers (web/js/48b plPickScoped, 48d plPanel): only the selected project's own entries + built-ins;
a stage agent/skill outside those stays listed first and marked. Pure functions under node + static reads."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

AGS = [{"name": "cart-fix", "scope": "project"}, {"name": "home-reviewer", "scope": "user"},
       {"name": "other-proj-qa", "scope": "user"}, {"name": "cart-qa", "scope": "user"}]


def _js(expr):
    consts = "\n".join(re.search(r"^const %s[^\n]*$" % c, js_all(), re.M).group(0) for c in ("PL_PICK_BUILTIN", "PL_BUILTIN_AG"))
    pre = "const esc = s => String(s), T = s => s;\n" + js_fn("plOpt") + "\n" + js_fn("plGrpOpts") + "\n" + js_fn("plAgOpts") + "\n" + js_fn("plSkOpts") + "\n"
    src = pre + consts + "\n" + js_fn("plAgMissing") + "\n" + js_fn("plFolder") + "\n" + js_fn("plStem") + "\n" + js_fn("plOwnName") + "\n" + js_fn("plPickScoped") + "\n" + js_fn("plPickAgents") + "\n" + js_fn("plPickSkills") + "\nconsole.log(JSON.stringify(" + expr + "));"
    return json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True).stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class AgentPick(unittest.TestCase):
    def test_project_and_builtins_only(self):
        r = _js("plPickAgents(%s, 'cart-fix', '/w/.cart/')" % json.dumps(AGS))
        self.assertEqual([a["name"] for a in r], ["cart-fix", "cart-qa", "general-purpose", "Explore", "Plan", "claude-code-guide", "statusline-setup"])
        self.assertFalse(any(a["out"] for a in r))

    def test_set_global_agent_kept_and_marked(self):
        r = _js("plPickAgents(%s, 'home-reviewer', '/w/cart')" % json.dumps(AGS))
        self.assertEqual(r[0], {"name": "home-reviewer", "out": True, "grp": "out"})
        self.assertNotIn("other-proj-qa", [a["name"] for a in r])
        # still installed (user scope): not reported missing, so dispatch is unchanged
        self.assertFalse(_js("plAgMissing('home-reviewer', %s)" % json.dumps(AGS)))

    def test_sibling_folder_stem_counts_as_own(self):
        ags = [{"name": "otherproj-dev", "scope": "user"}, {"name": "cart-qa", "scope": "user"}]
        r = _js("plPickAgents(%s, '', '/w/otherproj-api')" % json.dumps(ags))
        self.assertEqual([a["name"] for a in r if a["grp"] == "own"], ["otherproj-dev"])

    def test_unknown_agent_marked_and_missing(self):
        r = _js("plPickAgents(%s, 'ghost')" % json.dumps(AGS))
        self.assertEqual(r[0], {"name": "ghost", "out": True, "grp": "out"})
        self.assertTrue(_js("plAgMissing('ghost', %s)" % json.dumps(AGS)))

    def test_builtin_current_not_duplicated(self):
        r = _js("plPickAgents([], 'Explore')")
        self.assertEqual([a["name"] for a in r].count("Explore"), 1)
        self.assertFalse(any(a["out"] for a in r))

    def test_optgroups(self):
        h = _js("plAgOpts(plPickAgents(%s, 'ghost', '/w/cart'), %s, 'ghost')" % (json.dumps(AGS), json.dumps(AGS)))
        self.assertTrue(h.startswith('<option value="ghost" selected>ghost (not installed'), h)
        self.assertLess(h.index('<optgroup label="This project"><option value="cart-fix">'), h.index('<optgroup label="Built-in"><option value="general-purpose">'))
        h = _js("plAgOpts(plPickAgents([], 'Plan', ''), [], 'Plan')")
        self.assertNotIn("This project", h)
        self.assertTrue(h.startswith('<optgroup label="Built-in">'), h)

    def test_panel_uses_selected_project_data(self):
        self.assertIn("ags = plPickAgents(d.agents, n.agent, PLS.proj)", js_fn("plPanel"))
        # canvas is fed PLS.data[PLS.proj] (re-fetched per project in plLoad), so a project switch re-scopes the list
        body = js_fn("plBody")
        self.assertIn("const d = PLS.data[PLS.proj];", body)
        self.assertIn("plCanvas(p, d, lt)", body)
        self.assertIn("plAgOpts(ags, d.agents, n.agent)", js_fn("plPanel"))
        self.assertIn("'outside this project'", js_fn("plAgOpts"))
        self.assertIn("sks = plPickSkills(d.skills, n.skill, PLS.proj, ((PLS.projs && PLS.projs.projects) || []).map(x => x.path).concat(Object.keys(PLS.data)))", js_fn("plPanel"))
        self.assertIn("plSkOpts(sks, d.skills, n.skill || '')", js_fn("plPanel"))


SKS = [{"name": "requirements", "scope": "project"}, {"name": "sidereus-ship", "scope": "project"},
       {"name": "otherproj-review", "scope": "user"}, {"name": "docnote", "scope": "user"}, {"name": "sidereus-extra", "scope": "user"}]


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SkillPick(unittest.TestCase):
    PROJS = json.dumps(["/Users/x/.sidereus", "/w/otherproj", "/w/sidereus"])

    def test_other_project_skill_hidden_generic_kept(self):
        r = _js("plPickSkills(%s, '', '/Users/x/.sidereus', %s)" % (json.dumps(SKS), self.PROJS))
        self.assertEqual([(a["name"], a["grp"]) for a in r],
                         [("requirements", "own"), ("sidereus-ship", "own"), ("sidereus-extra", "own"), ("docnote", "bi")])

    def test_prefix_of_unknown_project_is_generic(self):
        r = _js("plPickSkills(%s, '', '/w/sidereus', [])" % json.dumps(SKS))
        self.assertIn(("otherproj-review", "bi"), [(a["name"], a["grp"]) for a in r])
        r = _js("plPickSkills(%s, '', '/w/otherproj', %s)" % (json.dumps(SKS), self.PROJS))
        self.assertIn(("otherproj-review", "own"), [(a["name"], a["grp"]) for a in r])
        self.assertNotIn("sidereus-extra", [a["name"] for a in r])

    def test_sibling_repo_stem_hides_and_generic_stays(self):
        sks = SKS + [{"name": "github-study-log", "scope": "user"}]
        projs = json.dumps(["/Users/x/.sidereus", "/w/otherproj-api", "/w/otherproj-origin"])
        r = _js("plPickSkills(%s, '', '/Users/x/.sidereus', %s)" % (json.dumps(sks), projs))
        self.assertNotIn("otherproj-review", [a["name"] for a in r])
        self.assertEqual([a["name"] for a in r if a["grp"] == "bi"], ["docnote", "github-study-log"])
        r = _js("plPickSkills(%s, '', '/w/otherproj-api', %s)" % (json.dumps(sks), projs))
        self.assertIn(("otherproj-review", "own"), [(a["name"], a["grp"]) for a in r])

    def test_set_outside_skill_kept_on_top(self):
        r = _js("plPickSkills(%s, 'otherproj-review', '/w/sidereus', %s)" % (json.dumps(SKS), self.PROJS))
        self.assertEqual(r[0], {"name": "otherproj-review", "out": True, "grp": "out"})
        h = _js("plSkOpts(plPickSkills(%s, 'otherproj-review', '/w/sidereus', %s), %s, 'otherproj-review')" % (json.dumps(SKS), self.PROJS, json.dumps(SKS)))
        self.assertTrue(h.startswith('<option value="otherproj-review" selected>otherproj-review (outside this project)</option><optgroup label="This project">'), h)
        self.assertIn('<optgroup label="General"><option value="docnote">', h)
        self.assertNotIn("Built-in", h)
        h = _js("plSkOpts(plPickSkills(%s, 'ghost', '/w/sidereus'), %s, 'ghost')" % (json.dumps(SKS), json.dumps(SKS)))
        self.assertTrue(h.startswith('<option value="ghost" selected>ghost (not installed)</option>'), h)


if __name__ == "__main__":
    unittest.main()
