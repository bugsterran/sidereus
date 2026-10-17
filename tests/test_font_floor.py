"""web/js/00-core.js fsSize: every px font-size in web/css lands at >= 12px (x --fs) after the ladder;
no inline style in web/js sets a font-size below 12px."""
import glob
import json
import os
import re
import subprocess
import unittest

from tests._load import js_fn, js_all
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALC = re.compile(r"^calc\(([\d.]+)px \* var\(--fs,1\)\)$")


def fs_keep():
    m = re.search(r"^const FS_KEEP = (\{.*?\});", js_all(), re.M | re.S)
    return json.loads(re.sub(r"'", '"', m.group(1))) if m and m.group(1).strip("{} ") else {}


def run(calls):
    """calls: [[value, laddered, floor|None], ...] -> fsSize results."""
    js = js_fn("fsSize") + "\nconsole.log(JSON.stringify(%s.map(a => fsSize(a[0], a[1], a[2] == null ? undefined : a[2]))));" % json.dumps(calls)
    return json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


def css_sizes():
    """(file, selector, px) for every `font-size:Npx` literal in web/css/*.css."""
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "web", "css", "*.css"))):
        with open(p, encoding="utf-8") as fh:
            src = re.sub(r"/\*.*?\*/", "", fh.read(), flags=re.S)
        for m in re.finditer(r"([^{}]*)\{([^{}]*)\}", src):
            sel = m.group(1).strip()
            for n in re.findall(r"font-size:\s*([\d.]+)px", m.group(2)):
                out.append((os.path.basename(p), sel, float(n)))
    return out


class FontFloor(unittest.TestCase):
    def test_css_literals_reach_floor(self):
        keep = fs_keep()
        rows = css_sizes()
        self.assertGreater(len(rows), 300)
        res = run([[("%gpx" % n), "data-ui" not in sel, keep.get(sel)] for _, sel, n in rows])
        bad = []
        for (f, sel, n), r in zip(rows, res):
            if n < 8:
                self.assertEqual(r, "", sel)
                continue
            m = CALC.match(r)
            self.assertIsNotNone(m, r)
            if float(m.group(1)) < keep.get(sel, 12):
                bad.append("%s %s %gpx -> %s" % (f, sel, n, r))
        self.assertEqual(bad, [])

    def test_ladder_kept_above_floor(self):
        self.assertEqual(run([["13px", True, None], ["14px", True, None], ["12px", False, None],
                              ["11px", True, None], ["10px", False, None], ["16px", False, None]]),
                         ["calc(14px * var(--fs,1))", "calc(16px * var(--fs,1))", "calc(12px * var(--fs,1))",
                          "calc(12px * var(--fs,1))", "calc(12px * var(--fs,1))", "calc(16px * var(--fs,1))"])

    def test_keep_floor_and_untouched(self):
        self.assertEqual(run([["8.5px", True, 11], ["6px", True, None], ["1em", True, None], ["", False, None]]),
                         ["calc(11px * var(--fs,1))", "", "", ""])

    def test_var_wrapped(self):
        self.assertEqual(run([["var(--nx-fs)", True, None]]), ["calc(var(--nx-fs) * var(--fs,1))"])

    def test_no_small_inline_px_in_js(self):
        bad = []
        for p in sorted(glob.glob(os.path.join(ROOT, "web", "js", "*.js"))) + [os.path.join(ROOT, "web", "app-head.js")]:
            with open(p, encoding="utf-8") as fh:
                for i, line in enumerate(fh, 1):
                    # `font-size:Npx` is CSS (inline style); SVG attributes are `font-size="N"` and stay out of scope
                    for n in re.findall(r"font-size\s*:\s*([\d.]+)px", line):
                        if float(n) < 12:
                            bad.append("%s:%d %spx" % (os.path.basename(p), i, n))
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
