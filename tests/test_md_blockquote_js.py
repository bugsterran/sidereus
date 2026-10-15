"""md() blockquotes: consecutive `>` lines become one <blockquote>, nested `> >` nests, body is escaped (node)."""
import json
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


def run(body):
    src = ("const NL = '\\n';\n"
           "function esc(s){ return String(s).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c])); }\n"
           "const inline = x => esc(x); const mdLinks = x => x; const codeBlock = b => '<pre>' + esc(b) + '</pre>';\n"
           + js_fn("md") + "\n" + body)
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=30)
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


class Blockquote(unittest.TestCase):
    def test_quote(self):
        out = run("process.stdout.write(JSON.stringify(["
                  "md('a\\n> one\\n> two\\nb', 1), md('> x\\n> > y', 1), md('> <b>', 1)]));")
        self.assertEqual(out[0], '<p>a</p><blockquote><p>one</p><p>two</p></blockquote><p>b</p>')
        self.assertEqual(out[1], '<blockquote><p>x</p><blockquote><p>y</p></blockquote></blockquote>')
        self.assertEqual(out[2], '<blockquote><p>&lt;b&gt;</p></blockquote>')


if __name__ == "__main__":
    unittest.main()
