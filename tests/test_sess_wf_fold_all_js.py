"""Session tree «Expand all / Collapse all» over team/workflow groups (web/js/40b-sessions-list.js wfFoldAll · wfFoldBtns)."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

STUB = "const esc = s => String(s); const T = s => s; const wfFold = new Set(['old']);\n"


def _js(body):
    src = STUB + js_fn("wfFoldAll") + "\n" + js_fn("wfFoldBtns") + "\n" + body
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class WfFoldAll(unittest.TestCase):
    def test_collapse_then_expand(self):
        o = _js("wfFoldAll(['team', 'wf_1'], false); const a = [...wfFold].sort();"
                "wfFoldAll(['team', 'wf_1'], true); console.log(JSON.stringify({a: a, b: [...wfFold]}));")
        self.assertEqual(o["a"], ["old", "team", "wf_1"])
        self.assertEqual(o["b"], [])

    def test_buttons_only_with_a_group(self):
        o = _js("console.log(JSON.stringify([wfFoldBtns([{wf: []}, {}]), wfFoldBtns([{team: {}}]), wfFoldBtns([{wf: [{id: 'x'}]}])]));")
        self.assertEqual(o[0], "")
        for h in o[1:]:
            self.assertIn('data-wfa=1>Expand all<', h)
            self.assertIn('data-wfa=0>Collapse all<', h)


if __name__ == "__main__":
    unittest.main()
