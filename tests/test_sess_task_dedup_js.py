"""sessTaskHtml (web/js/40b) drops the «doing» line when a running subagent row already shows the same text."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(name):
    return open(os.path.join(ROOT, "web", "js", name), encoding="utf-8").read()


def _fn(s, n):
    return re.search(r"^function " + n + r"\(.*?^}", s, re.S | re.M).group(0)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SessTaskDedup(unittest.TestCase):
    def run_js(self, rows):
        core, sl = _src("00-core.js"), _src("40b-sessions-list.js")
        js = "\n".join([
            "const NL = '\\n'; function T(s){ return s; }",
            re.search(r"^const esc = .*?\n.*$", core, re.M).group(0),
            re.search(r"^function plStrip\(.*$", core, re.M).group(0),
            re.search(r"^const SUB_PLAIN_TY = .*$", sl, re.M).group(0), _fn(sl, "subLab"), _fn(sl, "sessTaskHtml"),
            "console.log(JSON.stringify(%s.map(sessTaskHtml)));" % json.dumps(rows)])
        r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_dedup(self):
        out = self.run_js([
            {"state": "tool", "targ": "[pl:v/fix] Slice F", "sub": [{"lab": "general-purpose: [pl:v/fix] Slice F"}]},
            {"state": "tool", "targ": "Slice F", "sub": ["Explore: Slice F"]},
            {"state": "tool", "targ": "Slice F", "sub": [{"lab": "general-purpose: other task"}]},
            {"state": "think", "targ": "Slice F"},
            {"state": "done", "targ": "Slice F", "sub": []}])
        self.assertEqual(out[0], "")
        self.assertEqual(out[1], "")
        self.assertIn(">Slice F</div>", out[2])
        self.assertIn(">Slice F</div>", out[3])
        self.assertEqual(out[4], "")


if __name__ == "__main__":
    unittest.main()
