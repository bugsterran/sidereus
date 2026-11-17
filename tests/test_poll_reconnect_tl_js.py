"""Reconnect refreshes a stale Timeline error note (web/js/95-poll.js pollReconnTl): tlErr is set only by a failed loadTl,
and the next unforced loadTl waits for tlAuto (never under «Manual»), so the reconnect branch forces one fetch."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

BASE = r"""
let tlErr = '', mainView = 'time', CALLS = [];
var document = {hidden: false};
function loadTl(force){ CALLS.push(force === true); }
function softErr(){}
"""


def run(body):
    js = (BASE + js_fn("pollReconnTl") + "\nconst R = {};\n" + body
          + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PollReconnectTl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
tlErr = 'Could not fetch — showing the last data received'; pollReconnTl(); R.err = CALLS.slice();
CALLS = []; tlErr = ''; pollReconnTl(); R.clear = CALLS.slice();
CALLS = []; tlErr = 'x'; mainView = 'chat'; pollReconnTl(); R.other = CALLS.slice();
CALLS = []; mainView = 'time'; document.hidden = true; pollReconnTl(); R.hidden = CALLS.slice();
""")

    def test_error_note_forces_one_fetch(self):
        self.assertEqual(self.R["err"], [True])

    def test_no_fetch_without_error(self):
        self.assertEqual(self.R["clear"], [])

    def test_no_fetch_off_timeline_or_hidden(self):
        self.assertEqual(self.R["other"], [])
        self.assertEqual(self.R["hidden"], [])

    def test_reconnect_branch_calls_it(self):
        poll = re.search(r"^async function poll\(.*?^}$", js_all(), re.M | re.S).group(0)
        self.assertRegex(poll, r"if\(wasDown\)\{[^}]*pollReconnTl\(\)")


if __name__ == "__main__":
    unittest.main()
