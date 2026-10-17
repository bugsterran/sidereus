"""Timeline roving focus (web/js/74b tlRoveTarget, 98-a11y a11yOne): rows are the only tab stops,
bars get tabIndex -1 but keep data-kb; arrows walk bars in a row and move to the nearest bar in the next row."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TlRove(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src = js_fn("tlRoveTarget") + "\n" + js_fn("a11yOne") + r"""
const A11Y_NATIVE = /^(A|BUTTON)$/;
const getComputedStyle = () => ({ cursor: 'pointer' });
const mkRow = (name, xs) => {
  const row = { name, classList: { contains: c => c === 'tlr' }, bars: [] };
  row.bars = xs.map((x, i) => ({ name: name + i, row, classList: { contains: c => c === 'tlb' },
    closest: s => s === '.tlr' ? row : null, getBoundingClientRect: () => ({ left: x, width: 10 }) }));
  row.querySelectorAll = () => row.bars;
  return row;
};
const r0 = mkRow('a', [0, 100, 200]), r1 = mkRow('b', [190]), r2 = mkRow('c', []);
const rows = [r0, r1, r2];
const nm = (t, k) => { const n = tlRoveTarget(t, k, rows); return n ? n.name : null; };
const R = {
  rowRight: nm(r0, 'ArrowRight'), rowLeft: nm(r0, 'ArrowLeft'), rowDown: nm(r0, 'ArrowDown'), rowUp: nm(r0, 'ArrowUp'),
  barRight: nm(r0.bars[0], 'ArrowRight'), lastRight: nm(r0.bars[2], 'ArrowRight'),
  barLeft: nm(r0.bars[1], 'ArrowLeft'), firstLeft: nm(r0.bars[0], 'ArrowLeft'),
  home: nm(r0.bars[2], 'Home'), end: nm(r0, 'End'),
  downNearest: nm(r0.bars[2], 'ArrowDown'), upNearest: nm(r1.bars[0], 'ArrowUp'),
  downNoBars: nm(r1.bars[0], 'ArrowDown'), enter: nm(r0, 'Enter'),
};
const mkEl = sel => { const a = {}; return { tagName: 'DIV', tabIndex: null, attrs: a,
  hasAttribute: k => k in a, setAttribute: (k, v) => { a[k] = v; }, closest: () => null, matches: s => s === sel }; };
const bar = mkEl('#feed .tlr .tlb'), row = mkEl('nope');
a11yOne(bar); a11yOne(row);
R.barTab = bar.tabIndex; R.barKb = 'data-kb' in bar.attrs; R.rowTab = row.tabIndex;
process.stdout.write(JSON.stringify(R));
"""
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        cls.R = json.loads(r.stdout)

    def test_row_moves(self):
        R = self.R
        self.assertEqual((R["rowRight"], R["rowLeft"], R["rowDown"], R["rowUp"]), ("a0", None, "b", None))
        self.assertEqual((R["end"], R["enter"]), ("a2", None))   # Enter is left to the activators

    def test_bar_moves(self):
        R = self.R
        self.assertEqual((R["barRight"], R["lastRight"], R["barLeft"], R["firstLeft"], R["home"]),
                         ("a1", None, "a0", "a", "a0"))
        self.assertEqual((R["downNearest"], R["upNearest"], R["downNoBars"]), ("b0", "a2", "c"))

    def test_bars_are_not_tab_stops(self):
        self.assertEqual((self.R["barTab"], self.R["barKb"], self.R["rowTab"]), (-1, True, 0))


if __name__ == "__main__":
    unittest.main()
