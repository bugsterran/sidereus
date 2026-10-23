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
let SESS = [], PLNEW = null, PLDRAFT = null, PLSTD = false, PLTPLO = false, GO = [], MV = [], PAINT = 0, FIT = 0, LS = {};
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
                                      "tlSessNmB", "tlAgNmB", "tlAgNm", "tlAgLab", "subWorkId", "plNowAgents", "plNowPickApply",
                                      "plPrLive", "plNowSt", "plNowRun", "plNowRunTxt", "plNowLive", "plNowFolded", "plNowList", "plNowWrap", "plNowPick", "plNowGoProj", "plProjGo", "plPickProj")])
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
        self.assertIn('<div class="plnlr on"><button type=button class="plnli tlnm on" data-pncwd="/b" data-pnplat="cc" title="beta\nIdle" aria-label="beta · Idle · No pipeline · docs" aria-current=true>', h)
        self.assertEqual(h.count("aria-current"), 1)

    def test_r5_collapsed_rail_dots(self):
        h = run(NOW + "LS['sidereus.plnowc'] = '1'; console.log(JSON.stringify(plNowList(" + LIVE + ")));")
        self.assertTrue(h.startswith('<aside class="plnl plnlc">'))
        self.assertIn('aria-label="Expand list"', h)
        self.assertEqual(re.findall(r'class="plnlrd plnld-(\w+)( plnlrp)?" data-pncwd="([^"]+)"', h), [("work", " plnlrp", "/a"), ("idle", "", "/b"), ("work", " plnlrp", "/c")])
        self.assertIn('data-pnlp="beta" data-pnls="Idle · No pipeline · docs" aria-label="beta · Idle"', h)
        self.assertNotIn("title=", h.split("plnlrd", 1)[1])                    # floating label replaces the native title
        self.assertNotIn("plnli", h)
        css = open(os.path.join(ROOT, "web", "css", "43-pipeline.css"), encoding="utf-8").read()
        self.assertIn("html[data-ui] .plw aside.plnl.plnlc{padding:4px 0;border:0;background:none;overflow:hidden", css)

    def test_r5_collapsed_rail_marks_selected(self):
        h = run(NOW + "LS['sidereus.plnowc'] = '1'; PLS.nowSid = 's2'; console.log(JSON.stringify(plNowList(" + LIVE + ")));")
        self.assertEqual(re.findall(r'class="plnlrd plnld-\w+ on" data-pncwd="([^"]+)"', h), ["/b"])
        self.assertEqual(h.count(" on\""), 1)
        self.assertEqual(h.count("aria-current=true"), 1)
        self.assertIn('aria-label="beta · Idle" aria-current=true>', h)
        css = open(os.path.join(ROOT, "web", "css", "43-pipeline.css"), encoding="utf-8").read()
        self.assertIn(".plnlrd.on{box-shadow:inset 0 0 0 2px", css)

    def test_r5_rail_label_and_pulse(self):
        r = run(NOW + js_fn("plNowTip") + "\nconsole.log(JSON.stringify(plNowTip('<x>', 'Working · Implement')));")
        self.assertEqual(r, '<b>&lt;x></b><span>Working · Implement</span>')
        h = run(NOW + "LS['sidereus.plnowc'] = '1'; console.log(JSON.stringify(plNowList(" + LIVE + ")));")
        self.assertIn('data-pnlp="alpha" data-pnls="Working · Implement"', h)
        s = _src("48j-pipeline-now.js")
        for frag in ("document.addEventListener('mouseover', plNowTipOn);", "document.addEventListener('focusin', plNowTipOn);",
                     "document.addEventListener('focusout', plNowTipHide);", "document.addEventListener('scroll', plNowTipHide, true);"):
            self.assertIn(frag, s)
        self.assertNotIn("T(b.dataset", s)
        css = open(os.path.join(ROOT, "web", "css", "43-pipeline.css"), encoding="utf-8").read()
        self.assertIn("#plnltip{position:fixed;", css)
        self.assertIn(".plnlrd.plnlrp::after{", css)
        self.assertIn("animation:plr ", css.split(".plnlrd.plnlrp::after{", 1)[1].split("}", 1)[0])
        self.assertIn("@media (prefers-reduced-motion:reduce){.plnlrd.plnlrp::after{animation:none;", css)
        self.assertIn(".plnlrd.plnld-need::before{background:var(--nx-warn", css)

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

    def test_running_row_pick_marks_live_session(self):
        # «Running N» row click (48b plOvPick) marks the session running it in «Working now»; no live match → ''.
        ov = js_fn("plOvSid") + "\n" + js_fn("plOvPick") + "\nlet PLVIEW = 'pipe';\n"
        r = run(NOW + ov + "SESS = " + LIVE + ";"
                "plOvPick('/a', 'chg', ''); const a = PLS.nowSid; const h = plNowList();"
                "plOvPick('/b', 'chg', ''); const b = PLS.nowSid;"
                "plOvPick('/c', 'x', 's3'); const c = PLS.nowSid;"
                "plOvPick('/z', 'x', 'dead'); const d = PLS.nowSid;"
                "SESS = [{state: 'tool', sid: 'p1', cwd: '/w', plm: {name: 'rel'}}]; plOvPick('/w', 'rel'); const e = PLS.nowSid;"
                "console.log(JSON.stringify([a, b, c, d, e, h]));")
        self.assertEqual(r[:5], ["s1", "", "s3", "", "p1"])
        self.assertIn('class="plnli tlnm on" data-pncwd="/a"', r[5])
        self.assertIn("aria-current=true", r[5])
        src = _src("48b-pipeline-run.js")
        self.assertIn("plOvPick(r.dataset.plovwp, r.dataset.plovwn, r.dataset.plovw)", src)
        pk = js_fn("plOvPick")
        self.assertLess(pk.index("plProjGo(proj)"), pk.index("PLS.nowSid ="))   # set after plProjGo clears it
        self.assertNotRegex(pk, r"scrollInto|scrollTo|plFit\(|plCentre\(")

    def test_running_row_pick_borrowed_goes_to_owning_repo(self):
        # Session folder /app owns only bugfix; its open arch-map run lives in /sid: the pick must not fall back to bugfix.
        ov = js_fn("plOvSid") + "\n" + js_fn("plOvPick") + "\nlet PLVIEW = 'pipe';\n"
        r = run(NOW + ov + "PLS.projs = {ok: true}; PLS.data['/app'] = {ok: true, pipelines: [{name: 'bugfix'}], borrowed: []};"
                "SESS = [{state: 'tool', sid: 'd1', cwd: '/app', plrun: [{name: 'arch-map', proj: '/sid'}]}];"
                "plOvPick('/app', 'arch-map', 'd1'); const a = [PLS.proj, PLS.sel, PLS.nowSid];"
                "SESS = []; PLS.proj = '/old'; plOvPick('/app', 'arch-map', ''); const b = [PLS.proj, PLS.data['/app']];"
                "console.log(JSON.stringify([a, b]));")
        self.assertEqual(r[0], ["/sid", "arch-map", "d1"])
        self.assertEqual(r[1], ["/app", None])                                 # no owner known: stale list dropped, paintPipe reloads

    def test_f7_picker_clears_session_pick(self):
        pk = js_fn("plPickProj")
        self.assertIn("plProjGo(p)", pk)

    def test_switch_closes_draft_and_template_forms(self):
        # A form built for one project must not stay open on another; same project keeps it.
        st = "const S = () => [PLDRAFT, PLSTD, PLNEW, PLS.proj]; const set = () => { PLDRAFT = {desc: 'x'}; PLSTD = true; PLNEW = {}; };"
        r = run(NOW + st + "SESS = [{state: 'tool', sid: 's1', cwd: '/c'}];"
                "set(); plPickProj('/b'); const a = S(); set(); plNowPick('/c', ''); const b = S();"
                "set(); plPickProj('/c'); const c = S(); set(); plNowPick('/c', ''); console.log(JSON.stringify([a, b, c, S(), PLS.nowSid]));")
        self.assertEqual(r[0], [None, False, None, "/b"])
        self.assertEqual(r[1], [None, False, None, "/c"])
        self.assertEqual(r[2], [{"desc": "x"}, True, {}, "/c"])
        self.assertEqual(r[3], [{"desc": "x"}, True, {}, "/c"])
        self.assertEqual(r[4], "s1")

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

    def test_wait_with_live_work_is_working(self):
        # Turn ended ('wait') but tagged work still runs: row, rail dot and canvas share one predicate.
        xs = """[{state: 'wait', plrun: [{name: 'c', stages: {A: {o: 'run'}}}]}, {state: 'wait', sub: [{lab: 'a', idle: 5}]},
        {state: 'wait', bgs: [{lab: '[pl:c/A] gates', min: 2}]}, {state: 'wait', blocked: true, bgs: [{lab: 'x'}]},
        {state: 'wait', sub: [{lab: 'a', idle: 999}], plrun: [{name: 'c', end: 9, stages: {A: {o: 'run'}}}, {name: 'd', stages: {A: {o: 'done'}}}]},
        {state: 'wait'}, {state: 'tool'}]"""
        r = run(NOW + "console.log(JSON.stringify(" + xs + ".map(plNowSt)));")
        self.assertEqual(r, ["work", "work", "work", "need", "idle", "idle", "work"])
        h = run(NOW + "SESS = [{state: 'wait', sid: 's2', cwd: '/b', project: 'beta', bgs: [{lab: 'g', min: 1}]}];"
                + "lsSet('sidereus.plnowc', '1'); console.log(JSON.stringify(plNowList()));")
        self.assertIn("plnld-work plnlrp", h)                                  # collapsed rail dot pulses
        h = run(NOW + "const S = [{state: 'wait', sid: 's2', cwd: '/b', project: 'beta', bgs: [{lab: 'g', min: 1}]}, {state: 'wait', sid: 's3', cwd: '/c', project: 'g'}];"
                + "const o = plNowList(S); console.log(JSON.stringify([o, S[0].state]));")
        self.assertIn("<D run>", h[0])                                         # expanded row dot: working
        self.assertIn("<D wait>", h[0])                                        # idle row unchanged
        self.assertEqual(h[1], "wait")                                         # session object not mutated

    def test_r3_start_buttons_first(self):
        h = run(_const("PL_TPLS", "48e-pipeline-new.js") + "\n"
                + "\n".join(js_fn(n) for n in ("plNewDis", "plStartBtns", "plTplPick"))
                + "\nPLS.proj = '/p'; function plSessions(){ return [{login: true}]; }"
                + "\nconsole.log(JSON.stringify(plTplPick()));")
        btns = re.findall(r"<button[^>]*>", h)
        self.assertIn("data-pldnew", btns[0])
        self.assertIn("data-plstd", btns[1])
        self.assertIn('plsv', btns[0])
        self.assertIn("data-pltplo", btns[2])                                 # quick templates fold behind a toggle
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

    def test_r9_type_chip_hidden_beside_description_only(self):
        with open(os.path.join(ROOT, "web", "css", "43-pipeline.css"), encoding="utf-8") as f:
            pl = f.read()
        with open(os.path.join(ROOT, "web", "css", "20-timeline.css"), encoding="utf-8") as f:
            tl = f.read()
        self.assertIn(".plw .plnl .plnagr .tlagd~.tlagt{display:none}", pl)
        self.assertRegex(tl, r"\n\.tlagt\{[^}]*flex:0 0 auto")                 # Timeline chip untouched
        src = "{cwd: '/a', sub: [{lab: 'general-purpose: build the thing', aid: 'a1'}]}"
        on = run(NOW + "console.log(JSON.stringify(plNowAgents(" + src + ")));")
        self.assertIn("<em class=tlagd", on)
        self.assertRegex(on, r'title="[^"]*general-purpose')                   # type kept in the row tooltip
        off = run(NOW + "tlAgDesc = false; console.log(JSON.stringify(plNowAgents(" + src + ")));")
        self.assertNotIn("tlagt", off)                                         # descriptions off: type is plain text, not hidden
        self.assertIn("general-purpose", re.sub(r'title="[^"]*"', "", off))

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
    def test_a11y_state_in_words_per_state(self):
        ss = ("[{state: 'tool', sid: 's1', cwd: '/a', project: 'alpha', plrun: [{name: 'chg', cur: 'Implement'}]},"
              " {state: 'ask', sid: 's2', cwd: '/b', project: 'beta', plrun: [{name: 'old', end: 3}]},"
              " {state: 'wait', sid: 's3', cwd: '/c', project: 'gamma', plNone: {u: 1}}, {state: 'wait', sid: 's4', cwd: '/d', project: 'delta'}]")
        h = run(NOW + "console.log(JSON.stringify(plNowList(" + ss + ")));")
        rows = re.findall(r'class="plnli tlnm[^"]*" data-pncwd="[^"]*" data-pnplat="[^"]*" title="([^"]*)" aria-label="([^"]*)"', h)
        self.assertEqual(rows, [("alpha\nWorking", "alpha · Working · Implement"), ("beta\nNeeds you", "beta · Needs you · old done"),
                                ("gamma\nIdle", "gamma · Idle · Undeclared"), ("delta\nIdle", "delta · Idle")])
        r = run(NOW + "LS['sidereus.plnowc'] = '1'; console.log(JSON.stringify(plNowList(" + ss + ")));")
        self.assertEqual(re.findall(r'class="plnlrd[^"]*"[^>]*aria-label="([^"]*)"', r), ["alpha · Working", "beta · Needs you", "gamma · Idle", "delta · Idle"])
        self.assertIn("plNowRunTxt(x)", js_fn("plNowList"))                    # project name never goes through T()
        self.assertNotIn("T(x.project", js_fn("plNowList"))

    def test_a11y_subagent_running_idle(self):
        h = run(NOW + "console.log(JSON.stringify(plNowAgents({cwd: '/a', sub: [{lab: 'impl: build', aid: 'a1', idle: 5}, {lab: 'rev: look', aid: 'a2', idle: 600}]})));")
        rows = re.findall(r'class="plnagr tlnm( quiet)?"[^>]*title="([^"]*)" aria-label="([^"]*)"', h)
        self.assertEqual([(q, t.endswith(" · Running"), a == t) for q, t, a in rows][0], ("", True, True))
        self.assertTrue(rows[1][1].endswith(" · Idle") and rows[1][0] == " quiet")
        self.assertIn("'Idle':", _src("05a-i18n-en.js"))                       # ko entry lives in 05a; a second one fails i18n_check

    def test_a11y_css_targets_at_least_24px(self):
        with open(os.path.join(ROOT, "web", "css", "43-pipeline.css"), encoding="utf-8") as f:
            css = f.read()

        def rule(sel):
            m = re.search(r"(?:^|\n|\})" + re.escape(sel) + r"\{([^}]*)\}", css)
            self.assertIsNotNone(m, sel)
            return m.group(1)

        def px(body, prop):
            m = re.search(r"(?:^|;)" + prop + r":(-?\d+)px", body)
            self.assertIsNotNone(m, prop + " in " + body)
            return int(m.group(1))
        self.assertGreaterEqual(px(rule(".plnlf"), "height"), 24)
        self.assertGreaterEqual(px(rule(".plw .plnl .plnagr.tlnm"), "min-height"), 24)
        self.assertGreaterEqual(px(rule(".plovr"), "min-height"), 24)
        self.assertGreaterEqual(px(rule(".plwa"), "min-height"), 24)
        rd = rule(".plnlrd")
        self.assertGreaterEqual(min(px(rd, "width"), px(rd, "height")), 24)
        self.assertEqual(px(rule(".plnlrd::before"), "width"), 10)               # visible dot unchanged
        ps = rule(".plnd .plpass")                                               # canvas scale(z): 24px/z keeps 24 on screen (19.2 at 0.8 before)
        self.assertIn("--plph:clamp(24px,calc(24px / var(--plz,1)),60px)", ps)  # 60 = 24/PL_ZFIT
        for d in ("height:var(--plph)", "line-height:var(--plph)", "bottom:calc(var(--plph) / -2)"):
            self.assertIn(d, ps)                                                 # centred on the card edge at any zoom
        pb = rule(".plnd .plpass::before")
        for d in ("top:50%", "height:18px", "box-sizing:border-box", "translate:0 -50%"):
            self.assertIn(d, pb)                                                 # visible pill fixed at 18px
        with open(os.path.join(ROOT, "web", "js", "48d-pipeline-canvas.js"), encoding="utf-8") as f:
            cvjs = f.read()
        self.assertIn("scale(' + v.z + ');--plz:' + v.z + '\">'", cvjs)         # first paint carries the zoom
        self.assertIn("i.style.setProperty('--plz', E.view.z)", cvjs)            # and every pan/zoom update
        rv = rule(".plrv")
        self.assertEqual(px(rv, "line-height") + 2, 16)                          # visible row stays 16px
        self.assertIn("inset:-5px 0", rule(".plrv::before"))                    # 14 + 2*5 = 24 from the padding box
        for sel in ("html[data-ui=next] .plw .pltop>.plwrun>.plrunst>span", "html[data-ui=next] .plw .plbar>.plrunst>span"):
            sp = rule(sel)                                                       # overflow:hidden clip grown 4px each side = 16 + 8 = 24
            self.assertIn("overflow:hidden", sp)
            self.assertEqual((px(sp, "line-height"), sp.count("padding:4px 0;margin:-4px 0;")), (16, 1))
        self.assertEqual(px(rule(".plwgr"), "height"), 24)                       # the hit area is the grip's own row
        self.assertNotIn(".plwgr::before", css)                                  # no overhang over the canvas / card edges
        bar = rule(".plwgr::after")
        self.assertEqual(2 * px(bar, "top") + px(bar, "height"), 24)            # visible 4px bar centred
        self.assertIn(".plgw.plwt{grid-template-rows:var(--plcvh,clamp(260px,34vh,700px)) 24px var(--plwph", css)                # grid row matches PLW_GRIP
        self.assertIn("PLW_GRIP = 24,", _src("48k-pipeline-mode.js"))

    def test_collapsed_rail_scrolls_not_clips(self):
        with open(os.path.join(ROOT, "web", "css", "43-pipeline.css"), encoding="utf-8") as f:
            css = f.read()
        m = re.search(r"\.plw aside\.plnl\.plnlc\{([^}]*)\}", css)
        self.assertIsNotNone(m)
        self.assertRegex(m.group(1), r"(?:^|;)overflow:hidden auto(?:;|$)")      # many live sessions stay reachable
        self.assertRegex(m.group(1), r"(?:^|;)gap:[1-9]\d*px")                   # dot hit areas never touch
        self.assertIn("contain:size", m.group(1))                                # sized by the stack, not by its dots
        self.assertRegex(css, r"\.plnlc>\.plnlh\{[^}]*flex:none")               # fold button never shrinks in the scroller


if __name__ == "__main__":
    unittest.main()
