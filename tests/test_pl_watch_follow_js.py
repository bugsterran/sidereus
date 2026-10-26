"""«Pipelines» Watch: the selection follows the running stage (48k plWatchFollow, 48d plCanvas call, R1-R4).
Pure functions under node with stubs; no live files."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import ROOT, js_fn
from tests._node import node_e

PRE = """
let PLNOW_SEEN = null, PLMODE = 'watch', PAINT = 0, FIT = 0;
const PLS = { runSel: null };
function plPaint(){ PAINT++; } function plFit(){ FIT++; }
const G = {nodes: [{id: 'a', title: 'A'}, {id: 'b', title: 'B'}, {id: 'c', title: 'C'}, {id: 'd', title: 'D'}]};
const lt = o => { const r = {}; Object.keys(o).forEach(k => r[k] = {st: o[k]}); return r; };
const pick = (E, id) => { E.sel = {k: 'n', id}; };
"""


def _fn():
    return js_fn("plWRunKey") + "\n" + js_fn("plWatchFollow")


def run(body):
    r = subprocess.run(node_e(PRE + _fn() + "\n" + body), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PlWatchFollow(unittest.TestCase):
    def test_r1_follows_next_running_stage_twice(self):
        o = run("const E = {G}; pick(E, 'a'); plWatchFollow(E, lt({A: 'run', B: 'wait'}));"
                "plWatchFollow(E, lt({A: 'done', B: 'run'})); const s1 = E.sel.id;"
                "plWatchFollow(E, lt({A: 'done', B: 'done', C: 'run'})); console.log(JSON.stringify([s1, E.sel.id]));")
        self.assertEqual(o, ["b", "c"])

    def test_r1_loop_back_counts(self):
        o = run("const E = {G}; pick(E, 'c'); plWatchFollow(E, lt({A: 'done', C: 'run'}));"
                "plWatchFollow(E, lt({A: 'run', C: 'fail'})); console.log(JSON.stringify(E.sel.id));")
        self.assertEqual(o, "a")

    def test_r1_new_run_never_followed(self):
        o = run("const k1 = plWRunKey({sid: 's', pr: {rid: 1}}), k2 = plWRunKey({sid: 's', pr: {rid: 2}});"
                "const E = {G}; pick(E, 'd'); plWatchFollow(E, lt({A: 'done', D: 'run'}), k1);"
                "plWatchFollow(E, lt({A: 'done', B: 'done', C: 'done', D: 'done'}), k1); const over = E.wsel.arm;"
                "plWatchFollow(E, lt({A: 'run', B: 'wait', C: 'wait', D: 'wait'}), k2); const a = E.sel.id;"
                "const F = {G}; pick(F, 'd'); plWatchFollow(F, lt({D: 'run'}), k1);"
                "plWatchFollow(F, lt({A: 'run', D: 'wait'}), k2);"
                "console.log(JSON.stringify([over, a, F.sel.id, F.wsel.arm]));")
        self.assertEqual(o, [False, "d", "d", False])   # run over disarms; a new run key disarms too

    def test_r1_gap_keeps_arm(self):
        o = run("const E = {G}; pick(E, 'a'); plWatchFollow(E, lt({A: 'run'}));"
                "plWatchFollow(E, lt({A: 'done', B: 'wait'})); const g = [E.sel.id, E.wsel.arm];"
                "plWatchFollow(E, lt({A: 'done', B: 'run'})); console.log(JSON.stringify(g.concat(E.sel.id)));")
        self.assertEqual(o, ["a", True, "b"])

    def test_r2_two_live_runs_stays(self):
        o = run("PLNOW_SEEN = {r1: {}, r2: {}}; const E = {G}; pick(E, 'a'); plWatchFollow(E, lt({A: 'run'}));"
                "plWatchFollow(E, lt({A: 'done', B: 'run'})); console.log(JSON.stringify(E.sel.id));")
        self.assertEqual(o, "a")

    def test_r3_picked_done_stage_stays(self):
        o = run("const E = {G}; pick(E, 'a'); plWatchFollow(E, lt({A: 'done', B: 'run'}));"
                "plWatchFollow(E, lt({A: 'done', B: 'done', C: 'run'})); console.log(JSON.stringify([E.sel.id, E.wsel.arm]));")
        self.assertEqual(o, ["a", False])

    def test_r3_pick_unjudged_never_armed_later(self):
        o = run("PLNOW_SEEN = {r1: {}, r2: {}}; const E = {G}; pick(E, 'a'); plWatchFollow(E, lt({A: 'run'}));"
                "const w = E.wsel.arm; PLNOW_SEEN = {r1: {}}; plWatchFollow(E, lt({A: 'run'}));"
                "plWatchFollow(E, lt({A: 'done', B: 'run'})); const F = {G}; pick(F, 'a'); plWatchFollow(F, null);"
                "plWatchFollow(F, lt({A: 'run'})); plWatchFollow(F, lt({A: 'done', B: 'run'}));"
                "console.log(JSON.stringify([w, E.sel.id, F.wsel.arm, F.sel.id]));")
        self.assertEqual(o, [False, "a", False, "a"])

    def test_r3_fan_out_stays_and_disarms(self):
        o = run("const E = {G}; pick(E, 'a'); plWatchFollow(E, lt({A: 'run'}));"
                "plWatchFollow(E, lt({A: 'done', B: 'run', C: 'run'})); const f = [E.sel.id, E.wsel.arm];"
                "plWatchFollow(E, lt({A: 'done', B: 'done', C: 'run'})); console.log(JSON.stringify(f.concat(E.sel.id)));")
        self.assertEqual(o, ["a", False, "a"])

    def test_r4_selection_only_no_view_move(self):
        o = run("const E = {G, view: {x: 5, y: 6, z: 0.8}}; pick(E, 'a'); plWatchFollow(E, lt({A: 'run'}));"
                "plWatchFollow(E, lt({A: 'done', B: 'run'}));"
                "console.log(JSON.stringify([E.sel.id, E.view, PAINT, FIT]));")
        self.assertEqual(o, ["b", {"x": 5, "y": 6, "z": 0.8}, 0, 0])

    def test_r4_canvas_calls_only_in_watch(self):
        with open(os.path.join(ROOT, "web/js/48d-pipeline-canvas.js"), encoding="utf-8") as f:
            src = f.read()
        i = src.index("function plCanvas(")
        body = src[i:src.index("\n}", i)]
        self.assertIn("plWatchFor(p) && typeof plWatchFollow === 'function') plWatchFollow(E, lt, plWRunKey(plViewRun(PLS.proj, p.name)))", body)
        self.assertLess(body.index("plWatchFollow(E, lt"), body.index("plNodeHtml("))   # before node HTML reads E.sel

    def test_r4_edit_never_follows(self):
        from tests import test_pl_mode_js as m
        body = (m.MODE + m.CANVAS_STUB + js_fn("plCanvas") + "\nplModeSet('edit', true); E.sel = {k: 'n', id: 'n1'}; E.wsel = {id: 'n1', rk: plWRunKey(plViewRun()), arm: true};"
                "plCanvas(" + m.SAVED + ", D, {A: {st: 'done'}, B: {st: 'run'}}); const e = E.sel.id;"
                "plModeSet('watch', true); plCanvas(" + m.SAVED + ", D, {A: {st: 'done'}, B: {st: 'run'}});"
                "console.log(JSON.stringify([e, E.sel.id]));")
        r = subprocess.run(node_e(m.PRE + body), capture_output=True, text=True, timeout=20, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), ["n1", "n2"])   # Edit untouched; the same call in Watch follows

    def test_past_run_and_non_node_unchanged(self):
        o = run("PLS.runSel = {rid: 1}; const E = {G}; pick(E, 'a'); E.wsel = {id: 'a', arm: true};"
                "plWatchFollow(E, lt({A: 'done', B: 'run'})); const p = E.sel.id; PLS.runSel = null;"
                "E.sel = {k: 'e', id: 'x'}; plWatchFollow(E, lt({B: 'run'}));"
                "console.log(JSON.stringify([p, E.sel.k, E.wsel]));")
        self.assertEqual(o, ["a", "e", None])


if __name__ == "__main__":
    unittest.main()
