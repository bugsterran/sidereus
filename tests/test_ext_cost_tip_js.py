"""External CLI row token tooltip: the pricing-source sentence follows the platform key, and a pi row on
provider anthropic says it counts in «Who is using the 5h» instead of «Not counted…». Node, no live files."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

PRE = """
const T = s => s;
const TV = o => o.msg.replace(/\\{(\\w+)\\}/g, (_, k) => o.vars[k]);
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
function fmtTok(n){ return String(n); } function extCostStr(c){ return '$' + c; }
"""
FNS = "\n".join(js_fn(n) for n in ("extCostTip", "extTokChip"))


def tips(rows):
    src = (PRE + FNS + "\nconst rows = " + json.dumps(rows) + ";"
           "\nconsole.log(JSON.stringify(rows.map(x => extTokChip(Object.assign({tok: 10, estCost: 1.5}, x)))));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ExtCostTipJs(unittest.TestCase):
    def test_wording_per_platform(self):
        cx, gm, pa, po, cu = tips([{"plat": "cx"}, {"plat": "gm"}, {"plat": "pi", "model": "anthropic/claude-x"},
                                   {"plat": "pi", "model": "openai/gpt-x"}, {"plat": "cu"}])
        self.assertIn("OpenAI API list prices", cx)
        self.assertNotIn("Google", cx)
        self.assertIn("Google list prices", gm)
        self.assertIn("Cost recorded by pi", pa)
        self.assertNotIn("Google", pa)
        self.assertNotIn("Not counted in the Claude", pa)
        self.assertIn("Who is using the 5h", pa)
        self.assertIn("Not counted in the Claude", po)
        self.assertNotIn("Who is using the 5h", po)
        self.assertNotIn("list prices", cu)            # unknown key: amount only
        self.assertIn("$1.5", cu)

    def test_tokens_tab_keeps_unpriced_sentence(self):
        src = PRE + js_fn("extCostTip") + "\nconsole.log(JSON.stringify(extCostTip(null, 0, 'gm')));"
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        self.assertEqual(json.loads(r.stdout), "Model not in the price table")


if __name__ == "__main__":
    unittest.main()
