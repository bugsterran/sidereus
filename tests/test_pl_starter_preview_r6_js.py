"""«Start with recommended setup» (48l): dry diff preview, strict mode a separate unticked box, test-command input, write only on confirm.
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
const T = s => s, FEATS = {};
let LS = {}, POSTS = [];
function lsGet(k, d){ return k in LS ? LS[k] : d; } function lsSet(k, v){ LS[k] = v; }
function plPaint(){} function plLoadAll(){} function diffHtml(s){ return '<code>' + esc(s) + '</code>'; } function TE(r){ return r.err || ''; }
async function plLoadProjs(){} async function plLoad(){}
let DET = '';
async function postJSON(u, b){ POSTS.push([u, b]); return b.dry ? { ok: true, diff: '+ new file ' + (b.policy ? '_policy.json' : 'ci.json') + ' gate=' + (b.gate || ''), files: ['.claude/pipelines/ci.json'], detected: DET }
  : { ok: true, written: ['.claude/pipelines/ci.json'], skipped: [] }; }
const PLST_KEY = 'sidereus.plStartDone';
let PLST_DX = { on: false }, PLST_PV = null;
let PLS = { proj: '/a', projs: { ok: true, projects: [{ path: '/a', n: 0 }] }, data: { '/a': { ok: true, pipelines: [] } }, msg: '' };
"""


def _run(body):
    fetch = re.search(r"^async function plStartFetch\([\s\S]*?^}$", js_all(), re.M).group(0)
    code = STUBS + "\n".join(js_fn(n) for n in ("plStartDxOn", "plStartDx", "plStartSteps", "plStartList", "plStartPrev")) \
        + "\n" + fetch + "\n(async () => {" + body + "})();"
    r = subprocess.run(node_e(code), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


NEW = "PLST_PV = {proj: '/a', policy: false, busy: false, diff: null, files: [], cmd: null, det: '', err: ''};"


@unittest.skipUnless(shutil.which("node"), "node not installed")
class Starter(unittest.TestCase):
    def test_button_only_for_empty_project(self):
        r = _run("const a = plStartList(); PLS.data['/a'].pipelines = [{name: 'x', red: 0}]; PLS.projs.projects[0].n = 1;"
                 "const b = plStartList(); console.log(JSON.stringify([a, b]));")
        a, b = r
        self.assertIn("data-plstgo", a)
        self.assertIn("Start with recommended setup", a)
        self.assertNotIn("data-plstgo", b)

    def test_r6_dry_preview_unticked_strict_and_empty_input(self):
        r = _run(NEW + "await plStartFetch(false); const h = plStartList(); console.log(JSON.stringify([h, POSTS]));")
        h, posts = r
        self.assertEqual(posts, [["/api/pipelines/starter", {"proj": "/a", "policy": False, "dry": True}]])
        self.assertIn("+ new file ci.json", h)
        self.assertIn("Turn on strict mode (file edits need an open run)", h)
        self.assertIn("When on, file edits in this project need an open pipeline run.", h)
        self.assertNotRegex(h, r"data-plstpol[^>]*checked")
        self.assertRegex(h, r'data-plstcmd value="" placeholder="Your test command, e.g. npm test"')
        self.assertNotIn("Detected", h)
        self.assertIn("Empty — the gate is left out", h)
        self.assertIn("data-plstok", h)

    def test_detected_prefill_and_edit_refetches_with_gate(self):
        r = _run("DET = 'npm test';" + NEW + "await plStartFetch(false); const a = plStartList();"
                 "PLST_PV.cmd = 'make check'; await plStartFetch(false); const b = plStartList();"
                 "PLST_PV.cmd = ' '; await plStartFetch(false); const c = plStartList();"
                 "console.log(JSON.stringify([a, b, c, POSTS.map(p => p[1].gate)]));")
        a, b, c, gates = r
        self.assertIn('value="npm test"', a)
        self.assertIn("Detected", a)
        self.assertIn('value="make check"', b)
        self.assertNotIn("Detected", b)
        self.assertIn("gate=make check", b)
        self.assertIn("Empty — the gate is left out", c)
        self.assertEqual(gates, [None, "make check", ""])

    def test_strict_refetches_dry_then_confirm_writes(self):
        r = _run(NEW + "await plStartFetch(false); PLST_PV.policy = true; await plStartFetch(false); const n = POSTS.length;"
                 "const h = plStartList(); await plStartFetch(true); console.log(JSON.stringify([n, h, POSTS, PLST_PV, PLS.msg]));")
        n, h, posts, pv, msg = r
        self.assertEqual(n, 2)
        self.assertTrue(all(p[1]["dry"] for p in posts[:2]))    # nothing written before Confirm
        self.assertIn("_policy.json", h)
        self.assertEqual(posts[2], ["/api/pipelines/starter", {"proj": "/a", "policy": True, "dry": False, "gate": ""}])
        self.assertIsNone(pv)
        self.assertIn("ci.json", msg)

    def test_late_reply_for_closed_preview_is_dropped(self):
        r = _run(NEW + "const p = plStartFetch(false); PLST_PV = null; await p; console.log(JSON.stringify([PLST_PV]));")
        self.assertEqual(r, [None])


if __name__ == "__main__":
    unittest.main()
