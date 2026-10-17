"""Token series colours (web/js/45-tokens.js wkc · 46-tokens-tab.js tkProjIdx): light twins clear 3:1 on the panel,
and the context table colours a project by its index in the weekly project rows, not its own row order."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests.test_saver_quota_js import jconst
from tests._node import node_e

PANEL_LT = "#f4f5f7"


def _lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _ratio(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def run(theme, body):
    src = ("var document = {documentElement: {dataset: {theme: %s}}};\n" % json.dumps(theme)
           + jconst("thc") + "\n" + jconst("WKC") + "\n" + jconst("WKC_LT") + "\n" + jconst("wkc") + "\n"
           + js_fn("tkProjIdx") + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TokenColors(unittest.TestCase):
    def test_light_twins_contrast(self):
        lt = re.findall(r"#[0-9a-f]{6}", jconst("WKC_LT"))
        self.assertEqual(len(lt), len(re.findall(r"#[0-9a-f]{6}", jconst("WKC"))))
        for h in lt:
            self.assertGreaterEqual(_ratio(h, PANEL_LT), 3.0, h)
            self.assertGreaterEqual(_ratio(h, "#ffffff"), 4.5, h)   # white .wktb labels in light theme

    def test_wkc_follows_theme(self):
        lt = run("light", "R.c = [0, 1, 8].map(wkc);")["c"]
        dk = run("dark", "R.c = [0, 1, 8].map(wkc);")["c"]
        # ★WKC_LT[1] #b8641a -> #a8581a: white bar labels need 4.5:1 (was 4.31)
        self.assertEqual(lt, ["#3a6fd4", "#a8581a", "#3a6fd4"])
        self.assertEqual(dk, ["#5b8def", "#e8913a", "#5b8def"])

    def test_context_colour_by_project(self):
        R = run("light", """
const ref = [{name: 'acme-web'}, {name: 'billing'}, {name: 'infra'}];
const ctx = [{name: 'billing'}, {name: 'new-one'}, {name: 'acme-web'}, {name: 'other'}];
R.i = tkProjIdx(ctx, ref);
R.c = R.i.map(wkc);
R.ref0 = wkc(0);
R.empty = tkProjIdx(ctx, []);
""")
        self.assertEqual(R["i"], [1, 3, 0, 4])
        self.assertEqual(R["c"][2], R["ref0"])   # acme-web keeps the weekly-table colour
        self.assertEqual(R["empty"], [0, 1, 2, 3])

    def test_no_raw_row_index_colours(self):
        src = js_all()
        self.assertNotRegex(src, r"WKC\[i\s*%(?!.*WKC_LT)")


if __name__ == "__main__":
    unittest.main()
