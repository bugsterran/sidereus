"""Timeline tab dot (92 buildMv): lit by running subagents and by main sessions working without one.
Runs buildMv under node with stubbed globals; no live files."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

STUB = """
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const T = s => s; let HTML = '';
const el = { contains(){ return false; }, querySelectorAll(){ return []; } };
const document = { getElementById(){ return el; }, activeElement: null };
let wtabs = [], wtData = {}, mainView = 'pipe', STATE_IN = false, FEATS = {}, SESS = [];
const TAB_FEAT = {};
function tabIco(){ return ''; } function mvLab(k){ return k; } function mpTabs(){ return {order: ['time', 'pipe'], hide: []}; }
function plKnown(){ return {}; } function plLiveProjs(){ return {}; } function plLiveN(){ return 0; } function plMem(){ return {}; }
function plLiveDot(){ return ''; } function plLoadProjs(){} function chatNew(){ return 0; } function lsGet(k, d){ return d; } function lsSet(){}
function softErr(){} function railTitle(){} function setMainView(){} function mvKey(){}
function setHtml(e, h){ HTML = h; return true; }
"""


def dot(sess):
    js = STUB + js_fn("wfRunning") + js_fn("waitOnLabel") + js_fn("buildMv") +"\nSESS = " + json.dumps(sess) + "; buildMv();" \
        "const m = HTML.match(/data-mv=\"time\"[^]*?<\\/button>/)[0]; const t = m.match(/class=mvdot title=\"([^\"]*)\"/);" \
        "console.log(JSON.stringify(t ? t[1] : null));"
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TimelineTabDot(unittest.TestCase):
    def test_main_session_working_lights_dot(self):
        self.assertEqual(dot([{"state": "think", "ageSec": 5, "sub": []}]), "{n} sessions working".replace("{n}", "1"))

    def test_subagents_and_sessions_both_named(self):
        t = dot([{"state": "tool", "ageSec": 5, "sub": [{}, {}]}])
        self.assertEqual(t, "2 subagents running · 1 sessions working")

    def test_waiting_on_background_command_lights_dot(self):
        # A turn ended while a background shell build runs: the session is working, not idle (even past 600s).
        self.assertEqual(dot([{"state": "wait", "ageSec": 900, "sub": [], "bgs": [{"lab": "Bash", "min": 4}]}]),
                         "1 sessions working")

    def test_idle_or_stale_stays_dark(self):
        self.assertIsNone(dot([{"state": "wait", "ageSec": 5, "sub": []}, {"state": "think", "ageSec": 900, "sub": []}]))


if __name__ == "__main__":
    unittest.main()
