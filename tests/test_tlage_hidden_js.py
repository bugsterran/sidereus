"""Timeline age ticker (web/js/70-timeline-state.js tlAgeTick): a hidden tab neither writes #tlage nor polls;
the first visible tick reloads because tlAt went stale. setInterval/clock are stubbed (no real timers)."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

BASE = r"""
let cb = null; const setInterval = f => { cb = f; return 1; }; const clearInterval = () => {};
let NOW = 100000; const Date = {now: () => NOW};
const el = {textContent: ''};
var document = {hidden: true, getElementById: id => id === 'tlage' ? el : null};
const AGO = s => s + ' ago', U = (n, u) => n + u, T = s => s;
let tlAt = 0, tlAuto = 30, mainView = 'time', loads = 0, tlAgeTimer = 0;
const loadTl = () => { loads++; tlAt = NOW; };
"""


def run(body):
    src = BASE + js_fn("tlAgeTick") + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));"
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TlAgeHidden(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
tlAgeTick();
for(let i = 0; i < 120; i++){ NOW += 1000; cb(); }
R.hidden = [loads, el.textContent];
document.hidden = false; NOW += 1000; cb();
R.visible = [loads, el.textContent !== ''];
""")

    def test_hidden_tab_does_not_poll_or_write(self):
        self.assertEqual(self.R["hidden"], [0, ""])

    def test_first_visible_tick_reloads(self):
        self.assertEqual(self.R["visible"], [1, True])
