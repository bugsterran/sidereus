"""«Pipelines» Watch: the «Working now» side list ends at the measured feed bottom (48k plWListMax / plWatchFit).
★1100x900 with the «Warnings» banner and 5 «hooks not connected» cards: the CSS calc(100vh - 110px) cap left the list
18px below #feed and the page scrolled 22-31px. Pure functions under node with stubs; no live files."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

_ALL = js_all()
CONSTS = "\n".join(re.search(r"^(?:const|let) %s[^\n]*$" % c, _ALL, re.M).group(0) for c in ("PLW_MIN", "PLWDRAG", "PLWUSER"))
FNS = "\n".join(js_fn(f) for f in ("plWListMax", "plWShares", "plWSizes", "plWApply", "plWSnap", "plWatchFit"))

# Feed bottom 900 (padding 8), list top below banner + cards at 420; the stack ends exactly at the feed bottom.
DOM = """
const SAVED = {}; function lsJson(k, d){ return k in SAVED ? SAVED[k] : d; }
const ST = {}, G = {style: {setProperty(k, v){ ST[k] = v; }, getPropertyValue(k){ return ST[k] || ''; }}, querySelector: () => null};
const OC = {style: {}, getBoundingClientRect: () => ({bottom: 890})};
const NL = {style: {}, getBoundingClientRect: () => ({top: 420})};
const FD = {scrollHeight: 0, clientHeight: 0, getBoundingClientRect: () => ({bottom: 900})};
var document = {querySelector(q){ return q.includes('plwov') ? OC : q.includes('plnl') ? NL : G; }, querySelectorAll: () => []};
var getComputedStyle = () => ({paddingBottom: '8px', borderBottomWidth: '0px'});
"""


def run(body):
    r = subprocess.run(node_e(CONSTS + "\n" + FNS + "\n" + DOM + body), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PlWatchListMax(unittest.TestCase):
    def test_list_max_is_the_room_down_to_the_feed_bottom(self):
        o = run("console.log(JSON.stringify([plWListMax(900, 8, 420), plWListMax(900.6, 0, 100.2), plWListMax(500, 8, 480), plWListMax(NaN, 0, 0)]));")
        self.assertEqual(o[0], 470)          # 900 - 8 - 420 - 2
        self.assertEqual(o[1], 798)          # floored, never rounded up past the edge
        self.assertEqual(o[2], 84)           # no room: the Running card minimum, not 0 or negative
        self.assertEqual(o[3], 0)            # unmeasurable: keep the CSS fallback

    def test_watch_fit_caps_the_list_at_the_feed_bottom(self):
        o = run("plWatchFit(G, FD, 700, 0); console.log(JSON.stringify([NL.style.maxHeight, NL.style.minHeight]));")
        self.assertEqual(o[0], "470px")      # the list never reaches past the feed bottom
        self.assertEqual(o[1], "470px")      # min (stack end 890 - 420) stays within the max


if __name__ == "__main__":
    unittest.main()
