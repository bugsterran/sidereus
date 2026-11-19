"""The two former window.prompt() sites ask through the shared dialog (08c uiPrompt).
R1: «Saved views» «Save» (vwSaveRun) saves the trimmed name capped at VW_NAME_MAX; null or blank writes nothing.
R2: timeline range «Custom…» (tlCustomHours) applies 0.5-168 rounded to 0.1; cancel, empty or non-number restores the select."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

# uiPrompt is a stub that records its arguments and resolves the queued answer.
STUB = r"""
function T(s){ return s; }
const CALLS = []; let ANS = null;
async function uiPrompt(title, o){ CALLS.push([title, o]); return ANS; }
"""

VIEWS = r"""
let vwOpen = true, STORE = [], WRITES = 0; const NOTES = [];
function vwLoad(){ return STORE.slice(); }
function vwStore(a){ STORE = a; WRITES++; }
function vwSnap(){ return {f: 1}; }
function vwPaint(){}
function note(s){ NOTES.push(s); }
async function uiConfirm(){ return true; }
"""

TL = r"""
let tlHours = 6, LS = [], LOADS = [], LIVE = null;
function lsSet(k, v){ LS.push([k, v]); }
function loadTl(f){ LOADS.push(f); }
const document = {getElementById: id => id === 'tlselh' ? LIVE : null};
"""


def _node(js):
    r = subprocess.run(node_e("(async () => { const R = {};\n" + js + "\nprocess.stdout.write(JSON.stringify(R)); })()"
                              ".catch(e => { console.error(e.stack); process.exit(1); });"),
                       capture_output=True, text=True, timeout=30, encoding="utf-8")
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SavedViewsPrompt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        consts = re.search(r"^const VW_KEY\b.*$", js_all(), re.M).group(0)
        cls.R = _node(consts + STUB + VIEWS + js_fn("vwSaveRun") + r"""
const run = async a => { ANS = a; STORE = []; WRITES = 0; await vwSaveRun(); return {w: WRITES, names: STORE.map(x => x.n)}; };
R.trim = await run('  a  ');
R.none = [await run(null), await run(''), await run('   ')];
R.long = await run('x'.repeat(70));
R.args = CALLS[0]; R.max = VW_NAME_MAX;
""")

    def test_r1_uses_ui_prompt_with_cap(self):
        self.assertNotRegex(js_fn("vwSaveRun"), r"(?<![\w$.])prompt\(")
        self.assertEqual(self.R["args"], ["Name for the current filter combination?", {"ok": "Save", "maxlength": self.R["max"]}])

    def test_r1_saves_trimmed_name(self):
        self.assertEqual(self.R["trim"], {"w": 1, "names": ["a"]})
        self.assertEqual(self.R["long"], {"w": 1, "names": ["x" * self.R["max"]]})

    def test_r1_cancel_or_blank_writes_nothing(self):
        self.assertEqual(self.R["none"], [{"w": 0, "names": []}] * 3)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TimelineCustomHours(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = _node(STUB + TL + js_fn("tlCustomHours") + r"""
const run = async (a, live) => { ANS = a; tlHours = 6; LS = []; LOADS = []; const sh = {value: 'custom'};
  LIVE = live ? {value: 'custom'} : null;
  await tlCustomHours(sh); return {h: tlHours, ls: LS, loads: LOADS, sh: sh.value, live: LIVE && LIVE.value}; };
R.ok = [await run('3.14'), await run('999'), await run('0.1')];
R.bad = [await run(null), await run(''), await run('x')];
R.detached = await run(null, true);
R.args = CALLS[0];
""")

    def test_r2_uses_ui_prompt_prefilled(self):
        self.assertNotRegex(js_fn("tlCustomHours"), r"(?<![\w$.])prompt\(")
        self.assertEqual(self.R["args"], ["How many hours to show? (0.5 - 168)", {"value": "6", "ok": "Apply", "inputmode": "decimal"}])

    def test_r2_clamps_and_rounds(self):
        self.assertEqual([(o["h"], o["ls"], o["loads"]) for o in self.R["ok"]],
                         [(3.1, [["mbTlHours", 3.1]], [True]), (168, [["mbTlHours", 168]], [True]),
                          (0.5, [["mbTlHours", 0.5]], [True])])

    def test_r2_cancel_restores_select_and_changes_nothing(self):
        self.assertEqual(self.R["bad"], [{"h": 6, "ls": [], "loads": [], "sh": "6", "live": None}] * 3)

    def test_r2_revert_finds_repainted_select(self):
        self.assertEqual(self.R["detached"], {"h": 6, "ls": [], "loads": [], "sh": "custom", "live": "6"})


if __name__ == "__main__":
    unittest.main()
