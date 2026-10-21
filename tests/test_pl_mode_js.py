"""«Pipelines» Watch / Edit mode (48k plModeSet/plWatchFor/plModeBtn/plWatchPane, 48d plCanvas, 48h plRO, R5-R7).
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
let LS = {}, PAINT = 0, CUR = null, PLAG = false;
function lsGet(k, d){ return k in LS ? LS[k] : d; }
function lsSet(k, v){ LS[k] = String(v); }
function plPaint(){ PAINT++; }
function plCur(){ return CUR; }
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
EDIT_SHA = "e7436b7d66a2c39039d3114c7cf16d4b29ebc827412af70e82f4774e202c1831"


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
        self.assertIn("data-plgh", h)                                         # split handle kept

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
                "const none = plWatchPane({G: E.G, sel: null}, {}, null, lt);"
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
        self.assertIn('data-plmode="edit"', w)
        self.assertIn(">Edit<", w)
        self.assertIn('data-plmode="watch"', e)
        self.assertIn(">Done<", e)
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
        self.assertIn("(wt ? '' : plDelPrev(p))", body)
        self.assertIn("(wt ? '' : diff)", body)

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


if __name__ == "__main__":
    unittest.main()
