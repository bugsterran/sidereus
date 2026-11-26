"""«Compacts in ~N turns» chip on the session row (40ba sessUsage): drawn only from the server's x.cmpEta. Node, no live files."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

PRE = """
const T = s => s;
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const TV = o => o.msg.replace(/\\{(\\w+)\\}/g, (m, k) => (k in o.vars ? o.vars[k] : m));
function money(c){ return '$' + c; } function sz(b){ return b + 'B'; }
function extTokChip(x){ return ''; }
function fmtTok(n){ return n >= 1000 ? Math.round(n / 1000) + 'K' : String(n); }
"""


def chips(rows):
    src = (PRE + js_fn("sessUsage") + "\nconst rows = " + json.dumps(rows) + ";"
           "\nconsole.log(JSON.stringify(rows.map(x => sessUsage(x))));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def eta(n, **kw):
    row = {"plat": "cc", "ctx": 150000, "win": 200000, "cmpEta": {"n": n, "pt": 180000, "grow": 6000, "k": 5}}
    row.update(kw)
    return row


def chip(html):
    m = re.search(r'<span class="(sce[^"]*)" title="([^"]*)">([^<]*)</span>', html)
    return m and (m.group(1), m.group(2), m.group(3))


@unittest.skipUnless(shutil.which("node"), "node not installed")
class CmpEtaJs(unittest.TestCase):
    def test_R1_label(self):
        five, one = chips([eta(5), eta(1)])
        self.assertEqual(chip(five)[2], "Compacts in ~5 turns")
        self.assertEqual(chip(one)[2], "Compacts in ~1 turn")
        # Right after the context % chip, before size/cost/model.
        self.assertTrue(re.search(r"return ctx \+ eta \+ size", js_all()))
        self.assertLess(five.index('class="sc'), five.index('class="sce'))
        self.assertIn("'Compacts in ~{n} turns':", js_all())

    def test_R2_absent_no_chip(self):
        rows = [{"plat": "cc", "ctx": 150000}, eta(0), eta(-2), eta(None), {"plat": "cc", "ctx": 1, "cmpEta": None},
                eta(4, plat="cx"), eta(4, plat="pi"), eta(4, plat="gm")]
        for h in chips(rows):
            self.assertNotIn("sce", h)

    def test_R3_warn_at_3_not_4(self):
        three, four = chips([eta(3), eta(4)])
        self.assertEqual(chip(three)[0], "sce warn")
        self.assertEqual(chip(four)[0], "sce")
        drop = json.loads(re.search(r"^const SX_DROP = (\[.*?\]);$", js_all(), re.M).group(1).replace("'", '"'))
        self.assertNotIn("sce", drop)

    def test_R3_tooltip_has_pt_ctx_grow(self):
        tip = chip(chips([eta(2)])[0])[1]
        self.assertEqual(tip, "Auto-compaction at 180K tokens · now 150K tokens · ~6K tokens per turn (median of last 5)")


if __name__ == "__main__":
    unittest.main()
