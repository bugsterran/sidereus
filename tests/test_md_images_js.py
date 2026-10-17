"""Markdown images in the source viewer preview (00-core.js mdLinks, 81d strMdImgSrc / strMdImgs). R1, R2, R4.
One node run over fixtures — no server, no fetch."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRE = (r"""const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
const inline = s => esc(s).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
""")
FILES = [{"p": "docs/x.png", "sec": 0, "bytes": 10}, {"p": "docs/big.png", "sec": 0, "bytes": 5 * 1024 * 1024 + 1},
         {"p": "docs/k.png", "sec": 1, "bytes": 10}, {"p": "docs/a b.svg", "sec": 0, "bytes": 10}]


def run(body):
    src = PRE + "\n".join(js_fn(f) for f in ("mdLinks", "strMdRel", "strMdImgSrc")) + "\nconst R = {};\n" + body \
        + "\nprocess.stdout.write(JSON.stringify(R));"
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class MdImages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
const L = s => mdLinks(inline(s)), F = %s;
R.rel = L('![a](docs/x.png)'); R.noalt = L('![](x.SVG?v=1#t)'); R.q = L('![a](x".png)');
R.plain = ['http://h/x.png', 'https://h/x.png', '/abs.png', '//h/x.png', 'data:image/png;base64,x', 'x.txt', 'x.png.txt']
  .map(u => L('![a](' + u + ')'));
const S = h => strMdImgSrc('/r/p', 'README.md', h, F);
R.up = S('../../x.png'); R.sec = S('docs/k.png'); R.big = S('docs/big.png'); R.unl = S('docs/no.png');
R.ok = S('docs/x.png'); R.sp = S('docs/a%%20b.svg'); R.sp2 = strMdImgSrc('/r/p', 'docs/README.md', 'a b.svg', F);
""" % json.dumps(FILES))

    def test_relative_image_gets_data_attr(self):     # R1
        self.assertEqual(self.R["rel"], '<span class=mdimg data-mdimg="docs/x.png">a</span>')
        self.assertEqual(self.R["noalt"], '<span class=mdimg data-mdimg="x.SVG?v=1#t">x.SVG?v=1#t</span>')
        self.assertEqual(self.R["q"], '<span class=mdimg data-mdimg="x&quot;.png">a</span>')   # u arrives escaped

    def test_other_images_stay_plain(self):          # R2: same bytes as before
        for h in self.R["plain"]:
            self.assertEqual(h, '<span class=mdimg>a</span>')

    def test_src_refused(self):                      # R2
        for k in ("up", "sec", "big", "unl"):
            self.assertEqual(self.R[k], "", k)

    def test_src_encoded(self):                      # R1
        self.assertEqual(self.R["ok"], "/api/structure/img?path=%2Fr%2Fp&file=docs%2Fx.png")
        self.assertEqual(self.R["sp2"], "/api/structure/img?path=%2Fr%2Fp&file=docs%2Fa%20b.svg")
        self.assertEqual(self.R["sp"], "")           # percent-encoded href is not decoded — unlisted

    def test_hydrate_is_dom_only(self):              # R2, R4
        body = js_fn("strMdImgs")
        self.assertIn("img.onerror = () => img.replaceWith(span)", body)
        self.assertIn("img.alt = span.textContent", body)
        self.assertNotIn("<img", body)
        self.assertNotIn("innerHTML", body)
        self.assertNotIn("T(", body)
        with open(os.path.join(ROOT, "web/js/81b-structure-tree.js"), encoding="utf-8") as f:
            self.assertTrue(re.search(r"el\.innerHTML = strTreeCode\(g, q\);\n\s*strMdImgs\(el, q\);", f.read()))


if __name__ == "__main__":
    unittest.main()
