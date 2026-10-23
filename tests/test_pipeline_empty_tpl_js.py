"""«Pipelines» empty project (48 plBody, 48e plTplPick): template buttons in place of the note; a click opens the
create preview (dry run) only. Pure functions and listeners under node with stubs; no live files."""
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
let SESS = [], PLAG = false, ARCH_PL = 'arch-map', PLNEW = null, PLDRAFT = null, PLSTD = false, PLTPLO = false, POSTS = [], PAINT = 0;
function plLiveProjs(){ return {}; } function plMem(){ return {}; } function plKnown(){ return null; }
function plPickHtml(){ return ''; } function plNewBtn(p){ return p ? '<NEWBTN pri/>' : '<NEWBTN/>'; } function plNewForm(){ return ''; }
function wfBtns(){ return ''; } function plBorrowChips(){ return ''; } function plBorrowOf(){ return null; }
function plSugBody(){ return '<SUG/>'; } function plDelPrev(){ return ''; } function plCur(){ return {ok: false, errs: []}; }
function plPaint(){ PAINT++; } function plRefocus(){}
let LIVE = [{login: true}]; function plSessions(){ return LIVE; }   // default: a session can take the AI draft
async function postJSON(u, b){ POSTS.push([u, b]); return {ok: true, diff: '+x'}; }
"""


def run(body):
    r = subprocess.run(node_e(PRE + body), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def _src(name):
    with open(os.path.join(ROOT, "web", "js", name), encoding="utf-8") as f:
        return f.read()


def _tpls():
    s = _src("48e-pipeline-new.js")
    return s[s.index("const PL_TPLS"):s.index("];", s.index("const PL_TPLS")) + 2]


FNS = "\n".join(js_fn(n) for n in ("plNewDis", "plStartBtns", "plTplPick", "plHeadRow", "plBody")) + "\n"


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PipelineEmptyTpl(unittest.TestCase):
    def test_empty_project_shows_template_buttons(self):
        r = run(_tpls() + "\n" + FNS +
                "let PLS = {proj: '/p', data: {'/p': {ok: true, pipelines: [], suggest: []}}};"
                "PLTPLO = true; const a = plBody(); PLNEW = {}; const b = plBody(); PLNEW = null;"
                "PLS.data['/p'].suggest = [{name: 's'}]; const c = plBody();"
                "PLS.data['/p'] = {ok: true, pipelines: [{name: 'x', ok: false}]}; const d = plBody();"
                "console.log(JSON.stringify([a, b, c, d, PL_TPLS.map(x => x[0])]));")
        a, b, c, d, keys = r
        self.assertEqual(re.findall(r'data-pltpl="([^"]+)"', a), keys)   # one button per template
        self.assertIn("Start from a template", a)
        self.assertNotIn("plempty", a)
        self.assertNotIn("has no pipelines", a)
        self.assertIn("<NEWBTN/>", a)                                      # «+ New» head row kept, not primary (two start buttons are)
        self.assertEqual(b.count("disabled"), len(keys))                   # a form is open: buttons disabled
        self.assertEqual(c, "<SUG/>")                                      # suggestions keep plSugBody
        self.assertNotIn("data-pltpl", d)                                  # a project with pipelines

    def test_draft_and_std_buttons_follow_menu_rules(self):
        r = run(_tpls() + "\n" + FNS +
                "let PLS = {proj: '/p'}; const p = () => plTplPick(); const a = p(); PLNEW = {}; const b = p(); PLNEW = null;"
                "PLDRAFT = {}; const c = p(); PLDRAFT = null; PLSTD = true; const d = p();"
                "console.log(JSON.stringify([a, b, c, d]));")
        a, b, c, d = r
        dn = lambda h: re.search(r"<button[^>]*data-pldnew[^>]*>", h).group(0)
        sd = lambda h: re.search(r"<button[^>]*data-plstd[^>]*>", h).group(0)
        self.assertIn("Ask AI for a draft", a)
        self.assertIn("data-plstd>Start from a template<", a)                       # the standard list opens from the outlined start
        self.assertNotIn("disabled", dn(a) + sd(a))
        self.assertNotIn("disabled", dn(b))                                # plNewDis(PLDRAFT): a «+ New» form leaves it on
        self.assertIn("disabled", dn(c))                                   # a draft form is open
        self.assertNotIn("disabled", sd(c))                                # standard list is never disabled
        self.assertNotIn(" on", sd(a))
        self.assertIn('class="wkrgb on"', sd(d))                                # PLSTD open: .on like the menu item

    def test_r1_one_filled_primary_is_ai_draft(self):
        h = run(_tpls() + "\n" + FNS + "let PLS = {proj: '/p'}; console.log(JSON.stringify(plTplPick()));")
        filled = [b for b in re.findall(r"<button[^>]*>", h) if "plsv" in b]
        self.assertEqual(len(filled), 1)                                   # R1: exactly one filled primary
        self.assertIn("data-pldnew", filled[0])
        self.assertNotIn("plsv", re.search(r"<button[^>]*data-plstd[^>]*>", h).group(0))   # R1: template start is outlined

    def test_no_receiving_session_makes_template_primary(self):
        r = run(_tpls() + "\n" + FNS + "let PLS = {proj: '/p'}; const out = [];"
                "for(const l of [[], [{login: false}], [{login: true}]]){ LIVE = l; out.push(plTplPick()); }"
                "console.log(JSON.stringify(out));")
        for h, live in zip(r, (False, False, True)):
            btns = re.findall(r"<button[^>]*>", h)
            filled = [b for b in btns if "plsv" in b]
            self.assertEqual(len(filled), 1)                               # still exactly one filled primary
            self.assertIn("data-pldnew" if live else "data-plstd", filled[0])
            self.assertIn("data-pldnew" if live else "data-plstd", btns[0])   # primary comes first
            self.assertIn("Ask AI for a draft", h)                         # AI draft stays visible when secondary

    def test_r2_quick_templates_fold(self):
        r = run(_tpls() + "\n" + FNS +
                "let PLS = {proj: '/p'}; const a = plTplPick(); PLTPLO = true; const b = plTplPick(); PLNEW = {}; const c = plTplPick(); PLNEW = null;"
                "PLDRAFT = {}; const d = plTplPick(); console.log(JSON.stringify([a, b, c, d]));")
        a, b, c, d = r
        tg = lambda h: re.search(r"<button[^>]*data-pltplo[^>]*>", h).group(0)
        self.assertEqual(a.count("data-pltpl="), 0)                        # R2: closed at first
        self.assertIn('aria-expanded="false"', tg(a))
        self.assertIn("Quick templates", a)
        self.assertEqual(b.count("data-pltpl="), 6)                        # R2: opened = the six templates
        self.assertIn('aria-expanded="true"', tg(b))
        self.assertIn(" on", tg(b))
        self.assertEqual(re.findall(r"<button[^>]*data-pltpl=[^>]*>", b)[0].count("disabled"), 0)
        for h in (c, d):                                                   # same disable rules under PLNEW / PLDRAFT
            self.assertTrue(all("disabled" in x for x in re.findall(r"<button[^>]*data-pltpl=[^>]*>", h)))

    def test_r2_toggle_handler(self):
        s = _src("48e-pipeline-new.js")
        self.assertIn("if(e.target.closest('[data-pltplo]')){ PLTPLO = !PLTPLO; plPaint(); plRefocus('[data-pltplo]'); return; }", s)

    def test_r3_apply_needs_a_pipeline_orphan_note_does_not(self):
        mb = js_fn("plMainBody")
        r = run("let PLS = {proj: '/p', data: {'/p': {ok: true, pipelines: []}}};"
                "function plOverview(){ return ''; } function plBody(){ return '<B/>'; } function plChips(){ return ''; }"
                "function plApplySeg(){ return '<APPLY/>'; }\n" + mb +
                "\nconst a = plMainBody(); PLS.data['/p'].pipelines = [{name: 'x'}]; const b = plMainBody();"
                "console.log(JSON.stringify([a, b]));")
        self.assertNotIn("<APPLY/>", r[0])                                 # R3: no «Apply» for []
        self.assertIn("<APPLY/>", r[1])                                    # R3: shown with one pipeline
        s = _src("48b-pipeline-run.js")
        self.assertIn("+ plOrphHtml(orph);", s)   # missing-file note is not gated: it matters most in an empty project

    def test_r4_empty_project_at_most_five_controls(self):
        r = run(_tpls() + "\n" + FNS +
                "plNewBtn = () => '<button data-plnewm>+</button>';"
                "let PLS = {proj: '/p', data: {'/p': {ok: true, pipelines: [], suggest: []}}};"
                "console.log(JSON.stringify(plBody()));")
        self.assertLessEqual(len(re.findall(r"<button\b", r)), 5)         # R4: start row + «+ New ▾», chips not in plBody

    def test_cross_review_template_listed(self):
        r = run(_tpls() + "\nconsole.log(JSON.stringify(PL_TPLS.map(x => x[0])));")
        self.assertIn("cross-review", r)                                   # R1: «Cross-review (Codex)» in the list

    def test_reuses_menu_handlers(self):
        s = _src("48e-pipeline-new.js")
        self.assertEqual(s.count("e.target.closest('[data-pldnew]')"), 1)  # no second handler
        self.assertEqual(s.count("e.target.closest('[data-plstd]')"), 1)

    def test_click_opens_dry_run_preview(self):
        s = _src("48e-pipeline-new.js")
        h = s[s.index("document.addEventListener('click', e => {\n  if(!e.target.closest || !e.target.closest('.plw')) return;\n  if(e.target.closest('[data-plnew]'))"):]
        h = h[:h.index("\n});\n") + 5]
        send = s[s.index("async function plNewSend("):]
        send = send[:send.index("\n}\n") + 3]
        r = run("let PLS = {proj: '/p', data: {'/p': {ok: true, pipelines: []}}};\n"
                + js_fn("plNewNameErr") + "\n" + send + "\n"
                "let L = []; const document = { addEventListener(t, f){ L.push(f); } };\n" + h +
                "\nconst ev = k => ({ preventDefault(){}, target: { closest: s => s === '.plw' ? {} : (s === '[data-pltpl]' ? { dataset: { pltpl: k } } : null) } });"
                "(async () => { await L[0](ev('bugfix')); const a = JSON.parse(JSON.stringify(PLNEW));"
                " await L[0](ev('change')); const n = POSTS.length; PLNEW = null; await L[0](ev('empty'));"
                " console.log(JSON.stringify([a, n, POSTS, PLNEW.name])); })();")
        a, n, posts, nm = r
        self.assertEqual((a["tpl"], a["name"], a["diff"]), ("bugfix", "bugfix", "+x"))
        self.assertEqual(n, 1)                                             # open form: a second click does nothing
        self.assertEqual(posts[0], ["/api/pipelines/create", {"proj": "/p", "name": "bugfix", "title": "", "dry": True, "template": "bugfix"}])
        self.assertTrue(all(p[1]["dry"] for p in posts))                  # never a write without «Confirm — create»
        self.assertEqual(nm, "main")


if __name__ == "__main__":
    unittest.main()
