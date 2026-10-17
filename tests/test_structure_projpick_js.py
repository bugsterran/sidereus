"""Structure header project picker (80 paintStruct → 08b ppComboHtml): the same combobox as Pipelines, no chip row.
paintStruct runs with stubs until the toolbar html reaches tbSlot, which throws it back."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

PRE = r"""
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const T = s => s, PPC = {}; let PPS = null, strSessSig = '', strBrH = '', strMs = 0;
const mainView = 'struct', SESS = [], PLS = {}, strOn = ['/w/a'], strLoad = {'/w/a|0': 1};
const document = { getElementById(id){ return id === 'feed' ? {} : null; } };
function strPickDef(){} function strSessKey(){ return ''; } function plMem(){ return {}; } function plKnown(){ return {}; }
function plLiveProjs(){ return {'/w/a': [1, 2]}; } function plLiveDot(n){ return '<i class=mvdot data-n=' + n + '></i>'; }
function strCk(p){ return p + '|0'; } function strBrHtml(){ return ''; } function strPickProj(){}
function strProjList(){ return [{p: '/w/a', name: 'a', open: 1, ss: ['s1', 's2']}, {p: '/w/b', name: 'b', open: 0, ss: []}]; }
function tbSlot(k, h){ throw {h: h}; }
"""


def run(body):
    src = (PRE + js_fn("ppComboHtml") + "\n" + js_fn("paintStruct") + "\nconst R = {};\n" + body
           + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class StructProjPick(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run("try { paintStruct(); } catch(e){ if(!e.h) throw e; R.h = e.h; }"
                    "PPS = {cfg: PPC.str}; R.note = [PPC.str.note(strProjList()[0]), PPC.str.note(strProjList()[1])];")

    def test_combobox_not_chips(self):
        h = self.R["h"]
        self.assertIn('<span class="strps tbg"><b>Project</b><button type=button class="strp ppbtn ppcombo" data-ppk="str"', h)
        for gone in ("ppcs", "data-sp=", "More ▾", "strld"):
            self.assertNotIn(gone, h)

    def test_button_badge_and_tooltip(self):
        h = self.R["h"]
        self.assertIn('<span class=ppcn>a</span><i class=mvdot data-n=2></i> … ▾</button>', h)
        self.assertNotIn("strpc", h.split("</button>")[0])   # session count stays off the button
        self.assertIn('title="/w/a\nSessions 2: s1, s2 — loading"', h)

    def test_popover_row_note(self):
        self.assertEqual(self.R["note"], [" <small class=strpc>2</small>", ""])


if __name__ == "__main__":
    unittest.main()
