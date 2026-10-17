"""Timeline «Changes» session picker (77 tlgSelHtml → 08b ppComboHtml): the shared combobox, an «Auto» first row,
rows carry project · sid · state only, a pick sets tlgSel, and an open popover blocks the chip repaint."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

PRE = r"""
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const T = s => s, PPC = {}; let PPS = null, POP = false, SESS = [], tlgSel = '';
const R = {saved: 0, ticks: 0, paints: 0};
const cpKey = x => 's:' + x.sid, sid8 = s => s.slice(0, 8), stateLbl = s => s === 'busy' ? 'Busy' : '';
function popIsOpen(id){ return POP && id === 'ppop'; } function tlgKeepSave(){ R.saved++; } function tlgTick(){ R.ticks++; }
function tlgChipInner(){ R.paints++; return 'x'; } function setHtml(){ return false; }
var document = {activeElement: null, getElementById: id => id === 'tlgb' ? {} : null};
"""
SESS = [{"sid": "s1aaaaaaaa", "cwd": "/r/a", "project": "a", "ageSec": 5, "state": "busy", "msg": "SECRET"},
        {"sid": "s2bbbbbbbb", "cwd": "/r/b", "project": "b", "ageSec": 90}]


def run(body):
    auto = re.search(r"^const TLG_AUTO = .*$", js_all(), re.M).group(0)
    fns = "\n".join(js_fn(n) for n in ("ppComboHtml", "tlgAge", "tlgName", "tlgSessions", "tlgTarget",
                                        "tlgProj", "tlgNote", "tlgSelHtml", "tlgFocusId", "tlgPaint"))
    src = (PRE + auto + "\n" + fns + "\nSESS = " + json.dumps(SESS) + ";\n" + body
           + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TlgSessPick(unittest.TestCase):
    def test_combobox_not_select(self):
        h = run("R.h = tlgSelHtml(tlgTarget());")["h"]
        self.assertIn('<b>Session</b><button type=button class="strp ppbtn ppcombo" data-ppk="tlgs"', h)
        self.assertIn("<span class=ppcn>a</span><span class=tlgau>auto</span> ▾</button>", h)
        self.assertIn('title="Auto (latest active)\n/r/a · s1aaaaaaaa"', h)
        self.assertNotIn("<select", h)
        self.assertNotIn("<select", js_fn("tlgSelHtml"))

    def test_rows_auto_first_metadata_only(self):
        r = run("const tg = tlgTarget(); tlgSelHtml(tg); PPS = {i: 0, cfg: PPC.tlgs};"
                "R.rows = PPC.tlgs.flat('').map((e, i) => PPC.tlgs.rowHtml(e, i)); R.q = PPC.tlgs.flat('b').map(e => e.p);")
        self.assertEqual(len(r["rows"]), 3)
        self.assertIn("ppcur", r["rows"][0])
        self.assertIn("<span class=cmdkp>Auto (latest active)</span><span class=cmdkc>a · s1aaaaaa · Busy</span>", r["rows"][0])
        self.assertIn('title="/r/b · s2bbbbbbbb"><span class=cmdkp>b</span><span class=cmdkc>s2bbbbbb</span>', r["rows"][2])
        self.assertNotIn("SECRET", "".join(r["rows"]))
        self.assertEqual(r["q"], ["s:s2bbbbbbbb"])

    def test_pick_sets_and_auto_clears(self):
        r = run("tlgSelHtml(tlgTarget()); PPC.tlgs.pick('s:s2bbbbbbbb'); R.a = tlgSel; R.cur = (tlgSelHtml(tlgTarget()), PPC.tlgs.cur);"
                "PPC.tlgs.pick('auto'); R.b = tlgSel;")
        self.assertEqual([r["a"], r["cur"], r["b"], r["saved"], r["ticks"]], ["s:s2bbbbbbbb", "s:s2bbbbbbbb", "", 2, 2])

    def test_hidden_with_one_session(self):
        self.assertEqual(run("SESS = SESS.slice(0, 1); R.h = tlgSelHtml(tlgTarget());")["h"], "")

    def test_open_popover_skips_repaint(self):
        self.assertEqual(run("POP = true; tlgPaint();")["paints"], 0)
        self.assertEqual(run("tlgPaint();")["paints"], 1)
        self.assertNotIn("tlgss", js_fn("tlgFocusId"))


if __name__ == "__main__":
    unittest.main()
