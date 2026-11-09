"""Sessions list worktree nesting (web/js/40bb sessWtGroups / sessWtAttn): children follow their main repo's
session, a missing main gets a header-only group, the group sits at its best-ranked member's index.
With a main session in view, worktree sessions render as .swts sub-lines inside its card (sessWtSubHtml)."""
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



RENDER = "\n".join(js_fn(n) for n in ("brNorm", "sessWtNorm", "sessWtGroups", "sessWtAttn", "sessWtNeed", "sessWtCount", "sessWtCaret",
                                      "sessWtHeadHtml", "sessWtLead", "sessWtSubHtml", "sessWtListHtml", "sessWtAny", "sessOpenRow")) + r"""
const wtFold = new Set();
let cpFlash = '';
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const T = s => s, TV = o => o.msg.replace(/\{(\w+)\}/g, (_, k) => o.vars[k]);
const AGO = t => t + ' ago', ago = s => s + 's', cpKey = x => 's:' + x.sid;
const sessLabel = x => 'L:' + (x.state || ''), sessCardTip = x => x.cwd + ' · ' + x.sid;
// stub card: echoes the tail so the test sees what lands inside the main card
const sessRowHtml = (x, tail) => '<div class="sxw " data-ssid="' + x.sid + '"><span class=sxl></span>' + (tail || '') + '</div>';
const M = '/r/app', S = (sid, wt, extra) => Object.assign({sid, cwd: wt ? wt.root : '/x/' + sid, wt, ageSec: 5}, extra || {});
const main = {root: M, main: '', name: 'app'};
const w = n => ({root: '/r/app/.claude/worktrees/' + n, main: M, name: n});
const opened = [];
let SESS = [{sid: 'e1'}];
const extTid = x => x && x.sid === 'e1' ? 'ext:e1' : '';
const openSession = (cwd, t) => opened.push([cwd, t]);
const withHead = [S('p', main), S('a', w('a'), {state: 'ask'}), S('b', w('b'), {blocked: 'x'})];
const orphan = [S('o', null), S('a', w('a'))];
const out = {head: sessWtListHtml(withHead), orphan: sessWtListHtml(orphan)};
wtFold.add('/r/app');
out.folded = sessWtListHtml(orphan);
wtFold.clear();
out.anyHead = sessWtAny(withHead); out.anyOrphan = sessWtAny(orphan);
out.fallback = sessWtSubHtml([S('z', {root: '/r/z', main: M, name: ''}, {branch: 'feat<x'})]);
cpFlash = 's:a'; out.flash = sessWtSubHtml([S('a', w('a'))]);
out.r1 = sessOpenRow('/r/w', 'k'); out.r2 = sessOpenRow('/r/e', 'e1'); out.r3 = sessOpenRow('', 'k');
out.opened = opened;
process.stdout.write(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SessWtSubLine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r = subprocess.run(node_e(RENDER), capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        cls.R = json.loads(r.stdout)

    def test_head_card_holds_sub_lines(self):
        h = self.R["head"]
        self.assertEqual(h.count('class="sxw'), 1)
        self.assertEqual(h.count('stiw swts'), 2)
        self.assertIn('data-ssid="a"', h)
        self.assertIn('data-ssid="b"', h)
        self.assertEqual(h.count('class="stree swtsl"'), 1)   # same .stree indent as subagent sub-lines
        self.assertTrue(h.endswith('</div></div></div></div>'))   # subs land before the card's closing tag

    def test_head_has_no_caret_or_child_rows(self):
        self.assertNotIn("swtbr", self.R["head"])
        self.assertNotIn("swtg", self.R["head"])
        self.assertNotIn("swtk", self.R["head"])

    def test_orphan_keeps_header_group(self):
        o = self.R["orphan"]
        self.assertIn('class="swth"', o)
        self.assertIn('class="sxw swtk', o)
        self.assertNotIn("swts", o)
        self.assertIn('class="swth swthf"', self.R["folded"])
        self.assertNotIn("swtk", self.R["folded"])

    def test_sub_line_attention(self):
        self.assertIn("swta-ask", self.R["head"])
        self.assertIn("swta-blocked", self.R["head"])

    def test_expand_all_only_for_orphans(self):
        self.assertFalse(self.R["anyHead"])
        self.assertTrue(self.R["anyOrphan"])

    def test_name_falls_back_to_branch_escaped(self):
        self.assertIn("<span class=v>feat&lt;x</span>", self.R["fallback"])
        self.assertNotIn("feat<x", self.R["fallback"])

    def test_sub_line_metadata(self):
        f = self.R["flash"]
        self.assertIn("cphit", f)
        self.assertIn('class="k w">Worktree<', f)
        self.assertIn("L:", f)
        self.assertIn("5s ago", f)
        self.assertNotIn("cphit", self.R["head"])

    def test_open_row_matches_row_click(self):
        self.assertEqual([self.R["r1"], self.R["r2"], self.R["r3"]], [True, True, False])
        self.assertEqual(self.R["opened"], [["/r/w", "sess:/r/w|k"], ["/r/e", "ext:e1"]])


JUMP = js_fn("cpFindRow") + "\n" + js_fn("sessClick") + r"""
const el = a => ({getAttribute: k => a[k] === undefined ? null : a[k]});
const rows = [el({'data-ssid': 'p', 'data-scwd': '/r/app'})];
const subs = [el({'data-ssid': 'a', 'data-scwd': '/r/app/wt/a'})];
const document = {querySelectorAll: s => s === '#sess .sxw' ? rows : s === '#sess .swts[data-ssid]' ? subs : []};
const out = {sid: cpFindRow({sid: 'a', cwd: ''}) === subs[0], cwd: cpFindRow({cwd: '/r/app/wt/a'}) === subs[0],
             row: cpFindRow({sid: 'p'}) === rows[0], none: cpFindRow({sid: 'zz', cwd: '/nope'})};
// sessClick: the target sits inside both a .swts line and the card header area; the .swts branch must win.
const window = {getSelection: () => ''};
const acctOthClick = () => false, calls = [];
const sessOpenRow = (cwd, sid) => { calls.push(['open', cwd, sid]); return true; };
const hdr = {closest: () => ({getAttribute: k => k === 'data-scwd' ? '/r/app' : 'p'})};
const target = {tagName: 'SPAN', closest: s => s === '.swts[data-ssid]' ? subs[0] : s === '.sxw > .sx, .sxw > .sx2, .sxw > .sq' ? hdr : null};
let stopped = 0;
sessClick({target, stopPropagation: () => { stopped++; }});
out.calls = calls; out.stopped = stopped;
process.stdout.write(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SessWtJump(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r = subprocess.run(node_e(JUMP), capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        cls.R = json.loads(r.stdout)

    def test_palette_finds_sub_line_by_sid_and_cwd(self):
        self.assertTrue(self.R["sid"])
        self.assertTrue(self.R["cwd"])
        self.assertTrue(self.R["row"])
        self.assertIsNone(self.R["none"])

    def test_sub_line_click_opens_that_session_not_the_card(self):
        self.assertEqual(self.R["calls"], [["open", "/r/app/wt/a", "a"]])
        self.assertEqual(self.R["stopped"], 1)


if __name__ == "__main__":
    unittest.main()
