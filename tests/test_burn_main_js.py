"""Per-account burndown for a non-primary «Main account» (55b burnFor/burnMainDir, 55 svLive/svCapLine):
no main = the primary's BURN/QLAST as before; main = BURNM and main's window only, never the primary's numbers."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import i18n, jconst
from tests._node import node_e

FNS = ("acctList", "mainAcct", "mainAcctOk", "knQ", "burnMainDir", "burnFor", "svLive", "svCapLine")


def run(body):
    src = ("var document = {getElementById: () => null};\n"
           "let QLAST = null, ACCTS = [], STORE = {}, SV = null, BURNM = null, BURNM_DIR = '';\n"
           "let BURN = {ok: true, at: 1000, cur: {now_pct: 40, rate_pph: 60, reset: 99999999999, elapsed: 600},"
           " cap: {n: 3, avail_tpm: 2e6, per_tpm: 5e5, running: 1}};\n"
           "const UIS = {getItem: k => k in STORE ? STORE[k] : null};\n"
           + i18n() + "\n" + jconst("esc") + "\n" + "\n".join(js_fn(f) for f in FNS)
           + "\nconst R = {};\nLANG = 'en';\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"))
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class BurnMain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
const lv = () => { const l = svLive(); return l && {pct: l.pct, rate: l.rate, avg: l.avg}; };
QLAST = {q: {five_hour: {pct: 10, leftSec: 600}, accounts: [{label: 'work', five_hour: {pct: 33, leftSec: 1200}}]}};
R.one = [burnFor() === BURN, lv(), svCapLine()];
ACCTS = [{label: 'me', primary: true, dir: '/p'}, {label: 'work', dir: '/w'}];
R.none = [burnFor() === BURN, burnMainDir(), lv(), svCapLine()];
STORE.mbMainAcct = 'work';
R.dir = burnMainDir();
R.missing = [burnFor(), lv(), svCapLine()];
BURNM_DIR = '/w'; BURNM = {ok: false};
R.failed = [burnFor(), lv()];
BURNM = {ok: true, cur: {now_pct: 70, rate_pph: 120, elapsed: 600}, cap: {n: 1, avail_tpm: 1e6, per_tpm: 5e5, running: 0}};
R.main = [burnFor() === BURNM, lv(), svCapLine()];
BURNM_DIR = '/old'; R.stale = burnFor();
BURNM_DIR = '/w'; QLAST.q.accounts = []; R.miss = lv();
""")

    def test_no_main_is_primary(self):
        R = self.R
        self.assertTrue(R["one"][0])
        self.assertEqual(R["one"], R["none"][:1] + R["none"][2:])
        self.assertEqual(R["none"][1], "")
        self.assertEqual(R["one"][1], {"pct": 10, "rate": 1, "avg": 4})
        self.assertIn("3", R["one"][2])

    def test_main_never_uses_primary(self):
        R = self.R
        self.assertEqual(R["dir"], "/w")
        self.assertEqual(R["missing"][0], None)
        self.assertEqual(R["missing"][1], {"pct": 33, "rate": None, "avg": None})
        self.assertEqual(R["missing"][2], "")
        self.assertEqual(R["failed"], [None, {"pct": 33, "rate": None, "avg": None}])
        self.assertTrue(R["main"][0])
        self.assertEqual(R["main"][1], {"pct": 33, "rate": 2, "avg": 7})
        self.assertTrue(R["main"][2].startswith("1 "))
        self.assertIsNone(R["stale"])
        # main's quota row missing: no primary pct; BURNM's own now_pct fills in
        self.assertEqual(R["miss"], {"pct": 70, "rate": 2, "avg": 7})


if __name__ == "__main__":
    unittest.main()
