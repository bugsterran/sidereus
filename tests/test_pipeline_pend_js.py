"""«Pipelines» jump before the project list loads (plOvPick + plLoadProjs): the picked project survives the list load."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

PRE = "\n".join([
    "const LS = {}; function lsSet(k, v){ LS[k] = v; } let PLVIEW = 'harness', PLAG = true, PLNEW = null, PAINTS = 0; function plPaint(){ PAINTS++; }",
    "let LIST = {ok: true, projects: [{path: '/own', n: 2}]}; async function getJSON(){ return LIST; }",
    "const PLS = {projs: null, proj: '/own', data: {}, busy: {}, sel: ''};",
])


def run(body):   # js_fn only finds plain `function`, so the async loader is cut out here
    js = PRE + "\n" + js_fn("plOvPick") + "\n" + re.search(r"^async function plLoadProjs\(.*?^}$", js_all(), re.M | re.S).group(0) + "\n(async () => {" + body + "})();"
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PipelinePendingPick(unittest.TestCase):
    def test_jump_before_list_keeps_project(self):
        r = run("plOvPick('/borrow', 'bugfix'); await plLoadProjs();"
                "console.log(JSON.stringify([PLS.proj, PLS.sel, PLS.pend, PLVIEW, PLAG]));")
        self.assertEqual(r, ["/borrow", "bugfix", "", "pipe", False])

    def test_unlisted_remembered_project_still_resets(self):
        r = run("PLS.proj = '/gone'; await plLoadProjs(); console.log(JSON.stringify([PLS.proj]));")
        self.assertEqual(r, ["/own"])

    def test_pick_after_load_sets_no_pending(self):
        r = run("await plLoadProjs(); plOvPick('/borrow', 'x'); console.log(JSON.stringify([PLS.proj, PLS.pend || '']));")
        self.assertEqual(r, ["/borrow", ""])


if __name__ == "__main__":
    unittest.main()
