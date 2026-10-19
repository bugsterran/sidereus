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
let SESS = [], PLAG = false, ARCH_PL = 'arch-map', PLNEW = null, PLDRAFT = null, POSTS = [], PAINT = 0;
function plLiveProjs(){ return {}; } function plMem(){ return {}; } function plKnown(){ return null; }
function plPickHtml(){ return ''; } function plNewBtn(){ return '<NEWBTN/>'; } function plNewForm(){ return ''; }
function wfBtns(){ return ''; } function plBorrowChips(){ return ''; } function plBorrowOf(){ return null; }
function plSugBody(){ return '<SUG/>'; } function plDelPrev(){ return ''; } function plCur(){ return {ok: false, errs: []}; }
function plPaint(){ PAINT++; } function plRefocus(){}
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


FNS = "\n".join(js_fn(n) for n in ("plNewDis", "plTplPick", "plHeadRow", "plBody")) + "\n"


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PipelineEmptyTpl(unittest.TestCase):
    def test_empty_project_shows_template_buttons(self):
        r = run(_tpls() + "\n" + FNS +
                "let PLS = {proj: '/p', data: {'/p': {ok: true, pipelines: [], suggest: []}}};"
                "const a = plBody(); PLNEW = {}; const b = plBody(); PLNEW = null;"
                "PLS.data['/p'].suggest = [{name: 's'}]; const c = plBody();"
                "PLS.data['/p'] = {ok: true, pipelines: [{name: 'x', ok: false}]}; const d = plBody();"
                "console.log(JSON.stringify([a, b, c, d, PL_TPLS.map(x => x[0])]));")
        a, b, c, d, keys = r
        self.assertEqual(re.findall(r'data-pltpl="([^"]+)"', a), keys)   # one button per template
        self.assertIn("Start from a template", a)
        self.assertNotIn("plempty", a)
        self.assertNotIn("has no pipelines", a)
        self.assertIn("<NEWBTN/>", a)                                      # «+ New» head row kept
        self.assertEqual(b.count("disabled"), len(keys))                   # a form is open: buttons disabled
        self.assertEqual(c, "<SUG/>")                                      # suggestions keep plSugBody
        self.assertNotIn("data-pltpl", d)                                  # a project with pipelines

    def test_click_opens_dry_run_preview(self):
        s = _src("48e-pipeline-new.js")
        h = s[s.index("document.addEventListener('click', e => {\n  if(!e.target.closest || !e.target.closest('.plw')) return;\n  if(e.target.closest('[data-plnew]'))"):]
        h = h[:h.index("\n});\n") + 5]
        send = s[s.index("async function plNewSend("):]
        send = send[:send.index("\n}\n") + 3]
        r = run("let PLS = {proj: '/p', data: {'/p': {ok: true, pipelines: []}}}, PLSTD = false;\n"
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
