"""84m2 «Export HTML» › «Detailed» (R3): one self-contained static HTML of the module map — no script, no external URL,
CSP meta, escaped text, sanitised SVG at zoom 1x, safe file name."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

PRE = ("const esc = s => String(s).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));\n"
       + "\n".join(js_fn(n) for n in ("archXClean", "archXName", "archXDoc")))

SVG = ('<svg class="mmdsvg" xmlns="http://www.w3.org/2000/svg" width="1640" height="900" viewBox="0 0 820 450" data-z="2" onload="x()">'
       '<defs><marker id="mmdaall"><path d="M0,0L10,5z"/></marker></defs>'
       '<script>alert(1)</script><foreignObject><div>x</div></foreignObject><style>text{fill:red}</style>'
       '<g class="mmdn" data-p="m1" onclick="go()" style="marker-end:url(&quot;#mmdaall&quot;)"><rect width="10" height="5"/>'
       '<a href="https://evil.example/">e</a><use xlink:href="#mmdaall"/><use href="javascript:alert(1)"/>'
       '<path style="fill:url(https://evil.example/p.svg)" d="M0 0"/><text>a &lt;b&gt;</text></g></svg>')


def run(expr):
    js = PRE + "\nprocess.stdout.write(JSON.stringify(" + expr + "));"
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchExportJs(unittest.TestCase):
    def test_clean_strips_active_and_external(self):
        """R3: on*/data-*/xmlns, non-'#' href, script/style/foreignObject and external url() are dropped; markers kept."""
        out = run("archXClean(%s)" % json.dumps(SVG))
        for bad in ("onload", "onclick", "data-z", "data-p", "<script", "alert", "<foreignObject", "<style", "http", "javascript"):
            self.assertNotIn(bad, out, bad)
        for good in ('<marker id="mmdaall">', 'xlink:href="#mmdaall"', "url(&quot;#mmdaall&quot;)", "<text>a &lt;b&gt;</text>"):
            self.assertIn(good, out, good)

    def test_clean_resets_size_to_viewbox(self):
        """R3: zoom is not carried — width/height equal the viewBox; inner rect sizes untouched."""
        out = run("archXClean(%s)" % json.dumps(SVG))
        head = out[:out.index(">")]
        self.assertIn('width="820"', head)
        self.assertIn('height="450"', head)
        self.assertNotIn("1640", out)
        self.assertIn('<rect width="10" height="5"/>', out)

    def test_doc_is_self_contained(self):
        """R3: doctype, charset, CSP meta; no <script, no http; name text escaped; hostile colour falls back."""
        out = run("archXDoc({title: 'r<&\"x', meta: 'r<&\"x · abc1234', bg: 'red;}</style><script>', fg: 'rgb(1, 2, 3)', leg: '', svg: archXClean(%s)})"
                  % json.dumps(SVG))
        self.assertTrue(out.startswith("<!doctype html>"))
        self.assertIn("<meta charset=utf-8>", out)
        self.assertIn("default-src 'none'; style-src 'unsafe-inline'; img-src data:", out)
        self.assertNotIn("<script", out.lower())
        self.assertNotIn("http:", out)
        self.assertNotIn("https:", out)
        self.assertIn("r&lt;&amp;&quot;x", out)
        self.assertNotIn('r<&"x', out)
        self.assertIn("background:#ffffff", out)
        self.assertIn("color:rgb(1, 2, 3)", out)

    def test_name(self):
        """R3: file name keeps [A-Za-z0-9._-] only; the module suffix only when given (focus view)."""
        out = run("[archXName('my repo/../x', 'abcdef0123456', ''), archXName('..', '', 'web/api <x>'), archXName('r', 'abc', null)]")
        self.assertEqual(out[0], "arch-my_repo_.._x-abcdef0.html")
        self.assertEqual(out[1], "arch-repo-nocommit-web_api_x_.html")
        self.assertEqual(out[2], "arch-r-abc.html")
        for n in out:
            self.assertRegex(n, r"^[A-Za-z0-9._-]+$")


if __name__ == "__main__":
    unittest.main()
