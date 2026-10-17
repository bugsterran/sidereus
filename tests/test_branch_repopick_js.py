"""Branches header repository picker (88 brBarPaint → 08b ppComboHtml): the same combobox as Pipelines/Structure, no chip row."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

PRE = r"""
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const T = s => s, PPC = {}; let PPS = null, POP = false, STATE_IN = true;
let brRepo = '/w/a', brSel = 'x', brDet = {}, BR = {ok: true}, brPw = false;
const R = {tb: [], set: [], load: []};
function popIsOpen(){ return POP; } function strShort(p){ return p.slice(p.lastIndexOf('/') + 1); }
function brModeHtml(){ return '<mode>'; } function tbSet(k, h){ R.tb.push([k, h]); }
function tabSet(k, v){ R.set.push([k, v]); } function loadBr(f){ R.load.push(f); }
"""


def run(body):
    src = (PRE + js_fn("ppComboHtml") + "\n" + js_fn("brBarPaint") + "\n" + js_fn("brPickRepo") + "\n" + body
           + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class BranchRepoPick(unittest.TestCase):
    def test_combobox_not_chips(self):
        h = run("brBarPaint(['/w/a', '/w/b']);")["tb"][0][1]
        self.assertIn('<b>Repository</b><button type=button class="strp ppbtn ppcombo" data-ppk="br"', h)
        self.assertIn('title="/w/a"><span class=ppcn>a</span> ▾</button>', h)
        self.assertNotIn("data-bp=", h)
        for keep in ("<mode>", "id=brpwb", "id=brrf"):
            self.assertIn(keep, h)

    def test_empty_state(self):
        r = run("brBarPaint([]); STATE_IN = false; brBarPaint([]);")
        self.assertIn("<b>Repository</b><span class=strpnl>None</span>", r["tb"][0][1])
        self.assertIn("<span class=strpnl>Loading…</span>", r["tb"][1][1])
        self.assertNotIn("data-ppk", r["tb"][0][1])

    def test_open_popover_skips_repaint(self):
        self.assertEqual(run("POP = true; brBarPaint(['/w/a']);")["tb"], [])

    def test_pick_switches_repo(self):
        r = run("brBarPaint(['/w/a', '/w/b']); PPC.br.pick('/w/a'); PPC.br.pick('/w/b');"
                "R.after = [brRepo, brSel, brDet, BR, PPC.br.rkey];")
        self.assertEqual(r["set"], [["mbBrRepo", "/w/b"]])
        self.assertEqual(r["load"], [True])
        self.assertEqual(r["after"], ["/w/b", "", None, None, "sidereus.brrecent"])


if __name__ == "__main__":
    unittest.main()
