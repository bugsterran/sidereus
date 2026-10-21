"""«Pipelines» «Working now» master-detail list (48j plNowList/plNowRun/plNowWrap/plNowPick reusing 74b tlSessNmB, R1-R5)
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
const TV = o => o.msg.replace(/\{(\w+)\}/g, (m, k) => o.vars[k]);
let tlAgDesc = true;
const CSS = { escape: s => String(s).replace(/(["\\\\/ ])/g, '\\\\$1') };
let SESS = [], PLNEW = null, PLDRAFT = null, PLSTD = false, GO = [], MV = [], PAINT = 0, FIT = 0, LS = {};
function aiLogo(p){ return '<i class="ailg ailg-' + esc(p || 'cc') + '"></i>'; }
function lsGet(k, d){ return k in LS ? LS[k] : d; }
function lsSet(k, v){ LS[k] = String(v); }
function lsDel(k){ delete LS[k]; }
function plPaint(){ PAINT++; }
function repoHue(){ return 1; } function tlStateDot(it){ return '<D ' + it.state + (it.blocked ? ' blk' : '') + '>'; }
let PLAG = true; function plAgSet(on){ PLAG = !!on; }
function plFit(){ FIT++; }
function plgShow(t){ return t === 'Design' ? 'D-shown' : t; }
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


NOW = ("\n".join([_const("PL_DESC_RE", "48b-pipeline-run.js"), _const("STR_SPLIT_KEYS", "81i-structure-split.js")]
                + [js_fn(n) for n in ("sessPlChip", "plStrip", "plTk", "plDescStage", "plSubsOf", "plLabType", "plLabParts", "plLabDesc", "plLabTip",
                                      "strSplitGet", "strSplitCols", "strSplitDecl", "strSplitStyle", "strSplitGrip",
                                      "tlSessNmB", "tlAgNmB", "tlAgNm", "tlAgLab", "plNowAgents", "plNowPickApply",
                                      "plNowSt", "plNowRun", "plNowLive", "plNowFolded", "plNowList", "plNowWrap", "plNowPick", "plNowGoProj")])
       + "\n" + _const("PLNOW_ST", "48j-pipeline-now.js") + "\n" + _const("PLNOW_AGMAX", "48j-pipeline-now.js") + "\n")
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
        self.assertIn("Working · Implement", h)
        self.assertIn("No pipeline · docs", h)
        self.assertIn("Undeclared", h)
        self.assertIn("Working now", h)
        self.assertIn("<small class=plnln>3</small>", h)                       # count badge
        self.assertNotIn("+", re.sub(r"<[^>]+>", "", h).replace(" · ", ""))  # no «+N»: the list scrolls
        self.assertNotIn("data-pntl", h)                                      # per-row Timeline link removed (owner decision)
        self.assertNotIn("data-pnst", h)                                      # no per-agent rows (canvas shows them)

    def test_r1_row_is_timeline_name_cell_plus_run_summary(self):
        h = run(NOW + "console.log(JSON.stringify(plNowList(" + LIVE + ")));")
        items = re.findall(r'<button type=button class="plnli tlnm[^"]*"[^>]*>(.*?)</button>', h)
        self.assertEqual(items[0], '<b><i class="ailg ailg-cx"></i><i class="tlp c1" title="/a">alpha</i><D tool></b>'
                         '<span class="plnlrun plnlrun-work" title="Pipeline run: chg · Implement"><i class="plnld plnld-work plnlpulse"></i>Working · Implement</span>')
        self.assertNotIn("<u", "".join(items))                                # bare: no time/token chips
        tl = js_fn("tlSessRow")
        self.assertIn("tlSessNmB(g, it, act, nComp) + tlPlStrip(pl)", tl)    # Timeline keeps its chips and stepper

    def test_r1_run_summary_states(self):
        r = run(NOW + "console.log(JSON.stringify([plNowRun({plrun: [{name: 'chg', cur: 'Verify'}]}, 'need'), plNowRun({plrun: [{name: 'chg'}]}, 'idle'),"
                " plNowRun({plrun: [{name: 'chg', end: 5}]}, 'work'), plNowRun({}, 'work')]));")
        self.assertIn('plnlrun-need', r[0]); self.assertIn('plnld-need"></i>Needs you · Verify', r[0])   # same label as the rail dot
        self.assertNotIn("plnlpulse", r[0])
        self.assertIn('plnld-idle"></i>Idle · chg', r[1])
        self.assertIn('plnlrun-done', r[2]); self.assertIn("✓ chg done", r[2])
        self.assertEqual(r[3], "")

    def test_r1_run_summary_uses_stage_display_name(self):
        out = run(NOW + """console.log(JSON.stringify(plNowRun({ plrun: [{ name: 'p', cur: 'Design' }] }, 'work')));""")
        self.assertIn('Working · D-shown', out); self.assertNotIn('· Design', out)

    def test_r1_selected_row_marked(self):
        h = run(NOW + "PLS.nowSid = 's2'; console.log(JSON.stringify(plNowList(" + LIVE + ")));")
        self.assertIn('<div class="plnlr on"><button type=button class="plnli tlnm on" data-pncwd="/b" data-pnplat="cc" title="beta" aria-current=true>', h)
        self.assertEqual(h.count("aria-current"), 1)

    def test_r5_collapsed_rail_dots(self):
        h = run(NOW + "LS['sidereus.plnowc'] = '1'; console.log(JSON.stringify(plNowList(" + LIVE + ")));")
        self.assertTrue(h.startswith('<aside class="plnl plnlc">'))
        self.assertIn('aria-label="Expand list"', h)
        self.assertEqual(re.findall(r'class="plnlrd plnld-(\w+)" data-pncwd="([^"]+)"', h), [("work", "/a"), ("idle", "/b"), ("work", "/c")])
        self.assertIn('title="beta" aria-label="beta · Idle"', h)
        self.assertNotIn("plnli", h)
        css = open(os.path.join(ROOT, "web", "css", "43-pipeline.css"), encoding="utf-8").read()
        self.assertIn("html[data-ui] .plw aside.plnl.plnlc{padding:4px 0;border:0;background:none;overflow:hidden", css)

    def test_r5_rail_dot_click_expands_and_picks(self):
        s = _src("48j-pipeline-now.js")
        self.assertIn("if(t.classList.contains('plnlrd')) lsDel('sidereus.plnowc');", s)
        self.assertLess(s.index("lsDel('sidereus.plnowc');   // rail dot"), s.index("plNowPick(t.dataset.pncwd, t.dataset.pnplat);\n});"))

    def test_r1_empty_note(self):
        h = run(NOW + "console.log(JSON.stringify(plNowList([])));")
        self.assertIn("No sessions working now", h)
        self.assertIn("class=plnle", h)

    def test_r1_targ_never_in_text_description_label_only(self):
        h = run(NOW + "PLS.nowSid = 's1'; console.log(JSON.stringify(plNowList([{state: 'tool', sid: 's1', cwd: '/a', project: 'p',"
                " targ: 'SECRET-TASK', tool: 'Bash', prompt: 'SECRET-PROMPT',"
                " sub: [{lab: 'impl: [pl:chg/Implement] build the DESCX thing'}]}])));")
        self.assertNotIn("SECRET", h)
        self.assertIn("build the DESCX thing", h)                             # rule 1: the one-line Agent description label is allowed
        self.assertNotIn("[pl:", re.sub(r'title="[^"]*"', "", h))             # the tag itself is stripped from the label

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

    def test_f3_pick_closes_arch_map(self):
        r = run(NOW + "SESS = [{state: 'tool', sid: 's1', cwd: '/a'}]; plNowPick('/a', ''); console.log(JSON.stringify(PLAG));")
        self.assertFalse(r)

    def test_f7_picker_clears_session_pick(self):
        pk = js_fn("plPickProj")
        self.assertIn("PLS.nowSid = '';", pk)

    def test_f4_list_scroll_kept_across_rebuild(self):
        pp = js_fn("paintPipe")
        i = pp.index("box.innerHTML = h;")
        self.assertIn("nl.scrollTop", pp[:i])
        self.assertIn("nl2.scrollTop = nst", pp[i:])

    def test_r4_fold_and_wrap(self):
        a, b = run(NOW + "const w = () => plNowWrap('BODY'); const a = w(); LS['sidereus.plnowc'] = '1'; LS['sidereus.plmd'] = '200';"
                   "console.log(JSON.stringify([a, w()]));")
        self.assertTrue(a.startswith('<div class="plmd">'))
        self.assertIn('data-pnfold aria-expanded="true"', a)
        self.assertIn('data-spk=plmd', a)
        self.assertIn("<div class=plmdr>BODY</div></div>", a)
        self.assertTrue(b.startswith('<div class="plmd plnc" style="grid-template-columns:min(200px,60%) 1fr"><aside class="plnl plnlc">'))
        self.assertIn('aria-expanded="false"', b)
        self.assertNotIn("data-pncwd", b)

    def test_r4_split_key_and_drag_guard(self):
        r = run(NOW + "LS['sidereus.plmd'] = '120'; const lo = strSplitGet('plmd'); LS['sidereus.plmd'] = '180';"
                "console.log(JSON.stringify([STR_SPLIT_KEYS.includes('plmd'), lo, strSplitGet('plmd')]));")
        self.assertEqual(r, [True, 0, 180])                                   # below the 150px floor = default
        pp = js_fn("paintPipe")
        self.assertLess(pp.index("classList.contains('dragging')) return"), pp.index("plLoadProjs()"))
        self.assertIn("plNowShown() ? plNowWrap(plMainBody()) : plMainBody()", pp)   # 48k Edit: palette takes the left column

    def test_r4_css_no_shift(self):
        with open(os.path.join(ROOT, "web", "css", "43-pipeline.css"), encoding="utf-8") as f:
            css = f.read()
        self.assertIn(".plmdr{min-width:0}", css)
        self.assertIn("grid-template-columns:28px minmax(0,1fr)!important", css)
        self.assertNotIn(".plnow", css)

    def test_r3_backspace_in_list_keeps_stage(self):
        s = _src("48d-pipeline-cv-input.js")
        i = s.index("document.addEventListener('keydown', e => {\n  if(mainView !== 'pipe' || (e.key !== 'Delete'")
        src = s[i:s.index("\n});", i) + 4]
        r = run("let H = null, DEL = 0, mainView = 'pipe'; const document = { addEventListener: (k, f) => { H = f; } };"
                "const E = {sel: {k: 'n', id: 'n2'}}; function plCurEnt(){ return E; } function plRO(){ return false; } function plDelSel(){ DEL++; }"
                + src + "const ev = (inList) => ({ key: 'Backspace', preventDefault(){}, target: { tagName: inList ? 'BUTTON' : 'DIV',"
                " closest: q => (inList && q === '.plnl') ? {} : null } });"
                "H(ev(true)); const a = DEL; H(ev(false)); console.log(JSON.stringify([a, DEL]));")
        self.assertEqual(r, [0, 1])                                           # list row focus: no delete; canvas: delete

    def test_listener_wired(self):
        s = _src("48j-pipeline-now.js")
        for a in ("[data-pncwd]", "[data-pnfold]"):
            self.assertIn(".plw .plnl " + a, s)
        self.assertNotIn("data-pntl", s)
        self.assertNotIn("plNowGo(", s)
        for gone in ("plNowStage",):
            self.assertNotIn(gone, s)

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




    def test_r9_subagent_tree_reuses_timeline_cell(self):
        src = ("[{state: 'tool', sid: 's1', cwd: '/a', plat: 'cc', project: 'a', sub: ["
               "{lab: 'impl: [pl:chg/Implement] build it', aid: 'a1', idle: 5}, {lab: 'Explore: look <x &', aid: 'a2', idle: 600},"
               " {lab: 'rev: review', aid: 'a3', plat: 'cx'}, {lab: 'b: 1', aid: 'b1'}, {lab: 'b: 2', aid: 'b2'}, {lab: 'b: 3', aid: 'b3'}]}]")
        h = run(NOW + "console.log(JSON.stringify(plNowList(" + src + ")));")
        rows = re.findall(r'<button type=button class="plnagr tlnm( quiet)?"([^>]*)><b>(.*?)</b></button>', h)
        self.assertEqual(len(rows), 6)
        self.assertNotIn("plnagm", h)
        many = run(NOW + "console.log(JSON.stringify(plNowAgents({cwd: '/a', sub: Array.from({length: 12}, (_, i) => ({lab: 'b: ' + i}))})));")
        self.assertEqual(many.count('class="plnagr'), 6)                      # capped at 6
        self.assertIn("<div class=plnagm>+6 more</div>", many)
        self.assertEqual(rows[-1][0], " quiet")                               # quiet (idle 600s) sorts last, dimmed
        first = rows[0][2]
        self.assertTrue(first.startswith("<i class=tlbr2>├─</i><i class=\"ailg ailg-cc\"></i><em class=tlagd"))   # timeline connector + logo
        self.assertIn('<i class="tlds on"></i>', first)                       # running dot
        self.assertIn('data-pnname="chg" data-pnst="Implement"', rows[0][1])
        self.assertIn('ailg-cx', rows[1][2])                                  # a Codex child keeps its own logo
        self.assertNotIn("data-pnname", rows[1][1])                           # untagged: session only
        self.assertIn("look &lt;x &amp;", h)                                  # escaped
        self.assertIn('<i class="tlds"></i>', rows[-1][2])                    # quiet: no running dot
        c = run(NOW + "LS['sidereus.plnowc'] = '1'; console.log(JSON.stringify(plNowList(" + src + ")));")
        self.assertNotIn("plnagr", c)                                         # hidden in the collapsed rail

    def test_r9_agent_click_selects_stage_no_view_move(self):
        s = _src("48j-pipeline-now.js")
        self.assertIn("if(t.dataset.pnname){ PLS.sel = t.dataset.pnname; PLS.nowPick = { name: t.dataset.pnname, title: t.dataset.pnst }; plPaint(); }", s)
        r = run(NOW + "const E = {G: {nodes: [{id: 'n1', title: 'Design'}, {id: 'n2', title: 'Implement'}]}, sel: null, first: true, view: {x: 1, y: 2, z: 1}};"
                "let CUR = {name: 'chg'}; function plCur(){ return CUR; } function plEnt(){ return E; }"
                "PLS.proj = '/p'; PLS.nowPick = {name: 'chg', title: 'Implement'}; plNowPickApply(); const a = PLS.nowPick;"
                "PLS.data['/p'] = {ok: true}; plNowPickApply(); console.log(JSON.stringify([a, E.sel, E.first, E.view, FIT, PLS.nowPick]));")
        self.assertEqual(r[0], {"name": "chg", "title": "Implement"})       # project still loading: pick kept
        self.assertEqual(r[1:], [{"k": "n", "id": "n2"}, False, {"x": 1, "y": 2, "z": 1}, 0, None])
        for bad in ("plFit", "plCentre", "scrollIntoView", "E.view ="):
            self.assertNotIn(bad, js_fn("plNowPickApply"))
        self.assertIn("plNowPickApply(), plNowShown()", js_fn("paintPipe"))

if __name__ == "__main__":
    unittest.main()
