"""Timeline «Changes» repo picker (77 tlgSelHtml → 08b ppComboHtml): the shared combobox, an «Auto» first row, one row per
repo (own root + `repos`, deduped, capped) with its count, clean repos last, a pick sets tlgSel, a Timeline row click
follows that session (tlgFollow), and an open popover blocks the chip repaint."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

PRE = r"""
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
let TLGD = [];
const T = s => s, TV = o => o.msg.replace(/\{(\w+)\}/g, (m, k) => String(o.vars[k])), PPC = {}, tlgC = {};
let PPS = null, POP = false, SESS = [], tlgSel = '';
const R = {saved: 0, ticks: 0, paints: 0};
const cpKey = x => 's:' + x.sid, sid8 = s => s.slice(0, 8), stateLbl = s => s === 'busy' ? 'Busy' : '';
function popIsOpen(id){ return POP && id === 'ppop'; } function tlgKeepSave(){ R.saved++; } function tlgTick(){ R.ticks++; }
function tlgChipInner(){ R.paints++; return 'x'; } function setHtml(){ return false; }
function tlgBaseLabel(){ return '<span class=tlgbk>Uncommitted</span>'; } function loadDiff(...a){ (R.opened = R.opened || []).push(a); }
var document = {activeElement: null, getElementById: id => id === 'tlgb' ? {} : null};
"""
SESS = [{"sid": "s1aaaaaaaa", "cwd": "/r/a", "project": "a", "ageSec": 5, "state": "busy", "msg": "SECRET"},
        {"sid": "s2bbbbbbbb", "cwd": "/r/b", "project": "b", "ageSec": 90}]


def run(body):
    auto = "\n".join(re.search(p, js_all(), re.M).group(0) for p in (r"^const TLG_AUTO = .*$", r"^const TLG_MAX_REPOS = .*$"))
    fns = "\n".join(js_fn(n) for n in ("ppComboHtml", "tlgAge", "tlgName", "tlgSessions", "tlgSid", "tlgRepos", "tlgTarget", "tlgFollow",
                                        "tlgShownN", "tlgNum", "tlgCnt", "tlgNoGit", "tlgRepoName", "tlgProj", "tlgNote", "tlgSelHtml",
                                        "tlgDirty", "tlgDetBtn", "tlgDetHtml", "tlgOpenRepo",
                                        "tlgFocusId", "tlgPaint"))
    src = (PRE + auto + "\n" + fns + "\nSESS = " + json.dumps(SESS) + ";\n" + body
           + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TlgSessPick(unittest.TestCase):
    def test_combobox_not_select(self):
        h = run("R.h = tlgSelHtml(tlgTarget());")["h"]
        self.assertIn('<button type=button class="strp ppbtn ppcombo" data-ppk="tlgs"', h)
        self.assertNotIn('<b>Session</b>', h)   # bare: the label is the aria name and first title line, not visible
        self.assertIn('aria-label="Repository: a"', h)
        self.assertIn('title="Repository\n', h)
        self.assertIn("<span class=ppcn>a</span><span class=tlgau>auto</span> ▾</button>", h)
        self.assertIn('title="Repository\nAuto (latest active)\n/r/a · s1aaaaaaaa"', h)
        self.assertNotIn("<select", h)
        self.assertNotIn("<select", js_fn("tlgSelHtml"))

    def test_rows_auto_first_metadata_only(self):
        r = run("const tg = tlgTarget(); tlgSelHtml(tg); PPS = {i: 0, cfg: PPC.tlgs};"
                "R.rows = PPC.tlgs.flat('').map((e, i) => PPC.tlgs.rowHtml(e, i)); R.q = PPC.tlgs.flat('b').map(e => e.p);")
        self.assertEqual(len(r["rows"]), 3)
        self.assertIn("ppcur", r["rows"][0])
        self.assertIn("<span class=cmdkp>Auto (latest active)</span><span class=cmdkc>a · s1aaaaaa · Busy</span>", r["rows"][0])
        self.assertIn('title="/r/b\nb · s2bbbbbbbb"><span class=cmdkp>b</span><span class=cmdkc>s2bbbbbb</span>', r["rows"][2])
        self.assertNotIn("SECRET", "".join(r["rows"]))
        self.assertEqual(r["q"], ["r:/r/b"])

    def test_pick_sets_and_auto_clears(self):
        r = run("tlgSelHtml(tlgTarget()); PPC.tlgs.pick('r:/r/b'); R.a = tlgSel; const t = tlgTarget(); R.cur = (tlgSelHtml(t), PPC.tlgs.cur);"
                "R.t = [t.cwd, t.ck, t.sid]; PPC.tlgs.pick('auto'); R.b = tlgSel;")
        self.assertEqual([r["a"], r["cur"], r["b"], r["saved"], r["ticks"]], ["r:/r/b", "r:/r/b", "", 2, 2])
        self.assertEqual(r["t"], ["/r/b", "/r/b", "s2bbbbbbbb"])

    def test_repos_deduped_worktree_own_option_capped(self):
        # s1 (cwd /r/a/sub, root /r/a) also edited a worktree; s2 touched /r/a too — one option per repo, first-seen order.
        r = run("SESS = [{sid: 's1aaaaaaaa', cwd: '/r/a/sub', root: '/r/a', project: 'a', ageSec: 5, repos: ['/r/a', '/r/a-wt']},"
                "{sid: 's2bbbbbbbb', cwd: '/r/b', project: 'b', ageSec: 9, repos: ['/r/a', '/r/b']}];"
                "R.r = tlgRepos().map(e => [e.ck, e.cwd, e.ss.length]);"
                "SESS = Array.from({length: 40}, (_, i) => ({sid: 'x' + i, cwd: '/q/' + i, ageSec: i})); R.n = tlgRepos().length;")
        self.assertEqual(r["r"], [["/r/a", "/r/a/sub", 2], ["/r/a-wt", "/r/a-wt", 1], ["/r/b", "/r/b", 1]])
        self.assertEqual(r["n"], 30)

    def test_rows_show_counts_escaped_clean_last(self):
        r = run("SESS = [{sid: 's1aaaaaaaa', cwd: '/r/a', project: 'a', ageSec: 5, repos: ['/r/<x>', '/r/c']},"
                "{sid: 's2bbbbbbbb', cwd: '/r/b', project: 'b', ageSec: 9}];"
                "tlgC['/r/a'] = {d: {ok: true, n: 0, add: 0, del: 0, files: []}};"
                "tlgC['/r/<x>'] = {d: {ok: true, n: 2, add: 5, del: 1, files: []}};"
                "tlgC['/r/b'] = {d: {ok: true, n: 1, add: 1, del: 0, files: []}};"
                "const tg = tlgTarget(); tlgSelHtml(tg); PPS = {i: -1, cfg: PPC.tlgs};"
                "R.p = PPC.tlgs.items.map(e => e.p); R.rows = PPC.tlgs.flat('').map((e, i) => PPC.tlgs.rowHtml(e, i));")
        self.assertEqual(r["p"], ["auto", "r:/r/<x>", "r:/r/b", "r:/r/c", "r:/r/a"])   # changed, changed, not fetched, clean
        self.assertIn("<span class=cmdkp>&lt;x></span><span class=tlgcn>2 files <span class=tlga>+5</span><span class=tlgd>−1</span></span>"
                      "<span class=cmdkc>a · s1aaaaaa</span>", r["rows"][1])   # foreign repo names its session's project
        self.assertNotIn("<x>", "".join(r["rows"]))
        self.assertIn(" tlg0", r["rows"][4])
        self.assertNotIn("tlgcn", r["rows"][3])
        self.assertNotIn(" tlg0", r["rows"][1])

    def test_not_a_repo_shows_no_git_last_greyed(self):
        r = run("SESS = [{sid: 's1aaaaaaaa', cwd: '/r/a', project: 'a', ageSec: 5, repos: ['/r/n', '/r/c', '/r/u']}];"
                "tlgC['/r/n'] = {d: {ok: false, msg: 'Not a git repository.'}}; tlgC['/r/c'] = {d: {ok: true, n: 0, files: []}};"
                "tlgSelHtml(tlgTarget()); PPS = {i: -1, cfg: PPC.tlgs};"
                "R.p = PPC.tlgs.items.map(e => e.p); R.row = PPC.tlgs.rowHtml(PPC.tlgs.items[4], 4);")
        self.assertEqual(r["p"], ["auto", "r:/r/a", "r:/r/u", "r:/r/c", "r:/r/n"])
        self.assertIn(" tlg0", r["row"])
        self.assertIn("<span class=tlgcn>No git</span>", r["row"])

    def test_badge_counts_dirty_repos_untracked_excluded(self):
        # /r/a: 1 tracked + 1 untracked; /r/b: untracked only (n 1, untracked 1) => not dirty; /r/c clean.
        r = run("SESS = [{sid: 's1aaaaaaaa', cwd: '/r/a', project: 'a', ageSec: 5, repos: ['/r/b', '/r/c']}];"
                "tlgC['/r/a'] = {d: {ok: true, n: 2, untracked: 1, add: 3, del: 1, files: [{path: 'n', new: true, add: 2}]}};"
                "tlgC['/r/b'] = {d: {ok: true, n: 1, untracked: 1, files: [{path: 'x', new: true}]}};"
                "tlgC['/r/c'] = {d: {ok: true, n: 0, files: []}};"
                "R.h = tlgSelHtml(tlgTarget()); tlgC['/r/a'].d = {ok: true, n: 0, files: []}; R.h0 = tlgSelHtml(tlgTarget());")
        self.assertIn("<span class=tlgnb>1</span> ▾</button>", r["h"])
        self.assertIn('aria-label="Repository: a · Repositories with uncommitted changes: 1"', r["h"])
        self.assertNotIn("tlgnb", r["h0"])
        self.assertIn('aria-label="Repository: a"', r["h0"])

    def test_details_popup_sorted_escaped_opens_diff(self):
        r = run("SESS = [{sid: 's1aaaaaaaa', cwd: '/r/a', project: 'a', ageSec: 5, repos: ['/r/<x>', '/r/b']}];"
                "R.none = tlgDetBtn(tlgTarget());"
                "tlgC['/r/a'] = {d: {ok: true, n: 1, add: 1, del: 0, files: [], base: 'abc'}};"
                "tlgC['/r/<x>'] = {d: {ok: true, n: 5, add: 9, del: 2, files: []}};"
                "tlgC['/r/b'] = {d: {ok: true, n: 0, files: []}};"
                "const tg = tlgTarget(); R.btn = tlgDetBtn(tg); R.pop = tlgDetHtml(tg); R.keys = TLGD.map(e => e.ck);"
                "tlgOpenRepo(TLGD[1]); tlgOpenRepo(TLGD[0]);"
                "tlgC['/r/a'].d.n = 0; tlgC['/r/<x>'].d.n = 0; R.empty = tlgDetHtml(tlgTarget());")
        self.assertEqual(r["none"], "")                     # nothing fetched yet: no «Details»
        self.assertIn('id=tlgdt', r["btn"])
        self.assertIn('aria-label="Details"', r["btn"])
        self.assertEqual(r["keys"], ["/r/<x>", "/r/a"])      # most files first, clean /r/b left out
        self.assertIn("Repositories with uncommitted changes: 2 <span class=tlgbk>", r["pop"])
        self.assertIn('data-tlgi="0" title="/r/&lt;x>"><span class=tlgdn>&lt;x></span><span class=tlgdf>5 files</span>', r["pop"])
        self.assertNotIn("<x>", r["pop"])
        self.assertEqual(r["opened"], [["/r/a", "", "b:abc", "", "s1aaaaaaaa"], ["/r/<x>", "", "work", "", "s1aaaaaaaa"]])
        self.assertIn("Repositories with uncommitted changes: 0", r["empty"])
        self.assertIn("<div class=tlgde>No uncommitted changes</div>", r["empty"])

    def test_row_click_follows_session(self):
        r = run("tlgFollow('/r/b', '', 'agent-tool-id'); R.a = tlgSel; tlgFollow('/r/x', '', 'sess:/r/x|s1aaaaaaaa'); R.b = tlgSel;"
                "tlgFollow('/r/gone', '', 'sess:/r/gone|old'); R.c = tlgSel; tlgFollow('/r/b', 'gemini', 'ext:gemini|zz'); R.d = tlgSel;")
        self.assertEqual([r["a"], r["b"], r["c"], r["d"]], ["s:s2bbbbbbbb", "s:s1aaaaaaaa", "s:s1aaaaaaaa", "r:/r/b"])
        self.assertEqual((r["saved"], r["ticks"]), (3, 3))
        wire = js_fn("tlWireRows")
        self.assertEqual(wire.count("tlgFollow(tr.dataset.tlc, tr.dataset.tlp, "), 2)

    def test_hidden_with_one_session(self):
        self.assertEqual(run("SESS = SESS.slice(0, 1); R.h = tlgSelHtml(tlgTarget());")["h"], "")

    def test_open_popover_skips_repaint(self):
        self.assertEqual(run("POP = true; tlgPaint();")["paints"], 0)
        self.assertEqual(run("tlgPaint();")["paints"], 1)
        self.assertNotIn("tlgss", js_fn("tlgFocusId"))


if __name__ == "__main__":
    unittest.main()
