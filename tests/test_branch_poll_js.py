"""Branches poll (web/js/88-branch.js brPoll): an open tab stuck on «No git repository» loads once a repo appears
in the session list; once a repo is chosen the poll never refetches. No timers, no network."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

BASE = r"""
let mainView = 'br', ISPOP = false, ISWP = false, brRepo = '', brBusy = 0, SESS = [], loads = 0;
function loadBr(force){ loads++; const ps = brRepos(); if(!brRepo) brRepo = ps[0] || ''; }
"""


def run(body):
    src = BASE + js_fn("brRepos") + "\n" + js_fn("brPoll") + "\nconst R = {};\n" + body + \
        "\nprocess.stdout.write(JSON.stringify(R));"
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class BrPoll(unittest.TestCase):
    def test_repo_appearing_later_loads_once(self):
        R = run(r"""
brPoll(); brPoll(); R.empty = loads;
SESS = [{cwd: '/p/r/sub', repos: ['/p/r']}];
brPoll(); R.after = loads; R.repo = brRepo;
brPoll(); brPoll(); R.later = loads;
""")
        self.assertEqual([R["empty"], R["after"], R["repo"], R["later"]], [0, 1, "/p/r", 1])

    def test_other_view_or_popup_or_busy_skips(self):
        R = run(r"""
SESS = [{cwd: '/p/r', repos: ['/p/r']}];
mainView = 'sess'; brPoll();
mainView = 'br'; ISPOP = true; brPoll();
ISPOP = false; ISWP = true; brPoll();
ISWP = false; brBusy = 1; brPoll();
R.n = loads;
""")
        self.assertEqual(R["n"], 0)


if __name__ == "__main__":
    unittest.main()
