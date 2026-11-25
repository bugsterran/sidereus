"""«Pipelines» Watch pane line (48k plPmLine, R2): «Ran without approval prompts — <modes>» from the run's server `pm`;
nothing for no run, a Workflow run (no `pr`) or a run without `pm`. Pure function under node."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

PRE = r"""
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const T = s => s;
const TV = o => o.msg.replace(/\{(\w+)\}/g, (_, k) => o.vars[k]);
"""


def lines(lvs):
    code = PRE + js_fn("plPmLine") + "\nconsole.log(JSON.stringify(%s.map(plPmLine)));" % json.dumps(lvs)
    r = subprocess.run(node_e(code), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PmLine(unittest.TestCase):
    def test_sentence(self):
        one, two = lines([{"pr": {"pm": ["bypassPermissions"]}}, {"pr": {"pm": ["auto", "dontAsk"]}}])
        self.assertEqual(one, "<div class=plwpm>Ran without approval prompts — bypassPermissions</div>")
        self.assertIn("— auto, dontAsk<", two)

    def test_empty_cases(self):
        self.assertEqual(lines([None, {"run": {"run": True}}, {"pr": {}}, {"pr": {"pm": []}}, {"pr": {"pm": "auto"}}]), [""] * 5)

    def test_escaped(self):
        h, = lines([{"pr": {"pm": ["<b>"]}}])
        self.assertNotIn("<b>", h)


if __name__ == "__main__":
    unittest.main()
