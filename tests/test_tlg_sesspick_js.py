"""Timeline head pickers: the session combobox (77 tlgSelHtml → 08b ppComboHtml 'tlgs', «Auto» first, one row per live
session) and the «Changes» chip's own repo list (77 tlgRepoCfg 'tlgr': the followed session's repos only, with counts,
clean repos last). Picks set tlgSel, a Timeline row click follows that session (tlgFollow), and an open popover blocks
the chip repaint."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

PRE = r"""
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
let ppOpen = () => {};
const T = s => s, TV = o => o.msg.replace(/\{(\w+)\}/g, (m, k) => String(o.vars[k])), PPC = {}, tlgC = {};
let PPS = null, POP = false, SESS = [], tlgSel = '';
const R = {saved: 0, ticks: 0, paints: 0};
const cpKey = x => 's:' + x.sid, sid8 = s => s.slice(0, 8), stateLbl = s => s === 'busy' ? 'Busy' : '';
function popIsOpen(id){ return POP && id === 'ppop'; } function tlgKeepSave(){ R.saved++; } function tlgTick(){ R.ticks++; }
function setHtml(){ R.paints++; return false; } function tlgBaseText(){ return 'Uncommitted'; } function tlgBaseTip(){ return ''; }
function tlgShared(){ return []; }
function tlgBaseLabel(){ return '<span class=tlgbk>Uncommitted</span>'; } function loadDiff(...a){ (R.opened = R.opened || []).push(a); }
var document = {activeElement: null, getElementById: id => id === 'tlgb' ? {} : null};
"""
SESS = [{"sid": "s1aaaaaaaa", "cwd": "/r/a", "project": "a", "ageSec": 5, "state": "busy", "msg": "SECRET"},
        {"sid": "s2bbbbbbbb", "cwd": "/r/b", "project": "b", "ageSec": 90}]


def run(body):
    auto = "\n".join(re.search(p, js_all(), re.M).group(0) for p in (r"^const TLG_AUTO = .*$", r"^const TLG_MAX_REPOS = .*$",
                                                                          r"^let tlgSelS = .*$"))
    fns = "\n".join(js_fn(n) for n in ("ppComboHtml", "tlgAge", "tlgName", "tlgSessions", "tlgSid", "tlgRepos", "tlgTarget", "tlgFollow",
                                        "tlgShownN", "tlgNum", "tlgCnt", "tlgNoGit", "tlgRepoName", "tlgProj", "tlgNote", "tlgSelHtml", "tlgRepoCfg",
                                        "tlgDirty", "tlgOpen", "tlgChipClick", "tlgOpenRepo", "tlgChipInner",
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
        self.assertIn('aria-label="Session: a"', h)
        self.assertIn("<span class=ppcn>a</span><span class=tlgau>auto</span> ▾</button>", h)
        self.assertIn('title="Session\nAuto (latest active)\n/r/a · s1aaaaaa"', h)
        self.assertNotIn("tlgnb", h)   # the repo-count badge sits on the chip, not the session button
        self.assertNotIn("<select", h)

    def test_session_rows_auto_first_metadata_only(self):
        r = run("const tg = tlgTarget(); tlgSelHtml(tg); PPS = {i: 0, cfg: PPC.tlgs};"
                "R.rows = PPC.tlgs.flat('').map((e, i) => PPC.tlgs.rowHtml(e, i)); R.q = PPC.tlgs.flat('b').map(e => e.p);"
                "R.ph = [PPC.tlgs.ph, PPC.tlgs.empty, PPC.tlgs.foot];")
        self.assertEqual(len(r["rows"]), 3)
        self.assertIn("ppcur", r["rows"][0])
        self.assertIn("<span class=cmdkp>Auto (latest active)</span><span class=cmdkc>a · s1aaaaaa · Busy</span>", r["rows"][0])
        self.assertIn('title="/r/b · s2bbbbbb"><span class=cmdkp>b</span><span class=cmdkc>s2bbbbbb</span>', r["rows"][2])
        self.assertNotIn("SECRET", "".join(r["rows"]))
        self.assertEqual(r["q"], ["s:s2bbbbbbbb"])
        self.assertEqual(r["ph"], ["Find a session", "No matching sessions", None])

    def test_session_pick_follows_its_repo_and_auto_clears(self):
        r = run("tlgSelHtml(tlgTarget()); PPC.tlgs.pick('s:s2bbbbbbbb'); R.a = tlgSel; const t = tlgTarget(); R.cur = (tlgSelHtml(t), PPC.tlgs.cur);"
                "R.t = [t.cwd, t.ck, t.sid]; PPC.tlgs.pick('auto'); R.b = tlgSel;")
        self.assertEqual([r["a"], r["cur"], r["b"], r["saved"], r["ticks"]], ["s:s2bbbbbbbb", "s:s2bbbbbbbb", "", 2, 2])
        self.assertEqual(r["t"], ["/r/b", "/r/b", "s2bbbbbbbb"])

    def test_chip_list_is_followed_session_repos_only(self):
        r = run("SESS = [{sid: 's1aaaaaaaa', cwd: '/r/a', project: 'a', ageSec: 5, repos: ['/r/w']},"
                "{sid: 's2bbbbbbbb', cwd: '/r/b', project: 'b', ageSec: 9, repos: ['/r/x', '/r/y']}];"
                "R.a = tlgRepoCfg(tlgTarget()).items.map(e => e.p); tlgSel = 's:s2bbbbbbbb';"
                "R.b = tlgRepoCfg(tlgTarget()).items.map(e => e.p); R.k = PPC.tlgr.k;"
                "PPC.tlgr.pick('r:/r/y'); R.c = tlgSel; const t = tlgTarget(); R.row = t.row.sid; R.cur = (tlgSelHtml(t), PPC.tlgs.cur);"
                "R.d = tlgRepoCfg(t).items.map(e => e.p); PPC.tlgr.pick('r:/r/b'); R.e = tlgSel;"
                "tlgSel = ''; tlgRepoCfg(tlgTarget()); PPC.tlgr.pick('r:/r/a'); R.f = tlgSel;")
        self.assertEqual(r["a"], ["r:/r/a", "r:/r/w"])
        self.assertEqual(r["b"], ["r:/r/b", "r:/r/x", "r:/r/y"])
        self.assertEqual([r["k"], r["c"], r["row"], r["cur"]], ["tlgr", "r:/r/y", "s2bbbbbbbb", "s:s2bbbbbbbb"])
        self.assertEqual(r["d"], r["b"])
        self.assertEqual([r["e"], r["f"]], ["s:s2bbbbbbbb", ""])   # own repo = back to following the session (auto stays auto)

    def test_one_repo_session_has_no_list(self):
        r = run("SESS = [{sid: 's1aaaaaaaa', cwd: '/r/a', project: 'a', ageSec: 5}, {sid: 's2bbbbbbbb', cwd: '/r/b', ageSec: 9, repos: ['/r/x']}];"
                "R.n = tlgRepoCfg(tlgTarget()); R.h = tlgChipInner(tlgTarget());")
        self.assertIsNone(r["n"])
        self.assertNotIn("data-ppo", r["h"])

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
                "tlgSel = 'r:/r/b'; tlgRepoCfg(tlgTarget()); tlgSel = ''; const tg = tlgTarget(); tlgRepoCfg(tg); PPS = {i: -1, cfg: PPC.tlgr};"
                "R.p = PPC.tlgr.items.map(e => e.p); R.rows = PPC.tlgr.flat('').map((e, i) => PPC.tlgr.rowHtml(e, i));")
        self.assertEqual(r["p"], ["r:/r/<x>", "r:/r/c", "r:/r/a"])   # changed, not fetched, clean; s2's /r/b is not s1's
        self.assertIn("<span class=cmdkp>&lt;x></span><span class=tlgcn>2 files <span class=tlga>+5</span><span class=tlgd>−1</span></span>"
                      "<span class=cmdkc>a · s1aaaaaa</span>", r["rows"][0])   # foreign repo names its session's project
        self.assertNotIn("<x>", "".join(r["rows"]))
        self.assertIn(" tlg0", r["rows"][2])
        self.assertNotIn("tlgcn", r["rows"][1])
        self.assertNotIn(" tlg0", r["rows"][0])

    def test_not_a_repo_shows_no_git_last_greyed(self):
        r = run("SESS = [{sid: 's1aaaaaaaa', cwd: '/r/a', project: 'a', ageSec: 5, repos: ['/r/n', '/r/c', '/r/u']}];"
                "tlgC['/r/n'] = {d: {ok: false, msg: 'Not a git repository.'}}; tlgC['/r/c'] = {d: {ok: true, n: 0, files: []}};"
                "tlgRepoCfg(tlgTarget()); PPS = {i: -1, cfg: PPC.tlgr};"
                "R.p = PPC.tlgr.items.map(e => e.p); R.row = PPC.tlgr.rowHtml(PPC.tlgr.items[3], 3);")
        self.assertEqual(r["p"], ["r:/r/a", "r:/r/u", "r:/r/c", "r:/r/n"])
        self.assertIn(" tlg0", r["row"])
        self.assertIn("<span class=tlgcn>No git</span>", r["row"])

    def test_badge_counts_dirty_repos_untracked_excluded(self):
        # /r/a: 1 tracked + 1 untracked; /r/b: untracked only (n 1, untracked 1) => not dirty; /r/c clean.
        r = run("SESS = [{sid: 's1aaaaaaaa', cwd: '/r/a', project: 'a', ageSec: 5, repos: ['/r/b', '/r/c']}];"
                "tlgC['/r/a'] = {d: {ok: true, n: 2, untracked: 1, add: 3, del: 1, files: [{path: 'n', new: true, add: 2}]}};"
                "tlgC['/r/b'] = {d: {ok: true, n: 1, untracked: 1, files: [{path: 'x', new: true}]}};"
                "tlgC['/r/c'] = {d: {ok: true, n: 0, files: []}};"
                "R.h = tlgChipInner(tlgTarget()); tlgC['/r/a'].d = {ok: true, n: 0, files: []}; R.h0 = tlgChipInner(tlgTarget());")
        self.assertIn('<span class=tlgnb title="Repositories with uncommitted changes: 1">1 repos</span></button>', r["h"])   # on the chip, noun + title
        self.assertIn(" · Repositories with uncommitted changes: 1\"", r["h"])
        self.assertNotIn("tlgnb", r["h0"])
        self.assertNotIn("Repositories with uncommitted", r["h0"])

    def test_list_foot_views_all_changes_of_followed_repo(self):
        r = run("SESS = [{sid: 's1aaaaaaaa', cwd: '/r/a', project: 'a', ageSec: 5, repos: ['/r/<x>']}];"
                "tlgC['/r/<x>'] = {d: {ok: true, n: 5, base: 'abc'}}; tlgSel = 'r:/r/<x>';"
                "tlgRepoCfg(tlgTarget()); R.foot = PPC.tlgr.foot.html; PPC.tlgr.foot.act();")
        self.assertEqual(r["foot"], "View all changes <span class=ppfootn>&lt;x></span>")
        self.assertEqual(r["opened"], [["/r/<x>", "", "b:abc", "", "s1aaaaaaaa"]])
        src = js_all()
        for gone in ("tlgdt", "tlgDetBtn", "tlgdp", "TLGD", "'Details|repos'"):
            self.assertNotIn(gone, src)   # no «Details» toolbar button and no second popover: the list is the combobox

    def test_foot_is_opt_in_in_ppopen(self):
        body = js_fn("ppOpen")
        self.assertIn("(cfg.foot ? '<button type=button class=ppfoot data-ppfoot>' + cfg.foot.html + '</button>' : '')", body)
        import glob, os
        from tests._load import ROOT
        users = [os.path.basename(f) for f in sorted(glob.glob(os.path.join(ROOT, "web", "js", "*.js")))
                 if "foot: {" in open(f, encoding="utf-8").read()]
        self.assertEqual(users, ["77-timeline-git.js"])   # other pickers (Pipelines, Structure, History, Branches) unchanged

    def test_chip_click_opens_combo_under_chip(self):
        r = run("const b = {attrs: {'data-ppo': 1}, hasAttribute(k){ return k in this.attrs; }};"
                "ppOpen = (c, at) => { R.open = [c.k, at === b]; };"
                "SESS[0].repos = ['/r/w']; R.h = tlgChipInner(tlgTarget()); tlgChipClick(b); b.attrs = {}; tlgChipClick(b);"
                "PPS = {cfg: PPC.tlgr}; R.ex = tlgChipInner(tlgTarget()); PPS = {cfg: PPC.tlgs}; R.ex2 = tlgChipInner(tlgTarget());")
        self.assertEqual(r["open"], ["tlgr", True])   # ⚠never the session combo 'tlgs'
        self.assertIn('id=tlgcp data-ppo aria-haspopup=listbox aria-controls=ppop aria-expanded="false"', r["h"])
        self.assertIn('id=tlgcp data-ppo aria-haspopup=listbox aria-controls=ppop aria-expanded="true"', r["ex"])
        self.assertIn('id=tlgcp data-ppo aria-haspopup=listbox aria-controls=ppop aria-expanded="false"', r["ex2"])
        self.assertEqual(r["opened"], [["/r/a", "", "work", "", "s1aaaaaaaa"]])   # one repo, no list: the diff window

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
