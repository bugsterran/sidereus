"""«Pipelines» Watch / Edit mode (48k plModeSet/plWatchFor/plModeBtn/plModeBand/plWatchDef/plWatchPane, 48 plWatchBody, 48d plCanvas, 48h plRO, R1-R7).
Pure functions under node with stubs; no live files."""
import hashlib
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
const TV = j => j.msg.replace(/\{(\w+)\}/g, (a, k) => j.vars[k]);
let LS = {}, PAINT = 0, CUR = null, PLAG = false;
function lsGet(k, d){ return k in LS ? LS[k] : d; }
function lsSet(k, v){ LS[k] = String(v); }
function lsJson(k, d){ try{ return k in LS ? JSON.parse(LS[k]) : d; }catch(e){ return d; } }
function plPaint(){ PAINT++; }
function plCur(){ return CUR; }
let DIRTY = false; function plDirty(){ return DIRTY; }
const PLS = { proj: '/p', wf: null, g: {} };
"""
CANVAS_STUB = """
const PLG_LANE = 30;
const E = {G: {nodes: [{id: 'n1', title: 'A', ui: {x: 10, y: 20}}, {id: 'n2', title: 'B', ui: {x: 300, y: 20}}], loops: [{}]}, view: {x: 5, y: 6, z: 0.8}, sel: null};
function plEnt(){ return E; } function plgCheck(){ return {errs: [{id: 'n1', msg: 'bad <x>'}, {msg: 'other'}]}; } function plVG(E){ return E.G; }
function plgW(){ return 200; } function plgH(){ return 90; } function plEdgesSvg(){ return '<EDGES>'; } function plMarkers(){ return '<MK>'; } function plHeadsSvg(){ return '<HD>'; }
function plNodeHtml(E, n, bad, lt){ return '<N ' + n.id + (bad ? ' bad' : '') + (lt ? ' lt' : '') + '>'; }
function plPalette(E, c){ return '<PAL ' + (c ? c.items.length : 0) + '>'; } function plPanel(E, d){ return '<PAN>'; }
function plWatchPane(E, d, lv, lt){ return '<WP ' + (lv ? lv.sid : '') + '>'; } function plViewRun(){ return {sid: 's1'}; }
const D = {catalog: {items: [{title: {ko: 'A'}}, {title: {ko: 'C "q"'}}]}};
"""
# sha256 of plCanvas(...).html for CANVAS_STUB before the Watch mode existed (Edit output must be byte-identical, R7).
EDIT_SHA = "fac62b35114d2146218746ff496fe5f7ab3e358f3a25b7883372d0bcd4365106"   # re-pinned: .plcvi style gained the --plz zoom variable (only diff)


def _src(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


def _const(name, path):
    s = _src(path)
    i = s.index("const " + name)
    return s[i:s.index(";", i) + 1]


MODE = _src("web/js/48k-pipeline-mode.js").split("document.addEventListener(")[0].replace("let PLMODE", "var PLMODE")


def run(body):
    r = subprocess.run(node_e(PRE + body), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


SAVED = "{name: 'chg', ok: true, sha: 'abc'}"


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PlMode(unittest.TestCase):
    def test_r5_watch_canvas_has_no_palette_or_editor(self):
        h = run(MODE + CANVAS_STUB + js_fn("plCanvas") + "\nconsole.log(JSON.stringify(plCanvas(" + SAVED + ", D, {A: {}}).html));")
        self.assertIn('<div class="plgw plwt">', h)
        self.assertNotIn("<PAL", h)
        self.assertNotIn("<PAN>", h)
        self.assertIn("<WP s1>", h)
        self.assertIn('<div class=plwgr data-plwg=p', h)                       # Watch canvas | pane drag grip
        self.assertNotIn("data-plgh", h)

    def test_r7_edit_canvas_byte_identical(self):
        h = run(MODE + CANVAS_STUB + js_fn("plCanvas") + "\nplModeSet('edit', true);"
                "console.log(JSON.stringify(plCanvas(" + SAVED + ", D, {A: {}}).html));")
        self.assertEqual(hashlib.sha256(h.encode("utf-8")).hexdigest(), EDIT_SHA)

    def test_r5_ro_in_watch_and_backspace_keeps_graph(self):
        s = _src("web/js/48d-pipeline-cv-input.js")
        i = s.index("document.addEventListener('keydown', e => {\n  if(mainView !== 'pipe' || (e.key !== 'Delete'")
        lis = s[i:s.index("\n});", i) + 4]
        r = run(MODE + js_fn("plRO") + "\nlet H = null, mainView = 'pipe'; const document = { addEventListener: (k, f) => { H = f; } };"
                "const E = {G: {nodes: [{id: 'n1'}, {id: 'n2'}]}, sel: {k: 'n', id: 'n2'}}; function plCurEnt(){ return E; }"
                "function plDelSel(E){ E.G.nodes = E.G.nodes.filter(n => n.id !== E.sel.id); }"
                + lis + "CUR = " + SAVED + "; const ev = {key: 'Backspace', preventDefault(){}, target: {tagName: 'DIV', closest: () => null}};"
                "const ro = plRO(); H(ev); const a = E.G.nodes.length; plModeSet('edit', true); const ro2 = plRO(); H(ev);"
                "console.log(JSON.stringify([ro, a, ro2, E.G.nodes.length]));")
        self.assertEqual(r, [True, 2, False, 1])

    def test_r5_watch_pane_evidence_agents_metadata_only(self):
        fns = ["plWatchPane", "plStageRows", "plStageAgents", "plLabParts", "plLabDesc", "plLabTip", "plStrip", "plgNode"]
        h = run(MODE + _const("PL_DESC_RE", "web/js/48b-pipeline-run.js") + "\n" + _const("PL_MK", "web/js/48b-pipeline-run.js") + "\n"
                + "\n".join(js_fn(n) for n in fns)
                + "\nfunction plOc(s){ return 'OC-' + s; } function ago(s){ return s + 's'; } function plgShow(t){ return t; } function plAgLab(a){ return a.lab; }"
                "function subWorkId(a){ return a.tid; } function plPass(){ return null; } function plEvRows(){ return []; } function plEvCommits(){ return []; }"
                "function plEvLine(rows, L){ return '<span class=plev>EV ' + L.w0 + '</span>'; }"
                "const E = {G: {nodes: [{id: 'n1', title: 'Implement', agent: 'impl', model: 'opus', gate: 'scripts/check.sh --fast'}]}, sel: {k: 'n', id: 'n1'}};"
                "const lt = {Implement: {st: 'done', n: 2, sec: 30, w0: 7, w1: 37, from: {Verify: 1},"
                " ag: [{aid: 'a1', tid: 't1', lab: 'impl: [pl:chg/Implement] SECRET-DESC', t0: 1, t1: 31}]}};"
                "const x = {targ: 'SECRET-TARG', prompt: 'SECRET-PROMPT'};"
                "const none = plWatchPane({G: E.G, sel: null}, {}, null, {Implement: {st: 'wait'}});"
                "console.log(JSON.stringify([plWatchPane(E, {}, {sid: 's1'}, lt), none]));")
        pane, none = h
        self.assertIn("OC-done", pane)
        self.assertIn("↺ 1", pane)
        self.assertIn("Agents 2", pane)
        self.assertIn("EV 7", pane)                                           # gate evidence line
        self.assertIn("<code>scripts/check.sh --fast</code>", pane)
        self.assertIn('data-plwsid="s1" data-plwtid="t1"', pane)
        self.assertNotIn("SECRET-TARG", pane)
        self.assertNotIn("SECRET-PROMPT", pane)
        self.assertNotIn("SECRET-DESC", re.sub(r'title="[^"]*"', "", pane))  # description only in title=
        self.assertIn("Click a stage to see its result", none)
        s = _src("web/js/48k-pipeline-mode.js")
        self.assertIn("plOpenWork(t.dataset.plwsid, t.dataset.plwtid)", s)

    def test_r6_mode_persists_and_paints(self):
        r = run(MODE + "const a = PLMODE; plModeSet('edit'); const b = [PLMODE, LS['sidereus.plmode'], PAINT]; plModeSet('bogus');"
                "console.log(JSON.stringify([a, b, PLMODE, LS['sidereus.plmode'], PAINT]));")
        self.assertEqual(r, ["watch", ["edit", "edit", 1], "watch", "watch", 2])

    def test_r6_saved_mode_read_at_load(self):
        r = run("LS['sidereus.plmode'] = 'edit';" + MODE + "console.log(JSON.stringify(PLMODE));")
        self.assertEqual(r, "edit")

    def test_r6_dirty_graph_survives_toggle(self):
        r = run(MODE + "const G = {nodes: [{id: 'n1', title: 'X'}]}; PLS.g['/p\\nchg'] = {G, base: 'old'};"
                "plModeSet('edit'); G.nodes.push({id: 'n2'}); plModeSet('watch'); plModeSet('edit');"
                "console.log(JSON.stringify([PLS.g['/p\\nchg'].G === G, G.nodes.length, PLS.g['/p\\nchg'].base]));")
        self.assertEqual(r, [True, 2, "old"])

    def test_r6_button_borrowed_disabled_drafts_none(self):
        r = run(MODE + "const o = [];"
                "CUR = " + SAVED + "; o.push(plModeBtn()); plModeSet('edit', true); o.push(plModeBtn());"
                "CUR = {name: 'b', ok: true, sha: 's', from: '/other'}; o.push(plModeBtn());"
                "CUR = {name: 'std:x', ok: true, std: 1}; o.push(plModeBtn());"
                "CUR = {name: 'sg', ok: true, suggest: 1}; o.push(plModeBtn());"
                "console.log(JSON.stringify(o));")
        w, e, b, std, sug = r
        self.assertIn("data-plmode=edit", w)
        self.assertIn("<span aria-hidden=true>✎</span> Edit</button>", w)         # R3 pencil glyph + label
        self.assertIn("data-plmode=watch", e)
        self.assertIn(">Close</button>", e)                                    # clean Edit: one «Close», no «Done»
        self.assertIn("disabled", b)
        self.assertIn("Read-only — edit it in its own project", b)
        self.assertEqual([std, sug], ["", ""])

    def test_f6_borrowed_always_watch(self):
        r = run(MODE + "plModeSet('edit', true); console.log(JSON.stringify([plWatchFor({name: 'b', ok: true, sha: 's', from: '/o'}), plWatchFor(" + SAVED + ")]));")
        self.assertEqual(r, [True, False])

    def test_f1_watch_drops_write_previews(self):
        r = run(MODE + "PLS.diff = {name: 'x'}; PLS.del = {name: 'x'}; plModeSet('edit', true); const a = [!!PLS.diff, !!PLS.del];"
                "plModeSet('watch', true); console.log(JSON.stringify([a, PLS.diff, PLS.del]));")
        self.assertEqual(r, [[True, True], None, None])
        s = _src("web/js/48-pipeline.js")
        self.assertIn("if(e.target.closest('[data-plok]')) return plWatchOn() ? undefined : plSave(true);", s)
        self.assertIn("if(e.target.closest('[data-pldelok]')) return plWatchOn() ? undefined : plDelete(true);", s)
        body = js_fn("plBody")
        self.assertLess(body.index("if(wt) return plWatchBody("), body.index("plDelPrev(p) + cv.html"))   # Watch returns before any preview
        wb = js_fn("plWatchBody")
        for bad in ("plDelPrev", "diff", "data-plsave", "data-pldel"):
            self.assertNotIn(bad, wb)

    def test_r6_drafts_force_edit(self):
        r = run(MODE + "console.log(JSON.stringify([" + ",".join("plWatchFor(" + p + ")" for p in (
            SAVED, "{name: 'n', ok: true}", "{name: 's', ok: true, sha: 'x', std: 1}", "{name: 'g', ok: true, sha: 'x', suggest: 1}",
            "{name: 'bad', ok: false, sha: 'x'}", "null")) + "]));")
        self.assertEqual(r, [True, False, False, False, False, False])

    def test_r6_new_save_switches_to_edit(self):
        s = _src("web/js/48e-pipeline-new.js")
        body = s[s.index("async function plNewSend("):]
        body = body[:body.index("\n}\n")]
        self.assertRegex(body, r"else \{ plModeSet\('edit', true\); PLS\.sel = r\.name;")
        fix = js_fn("plEvalFixSelf")
        self.assertIn("if(plWatchOn()) plModeSet('edit', true);", fix)
        self.assertIn("p && p.from", fix)

    def test_r7_list_only_when_no_palette(self):
        pp = js_fn("paintPipe")
        self.assertIn("plNowShown() ? plNowWrap(plMainBody()) : plMainBody()", pp)
        r = run(MODE + "const o = []; CUR = " + SAVED + "; o.push(plNowShown()); plModeSet('edit', true); o.push(plNowShown());"
                "CUR = null; o.push(plNowShown()); console.log(JSON.stringify(o));")
        self.assertEqual(r, [True, False, True])

    def test_r7_css_one_column_in_1600_rule(self):
        css = _src("web/css/43-pipeline.css")
        m = re.search(r"@media \(min-width:1600px\)\{\.plgw\{.*?\}\}", css, re.S)
        self.assertIsNotNone(m)
        self.assertIn(".plgw.plwt{grid-template-columns:minmax(0,1fr)}", m.group(0))
        self.assertIn(".plgw.plwt>.plpan{grid-area:3/1/4/-1}", css)


    def _watch_head(self, mode):
        stubs = ("function plViewRun(){ return {sid: 's1', lt: {}}; } function plLight(){ return {}; } function plDirty(){ return false; }"
                 "function plCanvas(){ return {html: '<CV/>'}; } function plLiveHead(){ return '<RUNBAR/>'; } function plNewForm(){ return ''; }"
                 "function plRunTable(){ return ''; } function plRunPanel(){ return ''; } let PLRUN = null;")
        return run(MODE + stubs + "\n" + "\n".join(js_fn(n) for n in ("plHeadRow", "plRunBtn", "plWatchBody"))
                   + "\nCUR = " + SAVED + "; plModeSet('" + mode + "', true); const hd = {row: ''};"
                   "plWatchBody(CUR, {}, '<PROJ/><PIPE/>', hd, '', plModeBtn()); console.log(JSON.stringify(hd.row));")

    def test_r2_r3_watch_head_row(self):
        row = self._watch_head("watch")
        self.assertTrue(row.startswith("<PROJ/><PIPE/><span class=plwrun><RUNBAR/></span><span class=plact>"))
        act = row[row.index("<span class=plact>"):]
        self.assertLess(act.index("data-plmode=edit"), act.index("data-plrun"))   # [✎ Edit][▶ Run] one action group
        self.assertIn('class="wkrgb plsv plrn" data-plrun><span aria-hidden=true>▶</span> Run', act)   # Run = primary filled
        for bad in ("data-plap", "Gates", "pleunred", "data-pleval", "data-plsave", "data-pldel"):
            self.assertNotIn(bad, row)

    def test_r2_edit_keeps_eval_and_apply(self):
        body = js_fn("plBody")
        i = body.index("const bar = ")
        for k in ("Gates {n}/{m}", "plEvalHead(ev", "mb + plRunBtn(p, dirty)", "data-plsave", "data-pldel"):
            self.assertIn(k, body[i:])
        mb = js_fn("plMainBody")
        self.assertIn("(wt || !((PLS.data[PLS.proj] || {}).pipelines || []).length ? '' : plApplySeg(PLS.data[PLS.proj]))", mb)
        self.assertIn("plModeBand()", mb)

    def test_r3_edit_band_and_done(self):
        r = run(MODE + "CUR = " + SAVED + "; const a = plModeBand(); plModeSet('edit', true);"
                "const b = plModeBand(); CUR = {name: 'b', ok: true, sha: 's', from: '/o'}; console.log(JSON.stringify([a, b, plModeBand()]));")
        self.assertEqual(r[0], "")
        self.assertIn("Editing <b>chg</b>", r[1])
        self.assertTrue(r[1].startswith("<div class=plmband>"))
        self.assertEqual(r[2], "")

    def test_r4_watch_default_stage_and_no_run(self):
        st = "\n".join(js_fn(n) for n in ("plStageRows", "plLabParts", "plLabDesc", "plStrip", "plgNode")) + "\n" + _const("PL_DESC_RE", "web/js/48b-pipeline-run.js") + "\n" + _const("PL_MK", "web/js/48b-pipeline-run.js")
        r = run(MODE + st + "\nfunction plOc(s){ return s; } function ago(s){ return s; } function plgShow(t){ return t; } function plAgLab(a){ return a.lab; } function plPass(){ return null; }"
                "function plEvLine(){ return ''; } function plEvRows(){ return []; } function plEvCommits(){ return []; }"
                "const G = {nodes: [{id: 'a', title: 'A'}, {id: 'b', title: 'B'}, {id: 'c', title: 'C'}]};"
                "const o = [plWatchDef({G}, {A: {st: 'done'}, B: {st: 'run'}, C: {st: 'wait'}}), plWatchDef({G}, {A: {st: 'done'}, B: {st: 'fail'}, C: {st: 'wait'}}),"
                " plWatchDef({G}, null)].map(n => n && n.id);"
                "const E = {G, sel: null}; const pane = plWatchPane(E, {}, null, {A: {st: 'done'}, B: {st: 'run'}});"
                "console.log(JSON.stringify([o, pane.indexOf('<b>B</b>') > 0, E.sel, plWatchPane(E, {}, null, null)]));")
        ids, shows_b, sel, none = r
        self.assertEqual(ids, ["b", "b", None])                                # running stage, else last finished
        self.assertTrue(shows_b)
        self.assertIsNone(sel)                                                 # selection untouched (no view move)
        self.assertEqual(none, "")                                             # no run, nothing picked: no pane

    def test_r4_watch_grid_css_and_fit(self):
        css = _src("web/css/43-pipeline.css")
        self.assertIn(".plgw.plwt{grid-template-rows:var(--plcvh,clamp(260px,34vh,700px)) 24px var(--plwph,auto);height:auto", css)
        self.assertIn(".plwgr{position:relative;height:24px;cursor:ns-resize", css)
        self.assertIn(".plwov{overflow:auto;", css)
        self.assertIn("if(wt) plWatchFit(g, fd, h);", js_fn("plGwFit"))
        fit = js_fn("plWatchFit")
        self.assertIn("if(PLWDRAG) return;", fit)
        self.assertNotIn("scrollHeight }", fit)                                    # sizes from shares only, never from content
        self.assertIn("let A = h - 2 * PLW_GRIP;", fit)                             # canvas + pane + card = the free height
        self.assertIn("if(slack > 0){ A += slack;", fit)                             # reaches the feed bottom
        self.assertIn("if(over > 0){ A -= over;", fit)                               # no page scroll
        self.assertIn("nl.style.minHeight", fit)                                    # list card reaches the stack bottom

    def test_r8_watch_sizes_shares_and_mins(self):
        r = run(MODE + "console.log(JSON.stringify([plWSizes(1000, null), plWSizes(1000, [0.6, 0.25, 0.15]), plWSizes(300, [0.6, 0.3, 0.1]),"
                " plWSizes(2000, null), plWSizes(400, null)]));")
        self.assertEqual(r[0], [750, 140, 110])                                # default shares 0.75 / 0.14 / 0.11
        self.assertEqual(r[1], [600, 250, 150])                                # saved shares win and scale with the window
        self.assertEqual(r[2], [260, 80, 84])                                  # mins: card then pane give way, canvas keeps 260
        self.assertEqual(r[3], [1500, 280, 220])                               # no canvas maximum
        self.assertEqual(r[4], [260, 80, 84])                                  # small window: pane and card at their mins, canvas holds 260
        r = run(MODE + "LS['sidereus.plwv'] = '[0.5,0.3,0.2]'; const a = plWShares(); LS['sidereus.plwv'] = '[1,0,0]';"
                " console.log(JSON.stringify([a, plWShares()]));")
        self.assertEqual(r, [[0.5, 0.3, 0.2], None])

    def test_watch_grips_keyboard_and_aria(self):
        # WCAG 4.1.2 / 2.1.1: the grips were mouse-only separators with no name, value or keys.
        r = run(MODE + "console.log(JSON.stringify([plWGrip('p'), plWGrip('r')]));")
        for h, lab, now in ((r[0], "Resize canvas and result pane", 75), (r[1], "Resize result pane and Running card", 89)):
            self.assertIn(" tabindex=0 ", h)
            self.assertIn('aria-label="' + lab + '"', h)
            self.assertIn(" aria-valuemin=0 aria-valuemax=100 aria-valuenow=%d " % now, h)
        dom = ("const SAVED = {}; function lsSetJson(k, v){ SAVED[k] = v; } function lsDel(k){ delete SAVED[k]; }"
               "const ST = {}, G = {style: {setProperty(k, v){ ST[k] = v; }, getPropertyValue(k){ return ST[k] || ''; }}}, OC = {offsetHeight: 110, style: {}};"
               "const GR = {p: {dataset: {plwg: 'p'}, attrs: {}, setAttribute(k, v){ this.attrs[k] = v; }}, r: {dataset: {plwg: 'r'}, attrs: {}, setAttribute(k, v){ this.attrs[k] = v; }}};"
               "var document = {querySelector(q){ return q.includes('plwov') ? OC : G; }, querySelectorAll(){ return [GR.p, GR.r]; }};"
               "const key = (k, g) => { const e = {key: k, target: {closest: () => g}, prevented: 0, preventDefault(){ this.prevented = 1; }}; plWKey(e); return e.prevented; };")
        r = run(MODE + dom + "plWApply(G, OC, [750, 140, 110]); const out = [];"
                "out.push(key('ArrowDown', GR.p), ST['--plcvh'], ST['--plwph'], GR.p.attrs['aria-valuenow'], SAVED['sidereus.plwv']);"
                "for(let n = 0; n < 5; n++) key('ArrowDown', GR.p); out.push(ST['--plcvh'], ST['--plwph']);"     # pane stops at PLW_MIN[1]
                "OC.offsetHeight = 110; key('ArrowUp', GR.r); out.push(ST['--plwph'], OC.style.height, key('a', GR.p), key('ArrowDown', null));"
                "console.log(JSON.stringify(out));")
        self.assertEqual(r[:5], [1, "774px", "116px", 77, [0.774, 0.116, 0.11]])   # ArrowDown = 24px, same save as a drag
        self.assertEqual(r[5:7], ["810px", "80px"])                                 # clamped at the pane minimum
        self.assertEqual(r[7:], ["80px", "110px", 0, 0])                          # pane already at its min; other keys / non-grips ignored
        self.assertIn("document.addEventListener('keydown', plWKey);", _src("web/js/48k-pipeline-mode.js"))
        css = _src("web/css/43-pipeline.css")
        self.assertIn(".plwgr:focus-visible::after{opacity:1;", css)

    def test_running_card_fits_header_and_two_rows(self):
        # A 48px card showed the header + one row; a second (failed) run sat clipped below the fold.
        r = run(MODE + "console.log(JSON.stringify([PLW_MIN[2], plWSizes(600, null)[2], plWSizes(400, null)[0]]));")
        self.assertGreaterEqual(r[0], 84)
        self.assertGreaterEqual(r[1], r[0])
        self.assertGreaterEqual(r[2], 260)
        self.assertIn(".plwov{overflow:auto;min-height:84px;", _src("web/css/43-pipeline.css"))

    def test_r8_running_card_always_present(self):
        r = run(MODE + "console.log(JSON.stringify([plWatchOv(''), plWatchOv('<div class=plov>X</div>')]));")
        self.assertEqual(r[0], "<div class=plwov><div class=plov><b class=plovh>Running 0</b><span class=hidnote>No runs running</span></div></div>")
        self.assertEqual(r[1], "<div class=plwov><div class=plov>X</div></div>")
        s = _src("web/js/48k-pipeline-mode.js")
        self.assertIn("lsSetJson('sidereus.plwv'", s)                          # drag end stores shares
        self.assertIn("lsDel('sidereus.plwv')", s)                              # double-click resets

    def test_r6_draft_save_primary_in_action_group_with_back(self):
        stubs = ("function plCanvas(){ return {html: '<CV/>'}; } function plNewBtn(){ return ''; } function plNewForm(){ return ''; } function plStartBtns(){ return ''; }"
                 "function plPickHtml(){ return ''; } function plgTplShow(t){ return t; } let PLNEW = null;")
        r = run(MODE + stubs + "\n" + "\n".join(js_fn(n) for n in ("plHeadRow", "plStdBody", "plSugBody", "plDraftBand", "plBackBtn"))
                + "\nconsole.log(JSON.stringify([plStdBody({}, {title: 'T'}), plSugBody({suggest: [{title: 'S'}]})]));")
        std, sug = r
        for h, attr in ((std, "data-plstdsave"), (sug, "data-plsugsave")):
            act = h[h.index("<span class=plact>"):]
            self.assertRegex(act, r'<button class="wkrgb plsv" ' + attr)
            self.assertIn("Draft — not saved yet", h)
        self.assertLess(std.index("data-plstdx"), std.index("data-plstdsave"))
        self.assertIn('aria-label="Close this draft without saving"', std)

    def test_r6_every_draft_form_has_back(self):
        s = _src("web/js/48e-pipeline-new.js")
        for attr in ("data-plnx", "data-pldx", "data-plstdx"):
            self.assertIn("plBackBtn('" + attr + "')", s)
            self.assertIn("e.target.closest('[" + attr + "]')", s)

    def test_r6_esc_closes_draft(self):
        r = run("let mainView = 'pipe', PLNEWM = false, PLRV = false, PLPSK = null, PLAPK = null, PLRUN = null, PLESC_MENU = false, PLNEW = {}, PLDRAFT = {}; PLS.std = 'x';\n" + js_fn("plEscOwned") + "\n" + js_fn("plMenuOpen") + "\n" + js_fn("plEscSnap") + "\n" + js_fn("plDraftEsc")
                + "\nconst ev = (k, tag, dp) => ({key: k, target: {tagName: tag}, defaultPrevented: !!dp});"
                "const o = [plDraftEsc(ev('Escape', 'INPUT')), PLNEW !== null, plDraftEsc(ev('Escape', 'BUTTON')), PLNEW, PLDRAFT !== null,"
                " plDraftEsc(ev('Escape', 'DIV')), plDraftEsc(ev('Escape', 'DIV')), PLS.std, plDraftEsc(ev('Escape', 'DIV')), plDraftEsc(ev('Enter', 'DIV'))];"
                "PLS.std = 'y'; PLRV = true; o.push(plDraftEsc(ev('Escape', 'DIV')), PAINT); console.log(JSON.stringify(o));")
        self.assertEqual(r, [False, True, True, None, True, True, True, "", False, False, False, 3])

    def test_r6_esc_left_to_open_layers(self):
        base = "let mainView = 'pipe', PLNEWM = false, PLRV = false, PLPSK = null, PLAPK = null, PLRUN = null, PLESC_MENU = false, PLNEW = null, PLDRAFT = {desc: 'typed'};"
        fns = js_fn("plEscOwned") + "\n" + js_fn("plMenuOpen") + "\n" + js_fn("plEscSnap") + "\n" + js_fn("plDraftEsc")
        ev = "\nconst ev = {key: 'Escape', target: {tagName: 'DIV'}, defaultPrevented: false};"
        o = []
        for g in ("let SDRW_OPEN = true;", "const ISPOP = true;", "let strPop = {ak: 1};", "let cpOn = true;",
                  "let railOpen = true; function railMode(){ return 'overlay'; } const innerWidth = 900;"):
            o.append(run(base + g + "\n" + fns + ev + "console.log(JSON.stringify([plDraftEsc(ev), PLDRAFT && PLDRAFT.desc]));"))
        self.assertEqual(o, [[False, "typed"]] * 5)                          # the layer owns that Esc; the typed draft survives
        r = run(base + "let railOpen = true; function railMode(){ return 'docked'; } const innerWidth = 1440;\n" + fns + ev
                + "console.log(JSON.stringify([plDraftEsc(ev), PLDRAFT]));")
        self.assertEqual(r, [True, None])                                    # docked rail: no layer, Esc closes the draft

    def test_edit_close_or_cancel(self):
        r = run(MODE + "let RESET = 0; function plResetEnt(){ RESET++; } const o = [];"
                "CUR = " + SAVED + "; plModeSet('edit', true); o.push(plModeBtn(), plCancelBtn(CUR));"
                "DIRTY = true; o.push(plModeBtn(), plCancelBtn(CUR)); PLS.msg = 'm'; plCancelEdit(); o.push(RESET, PLMODE, PLS.msg, LS);"
                "console.log(JSON.stringify(o));")
        close, c0, mb, cancel, reset, mode, msg, ls = r
        self.assertIn(">Close</button>", close)
        self.assertEqual(c0, "")
        self.assertEqual(mb, "")                                               # dirty: no «Close» before Run
        self.assertIn("data-plcancel", cancel)
        self.assertIn(">Cancel</button>", cancel)
        self.assertEqual([reset, mode, msg, ls["sidereus.plmode"]], [1, "watch", "", "watch"])   # discard locally, back to Watch
        self.assertNotIn("postJSON", js_fn("plCancelEdit"))                   # no server write
        body = _src("web/js/48-pipeline.js")
        self.assertIn("(typeof plCancelBtn === 'function' ? plCancelBtn(p) : '')\n    + '<button class=\"wkrgb plsv\" data-plsave", body)   # «Cancel» right before «Save»
        self.assertIn("await plLoad(PLS.proj, true); if(typeof plModeSet === 'function') plModeSet('watch', true); }", body)   # only the confirmed write branch

    def test_edit_esc_closes_only_when_clean(self):
        pre = ("let mainView = 'pipe', PLNEWM = false, PLRV = false, PLPSK = null, PLAPK = null, PLRUN = null, PLESC_MENU = false, PLNEW = null, PLDRAFT = null; PLS.std = '';"
               "function plEscOwned(){ return false; }" + js_fn("plMenuOpen") + MODE + "CUR = " + SAVED + "; const K = {key: 'Escape', target: {tagName: 'DIV'}};")
        r = run(pre + "const o = []; plModeSet('edit', true); DIRTY = true; o.push(plEditEsc(K), PLMODE);"
                "DIRTY = false; o.push(plEditEsc({key: 'Escape', target: {tagName: 'INPUT'}}), PLMODE);"
                "PLS.diff = {}; o.push(plEditEsc(K)); PLS.diff = null; o.push(plEditEsc(K), PLMODE);"
                "plModeSet('edit', true); CUR = {name: 'std:x', ok: true, std: 1}; o.push(plEditEsc(K), PLMODE);"
                "console.log(JSON.stringify(o));")
        self.assertEqual(r, [False, "edit", False, "edit", False, True, "watch", False, "edit"])
        self.assertIn("document.addEventListener('keydown', plEditEsc);", _src("web/js/48k-pipeline-mode.js"))

    def test_esc_menu_clearing_its_flag_first_keeps_draft(self):
        # The menu's own listener runs before plDraftEsc and nulls its flag; the capture snapshot still sees it open.
        fns = js_fn("plEscOwned") + "\n" + js_fn("plMenuOpen") + "\n" + js_fn("plEscSnap") + "\n" + js_fn("plDraftEsc")
        o = []
        for flag in ("PLPSK", "PLRV", "PLAPK"):
            o.append(run("let mainView = 'pipe', PLNEWM = false, PLRV = false, PLPSK = null, PLAPK = null, PLRUN = null, PLESC_MENU = false, PLNEW = {}, PLDRAFT = null; PLS.std = '';\n"
                         + fns + "\nconst ev = {key: 'Escape', target: {tagName: 'DIV'}, defaultPrevented: false};"
                         + flag + " = {}; plEscSnap(ev); " + flag + " = null;"               # capture snapshot, then the menu closes itself
                         + "const a = plDraftEsc(ev); plEscSnap(ev); const b = plDraftEsc(ev);"   # next Esc: nothing open, the draft closes
                         + "console.log(JSON.stringify([a, b, PLNEW]));"))
        self.assertEqual(o, [[False, True, None]] * 3)
        self.assertIn("document.addEventListener('keydown', plEscSnap, true);", _src("web/js/48e-pipeline-new.js"))
        self.assertNotIn("stopPropagation", js_fn("plEscSnap"))

    def test_esc_run_panel_keeps_new_form(self):
        r = run("let mainView = 'pipe', PLNEWM = false, PLRV = false, PLPSK = null, PLAPK = null, PLRUN = {name: 'chg'}, PLESC_MENU = false, PLNEW = {}, PLDRAFT = null; PLS.std = '';\n"
                + js_fn("plEscOwned") + "\n" + js_fn("plMenuOpen") + "\n" + js_fn("plEscSnap") + "\n" + js_fn("plDraftEsc")
                + "\nconst ev = {key: 'Escape', target: {tagName: 'DIV'}, defaultPrevented: false}; plEscSnap(ev);"
                "console.log(JSON.stringify([plDraftEsc(ev), PLNEW, PLRUN]));")
        self.assertEqual(r, [False, {}, {"name": "chg"}])

if __name__ == "__main__":
    unittest.main()
