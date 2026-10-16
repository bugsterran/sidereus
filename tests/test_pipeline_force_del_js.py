"""«Force delete» for a schema-breaking pipeline file (48 plBody / plDelete): button, preview, guard.
Pure functions under node with stubs; no live files, no network."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

STUBS = """
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const T = s => s, SESS = [];
let PLS = { proj: '/p', sel: 'bad', data: {}, g: {}, msg: '', saving: false, del: null, std: '', wf: null };
let CUR = null, POSTS = [];
function plCur(){ return CUR; }
function plLiveProjs(){ return {}; } function plMem(){ return {}; } function plKnown(){ return []; }
function plDirty(){ return false; } function plSelHtml(){ return ''; } function plHeadRow(hd, h){ return h; } function plBorrowOf(){ return null; }
function wfBtns(){ return ''; } function plNewBtn(){ return ''; } function plNewForm(){ return ''; }
function plPaint(){} function plRefocus(){} function lsSet(){} function plEntKey(n){ return n; }
async function plLoadProjs(){} async function plLoad(){}
async function postJSON(u, b){ POSTS.push([u, b]); return b.dry ? { ok: true, path: '/p/.claude/pipelines/bad.json', to: '/bak/x--bad.json' } : { ok: true, backup: '/bak/x--bad.json' }; }
"""


def _async_fn(name):
    m = re.search(r"^async function " + name + r"\([\s\S]*?^}$", js_all(), re.M)
    return m.group(0)


def _run(body):
    code = STUBS + js_fn("plBody") + "\n" + js_fn("plDelPrev") + "\n" + _async_fn("plDelete") + "\n(async () => {" + body + "})();"
    r = subprocess.run(node_e(code), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


BAD = "{ name: 'bad', ok: false, errs: ['use: one line, 1..120 chars'] }"


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ForceDelete(unittest.TestCase):
    def test_button_preview_and_move(self):
        r = _run("PLS.data['/p'] = { ok: true, pipelines: [%s] }; CUR = PLS.data['/p'].pipelines[0];"
                 "const a = plBody(); await plDelete(false); const b = plBody(); await plDelete(true);"
                 "console.log(JSON.stringify([a, b, POSTS, PLS.msg]));" % BAD)
        a, b, posts, msg = r
        self.assertIn("data-pldel", a)
        self.assertIn("Force delete", a)
        self.assertNotIn("data-pldelok", a)              # nothing moves before the preview
        self.assertIn("/p/.claude/pipelines/bad.json", b)  # preview names the file
        self.assertIn("data-pldelok", b)
        self.assertEqual([(u, x["name"], x["dry"]) for u, x in posts],
                         [("/api/pipelines/delete", "bad", True), ("/api/pipelines/delete", "bad", False)])
        self.assertIn("/bak/x--bad.json", msg)

    def test_guards(self):
        # unsaved draft (ok, no sha) and borrowed rows never post; an unreadable invalid file (no sha) does
        r = _run("for (const c of [{ name: 'd', ok: true }, { name: 'b', ok: false, from: '/o' }, { name: 'u', ok: false }]) { CUR = c; await plDelete(false); }"
                 "console.log(JSON.stringify(POSTS.map(x => x[1].name)));")
        self.assertEqual(r, ["u"])


if __name__ == "__main__":
    unittest.main()
