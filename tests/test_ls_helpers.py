"""UI-pref wrappers (web/js/08-ui-kit.js lsGet/lsSet/lsDel/lsJson/lsSetJson) over UIS (app-head.js): a throwing store
returns the default and is counted under softErr('ls') — console.warn once per tag; a working store round-trips as before."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

STORE = """
const WARN = []; console.warn = (...a) => WARN.push(a.join(' '));
let THROW = false; const MEM = {};
const chk = () => { if(THROW) throw new Error('SecurityError'); };
globalThis.UIS = {
  getItem(k){ chk(); return k in MEM ? MEM[k] : null; },
  setItem(k, v){ chk(); MEM[k] = String(v); },
  removeItem(k){ chk(); delete MEM[k]; },
};
var SOFT_ERRS = {};
"""


def run(body):
    src = STORE + "\n".join(js_fn(f) for f in ("softErr", "lsGet", "lsSet", "lsDel", "lsJson", "lsSetJson")) \
        + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));"
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class LsHelpers(unittest.TestCase):
    def test_working_storage(self):
        R = run(r"""
R.miss = [lsGet('a', 'd'), lsGet('a', null), lsJson('j', {x: 1})];
R.set = lsSet('a', 5); R.a = lsGet('a', 'd'); R.raw = MEM.a;
R.sj = lsSetJson('j', {w: 3}); R.j = lsJson('j', {}); R.jraw = MEM.j;
MEM.n = 'null'; R.jnull = lsJson('n', 'dflt');
R.del = lsDel('a'); R.gone = lsGet('a', 'd');
R.errs = Object.keys(SOFT_ERRS);
""")
        self.assertEqual(R["miss"], ["d", None, {"x": 1}])
        self.assertEqual([R["set"], R["a"], R["raw"]], [True, "5", "5"])
        self.assertEqual([R["sj"], R["j"], R["jraw"]], [True, {"w": 3}, '{"w":3}'])
        self.assertEqual(R["jnull"], "dflt")
        self.assertEqual([R["del"], R["gone"]], [True, "d"])
        self.assertEqual(R["errs"], [])

    def test_throwing_storage(self):
        R = run(r"""
THROW = true;
R.get = lsGet('a', 'd'); R.n1 = SOFT_ERRS.ls.n; R.w1 = WARN.length;
R.json = lsJson('j', {x: 1}); R.set = lsSet('a', '1'); R.sj = lsSetJson('j', {}); R.del = lsDel('a');
R.n = SOFT_ERRS.ls.n; R.w = WARN.length; R.msg = SOFT_ERRS.ls.msg;
THROW = false; MEM.bad = '{oops'; R.corrupt = lsJson('bad', []); R.n2 = SOFT_ERRS.ls.n;
const cyc = {}; cyc.self = cyc; R.cyc = lsSetJson('c', cyc); R.cycStored = 'c' in MEM;
""")
        self.assertEqual([R["get"], R["n1"], R["w1"]], ["d", 1, 1])
        self.assertEqual([R["json"], R["set"], R["sj"], R["del"]], [{"x": 1}, False, False, False])
        self.assertEqual([R["n"], R["w"], R["msg"]], [5, 1, "SecurityError"])   # one count per failed call, one warn
        self.assertEqual([R["corrupt"], R["n2"]], [[], 6])
        self.assertEqual([R["cyc"], R["cycStored"]], [False, False])


if __name__ == "__main__":
    unittest.main()
