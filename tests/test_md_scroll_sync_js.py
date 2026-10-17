"""md split-view scroll sync: data-ln anchors only with ln, and the anchor-pair mapping (node)."""
import json
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


def run(body):
    src = ("const NL = '\\n';\n"
           "function esc(s){ return String(s).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c])); }\n"
           "const inline = x => esc(x); const mdLinks = x => x; const codeBlock = b => '<pre>' + esc(b) + '</pre>';\n"
           + js_fn("md") + "\n" + js_fn("strMdMap") + "\n" + body)
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=30, encoding="utf-8")
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


DOC = "# T\\n\\npara\\n```js\\nx\\n```\\n- a\\n- b\\n> q\\n---\\n|a|\\n|-|\\n|1|"


class Anchors(unittest.TestCase):
    def test_ln_mode(self):
        out = run("process.stdout.write(JSON.stringify([md('" + DOC + "', 1, 1), md('" + DOC + "', 1), md('" + DOC + "')]));")
        a = lambda n: '<i class=mdln data-ln="%d"></i>' % n
        self.assertEqual(out[0], a(1) + '<h1>T</h1>' + a(3) + '<p>para</p>' + a(4) + '<pre>x</pre>'
                         + a(7) + '<ul><li>a</li><li>b</li></ul>' + a(9) + '<blockquote><p>q</p></blockquote>'
                         + a(10) + '<hr>' + a(11) + '<table><thead><tr><th>a</th></tr></thead><tbody><tr><td>1</td></tr></tbody></table>')
        self.assertNotIn("data-ln", out[1])
        self.assertNotIn("data-ln", out[2])

    def test_map(self):
        out = run("const P = [[0, 0], [100, 300], [200, 350], [400, 1000]];"
                  "process.stdout.write(JSON.stringify([strMdMap(P, 0), strMdMap(P, 50), strMdMap(P, 150),"
                  " strMdMap(P, 300), strMdMap(P, 999), strMdMap(P, -5), strMdMap([], 10), strMdMap([[0,0],[0,5],[10,15]], 0)]));")
        self.assertEqual(out, [0, 150, 325, 675, 1000, 0, 0, 0])


if __name__ == "__main__":
    unittest.main()
