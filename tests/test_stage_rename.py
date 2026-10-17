"""Renamed recommended stage title (old -> new): every copy of the map agrees, and legacy files, tags and stored runs
still match under the new title. Repo sources and tmp dirs only."""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from tests._load import sidereus, js_fn
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("pl_flow_rename", os.path.join(ROOT, "hooks", "pl_flow.py"))
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)
OLD, NEW = "최종 검증", "재검증"


def _legacy_pipe():
    return {"v": 1, "name": "demo", "title": "d", "defaults": {"model": "inherit", "retry": 0}, "stages": [
        {"title": "구현", "agent": "general-purpose"},
        {"title": "리뷰", "agent": "general-purpose", "onFail": {"goto": "구현", "max": 1, "then": OLD}},
        {"title": OLD, "agent": "general-purpose", "onlyOnJump": True}]}


class Copies(unittest.TestCase):
    def test_maps_equal(self):
        want = {OLD: NEW}
        self.assertEqual(sidereus("pipeline_schema").RENAMED, want)
        self.assertEqual(sidereus("pl_runs").RENAMED, want)
        self.assertEqual(H.RENAMED, want)
        with open(os.path.join(ROOT, ".claude", "workflows", "pipeline.js"), encoding="utf-8") as f:
            src = f.read()
        m = re.search(r"^const RENAMED = (\{[^}]*\})", src, re.M)
        self.assertEqual(json.loads(m.group(1).replace("'", '"')), want)
        out = subprocess.run(node_e(js_fn("plTk") + "\nconsole.log(JSON.stringify([plTk(%s), plTk('x'), plTk('constructor'), plTk(null)]))"
                              % json.dumps(OLD)), capture_output=True, text=True, check=True, encoding="utf-8").stdout
        self.assertEqual(json.loads(out), [NEW, "x", "constructor", None])

    def test_new_title_is_recommended(self):
        S = sidereus("pipeline_schema")
        self.assertIn(NEW, S.STAGE_TITLES)
        self.assertNotIn(OLD, S.STAGE_TITLES)


class Legacy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_schema_accepts_legacy_file(self):
        self.assertEqual(sidereus("pipeline_schema").validate(_legacy_pipe(), "demo"), [])   # no task needed: maps to a recommended title

    def test_hook_reads_legacy_file_under_new_title(self):
        d = os.path.join(self.tmp, ".claude", "pipelines")
        os.makedirs(d)
        with open(os.path.join(d, "demo.json"), "w", encoding="utf-8") as f:
            json.dump(_legacy_pipe(), f, ensure_ascii=False)
        st, _ = H._stages(self.tmp, "demo")
        self.assertEqual([s["title"] for s in st], ["구현", "리뷰", NEW])
        self.assertEqual(st[1]["onFail"], {"goto": "구현", "max": 1, "then": NEW})
        self.assertEqual(H._ren(OLD), NEW)

    def test_pl_runs_maps_stored_old_keys(self):
        PR = sidereus("pl_runs")
        raw = {"demo": {"cur": OLD, "t0": 100.0, "t1": 200.0, "st": {"리뷰": {"s": "done", "t0": 100, "t1": 150, "n": 1},
                                                                       OLD: {"s": "run", "t0": 150, "t1": 200, "n": 1}},
                        "lb": [{"f": OLD, "g": "구현", "n": 1, "t": 160}]}}
        r = PR.pl_runs_of("sess-0001", 300.0, _raw=raw)[0]
        self.assertEqual((r["cur"], sorted(r["st"]), r["lb"][0]["f"]), (NEW, sorted(["리뷰", NEW]), NEW))


class CanvasRename(unittest.TestCase):
    """48d plRetitle: the editor model renames the node and loop-back «then»; bad names leave it as it was."""
    def _run(self, val):
        js = "\n".join(["const T = s => s, PLS = {msg: ''}; let touched = 0; const plTouch = () => touched++, plPaint = () => {};",
                        js_fn("plgNode"), js_fn("plTitleErr"), js_fn("plRetitle"),
                        "const G = {nodes: [{id: 'a', title: '리뷰'}, {id: 'b', title: '재검증'}], loops: [{from: 'a', to: 'a', max: 1, then: '재검증'}]};",
                        "plRetitle({G, sel: {k: 'n', id: 'b'}}, %s);" % json.dumps(val),
                        "console.log(JSON.stringify([G.nodes.map(n => n.title), G.loops[0].then, PLS.msg, touched]));"])
        return json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True, encoding="utf-8").stdout)

    def test_rename_follows_then(self):
        self.assertEqual(self._run("  Again  "), [["리뷰", "Again"], "Again", "", 1])

    def test_refusals(self):
        for v, msg in (("", "Stage name is empty"), ("x" * 25, "Stage name: at most 24 characters"), ("a/b", "Stage name cannot contain / ] |"),
                       ("a|b", "Stage name cannot contain / ] |"), ("리뷰", "A stage with that name exists: 리뷰")):
            self.assertEqual(self._run(v), [["리뷰", "재검증"], "재검증", msg, 0], v)


if __name__ == "__main__":
    unittest.main()
