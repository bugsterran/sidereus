"""Structure header helpers (80 strHdBadge): tint class, escaping."""
import json
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


def run(body):
    src = ("const esc = s => String(s).replace(/[&<>\"']/g, c => '&#' + c.charCodeAt(0) + ';');\n"
           + js_fn("strHdBadge") + "\n" + body)
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


class Header(unittest.TestCase):
    def test_badge(self):
        out = run("process.stdout.write(JSON.stringify([strHdBadge('up', '쓰는 곳 2'), strHdBadge('', 'a<b', 't\"x')]));")
        self.assertEqual(out[0], '<em class="strbg strbg-up">쓰는 곳 2</em>')
        self.assertEqual(out[1], '<em class="strbg" title="t&#34;x">a&#60;b</em>')


if __name__ == "__main__":
    unittest.main()
