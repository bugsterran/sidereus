"""«Pipelines» first run (48 plBody): no project and no session -> a next-step hint under «Pick a project». Stubs only."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

PRE = """
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const T = s => s; let SESS = [], PLS = {proj: '', data: {}}, SIDEREUS_DIR = '';
"""


def body(sess, code_dir=""):
    js = (PRE + js_fn("demoCmd") + "\n" + js_fn("plBody") + "\nSESS = " + json.dumps(sess) + "; SIDEREUS_DIR = " + json.dumps(code_dir)
          + "; console.log(JSON.stringify(plBody('', {})));")
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class FirstRun(unittest.TestCase):
    def test_no_session_shows_next_step(self):
        h = body([])
        self.assertTrue(h.startswith("<div class=hidnote>Pick a project</div><div class=hidnote>"), h)
        self.assertIn("Start a Claude Code, Codex or Gemini session and it shows up here.", h)
        self.assertIn("Or try the demo: <code>sidereus start --demo</code>", h)

    def test_clone_install_shows_module_command(self):
        self.assertIn("<code>python3 -m sidereus start --demo</code>", body([], "/opt/sidereus"))

    def test_with_session_only_pick(self):
        self.assertEqual(body([{"sid": "s1"}]), "<div class=hidnote>Pick a project</div>")


if __name__ == "__main__":
    unittest.main()
