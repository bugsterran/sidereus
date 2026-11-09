"""Timeline worktree nesting (web/js/74 tlWtNest + tlOrdered): linked-worktree session rows hang under the
main repo's session row (or a header-only group row), folding keeps the head and its needs-you count."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TlWtNest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src = "const tlWtFold = new Set();\n" + js_fn("brNorm") + "\n" + js_fn("tlWtOf") + "\n" + js_fn("tlLiveOf") + "\n" \
            + js_fn("tlWtNest") + "\n" + js_fn("tlOrdered") + r"""
let SESS = [];
const ag = (key, start, run, aid) => ({key, items: [{start, run, aid}]});
const sb = (cwd, kids, wt) => ({head: {key: 'S|' + cwd, sess: true, cwd, items: [{start: 1}]}, kids: kids || [], cwd, plat: ''});
const MAIN = '/r/app', WT = '/r/app/.claude/worktrees/x', OTHER = '/r/other';
const mk = withMain => {
  SESS = [{cwd: WT, plat: '', sid: 'w', wt: {root: WT, main: MAIN, name: 'x'}},
          {cwd: MAIN, plat: '', sid: 'm', wt: {root: MAIN, main: '', name: 'app'}}];
  // rank order: worktree first (best-ranked), other, main
  const o = [sb(WT, [ag('wa', 2, false, 'A')]), sb(OTHER, [ag('oa', 3, false, 'B')])];
  if(withMain) o.push(sb(MAIN, [ag('ma', 4, false, 'C')]));
  return o;
};
const rank = v => v.cwd === WT ? 1 : 2;
const rows = (o, ro) => tlOrdered(tlWtNest(o, rank), ro).map(g => [g.key, g.lv === undefined ? null : g.lv, g.wtHead ? 1 : 0]);
const res = {};
res.nest = rows(mk(true));
res.synth = rows(mk(false));
res.runOnly = rows(mk(true), true);
const o1 = tlWtNest(mk(true), rank);
res.att = o1.filter(v => v.head && v.head.wtPar).map(v => [v.head.key, v.head.wtN, v.head.wtAtt]);
tlWtFold.add(MAIN);
res.fold = rows(mk(true));
res.foldSynth = rows(mk(false));
tlWtFold.clear();
SESS = [];
res.ended = rows([sb(WT, []), sb(MAIN, [])]);
process.stdout.write(JSON.stringify(res));
"""
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        cls.R = json.loads(r.stdout)

    def test_child_under_parent_with_its_agents(self):
        self.assertEqual(self.R["nest"], [
            ["S|/r/app", None, 0], ["ma", 0, 0],
            ["S|/r/app/.claude/worktrees/x", None, 0], ["wa", 1, 0],
            ["S|/r/other", None, 0], ["oa", 0, 0]])

    def test_synthetic_head_when_parent_gone(self):
        self.assertEqual(self.R["synth"][:3], [
            ["W|/r/app", None, 1], ["S|/r/app/.claude/worktrees/x", None, 0], ["wa", 1, 0]])

    def test_folded_group_shows_head_only(self):
        self.assertEqual([k for k, _, _ in self.R["fold"]], ["S|/r/app", "ma", "S|/r/other", "oa"])
        self.assertEqual([k for k, _, _ in self.R["foldSynth"]], ["W|/r/app", "S|/r/other", "oa"])

    def test_head_carries_needs_you_count(self):
        self.assertEqual(self.R["att"], [["S|/r/app", 1, 1]])

    def test_run_only_keeps_child_heads(self):
        self.assertEqual([k for k, _, _ in self.R["runOnly"]],
                         ["S|/r/app", "S|/r/app/.claude/worktrees/x", "S|/r/other"])

    def test_ended_worktree_stays_top_level(self):
        self.assertEqual([k for k, _, _ in self.R["ended"]], ["S|/r/app/.claude/worktrees/x", "S|/r/app"])


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TlWtChip(unittest.TestCase):
    """A worktree session row carries a «worktree» tag; the worktree name is in its title."""

    def _cell(self, wt_kid):
        src = js_fn("brNorm") + "\n" + js_fn("tlWtOf") + "\n" + js_fn("tlSessNmB") + r"""
const esc = s => String(s).replace(/</g, '&lt;'), T = s => s, TV = o => o.msg, U = String, fmtTok = String;
const aiLogo = () => '', repoHue = () => 1, tlStateDot = () => '';
const SESS = [{cwd: '/r/app/.claude/worktrees/x', wt: {root: '/r/app/.claude/worktrees/x', main: '/r/app', name: 'x'}}];
const g = {cwd: '/r/app/.claude/worktrees/x', proj: 'app', plat: '', items: [], wtKid: %d};
process.stdout.write(tlSessNmB(g, {}, 0, 0, true, ''));
""" % wt_kid
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        return r.stdout

    def test_worktree_row_names_its_worktree(self):
        h = self._cell(1)
        self.assertIn('title="x · /r/app/.claude/worktrees/x">worktree</u>', h)

    def test_non_worktree_row_has_no_chip(self):
        self.assertNotIn("tlwtc", self._cell(0))
