"""Saver switch sync: a save drops the /api/state body cache, saver actions return the save promise
(cfgBind refocuses after the async repaint), and svSwSync ignores a poll body older than the saved value."""
import json
import re
import shutil
import subprocess
import types
import unittest

from tests._load import sidereus, js_all, js_fn
from tests.test_saver_quota_js import jconst
from tests._node import node_e


class StateCacheClear(unittest.TestCase):
    def setUp(self):
        self.st = sidereus("state")
        self.rp = sidereus("routes_post")
        self.calls = []
        self.orig = (self.st.state, self.st.time, self.rp.saver_set)
        self.st.state = lambda since, nc: self.calls.append((since, nc)) or {"n": len(self.calls)}
        self.st.time = types.SimpleNamespace(monotonic=lambda: 1000.0)   # frozen clock: TTL never expires on its own
        self.rp.saver_set = lambda req: {"ok": True, "switch": {"mode": "auto"}}
        self.st.state_cache_clear()

    def tearDown(self):
        self.st.state, self.st.time, self.rp.saver_set = self.orig
        self.st.state_cache_clear()

    def _post(self):
        sent = []
        h = types.SimpleNamespace(headers={}, _body_json=lambda n, d: {"mode": "auto"},
                                  _send=lambda code, body, ct: sent.append(code))
        self.rp._PostRoutes._p_saver_set(h, None)
        return sent

    def test_rebuilt_after_saver_set(self):
        self.st._state_body(0, 50)
        self.st._state_body(0, 50)
        self.assertEqual(len(self.calls), 1)            # cached inside the TTL
        self.assertEqual(self._post(), [200])
        body, _ = self.st._state_body(0, 50)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(json.loads(body), {"n": 2})

    def test_failed_save_keeps_cache(self):
        self.rp.saver_set = lambda req: {"ok": False, "err": "x"}
        self.st._state_body(0, 50)
        self.assertEqual(self._post(), [400])
        self.st._state_body(0, 50)
        self.assertEqual(len(self.calls), 1)


JS_BASE = """
var NOW = 1e6; Date.now = () => NOW;
var EL = {svpt: {value: '12:30'}, svgn: {value: '40'}};
var document = {getElementById: id => EL[id] || null, activeElement: null};
var T = s => s, softErr = () => {}, buildSaver = () => {}, buildSbar = () => {}, svOkLine = () => {};
var PAINTS = 0; function paintCfg(){ PAINTS++; }
function mpActs(){ return {}; }
var POSTED = []; async function postJSON(u, b){ POSTED.push(b); return {ok: true, switch: Object.assign({mode: 'auto', limit: 'advise'}, b), saver: {on: false}}; }
let SVSW = {mode: 'auto', limit: 'advise'}, SVST = {on: false}, SVERR = '', SVPACE = false, SVOK = 0, SVHOLD = null;
"""


def run_js(body):
    sv_set = re.search(r"^async function svSet\(.*?^}", js_all(), re.S | re.M).group(0)   # js_fn matches plain `function` only
    src = (JS_BASE + jconst("SV_LIM") + "\n" + sv_set + "\n" + "\n".join(js_fn(f) for f in ("svSwSync", "svLimSet", "cfgActs"))
           + "\nconst R = {};\n(async () => {\n" + body + "\nprocess.stdout.write(JSON.stringify(R));\n})();")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SaverJs(unittest.TestCase):
    def test_actions_return_thenable(self):
        R = run_js("""
const a = cfgActs(), th = p => !!(p && typeof p.then === 'function');
const ps = [a.svl('warn'), a.svm('off'), a.svm('on2'), a.svp('set'), a.svp('clear'), a.svg('n')];
R.th = ps.map(th); await Promise.all(ps); R.posted = POSTED.length;
""")
        self.assertEqual(R["th"], [True] * 6)
        self.assertEqual(R["posted"], 6)

    def test_sync_ignores_older_body(self):
        R = run_js("""
await svLimSet('warn');
const p0 = PAINTS;
svSwSync({mode: 'auto', limit: 'advise'}, {on: false});   // poll body built before the save
R.kept = SVSW.limit; R.painted = PAINTS - p0;
svSwSync({mode: 'auto', limit: 'warn'}, {on: false});     // matches the saved value: accepted
R.match = SVSW.limit;
NOW += 3500;
svSwSync({mode: 'auto', limit: 'block'}, {on: false});    // after the hold a CLI change still arrives
R.later = SVSW.limit;
""")
        self.assertEqual(R["kept"], "warn")
        self.assertEqual(R["painted"], 0)
        self.assertEqual(R["match"], "warn")
        self.assertEqual(R["later"], "block")


if __name__ == "__main__":
    unittest.main()
