"""«Spending credits» attention signal (17-attention.js): label keyed on k, the Korean why is passed through untouched."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e


def node(src):
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def const_src(name):
    return re.search(r"^const " + name + r" = [\s\S]*?;$", js_all(), re.M).group(0)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class AttentionCreditJs(unittest.TestCase):
    def why(self, lang, w):
        src = ("let LANG = " + json.dumps(lang) + "; const T = s => s; const UNIT_KO = {m: '\\ubd84'};\n"
               + "\n".join(js_fn(n) for n in ("U", "PL", "attnWhy")) + "\n"
               "process.stdout.write(JSON.stringify(attnWhy({k: 'credit', why: " + json.dumps(w) + "})));")
        return node(src)

    def test_R3_label(self):
        self.assertIn("credit:'Spending credits'", const_src("ATTN_LBL"))
        self.assertNotIn("credit", const_src("ATTN_LIST_ONLY"))
        self.assertIn("'Spending credits': '크레딧 사용 중'", js_all())

    def test_R3_why(self):
        w = "크레딧 사용 중 · 12K"
        self.assertEqual(self.why("en", w), "Spending credits")
        self.assertEqual(self.why("ko", w), w)


if __name__ == "__main__":
    unittest.main()
