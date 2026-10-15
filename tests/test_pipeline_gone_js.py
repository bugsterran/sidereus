"""«Pipelines» chips (web/js/48-pipeline.js plChips): a project whose folder was deleted (state `projGone`) loses
its chip even when the fetched project list still has it, and a selected one falls back to the first listed project."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


def run(body):
    src = ("let SESS = [], PROJ_GONE = new Set(), PLS = {proj: '', projs: null}, CFG = null;\n"
           "const esc = s => String(s), T = s => s;\n"
           "function plLiveProjs(){ return {}; } function plMem(){ return {}; } function plKnown(){ return null; }\n"
           "function strShort(p){ return p.split('/').pop(); } function strProjList(){ return []; }\n"
           "function plLiveDot(){ return ''; } function plAddForm(){ return ''; } function plPickProj(){} function plBrOpen(){}\n"
           "function ppChipsHtml(cfg){ CFG = cfg; return ''; }\n"
           + js_fn("plChips") + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PipelineGone(unittest.TestCase):
    def test_registered_gone_project_dropped_and_selection_falls_back(self):
        r = run("PLS.projs = {ok: true, projects: [{path: '/u/wt', n: 2}, {path: '/u/keep', n: 1}], added: []};"
                " PLS.proj = '/u/wt'; PROJ_GONE = new Set(['/u/wt']); plChips();"
                " R.items = CFG.items.map(e => e.p); R.proj = PLS.proj;")
        self.assertEqual(r["items"], ["/u/keep"])
        self.assertEqual(r["proj"], "/u/keep")

    def test_nothing_left_clears_selection(self):
        r = run("PLS.projs = {ok: true, projects: [{path: '/u/wt', n: 2}], added: []};"
                " PLS.proj = '/u/wt'; PROJ_GONE = new Set(['/u/wt']); plChips(); R.items = CFG.items.length; R.proj = PLS.proj;")
        self.assertEqual((r["items"], r["proj"]), (0, ""))

    def test_existing_selection_kept(self):
        r = run("PLS.projs = {ok: true, projects: [{path: '/u/a', n: 1}, {path: '/u/b', n: 1}], added: []};"
                " PLS.proj = '/u/b'; plChips(); R.proj = PLS.proj; R.items = CFG.items.map(e => e.p);")
        self.assertEqual(r["proj"], "/u/b")
        self.assertEqual(r["items"], ["/u/a", "/u/b"])


if __name__ == "__main__":
    unittest.main()
