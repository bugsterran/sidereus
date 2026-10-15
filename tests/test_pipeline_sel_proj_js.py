"""«Pipelines» selection (web/js/48-pipeline.js plSelBind): PLS.sel is remembered per project, so a pipeline picked in
one project does not open as a borrowed read-only view in a project that has none; the legacy single key is ignored."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

ARCH = "{name: 'arch-map', from: '/u/a', ok: true}"


def run(body, store=None):
    src = ("const STORE = " + json.dumps(store or {}) + ";\n"
           "function lsJson(k, d){ try{ const v = JSON.parse(STORE[k] || 'null'); return v === null ? d : v; }catch(e){ return d; } }\n"
           "function lsSetJson(k, o){ STORE[k] = JSON.stringify(o); }\n"
           "const PLS = {proj: '', data: {}, std: ''};\n"
           + js_fn("plSelMap") + "\n" + js_fn("plSelBind") + "\nplSelBind(PLS);\n"
           + js_fn("plBorrows") + "\n" + js_fn("plBorrowOf") + "\n" + js_fn("plCur") + "\n"
           "PLS.data['/u/a'] = {ok: true, pipelines: [" + ARCH + ", {name: 'other', ok: true}], borrowed: []};\n"
           "PLS.data['/u/b'] = {ok: true, pipelines: [], suggest: [], borrowed: [" + ARCH + "]};\n"
           "const R = {};\n" + body + "\nR.store = STORE;\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PipelineSelPerProject(unittest.TestCase):
    def test_switch_to_empty_project_shows_its_own_view(self):
        r = run("PLS.proj = '/u/a'; PLS.sel = 'arch-map'; R.a = plCur().name;"
                " PLS.proj = '/u/b'; R.bsel = PLS.sel; R.b = plCur();"
                " PLS.proj = '/u/a'; R.back = PLS.sel; R.a2 = plCur().name;")
        self.assertEqual(r["a"], "arch-map")
        self.assertEqual(r["bsel"], "")
        self.assertIsNone(r["b"])   # no borrowed (read-only) row: the empty / «New pipeline» view
        self.assertEqual((r["back"], r["a2"]), ("arch-map", "arch-map"))

    def test_explicit_pick_still_opens_borrowed_view(self):
        r = run("PLS.proj = '/u/b'; PLS.sel = 'arch-map'; const p = plCur(); R.from = p && p.from;")
        self.assertEqual(r["from"], "/u/a")

    def test_persisted_and_reloaded(self):
        r = run("PLS.proj = '/u/a'; PLS.sel = 'other';")
        self.assertEqual(json.loads(r["store"]["sidereus.plselp"]), {"/u/a": "other"})
        r2 = run("PLS.proj = '/u/a'; R.sel = PLS.sel; PLS.sel = ''; R.after = STORE['sidereus.plselp'];", r["store"])
        self.assertEqual((r2["sel"], r2["after"]), ("other", "{}"))

    def test_legacy_and_bad_values_ignored(self):
        r = run("PLS.proj = '/u/b'; R.sel = PLS.sel; R.b = plCur();",
                {"sidereus.plsel": "arch-map", "sidereus.plselp": "not json"})
        self.assertEqual(r["sel"], "")
        self.assertIsNone(r["b"])
        r2 = run("PLS.proj = '/u/a'; R.sel = PLS.sel;", {"sidereus.plselp": "[\"arch-map\"]"})
        self.assertEqual(r2["sel"], "")

    def test_unknown_remembered_name_falls_back_to_first(self):
        r = run("PLS.proj = '/u/a'; PLS.sel = 'gone'; R.a = plCur().name;")
        self.assertEqual(r["a"], "arch-map")


if __name__ == "__main__":
    unittest.main()
