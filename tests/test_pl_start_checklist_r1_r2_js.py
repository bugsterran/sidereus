"""«Get started» checklist (48l plStartSteps/plStartList/plStartDxOn): four steps from existing data, gone when done or hidden.
Pure functions under node with stubs; no live files, no network."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

STUBS = """
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const T = s => s, FEATS = {};
let LS = {}, GETS = [], DX_REPLY = null;
function lsGet(k, d){ return k in LS ? LS[k] : d; } function lsSet(k, v){ LS[k] = v; return true; }
function plPaint(){} function plLoadAll(){} function diffHtml(s){ return esc(s); }
function getJSON(u){ GETS.push(u); return DX_REPLY; }
const PLST_KEY = 'sidereus.plStartDone';
let PLST_DX = null, PLST_PV = null;
let PLS = { proj: '', projs: { ok: true, projects: [] }, data: {} };
"""


def _run(body):
    code = STUBS + "\n".join(js_fn(n) for n in ("plStartDxOn", "plStartDx", "plStartSteps", "plStartList", "plStartPrev")) \
        + "\n(async () => {" + body + "})();"
    r = subprocess.run(node_e(code), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class StartChecklist(unittest.TestCase):
    def test_dx_on(self):
        r = _run("console.log(JSON.stringify([plStartDxOn({ok: true, sidereus: {Stop: ['x']}, plugins: []}),"
                 " plStartDxOn({ok: true, sidereus: {}, plugins: [{name: 'sidereus', on: true}]}),"
                 " plStartDxOn({ok: true, sidereus: {}, plugins: [{name: 'sidereus', on: false}, {name: 'other'}]}),"
                 " plStartDxOn({ok: true})]));")
        self.assertEqual(r, [True, True, False, None])   # bare reply (demo) = unknown, not «not connected»

    def test_r1_no_project_shows_four_steps(self):
        r = _run("PLST_DX = {on: false}; const h = plStartList(); console.log(JSON.stringify([h, LS]));")
        h, ls = r
        for s in ("Claude Code connected", "Project added", "First pipeline", "Gate red-checked", "data-plsthide"):
            self.assertIn(s, h)
        self.assertEqual(h.count("<li"), 4)
        self.assertNotIn("plsti on", h)
        self.assertEqual(ls, {})

    def test_steps_from_data(self):
        r = _run("const pj = {ok: true, projects: [{path: '/a', n: 1}, {path: '/s', n: 3, self_only: true}]};"
                 "const a = plStartSteps(true, pj, {'/a': {ok: true, pipelines: [{name: 'x', red: 0}]}}).map(s => s.done);"
                 "const b = plStartSteps(true, pj, {'/a': {ok: true, pipelines: [{name: 'x', red: 2}]}}).map(s => s.done);"
                 "const c = plStartSteps(true, pj, {'/a': {ok: true, pipelines: [{name: 'x'}]}}).map(s => s.done);"
                 "const d = plStartSteps(null, {ok: true, projects: [{path: '/s', n: 3, self_only: true}]}, {}).map(s => s.done);"
                 "const e = plStartSteps(false, null, {}).map(s => s.done);"
                 "const f = plStartSteps(true, pj, {'/a': {ok: true, pipelines: [{name: 'x', ok: true, red: 0}, {name: 'bad', ok: false}]}}).map(s => s.done);"
                 "console.log(JSON.stringify([a, b, c, d, e, f]));")
        a, b, c, d, e, f = r
        self.assertEqual(f, [True, True, True, False])     # invalid pipeline file does not make the step unknown
        self.assertEqual(a, [True, True, True, False])
        self.assertEqual(b, [True, True, True, True])
        self.assertEqual(c[3], None)                       # server without `red`: unknown, not 0
        self.assertEqual(d, [None, False, False, False])   # built-in sample project is not «added»
        self.assertEqual(e, [False, None, None, None])

    def test_unknown_hides_and_diag_fetched_once(self):
        r = _run("DX_REPLY = new Promise(() => {}); const a = plStartList(); const b = plStartList();"
                 "console.log(JSON.stringify([a, b, GETS]));")
        self.assertEqual(r, ["", "", ["/api/diag"]])

    def test_diag_off_is_not_done_still_shown(self):
        r = _run("FEATS.diag = false; const h = plStartList(); console.log(JSON.stringify([h.indexOf('plst') >= 0, GETS]));")
        self.assertEqual(r, [True, []])

    def test_r2_all_done_sets_pref_and_hide(self):
        r = _run("PLST_DX = {on: true}; PLS.proj = '/a'; PLS.projs = {ok: true, projects: [{path: '/a', n: 1}]};"
                 "PLS.data = {'/a': {ok: true, pipelines: [{name: 'x', red: 1}]}};"
                 "const a = plStartList(); const ls = Object.assign({}, LS);"
                 "PLS.data['/a'].pipelines[0].red = 0; const b = plStartList();"
                 "console.log(JSON.stringify([a, ls, b]));")
        a, ls, b = r
        self.assertEqual(a, "")
        self.assertEqual(ls, {"sidereus.plStartDone": "1"})
        self.assertEqual(b, "")                            # stays gone (reload reads the same pref)

    def test_pref_key_allowed_by_server(self):
        import re
        from tests._load import sidereus
        self.assertTrue(sidereus("ui_prefs").KEY_RE.match("sidereus.plStartDone"))
        self.assertIsNotNone(re.search(r"^const PLST_KEY = 'sidereus\.plStartDone';$", js_all(), re.M))


if __name__ == "__main__":
    unittest.main()
