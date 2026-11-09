"""Sessions list worktree nesting (web/js/40bb sessWtGroups / sessWtAttn): children follow their main repo's
session, a missing main gets a header-only group, the group sits at its best-ranked member's index."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SessWtNest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src = js_fn("brNorm") + "\n" + js_fn("sessWtNorm") + "\n" + js_fn("sessWtGroups") + "\n" + js_fn("sessWtAttn") + r"""
const M = '/r/app', S = (sid, wt, extra) => Object.assign({sid, cwd: wt ? wt.root : '/x/' + sid, wt}, extra || {});
const main = {root: M, main: '', name: 'app'};
const w = n => ({root: '/r/app/.claude/worktrees/' + n, main: M, name: n});
const view = gs => gs.map(g => ({h: g.head ? g.head.sid : null, main: g.main, name: g.name, k: g.kids.map(x => x.sid)}));
const out = {
  // parent ranked first, an unrelated row between the two worktree kids
  nested: view(sessWtGroups([S('p', main), S('o', null), S('a', w('a')), S('b', w('b'))])),
  // no main-checkout session in view
  orphan: view(sessWtGroups([S('o', null), S('a', w('a'))])),
  // a running child ranked above its parent lifts the whole group
  lifted: view(sessWtGroups([S('o', null), S('a', w('a')), S('p', main)])),
  // a row without wt heads its repo by cwd (/private/ prefix normalised)
  bycwd: view(sessWtGroups([Object.assign(S('q', null), {cwd: '/private/r/app/'}), S('a', w('a'))])),
  // two main-checkout sessions: children attach to the first-ranked one
  twop: view(sessWtGroups([S('p1', main), S('p2', main), S('a', w('a'))])),
  attn: [sessWtAttn([{state: 'ask'}, {blocked: true}]), sessWtAttn([{gotPrompt: 3}, {state: 'ask'}]),
         sessWtAttn([{state: 'abort'}, {gotPrompt: 2}]), sessWtAttn([{gotPrompt: 2}]), sessWtAttn([{state: 'tool'}]), sessWtAttn(null)],
};
process.stdout.write(JSON.stringify(out));
"""
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        cls.R = json.loads(r.stdout)

    def test_children_follow_parent_in_order(self):
        self.assertEqual(self.R["nested"][0], {"h": "p", "main": "/r/app", "name": "app", "k": ["a", "b"]})
        self.assertEqual(self.R["nested"][1]["h"], "o")
        self.assertEqual(len(self.R["nested"]), 2)

    def test_missing_parent_is_header_only(self):
        self.assertEqual(self.R["orphan"][1], {"h": None, "main": "/r/app", "name": "app", "k": ["a"]})

    def test_group_sits_at_best_member(self):
        self.assertEqual([g["h"] for g in self.R["lifted"]], ["o", "p"])
        self.assertEqual(self.R["lifted"][1]["k"], ["a"])

    def test_parent_by_cwd_without_wt(self):
        self.assertEqual(self.R["bycwd"], [{"h": "q", "main": "/r/app", "name": "app", "k": ["a"]}])

    def test_first_ranked_parent_takes_children(self):
        self.assertEqual(self.R["twop"], [{"h": "p1", "main": "/r/app", "name": "app", "k": ["a"]},
                                          {"h": "p2", "main": "", "name": "", "k": []}])

    def test_attention_priority(self):
        self.assertEqual(self.R["attn"], ["blocked", "ask", "abort", "stuck", "", ""])


if __name__ == "__main__":
    unittest.main()
