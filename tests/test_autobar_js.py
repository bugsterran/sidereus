"""Automation banner (98c-automation-banner.js): shown only under webdriver, ?autobar=0 hides it."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


def run(body):
    code = "const softErr = () => {};\nconst R = {};\n" + js_fn("autobarShould") + "\n" + body + "\nprocess.stdout.write(JSON.stringify(R));"
    r = subprocess.run(node_e(code), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class Autobar(unittest.TestCase):
    def test_should(self):
        R = run("R.user = autobarShould(false, ''); R.userQ = autobarShould(false, '?autobar=1');"
                "R.wd = autobarShould(true, ''); R.wdTour = autobarShould(true, '?tour=1');"
                "R.hidden = autobarShould(true, '?cwd=x&autobar=0'); R.bad = autobarShould(true, undefined);")
        self.assertEqual(R, {"user": False, "userQ": False, "wd": True, "wdTour": True, "hidden": False, "bad": True})


if __name__ == "__main__":
    unittest.main()
