"""alarmPlace (web/js/15-alarms.js): a saved width never pushes the closed popover off-screen. Stubbed geometry."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


def place(inner_w, saved_w, bell_right):
    """Returns [left, right edge, maxWidth] after alarmPlace() on a closed popover (offsetWidth 0)."""
    src = ("const a = {offsetWidth: 0, style: {width: " + json.dumps(saved_w) + "}};\n"
           "const bell = {getBoundingClientRect: () => ({left: " + str(bell_right - 30) + ", right: " + str(bell_right)
           + ", top: 10, bottom: 40})};\n"
           "const document = {getElementById: id => id === 'alarm' ? a : id === 'bell' ? bell : {}};\n"
           "const getComputedStyle = () => ({position: 'fixed'});\n"
           "const innerWidth = " + str(inner_w) + ", innerHeight = 800;\n"
           + js_fn("popAnchor") + "\n" + js_fn("alarmPlace") + "\n"
           "alarmPlace();\n"
           "const l = parseFloat(a.style.left), w = Math.min(parseFloat(a.style.width) || 420, parseFloat(a.style.maxWidth));\n"
           "process.stdout.write(JSON.stringify([l, l + w, parseFloat(a.style.maxWidth)]));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class AlarmPlace(unittest.TestCase):
    def test_huge_saved_width_stays_on_screen(self):
        for iw in (900, 1100, 1440):
            l, right, mw = place(iw, "1056px", iw - 14)
            self.assertGreaterEqual(l, 12, iw)
            self.assertLessEqual(right, iw - 14, iw)
            self.assertEqual(mw, iw - 14 - 12)

    def test_default_width_right_aligned_to_bell(self):
        l, right, _ = place(1100, "", 1086)
        self.assertEqual((l, right), (666, 1086))

    def test_rail_bell_opens_right_of_rail_upward(self):
        src = ("const a = {offsetWidth: 0, style: {width: '1056px'}};\n"
               "const rail = {getBoundingClientRect: () => ({right: 56})};\n"
               "const bell = {closest: s => s === '#rail' ? rail : null,\n"
               "  getBoundingClientRect: () => ({left: 8, right: 48, top: 700, bottom: 740})};\n"
               "const document = {getElementById: id => id === 'alarm' ? a : id === 'bell' ? bell : {}};\n"
               "const getComputedStyle = () => ({position: 'fixed'});\n"
               "const innerWidth = 900, innerHeight = 800;\n"
               + js_fn("popAnchor") + "\n" + js_fn("alarmPlace") + "\n"
               "alarmPlace(); process.stdout.write(JSON.stringify(a.style));")
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        st = json.loads(r.stdout)
        self.assertEqual((st["left"], st["top"], st["bottom"]), ("64px", "auto", "60px"))
        self.assertEqual(st["maxWidth"], "824px")           # 900 - 64 - 12
        self.assertEqual(st["maxHeight"], "684px")          # bell bottom 740 - 56
        self.assertEqual(st["width"], "1056px")             # saved width kept, max-width caps it


if __name__ == "__main__":
    unittest.main()
