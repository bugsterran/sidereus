"""Per-tab view state (web/js/08 tabRead/tabWrite): this tab's sessionStorage wins, UIS (server prefs) is the new-tab default,
writes go to both, a throwing store is skipped. One node run with fake stores."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TabState(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src = "\n".join(js_fn(f) for f in ("tabRead", "tabWrite")) + r"""
const softErr = () => {};
const mk = o => ({ d: Object.assign({}, o), getItem(k){ return k in this.d ? this.d[k] : null; },
                   setItem(k, v){ this.d[k] = String(v); }, removeItem(k){ delete this.d[k]; } });
const bad = { getItem(){ throw new Error('x'); }, setItem(){ throw new Error('x'); }, removeItem(){ throw new Error('x'); } };
const R = {};
R.own = tabRead(mk({ v: 'struct' }), mk({ v: 'chat' }), 'v');
R.fresh = tabRead(mk({}), mk({ v: 'chat' }), 'v');
R.none = tabRead(mk({}), mk({}), 'v');
R.nullss = tabRead(null, mk({ v: 'chat' }), 'v');
R.badss = tabRead(bad, mk({ v: 'chat' }), 'v');
R.empty = tabRead(mk({ v: '' }), mk({ v: 'chat' }), 'v');
const a = mk({}), b = mk({});
R.n = tabWrite(a, b, 'v', 'br'); R.a = a.d; R.b = b.d;
R.nbad = tabWrite(bad, b, 'v', 'hist'); R.b2 = Object.assign({}, b.d);
R.ndel = tabWrite(a, b, 'v', null); R.a3 = a.d; R.b3 = b.d;
const t1 = mk({}), t2 = mk({}), ls = mk({});
tabWrite(t1, ls, 'v', 'time'); tabWrite(t2, ls, 'v', 'token');
R.tab1 = tabRead(t1, ls, 'v'); R.tab2 = tabRead(t2, ls, 'v'); R.tab3 = tabRead(mk({}), ls, 'v');
// the shared layer is UIS, never localStorage
globalThis.UIS = mk({ v: 'pipe' }); globalThis.sessionStorage = mk({}); globalThis.localStorage = mk({ v: 'stale' });
const st = tabStores(); R.layer = [st[0] === sessionStorage, st[1] === UIS];
"""
        src += "\n".join(js_fn(f) for f in ("tabStores", "tabGet", "tabSet")) + r"""
R.get = tabGet('v', 'd'); tabSet('w', 'br'); R.w = [UIS.d.w, sessionStorage.d.w, 'w' in localStorage.d];
process.stdout.write(JSON.stringify(R));
"""
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        cls.R = json.loads(r.stdout)

    def test_tab_value_wins(self):
        self.assertEqual(self.R["own"], "struct")
        self.assertEqual(self.R["empty"], "")                          # a stored empty string is still this tab's choice

    def test_new_tab_falls_back_to_shared(self):
        self.assertEqual(self.R["fresh"], "chat")
        self.assertIsNone(self.R["none"])
        self.assertEqual(self.R["nullss"], "chat")
        self.assertEqual(self.R["badss"], "chat")

    def test_write_both_and_delete(self):
        self.assertEqual(self.R["n"], 2)
        self.assertEqual(self.R["a"], {})                              # deleted afterwards (same object)
        self.assertEqual(self.R["nbad"], 1)
        self.assertEqual(self.R["b2"], {"v": "hist"})
        self.assertEqual(self.R["ndel"], 2)
        self.assertEqual(self.R["b3"], {})

    def test_shared_layer_is_uis(self):
        self.assertEqual(self.R["layer"], [True, True])
        self.assertEqual(self.R["get"], "pipe")
        self.assertEqual(self.R["w"], ["br", "br", False])

    def test_two_tabs_keep_their_own_view(self):
        self.assertEqual((self.R["tab1"], self.R["tab2"], self.R["tab3"]), ("time", "token", "token"))


if __name__ == "__main__":
    unittest.main()
