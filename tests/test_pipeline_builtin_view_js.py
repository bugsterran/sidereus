"""Builtin pipeline run shown on its target (48b plOverview, 48h plBorrowLv): the Running row lists the borrowed row's
stages with states, and the borrowed canvas picks the live run whose proj is the target over an ended legacy run
recorded under the Sidereus repo. Pure functions under node with stubs; no live files."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

PRE = """
const ARCH_PL = 'arch-map'; const PLS = {data: {}};
const PL_OS = ['run', 'done', 'fail', 'back', 'skip', 'hold'];
function T(s){ return s; } function plTk(t){ return t; } function plWhy(){ return ''; } function plPsOk(){ return []; }
function plAgRun(){ return null; } function plAgSteps(){ return []; } function plLoad(){} function plCur(){ return null; }
function plOrphHtml(){ return ''; } function plOvHtml(rows){ return JSON.stringify(rows.map(r => [r.proj, r.name, r.stages])); }
function plMem(){ return {}; } function plKnown(){ const k = {}; Object.defineProperty(k, 'bi', {value: new Set(['security-fix'])}); return k; }
function plLiveProjs(){ return {'/w/admin': ['security-fix']}; }
const SIDE = '/w/side', ADMIN = '/w/admin';
const B = {name: 'security-fix', ok: true, from: SIDE, builtin: true, stages: [{title: 'Fix'}, {title: 'Review'}]};
const LIVE = {name: 'security-fix', proj: ADMIN, t0: 1, t1: 9, stages: {Fix: {o: 'done', t0: 1, t1: 5}, Review: {o: 'run', t0: 6}}};
const OLD = {name: 'security-fix', proj: SIDE, t0: 1, t1: 20, end: 20, stages: {Fix: {o: 'done', t0: 1, t1: 20}}};
var SESS = [{sid: 'old', cwd: ADMIN, plrun: [OLD]}, {sid: 'new', cwd: SIDE, plrun: [LIVE]}];
PLS.data[ADMIN] = {ok: true, pipelines: [], borrowed: [B]};
"""
FNS = ("plBi", "plPrLive", "plAgLab", "plAgLabs", "plPrLt", "plPrLv", "plOvRow", "plBorrows", "plBorrowOf", "plBorrowLv", "plOverview")


def run(body):
    src = PRE + "\n".join(js_fn(n) for n in FNS) + "\n" + body
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PipelineBuiltinView(unittest.TestCase):
    def test_running_row_lists_builtin_stages(self):
        rows = run("console.log(plOverview());")
        self.assertEqual(rows, [["/w/admin", "security-fix", [{"t": "Fix", "st": "done", "rb": 0}, {"t": "Review", "st": "run", "rb": 0}]]])

    def test_borrow_lv_picks_live_target_run(self):
        r = run("const lv = plBorrowLv(ADMIN, B); console.log(JSON.stringify([lv.sid, lv.run.run]));")
        self.assertEqual(r, ["new", True])

    def test_borrow_lv_open_between_stages_beats_newer_ended(self):
        r = run("const GAP = {name: 'security-fix', proj: ADMIN, t0: 1, t1: 5, end: 0, stages: {Fix: {o: 'done', t0: 1, t1: 5}}};"
                "const ENDED = {name: 'security-fix', proj: ADMIN, t0: 1, t1: 30, end: 30, stages: {Fix: {o: 'done', t0: 1, t1: 30}}};"
                "SESS = [{sid: 'a', cwd: SIDE, plrun: [GAP]}, {sid: 'b', cwd: SIDE, plrun: [ENDED]}];"
                "console.log(JSON.stringify(plBorrowLv(ADMIN, B).sid));")
        self.assertEqual(r, "a")

    def test_arch_map_keeps_cwd_rule(self):
        r = run("const A = {name: 'arch-map', ok: true, from: SIDE, builtin: true, stages: [{title: 'Fix'}]};"
                "SESS = [{sid: 'far', cwd: SIDE, plrun: [{name: 'arch-map', proj: SIDE, t1: 3, stages: {Fix: {o: 'run'}}}]}];"
                "console.log(JSON.stringify(plBorrowLv(ADMIN, A)));")
        self.assertIsNone(r)


if __name__ == "__main__":
    unittest.main()
