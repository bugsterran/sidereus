"""Project picker core (web/js/08b-projpick.js): ppGroups chip order and disjoint groups, ppRecentList cap/dedup,
ppStep wrap. Pure functions only; one node run."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

FNS = ("ppGroups", "ppStep", "ppRecentList", "ppFitHide")


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
R.stable = (() => { const rec0 = ['/u/old', '/r/r1', '/r/r0'], a = ppGroups(I, rec0, '/u/old', '').chips.map(e => e.p);
  const b = ppGroups(I, ppRecentList(rec0, '/r/r1'), '/r/r1', '').chips.map(e => e.p); return [a, b]; })();
R.cap = ppGroups(I, ['/r/r0', '/r/r1', '/r/r2', '/r/r3', '/r/r4', '/r/r5'], '', '');
let l = [];
['a', 'b', 'c', 'a', 'd', 'e', 'f'].forEach(p => { l = ppRecentList(l, p); });
R.rec = l;
R.fit = [ppFitHide([50, 50, 50, 80], 5, 300, 3), ppFitHide([50, 50, 50, 80], 5, 200, 3), ppFitHide([50, 50, 50, 80], 5, 90, 3),
  ppFitHide([50, 50, 50, 80], 5, 100, -1), ppFitHide([50, 80, 50], 5, 140, 1)];
R.step = [ppStep(0, 1, 3), ppStep(2, 1, 3), ppStep(0, -1, 3), ppStep(-1, 1, 3), ppStep(-1, -1, 3), ppStep(0, 1, 0)];
""" % json.dumps(ITEMS))

    def test_chip_order(self):
        # running → live (by name) → recent (by name) → selection last; '/gone' is not listed so it never becomes a chip
        self.assertEqual([e["p"] for e in self.R["g"]["chips"]],
                         ["/u/beta", "/u/alpha", "/u/zeta", "/u/old", "/u/quiet"])

    def test_pick_in_row_keeps_order(self):
        a, b = self.R["stable"]
        self.assertEqual(a, b)
        self.assertEqual(a[3:], ["/u/old", "/r/r0", "/r/r1"])

    def test_selection_kept(self):
        self.assertEqual(self.R["none"]["chips"][-1]["p"], "/u/quiet")   # not live, not recent, filtered out of groups

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


if __name__ == "__main__":
    unittest.main()

    def test_fit_keeps_selection_visible(self):
        fits, one, only, nosel, mid = self.R["fit"]
        self.assertEqual(fits, [])            # 245 <= 300
        self.assertEqual(one, [2])            # fold the chip next to the selection: 190 <= 200
        self.assertEqual(only, [2, 1, 0])     # selection alone even when it still overflows
        self.assertEqual(nosel, [])           # no selection: nothing to protect, keep the plain clip
        self.assertEqual(mid, [2])            # selection not last: trailing chip folds first
