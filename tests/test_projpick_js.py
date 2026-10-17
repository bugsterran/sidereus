"""Project picker core (web/js/08b-projpick.js): ppGroups disjoint groups, ppRecentList cap/dedup,
ppStep wrap. Pure functions only; one node run."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

FNS = ("ppGroups", "ppStep", "ppRecentList")


def run(body):
    src = ("const PP_RECENT_N = 5;\nconst ppByName = (a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0);\n"
           + "\n".join(js_fn(f) for f in FNS) + "\nconst R = {};\n" + body
           + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


ITEMS = [
    {"p": "/u/zeta", "name": "zeta", "live": True},
    {"p": "/u/alpha", "name": "alpha", "live": True},
    {"p": "/u/beta", "name": "beta", "live": True, "run": True},
    {"p": "/u/old", "name": "old"},
    {"p": "/u/quiet", "name": "quiet"},
    {"p": "/w/deep/Sidereus", "name": "Sidereus"},
] + [{"p": "/r/r%d" % i, "name": "r%d" % i} for i in range(6)]


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ProjPick(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
const I = %s;
R.g = ppGroups(I, ['/u/old', '/u/alpha', '/gone'], '/u/quiet', '');
R.f1 = ppGroups(I, [], '', 'SID');
R.f2 = ppGroups(I, [], '', 'deep');
R.none = ppGroups(I, ['/u/old'], '/u/quiet', 'nothing-matches');
R.cap = ppGroups(I, ['/r/r0', '/r/r1', '/r/r2', '/r/r3', '/r/r4', '/r/r5'], '', '');
let l = [];
['a', 'b', 'c', 'a', 'd', 'e', 'f'].forEach(p => { l = ppRecentList(l, p); });
R.rec = l;
R.step = [ppStep(0, 1, 3), ppStep(2, 1, 3), ppStep(0, -1, 3), ppStep(-1, 1, 3), ppStep(-1, -1, 3), ppStep(0, 1, 0)];
""" % json.dumps(ITEMS))

    def test_groups_disjoint(self):
        g = self.R["g"]
        self.assertEqual([e["p"] for e in g["work"]], ["/u/beta", "/u/alpha", "/u/zeta"])
        self.assertEqual([e["p"] for e in g["rec"]], ["/u/old"])   # alpha is already in work
        ps = [e["p"] for k in ("work", "rec", "all") for e in g[k]]
        self.assertEqual(len(ps), len(set(ps)))
        self.assertEqual(sorted(ps), sorted(e["p"] for e in ITEMS))

    def test_filter_name_and_path(self):
        self.assertEqual([e["p"] for k in ("work", "rec", "all") for e in self.R["f1"][k]], ["/w/deep/Sidereus"])
        self.assertEqual([e["p"] for k in ("work", "rec", "all") for e in self.R["f2"][k]], ["/w/deep/Sidereus"])

    def test_empty_result(self):
        n = self.R["none"]
        self.assertEqual((n["work"], n["rec"], n["all"]), ([], [], []))

    def test_recent_cap(self):
        self.assertEqual(self.R["rec"], ["f", "e", "d", "a", "c"])
        self.assertEqual([e["p"] for e in self.R["cap"]["rec"]], ["/r/r0", "/r/r1", "/r/r2", "/r/r3", "/r/r4"])

    def test_step_wrap(self):
        self.assertEqual(self.R["step"], [1, 0, 2, 0, 2, -1])



def run_ui(body):
    # ppComboHtml / ppListPaint / ppPick with a stub DOM: one #ppop list node, recent writes recorded.
    pre = """
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const T = s => s, PP_RECENT_N = 5, PPC = {}, WR = [], PICK = [];
let PPS = null;
const ppByName = (a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0);
const L = { innerHTML: '', scrollTop: 0, clientHeight: 0, querySelector(){ return null; } };
const document = { querySelector(s){ return s === '#ppop .cmdkl' ? L : null; }, activeElement: null };
function tabJson(k, d){ return d; } function tabSetJson(k, v){ WR.push(k); } function popHide(){}
"""
    fns = ("ppGroups", "ppRecentList", "ppRecent", "ppFilter", "ppComboHtml", "ppRowHtml", "ppListPaint", "ppBtn", "ppClose", "ppPick")
    src = pre + "\n".join(js_fn(f) for f in fns) + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));"
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ProjPickFlat(unittest.TestCase):
    def test_project_combo_unchanged(self):
        r = run_ui("R.h = ppComboHtml({k: 'pl', label: 'Project', items: [{p: '/w/a', name: 'a'}], cur: '/w/a', rkey: 'k', badge: () => '<D/>'});"
                   "R.n = ppComboHtml({k: 'pl', label: 'Project', items: [], cur: ''});")
        self.assertEqual(r["h"], '<b>Project</b><button type=button class="strp ppbtn ppcombo" data-ppk="pl" aria-haspopup=listbox aria-controls=ppop '
                                 'aria-expanded="false" title="/w/a"><span class=ppcn>a</span><D/> ▾</button>')
        self.assertIn("<span class=ppcn>Pick a project</span>", r["n"])

    def test_flat_rows_no_headers_no_recent(self):
        r = run_ui("""
const items = [{p: 'x', name: 'x'}, {p: 'y', name: 'y'}];
const cfg = {k: 'plsel', label: 'Pipeline', none: '—', items, cur: '', empty: 'None here', flat: q => ppFilter(items, q),
  rowHtml: (e, i) => '<R ' + e.p + ' ' + i + '/>', pick: p => PICK.push(p)};
R.btn = ppComboHtml(cfg);
PPS = {cfg, q: '', i: 0, rows: []}; ppListPaint(); R.list = L.innerHTML;
PPS.q = 'zz'; ppListPaint(); R.empty = L.innerHTML;
PPS.q = 'Y'; ppListPaint(); ppPick(0); R.pick = PICK; R.wr = WR.slice();
R.proj = (() => { PPS = {cfg: {k: 'pl', items, cur: '', rkey: 'rk', pick(){}}, q: '', i: 0, rows: []}; ppListPaint(); const h = L.innerHTML; ppPick(0); return [h, WR]; })();
""")
        self.assertIn("<span class=ppcn>—</span>", r["btn"])
        self.assertEqual(r["list"], "<R x 0/><R y 1/>")            # no Working / Recent / All headers
        self.assertEqual(r["empty"], "<div class=cmdke>None here</div>")
        self.assertEqual((r["pick"], r["wr"]), (["y"], []))         # no rkey: nothing written to recent
        self.assertIn("<div class=ppg>All</div>", r["proj"][0])       # project cfg keeps its groups and recent write
        self.assertEqual(r["proj"][1], ["rk"])


if __name__ == "__main__":
    unittest.main()

