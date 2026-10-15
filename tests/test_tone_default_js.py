"""Tone default: nothing stored = «system» (follow the OS), and web/app-head.js (before first paint) agrees with
tonePref() (web/js/90-settings.js) so the page does not flash. A stored choice still wins. One node run per case."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

HEAD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "app-head.js")


def run(stored, os_light):
    """Returns [tonePref(), html data-theme, html data-tone] for a stored-prefs dict (window.__UIP) and an OS light flag."""
    with open(HEAD, encoding="utf-8") as f:
        head = f.read()
    src = ("const window = {__UIP: " + json.dumps(stored) + ", addEventListener(){}};\n"
           "const matchMedia = q => ({ matches: " + ("true" if os_light else "false") + " });\n"
           "const document = { documentElement: { dataset: {} } };\n"
           + head + "\n" + js_fn("tonePref") + "\n"
           "process.stdout.write(JSON.stringify([tonePref(), document.documentElement.dataset.theme,"
           " document.documentElement.dataset.tone]));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ToneDefault(unittest.TestCase):
    def test_nothing_stored_follows_os(self):
        self.assertEqual(run({}, True)[:2], ["system", "light"])
        self.assertEqual(run({}, False), ["system", "dark", "black"])

    def test_unknown_value_is_system(self):
        self.assertEqual(run({"mbTone": "nope"}, True)[:2], ["system", "light"])

    def test_stored_choice_wins(self):
        self.assertEqual(run({"mbTone": "black"}, True), ["black", "dark", "black"])
        self.assertEqual(run({"mbTone": "white"}, False)[:2], ["white", "light"])
        self.assertEqual(run({"mbTone": "grey"}, True), ["grey", "dark", "grey"])

    def test_system_in_os_dark_keeps_last_dark_tone(self):
        self.assertEqual(run({"mbToneDk": "blue"}, False), ["system", "dark", "blue"])


if __name__ == "__main__":
    unittest.main()
