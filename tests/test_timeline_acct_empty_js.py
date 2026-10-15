"""Timeline empty line (74 tlEmptyMsg): a pick that hides every row names the account and the hidden count."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import i18n, jconst
from tests._node import node_e

SCEN = r"""
let PICK = '';
function acctPick(v){ return v === 'time' ? PICK : ''; }
const D = {hours: 12, rows: [{sid: 'a'}, {sid: 'b'}]};
R.quiet = tlEmptyMsg({hours: 12, rows: []}, []);
R.nopick = tlEmptyMsg(D, []);
PICK = '<b>'; R.hidden = tlEmptyMsg(D, []);
LANG = 'ko'; R.ko = tlEmptyMsg(D, []);
"""


def run():
    src = ("var document = {getElementById: () => null};\n" + i18n() + "\n" + jconst("esc") + "\n" + js_fn("tlEmptyMsg")
           + "\nconst R = {};\nLANG = 'en';\n" + SCEN + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"))
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TlEmptyAcct(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run()

    def test_quiet_window_unchanged(self):
        self.assertEqual(self.R["quiet"], "No subagents ran in the last 12h")
        self.assertEqual(self.R["nopick"], "No subagents ran in the last 12h")

    def test_pick_hid_everything(self):
        self.assertEqual(self.R["hidden"], "Nothing for &lt;b&gt; in the last 12h · 2 in other accounts")
        self.assertIn("&lt;b&gt;", self.R["ko"])
        self.assertIn("2", self.R["ko"])


if __name__ == "__main__":
    unittest.main()
