"""Structure tab pure helpers (web/js/80-structure.js, 81-structure-panel.js): squarify area/bounds, layout tiers
(2 vs 3, zoom, «+N more» and per-file rest cells), strPick, strLevel age cuts, strSeries gaps, strSpark, strEdRows. One node run."""
import json
import re
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_all, js_fn
from tests._node import node_e

BASE = i18n_prelude("'ko'", ("T", "KE", "U")) + r"""
const NL = String.fromCharCode(10), thc = (d, l) => d;
let strZoom = '', strAxis = 'age', strIdx = 0, strLastMap = null, STR = null;
const STR_COL = ['#1d2530', '#23405c', '#2c5f92', '#3d85c6', '#63a9e8'];
"""
FNS = ("strWorst", "strSquarify", "strLayArea", "strLayout", "strPick", "strFk", "strSi", "strLastOf", "strLevel",
       "strShort", "strSeries", "strSpark", "strEdRows")


def run(body):
    age = re.search(r"^const STR_AGE = \[[^\]]*\];", js_all(), re.M).group(0)
    src = BASE + age + "\n" + "\n".join(js_fn(f) for f in FNS) + "\nconst R = {};\n" + body \
        + "\nprocess.stdout.write(JSON.stringify(R));"
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class StructureView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
const inside = (c, X, Y, W, H) => c.x >= X - 1e-6 && c.y >= Y - 1e-6 && c.x + c.w <= X + W + 1e-6 && c.y + c.h <= Y + H + 1e-6;
const sq = strSquarify([6, 6, 4, 3, 2, 2, 1].map((v, i) => ({v, d: i})), 10, 20, 600, 400);
R.sq = {n: sq.length, area: sq.reduce((s, c) => s + c.w * c.h, 0), inside: sq.every(c => inside(c, 10, 20, 600, 400)),
        finite: sq.every(c => [c.x, c.y, c.w, c.h].every(Number.isFinite)),
        prop: sq[0].w * sq[0].h / (sq[6].w * sq[6].h)};
R.sqZero = strSquarify([{v: 0, d: 'z'}, {v: -3, d: 'n'}, {v: 5, d: 'p'}], 0, 0, 100, 50).map(c => [c.d, c.w, c.h]);
R.sqFlat = [strSquarify([{v: 1, d: 1}], 0, 0, 0.4, 100).length, strSquarify([], 0, 0, 100, 100).length];
R.worst = [strWorst([], 1, 1), strWorst([{v: 4}], 4, 2), strWorst([{v: 0}], 1, 1)];
const areas = [{key: 'A', lines: 100, fns: [{file: 'a.py', lang: 'py', name: 'f', lines: 60}], more: 3,
                rest: [{file: 'd/a.py', n: 2, lines: 30}, {file: '', n: 1, lines: 10, etc: 1, files: 4}]},
               {key: 'B', lines: 50, fns: [{file: 'b.py', lang: 'py', name: 'g', lines: 50}]},
               {key: 'C', lines: 0, fns: []}];
const two = strLayout({areas}, 800, 600);
R.two = {areas: two.filter(r => r.area).map(r => r.a.key), cells: two.filter(r => r.f).map(r => r.f.name),
         proj: two.some(r => r.proj), inside: two.every(c => inside(c, 0, 0, 800, 600))};
areas[0].rest[0].lines = 29;    // rest no longer sums to lines - fns -> one «+N more» cell
R.restMismatch = strLayout({areas}, 800, 600).filter(r => r.f && r.f.more).map(r => r.f.name);
strZoom = 'B';
R.zoom = strLayout({areas}, 800, 600).filter(r => r.area).map(r => [r.a.key, r.w, r.h]);
strZoom = '';
const three = strLayout({areas, projs: [{lines: 150, areas: areas.slice(0, 1)}, {lines: 50, areas: areas.slice(1)}, {lines: 0}]}, 800, 600);
R.three = {proj: three.filter(r => r.proj).length, tight: three.filter(r => r.area).every(r => r.tight)};
R.none = strLayout({areas: [{lines: 0}]}, 800, 600).length;
R.pick = [[], [{at: 5}, {at: 9}, {at: 20}]].map(s => [0, 5, 10, 99].map(t => strPick(s, t)));
const f = {file: 'a.py', lang: 'py', name: 'f'};
R.lv = [[5, 5], [10, 9], [5, 4], [10, 4], [10, 3], [0, 0]].map(([si, last]) => strLevel({si}, Object.assign({last}, f)));
R.lvMore = strLevel({si: 3}, {more: 2});
strAxis = 'churn'; R.lvChurn = [0, 2, 9].map(c => strLevel({si: 3}, Object.assign({churn: c}, f))); strAxis = 'age';
strLastMap = new Map([['pka.py:py:f', 2]]); R.lvMap = strLevel({si: 4, pk: 'pk'}, f);
R.fk = [strFk({pk: 'p/'}, f), strFk(null, f)];
R.short = ['a/b/c.py', 'c.py', 'dir/'].map(strShort);
STR = {snaps: [{areas: [{key: 'A', fns: [{file: 'a.py', lang: 'py', name: 'f', lines: 3}]}]},
               {areas: [{key: 'A', fns: [{more: 1, file: 'a.py', lang: 'py', name: 'f'}]}]},
               {areas: [{key: 'B', fns: []}, {key: 'A', fns: [{file: 'a.py', lang: 'py', name: 'f'}]}]}]};
R.series = strSeries('A', 'a.py:py:f');
R.spark = [strSpark([1], 0), strSpark([1, null, 4], 2)];
R.ed = strEdRows('a\nb\nc\nd', 'a\nX\nY\nd').map(r => r.m + r.t);
R.edSame = strEdRows('a', 'a').map(r => r.m + r.t);
R.edNull = strEdRows(null, 'n').map(r => r.m + r.t);
R.edCap = strEdRows('', Array.from({length: 700}, (_, i) => 'l' + i).join('\n')).length;
""")

    def test_squarify_fills_bounds(self):
        s = self.R["sq"]
        self.assertEqual(s["n"], 7)
        self.assertAlmostEqual(s["area"], 600 * 400, delta=1)
        self.assertTrue(s["inside"] and s["finite"])
        self.assertAlmostEqual(s["prop"], 6.0, places=3)   # cell area proportional to v

    def test_squarify_guards(self):
        self.assertEqual(self.R["sqZero"], [["p", 100, 50]])   # v<=0 dropped before dividing
        self.assertEqual(self.R["sqFlat"], [0, 0])
        self.assertEqual(self.R["worst"][0], None)            # Infinity -> JSON null
        self.assertEqual(self.R["worst"][1], 1)
        self.assertIsNone(self.R["worst"][2])

    def test_two_tier_layout(self):
        t = self.R["two"]
        self.assertEqual(t["areas"], ["A", "B"])               # zero-line area dropped, biggest first
        self.assertEqual(t["cells"], ["f", "a.py · 2개", "기타 4개 파일 · 1개", "g"])   # per-file rest cells
        self.assertFalse(t["proj"])
        self.assertTrue(t["inside"])
        self.assertEqual(self.R["restMismatch"], ["+3개 더"])
        self.assertEqual(self.R["zoom"], [["B", 800, 600]])
        self.assertEqual(self.R["none"], 0)

    def test_three_tier_layout(self):
        self.assertEqual(self.R["three"], {"proj": 2, "tight": True})

    def test_pick(self):
        self.assertEqual(self.R["pick"], [[-1, -1, -1, -1], [-1, 0, 1, 2]])

    def test_levels(self):
        # age = (si - last) / si against STR_AGE [0, .1, .25, .6] -> 4 3 2 1, else 0; first snapshot = brightest
        self.assertEqual(self.R["lv"], [4, 3, 2, 1, 0, 4])   # ages 0 .1 .2 .6 .7
        self.assertEqual(self.R["lvMore"], -1)
        self.assertEqual(self.R["lvChurn"], [0, 2, 4])
        self.assertEqual(self.R["lvMap"], 1)                  # no `last`: rebuilt map keyed with the project prefix
        self.assertEqual(self.R["fk"], ["p/a.py:py:f", "a.py:py:f"])
        self.assertEqual(self.R["short"], ["c.py", "c.py", "dir/"])

    def test_series_and_spark(self):
        self.assertEqual(self.R["series"], [3, None, 0])      # capped-out = null (gap), present without lines = 0
        self.assertEqual(self.R["spark"][0], "")
        self.assertEqual(self.R["spark"][1].count("M"), 2)    # null breaks the line
        self.assertIn("<circle", self.R["spark"][1])

    def test_edit_rows(self):
        self.assertEqual(self.R["ed"], [" a", "-b", "-c", "+X", "+Y", " d"])
        self.assertEqual(self.R["edSame"], [" a"])
        self.assertEqual(self.R["edNull"], ["-", "+n"])
        self.assertEqual(self.R["edCap"], 600)


if __name__ == "__main__":
    unittest.main()
