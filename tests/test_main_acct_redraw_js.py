"""«Main account» switch (90b mpMainAcctRedraw -> 95 pollMainRedraw): the quota modal (#burn, #saver) repaints
from the last poll's saver fields at once, with SV set to the new main's view; before any poll nothing throws."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

FNS = ("acctList", "mainAcct", "mainAcctOk", "saverViewFor", "svViewSet", "pollMainRedraw", "mpMainAcctRedraw")


def run(body):
    src = ("let ACCTS = [], STORE = {}, SV = null, LASTS = null, CALLS = [];\n"
           "const UIS = {getItem: k => k in STORE ? STORE[k] : null};\n"
           "const softErr = (w, e) => { throw e; };\n"
           "const buildQuota = (u, q) => CALLS.push(['quota', u && u.u, q && q.q]);\n"
           "const burnTick = () => CALLS.push('tick'), buildBurn = () => CALLS.push('burn');\n"
           "const buildSaver = sv => CALLS.push(['saver', sv && sv.who, SV && SV.who]);\n"
           "const buildSbar = () => CALLS.push(['sbar', SV && SV.who]), sesdrBadge = () => CALLS.push('badge');\n"
           + "\n".join(js_fn(f) for f in FNS)
           + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class MainAcctRedraw(unittest.TestCase):
    def test_no_snapshot(self):
        R = run("mpMainAcctRedraw(); R.calls = CALLS; R.sv = SV;")
        self.assertEqual(R["calls"], [["sbar", None], "badge"])
        self.assertIsNone(R["sv"])

    def test_switch_repaints_modal(self):
        R = run(r"""
ACCTS = [{label: 'me', primary: true}, {label: 'work'}];
LASTS = {saverView: {who: 'prim'}, saverViews: {work: {who: 'work'}}, saver: {who: 'eff'}, usage: {u: 1}, quota: {q: 2}};
SV = {who: 'prim'};
STORE.mbMainAcct = 'work'; mpMainAcctRedraw(); R.calls = CALLS; R.sv = SV;
CALLS = []; STORE.mbMainAcct = ''; mpMainAcctRedraw(); R.back = SV;
""")
        self.assertEqual(R["calls"], [["quota", 1, 2], "tick", "burn", ["saver", "eff", "work"], ["sbar", "work"], "badge"])
        self.assertEqual(R["sv"], {"who": "work"})
        self.assertEqual(R["back"], {"who": "prim"})

    def test_main_without_view(self):
        R = run(r"""
ACCTS = [{label: 'me', primary: true}, {label: 'side'}];
LASTS = {saverView: {who: 'prim'}, saverViews: {}, saver: null, usage: null, quota: null};
STORE.mbMainAcct = 'side'; mpMainAcctRedraw(); R.calls = CALLS; R.sv = SV;
""")
        self.assertEqual(R["calls"], [["quota", None, None], "tick", "burn", ["saver", None, None], ["sbar", None], "badge"])
        self.assertIsNone(R["sv"])


class NoDuplicateTopLevelFunctions(unittest.TestCase):
    # ⚠The page is one script: a second top-level `function x` silently replaces the first (svSet in 90-settings).
    def test_unique(self):
        import re
        from collections import Counter
        from tests._load import js_all
        names = re.findall(r"^(?:async\s+)?function\*?\s*([A-Za-z_$][\w$]*)\s*\(", js_all(), re.M)
        self.assertEqual([n for n, c in Counter(names).items() if c > 1], [])


if __name__ == "__main__":
    unittest.main()
