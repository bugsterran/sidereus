"""«Pipelines» head row (48 plChips/plSelHtml/plMainBody, 48e plNewBtn, 08b ppComboHtml): project combobox · pipeline
select · «+ New ▾» menu on one row above «Apply». Pure functions and listeners under node with stubs; no live files."""
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
const T = s => s; let PPS = null; const PPC = {};
"""


def run(body):
    r = subprocess.run(node_e(PRE + body), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def _src(name):
    with open(os.path.join(ROOT, "web", "js", name), encoding="utf-8") as f:
        return f.read()


CHIPS = """
let SESS = [], PROJ_GONE = new Set(), PLS = {proj: '/w/b', projs: null}, PAINT = 0, LS = {}, PLNEW = 1;
function plLiveProjs(){ return {'/w/b': ['x']}; } function plMem(){ return {}; } function plKnown(){ return null; }
function strShort(p){ return p.split('/').pop(); } function strProjList(){ return []; }
function plLiveDot(){ return '<i class=mvdot></i>'; } function plAddForm(){ return ''; } function plBrOpen(){}
function plPaint(){ PAINT++; } function lsSet(k, v){ LS[k] = v; }
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PipelineHeader(unittest.TestCase):
    def test_R1_project_combobox_full_name(self):
        r = run(CHIPS + js_fn("ppComboHtml") + "\n" + js_fn("plChips") + "\nfunction plPickProj(){}\n"
                "PLS.projs = {ok: true, projects: [{path: '/w/a', n: 1}, {path: '/w/b', n: 2}, {path: '/w/a-very-long-project-name-here', n: 1}], added: ['/w/b']};"
                "const a = plChips(); PLS.proj = '/w/a-very-long-project-name-here'; const b = plChips();"
                "console.log(JSON.stringify([a, b]));")
        a, b = r
        self.assertEqual(a.count("data-ppk="), 1)              # one combobox, no chip row
        self.assertIn("aria-haspopup=listbox", a)
        self.assertIn('title="/w/b"', a)
        self.assertIn("class=mvdot", a)                         # live dot kept
        self.assertNotIn("More ▾", a)
        self.assertNotIn("ppcs", a)
        self.assertIn('data-plprojrm="/w/b"', a)                    # added project: × sits next to the combobox
        self.assertIn("a-very-long-project-name-here</span>", b)  # full name, not truncated
        self.assertNotIn("data-plprojrm", b)

    def test_R1_run_model_select_click_never_removes(self):
        # 48b's run-model select (select.plrsel) carries data-plrm; the project × uses its own attribute.
        s = _src("48-pipeline.js")
        h = s[s.index("document.addEventListener('click', e => {\n  if(!e.target.closest || !e.target.closest('.plw')) return;\n  const rm"):]
        h = h[:h.index("\n});\n") + 5]
        r = run("let REM = [], PLS = {data: {}, proj: '/p'}; function plRemove(p){ REM.push(p); } function plBrOpen(){} function plSave(){} function plDelete(){} function plPaint(){}"
                "let L = []; const document = { addEventListener(t, f){ L.push(f); } };\n" + h +
                "\nconst el = (attrs) => ({ dataset: attrs, matches(){ return false; } });"
                "const ev = (m) => ({ preventDefault(){}, target: { closest: s => s === '.plw' ? {} : (m[s] || null) } });"
                "L[0](ev({'[data-plrm]': el({plrm: 'Implement'})})); const a = REM.length;"
                "L[0](ev({'[data-plprojrm]': el({plprojrm: '/w/x'})}));"
                "console.log(JSON.stringify([a, REM]));")
        self.assertEqual(r, [0, ["/w/x"]])
        self.assertIn('<select class=plrsel data-plrm="', _src("48b-pipeline-run.js"))

    def test_R1_pick_loads_project(self):
        r = run(CHIPS + "let CFG = null; function ppComboHtml(cfg){ CFG = cfg; return ''; }\n" + js_fn("plChips") + "\n" + js_fn("plPickProj") + "\n"
                "PLS.projs = {ok: true, projects: [{path: '/w/a', n: 1}, {path: '/w/b', n: 1}], added: []}; plChips();"
                "CFG.pick('/w/a'); console.log(JSON.stringify([PLS.proj, LS['sidereus.plproj'], PAINT, PLNEW, CFG.rkey]));")
        self.assertEqual(r, ["/w/a", "/w/a", 1, None, "sidereus.plrecent"])
        # paintPipe loads the picked project's list (plLoad(PLS.proj)), as the chip click did
        self.assertIn("if(PLS.projs) plLoad(PLS.proj, false);", js_fn("paintPipe"))

    def test_R2_one_option_per_pipeline_selected(self):
        r = run("let DIRTY = {b: 1}; function plDirty(n){ return !!DIRTY[n]; }\n"
                "function plBorrows(d){ return d.borrowed || []; } function plBorrowLab(b){ return b.name + ' · from x'; }\n"
                + js_fn("plSelHtml") + "\n"
                "const ps = [{name: 'a', ok: true, title: 'A t'}, {name: 'b', ok: true}, {name: 'c', ok: false}], d = {borrowed: [{name: 'arch-map', from: '/s'}]};"
                "console.log(JSON.stringify([plSelHtml(ps, ps[1], ['b'], d), plSelHtml(ps, null, [], {}), plSelHtml([], null, [], {})]));")
        a, b, c = r
        self.assertEqual(a.count("<option value="), 4)          # 3 own + 1 borrowed
        self.assertEqual(a.count(" selected"), 1)
        self.assertIn('<option value="b" selected', a)
        self.assertIn("b • · running", a)                       # dirty + running in the option text
        self.assertIn('title="A t"', a)
        self.assertLess(a.index('value="c"'), a.index("<optgroup"))   # own first, then borrowed
        self.assertIn("data-plsel", a)
        self.assertIn('<option value="" selected>—</option>', b)   # nothing open: placeholder row
        self.assertEqual(c, "")

    def test_R2_change_opens_pipeline(self):
        r = run("let PLS = {sel: '', std: 'x', wf: {}, diff: 1, del: 1, msg: 'm', sugI: 0}, PAINT = 0, AG = null;"
                "function plPaint(){ PAINT++; } function plAgSet(v){ AG = v; }\n" + js_fn("plSelPick") + "\n"
                "plSelPick('b'); const a = Object.assign({}, PLS, {AG, PAINT}); plSelPick('sug:1'); plSelPick('');"
                "console.log(JSON.stringify([a, PLS.sugI, PAINT]));")
        a, sug, n = r
        self.assertEqual({k: a[k] for k in ("sel", "std", "wf", "diff", "del", "msg", "AG", "PAINT")},
                         {"sel": "b", "std": "", "wf": None, "diff": None, "del": None, "msg": "", "AG": False, "PAINT": 1})
        self.assertEqual((sug, n), (1, 2))                       # empty value («—») does nothing
        self.assertIn("el.matches('.plw select[data-plsel]')", _src("48-pipeline.js"))

    MENU = """
let PLNEW = null, PLDRAFT = null, PLSTD = false, PAINT = 0, FOC = [], L = [];
function plPaint(){ PAINT++; } function plRefocus(...s){ FOC.push(s[0]); }
function plNewDis(on){ return on ? ' disabled title="x"' : ''; }
function ppStep(i, d, n){ return 0; }
const document = { addEventListener(t, f, c){ L.push([t, f, !!c]); }, querySelectorAll(){ return []; } };
"""

    def _menu(self, body):
        s = _src("48e-pipeline-new.js")
        block = s[s.index("let PLNEWM = false;"):s.index("function plNewNameErr(")]
        return run(self.MENU + block + "\n" + body)

    def test_R3_menu_items_keep_attrs(self):
        r = self._menu("const a = plNewBtn(); PLNEWM = true; const b = plNewBtn(1); PLNEW = {}; PLSTD = true; const c = plNewBtn();"
                       "console.log(JSON.stringify([a, b, c]));")
        a, b, c = r
        self.assertIn("data-plnewm aria-haspopup=menu aria-expanded=\"false\"", a)
        self.assertIn("+ New ▾", a)
        for k in ("data-plnew>", "data-plimp", "data-pldnew", "data-plstd"):
            self.assertNotIn(k, a)                                # closed: items not rendered
            self.assertIn(k, b)
        self.assertIn("role=menu", b)
        self.assertIn("wkrgb plsv", b)                            # empty state keeps the primary fill
        self.assertIn('data-plnew disabled', c)                   # same plNewDis as the old buttons
        self.assertIn('data-plimp disabled', c)
        self.assertIn('class="wkrgb on" data-plstd', c)
        for lab in ("+ New pipeline", "Import from another project", "Ask AI for a draft", "Standard templates"):
            self.assertIn(lab, b)

    def test_R3_menu_closes_on_item_and_esc(self):
        r = self._menu("""
const ev = (inside) => ({ target: { closest: s => inside.includes(s) ? {} : null } });
const cap = L.filter(x => x[0] === 'click' && x[2])[0][1], key = L.filter(x => x[0] === 'keydown')[0][1];
PLNEWM = true; cap(ev(['.plnewm', '.plnewm button'])); const item = [PLNEWM, PAINT];
PLNEWM = true; let pd = 0; key({ key: 'Escape', preventDefault(){ pd++; }, stopPropagation(){}, target: { closest: s => s === '.plnewmw' ? {} : null } });
const esc_ = [PLNEWM, PAINT, FOC.slice(-1)[0], pd];
PLNEWM = true; cap(ev([])); const out = [PLNEWM, PAINT];
console.log(JSON.stringify([item, esc_, out]));""")
        item, esc_, out = r
        self.assertEqual(item, [False, 0])                        # item: closed; its own handler repaints
        self.assertEqual(esc_, [False, 1, "[data-plnewm]", 1])     # Esc: closed, focus back on «+ New ▾»
        self.assertEqual(out, [False, 1])                         # outside click: closed without a repaint (click not swallowed)

    def test_R4_one_head_row_before_apply(self):
        r = run("let PLS = {data: {}, proj: '/a'}; function plOverview(){ return ''; } function plChips(){ return '<P/>'; }"
                "function plApplySeg(){ return '<APPLY/>'; } function plBody(ov, hd){ hd.row = '<SEL/><NEW/>'; return '<BODY/>'; }\n"
                + js_fn("plMainBody") + "\nconsole.log(JSON.stringify(plMainBody()));")
        self.assertEqual(r, "<div class=pltop><P/><SEL/><NEW/></div><APPLY/><BODY/>")
        # real plBody: with a head sink the row leaves the body (no .plnames), without one it stays a standalone row
        stubs = ("let PLS = {proj: '/p', sel: 'a', data: {'/p': {ok: true, pipelines: [{name: 'a', ok: false, errs: ['x']}]}}, std: '', wf: null, msg: '', saving: false, del: null};"
                 "const SESS = []; function plCur(){ return PLS.data['/p'].pipelines[0]; } function plLiveProjs(){ return {}; } function plMem(){} function plKnown(){}"
                 "function plBorrowOf(){ return null; } function wfBtns(){ return '<WF/>'; } function plNewBtn(){ return '<NEW/>'; } function plNewForm(){ return ''; }"
                 "function plDelPrev(){ return ''; } function plSelHtml(){ return '<select data-plsel></select>'; }\n")
        a, b = run(stubs + js_fn("plHeadRow") + "\n" + js_fn("plBody") + "\nconst hd = {}; const a = plBody('', hd);"
                   "console.log(JSON.stringify([[a, hd.row], plBody('')]));")
        self.assertNotIn("plnames", a[0])
        self.assertEqual(a[1], "<select data-plsel></select><NEW/><WF/>")
        self.assertTrue(b.startswith("<div class=plnames><select data-plsel>"), b)
        with open(os.path.join(ROOT, "web", "css", "43-pipeline.css"), encoding="utf-8") as f:
            css = f.read()
        self.assertRegex(css, r"\.pltop\{display:flex;[^}]*align-items:center")


if __name__ == "__main__":
    unittest.main()
