"""R4: plStrip (00-core.js) also strips a leading [pl-none:<cat>] tag. Pure function; no live files."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


def _strip(s):
    code = js_fn("plStrip") + "\nconsole.log(JSON.stringify(plStrip(%s)));" % json.dumps(s)
    r = subprocess.run(node_e(code), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PlStripNone(unittest.TestCase):
    def test_none_tag(self):
        self.assertEqual(_strip("[pl-none:explore] x"), "x")
        self.assertEqual(_strip("general-purpose: [pl-none:small-fix] fix it"), "general-purpose: fix it")

    def test_existing_forms_kept(self):
        self.assertEqual(_strip("[pl:a/B] y"), "y")
        self.assertEqual(_strip("[pl-skip:a/B] y"), "y")
        self.assertEqual(_strip("[pl-nonex:a] y"), "[pl-nonex:a] y")


if __name__ == "__main__":
    unittest.main()
