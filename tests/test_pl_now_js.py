"""«Pipelines» «Working now» strip (48j plNowHtml/plNowGo, R2) and the empty-project start buttons (48e plTplPick, R3).
Pure functions under node with stubs; no live files."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import ROOT, js_fn
from tests._node import node_e

PRE = """
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const T = s => s;
const CSS = { escape: s => String(s).replace(/(["\\\\/ ])/g, '\\\\$1') };
let SESS = [], PLNEW = null, PLDRAFT = null, PLSTD = false, GO = [], MV = [];
function aiLogo(p){ return '<i class="ailg ailg-' + esc(p || 'cc') + '"></i>'; }
"""


def _src(name):
    with open(os.path.join(ROOT, "web", "js", name), encoding="utf-8") as f:
        return f.read()


def _const(name, file):
    s = _src(file)
    i = s.index("const " + name)
    return s[i:s.index(";", i) + 1]


NOW = _const("PLNOW_MAX", "48j-pipeline-now.js") + "\n" + "\n".join(
    js_fn(n) for n in ("sessPlChip", "plNowLive", "plNowHtml", "plNowGo")) + "\n"


def run(body):
    r = subprocess.run(node_e(PRE + body), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PlNow(unittest.TestCase):
    def test_r2_live_sessions_only_with_logo_project_chip(self):
        h = run(NOW + "console.log(JSON.stringify(plNowHtml(["
                "{state: 'tool', cwd: '/a', plat: 'cx', project: 'alpha', plrun: [{name: 'chg', cur: 'Implement'}]},"
                "{state: 'wait', cwd: '/b', plat: 'cc', project: 'beta', plNone: {cat: 'docs'}},"
                "{state: 'think', cwd: '/c', project: 'gamma', plNone: {u: 1}},"
                "{state: 'done', cwd: '/d', project: 'delta'}, {state: 'abort', cwd: '/e', project: 'eps'},"
                "{state: 'gone', cwd: '/f', plat: 'cx', project: 'zeta'}, {state: 'tool', cwd: '/a', plat: 'cx', project: 'alpha'}])));")
        self.assertEqual(re.findall(r'data-pncwd="([^"]+)"', h), ["/a", "/b", "/c"])   # done/abort/gone dropped, /a+cx once
        self.assertIn("ailg-cx", h)
        self.assertIn(">alpha<", h)
        self.assertIn("chg", h)
        self.assertIn(" · Implement", h)
        self.assertIn("No pipeline · docs", h)
        self.assertIn("Undeclared", h)
        self.assertIn("Working now", h)
        self.assertEqual(h.count('class=plnow>'), 1)                          # one line

    def test_r2_targ_never_rendered(self):
        h = run(NOW + "console.log(JSON.stringify(plNowHtml([{state: 'tool', cwd: '/a', project: 'p',"
                " targ: 'SECRET-TASK', tool: 'Bash', prompt: 'SECRET-PROMPT'}])));")
        self.assertNotIn("SECRET", h)

    def test_r2_empty_note_and_overflow(self):
        e, m = run(NOW + "const L = n => Array.from({length: n}, (_, i) => ({state: 'tool', cwd: '/' + i, project: 'p' + i}));"
                   "console.log(JSON.stringify([plNowHtml([]), plNowHtml(L(PLNOW_MAX + 3))]));")
        self.assertIn("No sessions working now", e)
        self.assertIn('class=plnow>', e)                                      # strip kept: fixed height, no shift
        self.assertEqual(m.count("data-pncwd"), 4)
        self.assertIn(">+3</span>", m)

    def test_r2_click_goes_to_timeline_row(self):
        a, b = run(NOW + "function mvGo(v, s){ GO.push([v, s]); }"
                   "plNowGo('/x \"y', 'cx'); console.log(JSON.stringify([GO, MV]));")
        self.assertEqual(a, [["time", '.tlr.tlrs[data-tlc="\\/x\\ \\"y"][data-tlp="cx"]']])
        self.assertEqual(b, [])

    def test_r2_claude_maps_to_empty_tlp(self):
        r = run(NOW + "function mvGo(v, s){ GO.push(s); } plNowGo('/a', 'cc'); plNowGo('/a', ''); console.log(JSON.stringify(GO));")
        self.assertEqual(r, ['.tlr.tlrs[data-tlc="\\/a"][data-tlp=""]'] * 2)    # Claude timeline rows carry data-tlp=""

    def test_r2_click_fallback_without_mvgo(self):
        r = run(NOW + "function setMainView(v){ MV.push(v); } plNowGo('/x', ''); console.log(JSON.stringify(MV));")
        self.assertEqual(r, ["time"])

    def test_r2_listener_wired(self):
        s = _src("48j-pipeline-now.js")
        self.assertIn("closest('.plw [data-pncwd]')", s)
        self.assertIn("plNowHtml() + plMainBody()", _src("48-pipeline.js"))

    def test_r3_start_buttons_first(self):
        h = run(_const("PL_TPLS", "48e-pipeline-new.js") + "\n"
                + "\n".join(js_fn(n) for n in ("plNewDis", "plStartBtns", "plTplPick"))
                + "\nconsole.log(JSON.stringify(plTplPick()));")
        btns = re.findall(r"<button[^>]*>", h)
        self.assertIn("data-plstd", btns[0])
        self.assertIn("data-pldnew", btns[1])
        for b in btns[:2]:
            self.assertIn('plsv', b)
        self.assertIn("data-pltpl", btns[2])
        self.assertLess(h.index("Or start from:"), h.index("data-pltpl"))
        self.assertNotIn("Standard templates", h)                             # duplicate dropped
        self.assertEqual(h.count("data-plstd"), 1)


if __name__ == "__main__":
    unittest.main()
