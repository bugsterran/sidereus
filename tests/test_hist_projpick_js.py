"""History project picker (85 histProjHtml → 08b ppComboHtml): the same combobox as Pipelines/Structure/Branches, no chip row."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import ROOT, js_fn
from tests._node import node_e

PRE = r"""
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const T = s => s, PPC = {}; let PPS = null;
let histProj = ['x'], histQ = 'q';
const R = {save: [], paint: 0};
function histExtKeys(d){ return d.gm ? ['gm'] : []; }
function histFSave(){ R.save.push([histProj.slice(), histQ]); } function paintHist(){ R.paint++; }
"""
LIST = ("[{date: 'd1', rows: [{project: 'b', sid: 's1'}, {project: 'a', sid: 's2'}, {project: 'a', sid: 's3'}],"
        " gm: {rows: [{project: 'b', sid: 'g1'}]}}, {date: 'd2', rows: [{project: 'a', sid: 's2'}, {sid: 's9'}]}]")


def run(body):
    src = (PRE + "\n".join(js_fn(n) for n in ("ppComboHtml", "ppFilter", "histProjs", "histProjHtml", "histPickProj"))
           + "\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class HistProjPick(unittest.TestCase):
    def test_projects_and_session_counts(self):
        r = run("R.hp = histProjs(" + LIST + ");")
        self.assertEqual(r["hp"], {"projs": ["?", "a", "b"], "cnt": {"?": 1, "a": 2, "b": 2}})

    def test_combobox_not_chips(self):
        r = run("const hp = histProjs(" + LIST + "); R.h = histProjHtml(hp.projs, hp.cnt, '');"
                "R.rows = PPC.hist.flat('').map(e => [e.p, e.name, PPC.hist.note(e)]); R.h2 = histProjHtml(hp.projs, hp.cnt, 'a');")
        self.assertIn('<b>Project</b><button type=button class="strp ppbtn ppcombo" data-ppk="hist"', r["h"])
        self.assertIn("<span class=ppcn>All</span> ▾</button>", r["h"])
        self.assertIn("<span class=ppcn>a</span> ▾</button>", r["h2"])
        self.assertNotIn("data-hp", r["h"])
        self.assertEqual(r["rows"][0], ["", "All", " <small class=strpc>5</small>"])
        self.assertEqual([x[0] for x in r["rows"]], ["", "?", "a", "b"])

    def test_hidden_below_two_projects(self):
        self.assertEqual(run("R.h = histProjHtml(['a'], {a: 1}, '');")["h"], "")

    def test_pick_sets_single_and_keeps_query(self):
        r = run("histProjHtml(['a', 'b'], {}, ''); PPC.hist.pick('b'); PPC.hist.pick('');")
        self.assertEqual(r["save"], [[["b"], "q"], [[], "q"]])
        self.assertEqual(r["paint"], 2)

    def test_stored_multi_pick_keeps_first(self):
        src = open(os.path.join(ROOT, "web", "js", "85-history.js"), encoding="utf-8").read()
        self.assertIn("v.p.filter(x => typeof x === 'string').slice(0, 1)", src)
        self.assertNotIn("class=hpcs", src)


if __name__ == "__main__":
    unittest.main()
