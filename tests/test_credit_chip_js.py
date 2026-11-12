"""«Credits» chip on the session row (40ba sessUsage): drawn only when the server sends x.credit. Node, no live files."""
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
const TV = o => o.msg; function money(c){ return '$' + c; } function sz(b){ return b + 'B'; }
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


@unittest.skipUnless(shutil.which("node"), "node not installed")
class CreditChipJs(unittest.TestCase):
    def test_R1_only_with_credit(self):
        on, roll, off, none = chips([{"plat": "pi", "credit": {"lastAt": 1, "tok": 12000}},
                                     {"plat": "pi", "credit": {"lastAt": 1, "tok": 5, "roll": 1}},
                                     {"plat": "pi", "tok": 900}, {"plat": "cc", "credit": None}])
        self.assertIn(">Credits 12K<", on)
        self.assertIn("current 5h window", on)
        self.assertIn("rolling last 5h", roll)
        self.assertNotIn("current 5h window", roll)
        self.assertNotIn("Credits", off)
        self.assertNotIn("Credits", none)

    def test_R1_chip_in_usage_group(self):
        self.assertTrue(re.search(r"extTokChip\(x\) \+ cred \+ model", js_all()))
        self.assertIn("'Credits': '크레딧'", js_all())

    def test_R1_chip_never_dropped(self):
        on = chips([{"plat": "pi", "credit": {"lastAt": 1, "tok": 3}}])[0]
        cls = re.search(r'<span class=(\w+) title="[^"]*">Credits', on).group(1)
        drop = json.loads(re.search(r"^const SX_DROP = (\[.*?\]);$", js_all(), re.M).group(1).replace("'", '"'))
        self.assertNotIn(cls, drop)


if __name__ == "__main__":
    unittest.main()
