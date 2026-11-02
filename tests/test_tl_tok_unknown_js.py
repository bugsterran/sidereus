"""Timeline session name cell: a platform group whose tokens are unknown (all tk 0, e.g. Cursor)
draws no «Tokens» chip; a group with tokens still does. One node run with stubs."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

STUB = r"""
const esc = s => String(s), T = s => s, TV = j => j.msg, U = (n, u) => n + u;
const aiLogo = p => '', repoHue = c => 0, tlStateDot = it => '';
"""


def run(body):
    code = (STUB + js_fn("fmtTok") + "\n" + js_fn("tlSessNmB")
            + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(code), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TlTokUnknown(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
R.zero = tlSessNmB({plat: 'cu', cwd: '/r/a', items: [{tk: 0}, {}]}, {}, 5, 0);
R.some = tlSessNmB({plat: 'cx', cwd: '/r/a', items: [{tk: 0}, {tk: 1500}]}, {}, 5, 0);
R.cc = tlSessNmB({cwd: '/r/a', items: [{tk: 0}]}, {}, 5, 0);
""")

    def test_unknown_tokens_no_chip(self):
        self.assertNotIn("Tokens", self.R["zero"])

    def test_known_tokens_chip(self):
        self.assertIn("Tokens", self.R["some"])

    def test_claude_row_keeps_active_chip(self):
        self.assertIn("active", self.R["cc"])


if __name__ == "__main__":
    unittest.main()
