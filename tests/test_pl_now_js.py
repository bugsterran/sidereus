"""«Pipelines» «Working now» master-detail list (48j plNowList/plNowWrap/plNowPick/plNowPickApply/plNowGo, R1-R4)
and the empty-project start buttons (48e plTplPick). Pure functions under node with stubs; no live files."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import ROOT, js_fn
from tests._node import node_e

PRE = """
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const T = s => s;
const CSS = { escape: s => String(s).replace(/(["\\\\/ ])/g, '\\\\$1') };
let SESS = [], PLNEW = null, PLDRAFT = null, PLSTD = false, GO = [], MV = [], PAINT = 0, FIT = 0, LS = {};
function aiLogo(p){ return '<i class="ailg ailg-' + esc(p || 'cc') + '"></i>'; }
function lsGet(k, d){ return k in LS ? LS[k] : d; }
function lsSet(k, v){ LS[k] = String(v); }
function lsDel(k){ delete LS[k]; }
function plPaint(){ PAINT++; }
let PLAG = true; function plAgSet(on){ PLAG = !!on; }
function plFit(){ FIT++; }
function plCentre(){ FIT++; }
const PLS = { proj: '/old', sel: 'old', data: {}, std: 'x', wf: {}, diff: {}, del: {}, msg: 'm', runSel: {}, nowSid: '', nowPick: null };
"""


def _src(name):
    with open(os.path.join(ROOT, "web", "js", name), encoding="utf-8") as f:
        return f.read()


def _const(name, file):
    s = _src(file)
    i = s.index("const " + name)
    return s[i:s.index(";", i) + 1]


NOW = "\n".join([_const("PL_DESC_RE", "48b-pipeline-run.js"), _const("STR_SPLIT_KEYS", "81i-structure-split.js")]
                + [js_fn(n) for n in ("sessPlChip", "plStrip", "plTk", "plDescStage", "plSubsOf", "plLabType", "plLabParts", "plLabDesc", "plLabTip",
                                      "strSplitGet", "strSplitCols", "strSplitDecl", "strSplitStyle", "strSplitGrip",
                                      "plNowLive", "plNowFolded", "plNowStages", "plNowList", "plNowWrap", "plNowPick", "plNowStage",
                                      "plNowPickApply", "plNowGo", "plNowGoProj")]) + "\n"
LIVE = """[{state: 'tool', sid: 's1', cwd: '/a', plat: 'cx', project: 'alpha', plrun: [{name: 'chg', cur: 'Implement'}]},
{state: 'wait', sid: 's2', cwd: '/b', plat: 'cc', project: 'beta', plNone: {cat: 'docs'}},
{state: 'think', sid: 's3', cwd: '/c', project: 'gamma', plNone: {u: 1}},
{state: 'done', cwd: '/d', project: 'delta'}, {state: 'abort', cwd: '/e', project: 'eps'},
{state: 'gone', cwd: '/f', plat: 'cx', project: 'zeta'}, {state: 'tool', sid: 's9', cwd: '/a', plat: 'cx', project: 'alpha'}]"""


def run(body):
    r = subprocess.run(node_e(PRE + body), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PlNow(unittest.TestCase):
    def test_r1_list_dedupe_drop_logo_project_chip(self):
        h = run(NOW + "console.log(JSON.stringify(plNowList(" + LIVE + ")));")
        self.assertEqual(re.findall(r'class="plnli[^"]*" data-pncwd="([^"]+)"', h), ["/a", "/b", "/c"])   # done/abort/gone dropped, /a+cx once
        self.assertTrue(h.startswith("<aside class=plnl>"))
        self.assertIn("ailg-cx", h)
        self.assertIn(">alpha<", h)
        self.assertIn(" · Implement", h)
        self.assertIn("No pipeline · docs", h)
        self.assertIn("Undeclared", h)
        self.assertIn("Working now", h)
        self.assertIn("<small>3</small>", h)                                  # count
        self.assertNotIn("+", re.sub(r"<[^>]+>", "", h).replace(" · ", ""))  # no «+N»: the list scrolls
        self.assertEqual(h.count("data-pntl="), 3)                            # Timeline link per item (non-goal kept)

    def test_r1_empty_note(self):
        h = run(NOW + "console.log(JSON.stringify(plNowList([])));")
        self.assertIn("No sessions working now", h)
        self.assertIn("class=plnle", h)

    def test_r1_targ_and_description_never_in_text(self):
        h = run(NOW + "PLS.nowSid = 's1'; console.log(JSON.stringify(plNowList([{state: 'tool', sid: 's1', cwd: '/a', project: 'p',"
                " targ: 'SECRET-TASK', tool: 'Bash', prompt: 'SECRET-PROMPT',"
                " sub: [{lab: 'impl: [pl:chg/Implement] build the DESCX thing'}]}])));")
        self.assertNotIn("SECRET", h)
        txt = re.sub(r'title="[^"]*"', "", h)
        self.assertNotIn("DESCX", txt)                                        # description only in title=
        self.assertIn('title="impl · build the DESCX thing"', h)

    def test_r1_stage_rows_only_under_selected(self):
        src = ("[{state: 'tool', sid: 's1', cwd: '/a', project: 'a', sub: [{lab: 'impl: [pl:chg/Implement] x'}, {lab: 'Explore: plain'}],"
               " plm: {name: 'chg', title: 'Verify'}}, {state: 'tool', sid: 's2', cwd: '/b', project: 'b', sub: [{lab: 'rev: [pl:chg/Review] y'}]}]")
        h = run(NOW + "PLS.nowSid = 's1'; console.log(JSON.stringify(plNowList(" + src + ")));")
        self.assertEqual(re.findall(r'data-pnst="([^"]+)"', h), ["Implement", "Verify"])
        self.assertIn('data-pnname="chg"', h)
        self.assertIn("<small>impl</small>", h)
        self.assertIn('class="plnli on" data-pncwd="/a"', h)

    def test_r2_pick_open_run_project_beats_cwd(self):
        r = run(NOW + "SESS = [{state: 'tool', sid: 's1', cwd: '/a', plat: 'cx', plrun: [{name: 'old', end: 5, proj: '/z'}, {name: 'chg', proj: '/p'}]}];"
                "plNowPick('/a', 'cx'); console.log(JSON.stringify([PLS.proj, PLS.sel, PLS.nowSid, PLS.runSel, PLS.std, PLS.wf, PLS.msg, LS['sidereus.plproj'], PAINT]));")
        self.assertEqual(r, ["/p", "chg", "s1", None, "", None, "", "/p", 1])

    def test_r2_pick_tag_then_no_run(self):
        r = run(NOW + "SESS = [{state: 'tool', sid: 's1', cwd: '/a', plm: {name: 'tg', title: 'Verify'}},"
                " {state: 'tool', sid: 's2', cwd: '/b', plrun: [{name: 'done', end: 9}]}];"
                "plNowPick('/a', ''); const a = [PLS.proj, PLS.sel]; PLS.sel = 'keep'; plNowPick('/b', '');"
                "console.log(JSON.stringify([a, PLS.proj, PLS.sel, PLS.nowSid]));")
        self.assertEqual(r, [["/a", "tg"], "/b", "keep", "s2"])              # no open run: project only

    def test_r3_stage_click_selects_node_by_title_no_view_move(self):
        r = run(NOW + "const E = {G: {nodes: [{id: 'n1', title: 'Design'}, {id: 'n2', title: 'Implement'}]}, sel: null, first: true, view: {x: 1, y: 2, z: 1}};"
                "let CUR = {name: 'other'}; function plCur(){ return CUR; } function plEnt(p){ return E; }"
                "SESS = [{sid: 's1', cwd: '/p'}]; PLS.nowSid = 's1'; PLS.proj = '/x'; plNowStage('chg', 'Implement'); const pend = [PLS.sel, JSON.stringify(PLS.nowPick)];"
                "plNowPickApply(); const loading = PLS.nowPick !== null; PLS.data['/p'] = {ok: true}; CUR = {name: 'chg', ok: true};"
                "plNowPickApply(); console.log(JSON.stringify([pend, loading, E.sel, E.first, E.view, FIT, PLS.nowPick]));")
        pend, loading, sel, first, view, fit, after = r
        self.assertEqual(pend[0], "chg")
        self.assertTrue(loading)                                              # data not loaded yet: pick kept
        self.assertEqual(sel, {"k": "n", "id": "n2"})
        self.assertFalse(first)
        self.assertEqual(view, {"x": 1, "y": 2, "z": 1})                      # view untouched
        self.assertEqual(fit, 0)
        self.assertIsNone(after)

    def test_f3_pick_and_stage_close_arch_map(self):
        r = run(NOW + "SESS = [{state: 'tool', sid: 's1', cwd: '/a'}]; plNowPick('/a', ''); const a = PLAG; PLAG = true;"
                "plNowStage('chg', 'Verify'); console.log(JSON.stringify([a, PLAG]));")
        self.assertEqual(r, [False, False])

    def test_f7_stage_uses_session_project_and_picker_clears(self):
        r = run(NOW + "SESS = [{state: 'tool', sid: 's1', cwd: '/a', plrun: [{name: 'chg', proj: '/home'}]}];"
                "PLS.nowSid = 's1'; PLS.proj = '/other'; plNowStage('chg', 'Verify'); const a = [PLS.proj, PLS.sel];"
                "PLS.nowSid = 'gone'; PLS.proj = '/q'; PLS.sel = 'keep'; plNowStage('zzz', 'T');"
                "console.log(JSON.stringify([a, PLS.proj, PLS.sel]));")
        self.assertEqual(r, [["/home", "chg"], "/q", "keep"])                # stale session: nothing written
        pk = js_fn("plPickProj")
        self.assertIn("PLS.nowSid = ''; PLS.nowPick = null;", pk)

    def test_f4_list_scroll_kept_across_rebuild(self):
        pp = js_fn("paintPipe")
        i = pp.index("box.innerHTML = h;")
        self.assertIn("nl.scrollTop", pp[:i])
        self.assertIn("nl2.scrollTop = nst", pp[i:])

    def test_r3_apply_source_never_fits(self):
        body = js_fn("plNowPickApply")
        for bad in ("plFit", "plCentre", "scrollIntoView", "E.view ="):
            self.assertNotIn(bad, body)

    def test_r4_fold_and_wrap(self):
        a, b = run(NOW + "const w = () => plNowWrap('BODY'); const a = w(); LS['sidereus.plnowc'] = '1'; LS['sidereus.plmd'] = '200';"
                   "console.log(JSON.stringify([a, w()]));")
        self.assertTrue(a.startswith('<div class="plmd">'))
        self.assertIn('data-pnfold aria-expanded="true"', a)
        self.assertIn('data-spk=plmd', a)
        self.assertIn("<div class=plmdr>BODY</div></div>", a)
        self.assertTrue(b.startswith('<div class="plmd plnc" style="grid-template-columns:min(200px,60%) 1fr">'))
        self.assertIn('aria-expanded="false"', b)
        self.assertNotIn("data-pncwd", b)

    def test_r4_split_key_and_drag_guard(self):
        r = run(NOW + "LS['sidereus.plmd'] = '120'; const lo = strSplitGet('plmd'); LS['sidereus.plmd'] = '180';"
                "console.log(JSON.stringify([STR_SPLIT_KEYS.includes('plmd'), lo, strSplitGet('plmd')]));")
        self.assertEqual(r, [True, 0, 180])                                   # below the 150px floor = default
        pp = js_fn("paintPipe")
        self.assertLess(pp.index("classList.contains('dragging')) return"), pp.index("plLoadProjs()"))
        self.assertIn("plNowShown() ? plNowWrap(plMainBody()) : plMainBody()", pp)   # 48k Edit: palette takes the left column
        self.assertLess(pp.index("plNowPickApply()"), pp.index("plNowWrap("))

    def test_r4_css_no_shift(self):
        with open(os.path.join(ROOT, "web", "css", "43-pipeline.css"), encoding="utf-8") as f:
            css = f.read()
        self.assertIn(".plmdr{min-width:0}", css)
        self.assertIn("grid-template-columns:28px minmax(0,1fr)!important", css)
        self.assertNotIn(".plnow", css)

    def test_click_goes_to_timeline_row(self):
        a, b = run(NOW + "function mvGo(v, s){ GO.push([v, s]); }"
                   "plNowGo('/x \"y', 'cx'); console.log(JSON.stringify([GO, MV]));")
        self.assertEqual(a, [["time", '.tlr.tlrs[data-tlc="\\/x\\ \\"y"][data-tlp="cx"]']])
        self.assertEqual(b, [])

    def test_claude_maps_to_empty_tlp(self):
        r = run(NOW + "function mvGo(v, s){ GO.push(s); } plNowGo('/a', 'cc'); plNowGo('/a', ''); console.log(JSON.stringify(GO));")
        self.assertEqual(r, ['.tlr.tlrs[data-tlc="\\/a"][data-tlp=""]'] * 2)    # Claude timeline rows carry data-tlp=""

    def test_click_fallback_without_mvgo(self):
        r = run(NOW + "function setMainView(v){ MV.push(v); } plNowGo('/x', ''); console.log(JSON.stringify(MV));")
        self.assertEqual(r, ["time"])

    def test_r3_backspace_in_list_keeps_stage(self):
        s = _src("48d-pipeline-cv-input.js")
        i = s.index("document.addEventListener('keydown', e => {\n  if(mainView !== 'pipe' || (e.key !== 'Delete'")
        src = s[i:s.index("\n});", i) + 4]
        r = run("let H = null, DEL = 0, mainView = 'pipe'; const document = { addEventListener: (k, f) => { H = f; } };"
                "const E = {sel: {k: 'n', id: 'n2'}}; function plCurEnt(){ return E; } function plRO(){ return false; } function plDelSel(){ DEL++; }"
                + src + "const ev = (inList) => ({ key: 'Backspace', preventDefault(){}, target: { tagName: inList ? 'BUTTON' : 'DIV',"
                " closest: q => (inList && q === '.plnl') ? {} : null } });"
                "H(ev(true)); const a = DEL; H(ev(false)); console.log(JSON.stringify([a, DEL]));")
        self.assertEqual(r, [0, 1])                                           # .plnls focus: no delete; canvas: delete

    def test_listener_wired(self):
        s = _src("48j-pipeline-now.js")
        for a in ("[data-pntl]", "[data-pncwd]", "[data-pnst]", "[data-pnfold]"):
            self.assertIn(".plw .plnl " + a, s)

    def test_r3_start_buttons_first(self):
        h = run(_const("PL_TPLS", "48e-pipeline-new.js") + "\n"
                + "\n".join(js_fn(n) for n in ("plNewDis", "plStartBtns", "plTplPick"))
                + "\nconsole.log(JSON.stringify(plTplPick()));")
        btns = re.findall(r"<button[^>]*>", h)
        self.assertIn("data-plstd", btns[0])
        self.assertIn("data-pldnew", btns[1])
        for b in btns[:2]:
            self.assertIn('plsv', b)
        self.assertIn("data-pltpl", btns[2])
        self.assertLess(h.index("Or start from:"), h.index("data-pltpl"))
        self.assertNotIn("Standard templates", h)                             # duplicate dropped
        self.assertEqual(h.count("data-plstd"), 1)


if __name__ == "__main__":
    unittest.main()
