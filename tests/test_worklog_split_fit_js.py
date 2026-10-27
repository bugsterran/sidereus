"""Work-log split view (web/js/35b-worklog-view.js): the pane grid height is px, so a resize of #wkmb must refit it
via wtFitSplit without a repaint. Fake DOM box + stubbed observers; one node run per case."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

FNS = ("wtFitSplit", "wkPinInit")

PRE = """
let wtSplit = true, wkAtEnd = true, wkTop = 0, repaints = 0;
function workPaint(){ repaints++; }
const ROS = [];
class ResizeObserver { constructor(f){ this.f = f; ROS.push(this); } observe(){} }
class MutationObserver { constructor(f){} observe(){} }
// box: clientHeight = window-driven, scrollHeight = content (strip + grid + 10px margin, plus a stray 0..n px)
function mkBox(ch, extra){
  const sp = {style: {height: '600px'}}, st = {offsetHeight: 40};
  return {clientHeight: ch, scrollTop: 0, sp,
    get scrollHeight(){ return Math.max(this.clientHeight, 40 + parseFloat(sp.style.height) + 10 + extra); },
    querySelector(s){ return s === '.wsp' ? sp : s === '.wtb' ? st : null; },
    addEventListener(){} };
}
let BOX = null;
function wkBox(){ return BOX; }
"""


def run(body):
    src = PRE + "\n".join(js_fn(f) for f in FNS) + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));"
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node missing")
class SplitFit(unittest.TestCase):
    def test_resize_refits_grow_and_shrink_without_repaint(self):
        R = run("BOX = mkBox(700, 0); wkPinInit();"
                "BOX.clientHeight = 1000; ROS.forEach(o => o.f()); R.grow = BOX.sp.style.height; R.growOver = BOX.scrollHeight - BOX.clientHeight;"
                "BOX.clientHeight = 500; ROS.forEach(o => o.f()); R.shrink = BOX.sp.style.height; R.shrinkOver = BOX.scrollHeight - BOX.clientHeight;"
                "R.repaints = repaints;")
        self.assertEqual(R["grow"], "950px")
        self.assertEqual(R["shrink"], "450px")
        self.assertEqual((R["growOver"], R["shrinkOver"], R["repaints"]), (0, 0, 0))

    def test_single_view_untouched(self):
        R = run("wtSplit = false; BOX = mkBox(1000, 0); wkPinInit(); ROS.forEach(o => o.f()); R.h = BOX.sp.style.height;")
        self.assertEqual(R["h"], "600px")

    def test_leftover_overflow_taken_back(self):
        R = run("BOX = mkBox(800, 7); wtFitSplit(BOX); R.h = BOX.sp.style.height; R.over = BOX.scrollHeight - BOX.clientHeight;")
        self.assertEqual((R["h"], R["over"]), ("743px", 0))


PIN_PRE = """
let wkOn = true, wtSplit = false, wkAtEnd = true, wkTop = 0, H = 2000;
const wtShown = () => ['k'];
const BOX = {clientHeight: 500, scrollTop: 0, get scrollHeight(){ return H; }};
function wkBox(){ return BOX; }
function workPaint(){ H += 1781; }   // late git diff grows the log (measured 13913 -> 15694)
"""


def run_pin(body):
    src = PIN_PRE + js_fn("agentRepaint") + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));"
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node missing")
class RepaintStaysAtEnd(unittest.TestCase):
    def test_reader_at_end_stays_at_end(self):
        R = run_pin("BOX.scrollTop = H - BOX.clientHeight; agentRepaint();"
                    "R.gap = H - BOX.scrollTop - BOX.clientHeight; R.end = wkAtEnd;")
        self.assertLessEqual(R["gap"], 0)
        self.assertTrue(R["end"])

    def test_reader_scrolled_up_keeps_position(self):
        R = run_pin("BOX.scrollTop = 300; agentRepaint(); R.top = BOX.scrollTop;")
        self.assertEqual(R["top"], 300)

    def test_split_view_left_to_panes(self):
        R = run_pin("wtSplit = true; BOX.scrollTop = H - BOX.clientHeight; const t = BOX.scrollTop; agentRepaint(); R.same = BOX.scrollTop === t;")
        self.assertTrue(R["same"])


if __name__ == "__main__":
    unittest.main()
