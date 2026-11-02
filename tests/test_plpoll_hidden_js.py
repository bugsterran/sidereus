"""Pipelines poll (web/js/48b-pipeline-run.js plPoll): a hidden tab does not repaint (the repaint refetches
/api/harness/evidence); a visible tab repaints. No timers, no network."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

BASE = r"""
var document = {hidden: true, getElementById: id => id === 'feed' ? {} : null};
let mainView = 'pipe', paints = 0;
const PLS = {draft: null}, PL_DRAFT_TTL = 600000;
const paintPipe = () => { paints++; }, plDraftSet = () => {}, plLoad = () => {};
"""


def run(body):
    src = BASE + js_fn("plPoll") + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));"
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PlPollHidden(unittest.TestCase):
    def test_hidden_skips_then_visible_repaints(self):
        R = run(r"""
plPoll(); plPoll(); R.hidden = paints;
document.hidden = false; plPoll(); R.visible = paints;
""")
        self.assertEqual([R["hidden"], R["visible"]], [0, 1])


if __name__ == "__main__":
    unittest.main()
