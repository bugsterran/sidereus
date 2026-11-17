"""Branches empty state (web/js/88-branch.js loadBr/brStatusHtml): no repository renders a neutral note,
not the red `.cwerr` error; a real fetch error still renders `.cwerr`; the empty flag is gone once a repo loads.
No timers, no network (fetch is stubbed)."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

BASE = r"""
let mainView = 'br', STATE_IN = true, SESS = [], BR = null, brRepo = '', brBusy = 0, brRetry = 1, brWaitN = 0;
const brBad = new Set(), BR_ERRS = {};
const T = s => s, TV = j => j.msg, esc = s => String(s).replace(/</g, '&lt;');
function tabGet(k, d){ return d; } function tabDel(k){}
function paintBr(){}
let FETCH = null;
function fetch(url){ return Promise.resolve(FETCH); }
"""


def run(body):
    fns = ["brRepos", "brForget", "loadBr", "brMsg", "brHeadHtml", "brStatusHtml"]
    src = BASE + "\n".join(js_fn(n) for n in fns) + "\nconst R = {};\n(async () => {\n" + body + \
        "\nprocess.stdout.write(JSON.stringify(R));\n})();"
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class BrEmpty(unittest.TestCase):
    def test_no_repo_is_neutral_note(self):
        R = run(r"""
loadBr(false); R.empty = !!BR.empty; R.html = brStatusHtml();
""")
        self.assertTrue(R["empty"])
        self.assertNotIn("cwerr", R["html"])
        self.assertIn("hidnote", R["html"])
        self.assertIn("No git repository in the session list yet", R["html"])

    def test_fetch_error_keeps_cwerr_and_clears_empty(self):
        R = run(r"""
loadBr(false); R.was = !!BR.empty;
SESS = [{cwd: '/p/r', branch: 'main', repos: ['/p/r']}];
FETCH = { status: 500, json: () => Promise.resolve({ ok: false, err: 'boom' }) };
loadBr(false);
await new Promise(res => setTimeout(res, 0));
R.empty = !!BR.empty; R.html = brStatusHtml();
""")
        self.assertTrue(R["was"])
        self.assertFalse(R["empty"])
        self.assertIn("tlhd cwerr", R["html"])
        self.assertIn("boom", R["html"])


if __name__ == "__main__":
    unittest.main()
