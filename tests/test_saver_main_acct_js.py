"""95-poll saverViewFor: the saver verdict follows the «Main account»; a non-primary main never gets the primary's view."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


def run(body):
    src = ("let ACCTS = [], STORE = {};\nconst UIS = {getItem: k => k in STORE ? STORE[k] : null};\n"
           + "\n".join(js_fn(f) for f in ("acctList", "mainAcct", "mainAcctOk", "saverViewFor"))
           + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SaverMainAcct(unittest.TestCase):
    def test_cases(self):
        R = run(r"""
ACCTS = [{label: 'me', primary: true}, {label: 'work'}, {label: 'side'}];
const s = {saverView: {who: 'prim'}, saverViews: {work: {who: 'work'}}};
R.none = saverViewFor(s);
STORE.mbMainAcct = 'me'; R.prim = saverViewFor(s);
STORE.mbMainAcct = 'work'; R.work = saverViewFor(s);
STORE.mbMainAcct = 'side'; R.side = saverViewFor(s);
R.noMap = saverViewFor({saverView: {who: 'prim'}});
STORE.mbMainAcct = ''; R.empty = saverViewFor({});
""")
        self.assertEqual(R["none"], {"who": "prim"})
        self.assertEqual(R["prim"], {"who": "prim"})
        self.assertEqual(R["work"], {"who": "work"})
        self.assertIsNone(R["side"])
        self.assertIsNone(R["noMap"])
        self.assertIsNone(R["empty"])


if __name__ == "__main__":
    unittest.main()
