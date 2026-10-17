"""UI prefs store UIS (web/app-head.js): seeded from window.__UIP, debounced per-key delta POSTs, one-time localStorage
migration, no writes back to localStorage, and the «설정 초기화» click path (web/js/90b-mypref.js mpUiReset).
One node run; window/fetch/timers/localStorage are stubs (no clock, no network, no live browser data)."""
import json
import os
import shutil
import subprocess
import unittest
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SRC = r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
const ROOT = process.argv[1], head = fs.readFileSync(path.join(ROOT, 'web', 'app-head.js'), 'utf8');
const R = {};
function boot(uip, ls, s0, wd, search, ss){
  const posts = [], timers = new Map(), hide = [], st = {v: s0 || 200}; let tid = 0, lsWrites = 0;
  const m = Object.assign({}, ls || {});
  const LS = {get length(){ return Object.keys(m).length; }, key: i => Object.keys(m)[i] ?? null, getItem: k => k in m ? m[k] : null,
              setItem(){ lsWrites++; }, removeItem(){ lsWrites++; }, clear(){ lsWrites++; }};
  const c = {console, Proxy, JSON, Object, String, Promise,
    window: {addEventListener: (ev, f) => { if(ev === 'pagehide') hide.push(f); }, localStorage: LS, navigator: {webdriver: !!wd},
             location: {search: search || ''}, sessionStorage: ss},
    document: {documentElement: {dataset: {}}}, matchMedia: () => ({matches: false}),
    fetch: (url, o) => { posts.push({url, body: JSON.parse(o.body), keepalive: o.keepalive, method: o.method}); return Promise.resolve({ok: st.v < 300, status: st.v}); },
    setTimeout: (f) => { timers.set(++tid, f); return tid; }, clearTimeout: id => { timers.delete(id); }};
  if(uip !== 'UNDEF') c.window.__UIP = uip;
  vm.createContext(c); vm.runInContext(head, c);
  const run = () => { const fs2 = [...timers.values()]; timers.clear(); fs2.forEach(f => f()); };
  return {c, U: c.UIS, posts, run, hide, st, lsw: () => lsWrites, pending: () => timers.size};
}
// 1. seeded from __UIP: values readable in every form, _v hidden, nothing posted
let b = boot({mbTone: 'grey', 'sidereus.x': '1', _v: 1});
R.seed = [b.U.mbTone, b.U.getItem('sidereus.x'), b.U['sidereus.x'], b.U.getItem('nope'), b.U.nope === undefined, Object.keys(b.U).sort(),
          b.U.length, 'mbTone' in b.U, b.c.document.documentElement.dataset.tone, b.posts.length];
// 2. a burst of writes = one POST with the merged delta, after the debounce only
b.U.a = 1; b.U.setItem('b', '2'); delete b.U['sidereus.x']; b.U.a = '3'; b.U.setItem('mbTone', 'grey');
R.burstBefore = b.posts.length; R.pend = b.pending(); b.run();
R.burst = b.posts.map(p => [p.url, p.method, p.body]);
// unchanged value = no POST; pagehide flushes with keepalive
b.U.a = '3'; b.run(); R.same = b.posts.length;
b.U.c = 'x'; b.hide.forEach(f => f()); R.hide = [b.posts.length, b.posts[1].body, b.posts[1].keepalive, b.pending()];
// a large value flushes at once (keepalive is capped at 64 KB)
b.U.big = 'x'.repeat(20000); R.big = [b.posts.length, b.pending(), b.posts[2] && b.posts[2].keepalive];
R.lsw1 = b.lsw();
// 3. migration: __UIP null copies matching localStorage keys once, minus drafts and notification keys
b = boot(null, {mbTone: 'blue', 'sidereus.y': '{"a":1}', 'sidereus.rvnotes.p': 'draft', 'sidereus.notify': '{}', 'sidereus.osntf': '1',
                agPH: '300', dfW: '40', relPaView: 'flow', other: 'z', agPHx: '1', mbTheme: 'light'});
R.mig = [b.posts.length, b.posts[0] && b.posts[0].body, b.U.mbTone];
b.U.mbLang = 'en'; b.U.removeItem('agPH'); b.run(); b.hide.forEach(f => f());
R.lsw2 = b.lsw(); R.migPosts = b.posts.length;
// the next load has a file (_v set): no second migration
b = boot({_v: 1, mbTone: 'white'}, {mbTone: 'blue', 'sidereus.y': '1'});
R.again = [b.posts.length, b.U.getItem('sidereus.y'), b.U.mbTone];
// 4. server script failed (__UIP undefined): defaults, writes kept in memory, nothing posted
b = boot('UNDEF', {mbTone: 'grey'});
b.U.z = '1'; b.run(); b.hide.forEach(f => f());
R.down = [b.U.mbTone === undefined, b.U.z, b.posts.length, b.lsw()];
// 4b. automation page (navigator.webdriver): owner prefs readable, changes stay in memory, nothing posted (no migration either)
b = boot({mbMainAcct: 'a1', mbTone: 'grey'}, null, 200, true);
b.U.removeItem('mbMainAcct'); b.U.mbTone = 'blue'; b.U.big = 'x'.repeat(20000); b.run(); b.hide.forEach(f => f());
R.wd = [b.U.mbMainAcct === undefined, b.U.mbTone, b.posts.length, b.hide.length, b.lsw()];
b = boot(null, {mbTone: 'blue'}, 200, true); b.run(); R.wdMig = [b.posts.length, b.U.mbTone];
// 4c. ?nosave=1 (MCP browsers report webdriver=false): same as automation, and the flag survives in-app navigation
const SS = (() => { const m = {}; return {getItem: k => k in m ? m[k] : null, setItem: (k, v) => { m[k] = String(v); }, m}; })();
b = boot({mbTone: 'grey'}, null, 200, false, '?tour=0&nosave=1', SS);
b.U.mbTone = 'blue'; b.run(); b.hide.forEach(f => f());
R.ns = [b.U.mbTone, b.posts.length, b.hide.length, SS.m['sidereus.nosave']];
b = boot({mbTone: 'grey'}, null, 200, false, '?view=x', SS); b.U.mbTone = 'blue'; b.run(); R.nsNav = b.posts.length;
b = boot(null, {mbTone: 'blue'}, 200, false, '?nosave=1', SS); b.run(); R.nsMig = b.posts.length;
const SS2 = {getItem: () => null, setItem(){}};
b = boot({mbTone: 'grey'}, null, 200, false, '?nosave=10', SS2); b.U.mbTone = 'blue'; b.run(); R.nsOff = [b.posts.length, b.hide.length];
// 5. «설정 초기화»: confirm → POST reset once → UIS emptied, tab state cleared, reload; later writes never post
(async () => {
  b = boot({mbTone: 'grey', 'sidereus.q': '1'});
  const calls = [], c = b.c;
  Object.assign(c, {T: s => s, KE: (k) => k, esc: s => String(s), softErr(){}, confirm: () => true, paintCfg(){}, MPERR_SEEN: 0,
    postJSON: async (url, body) => { calls.push(['post', url, body]); return {ok: true}; },
    sessionStorage: {clear(){ calls.push(['ss']); }}, location: {reload(){ calls.push(['reload']); }}});
  vm.runInContext(fs.readFileSync(path.join(ROOT, 'web', 'js', '90b-mypref.js'), 'utf8') + ';this.ACTS = mpActs(); this.RESET = mpUiReset;', c);
  await c.RESET();
  R.reset = [calls, Object.keys(b.U).length, b.U.mbTone === undefined];
  b.U.after = '1'; b.run(); b.hide.forEach(f => f()); R.resetPosts = b.posts.length;
  // cancelled confirm = no request
  const b2 = boot({mbTone: 'grey'}), calls2 = [];
  Object.assign(b2.c, {T: s => s, KE: (k) => k, esc: s => String(s), softErr(){}, confirm: () => false, paintCfg(){},
    postJSON: async (url) => { calls2.push(url); return {ok: true}; }, sessionStorage: {clear(){}}, location: {reload(){ calls2.push('reload'); }}});
  vm.runInContext(fs.readFileSync(path.join(ROOT, 'web', 'js', '90b-mypref.js'), 'utf8') + ';this.RESET = mpUiReset;', b2.c);
  await b2.c.RESET();
  R.cancel = [calls2, b2.U.mbTone];
  // 6. refused (4xx) batch is dropped; network/5xx failure is requeued; values over 64 KB are never posted
  const tick = () => new Promise(r => setImmediate(r));
  let b3 = boot({}); b3.st.v = 400; b3.U.a = '1'; b3.run(); await tick(); await tick();
  b3.st.v = 200; b3.U.b = '2'; b3.run(); await tick();
  R.r400 = b3.posts.map(p => p.body);
  b3 = boot({}); b3.st.v = 500; b3.U.a = '1'; b3.run(); await tick(); await tick();
  b3.st.v = 200; b3.U.b = '2'; b3.run(); await tick();
  R.r500 = b3.posts.map(p => p.body);
  b3 = boot({}); b3.U.huge = 'x'.repeat(70000); b3.U.ok = '1'; b3.run(); await tick();
  R.huge = [b3.posts.map(p => p.body), b3.U.huge.length];
  // a refused migration still marks _v so it does not repeat on every load
  b3 = boot(null, {mbTone: 'blue'}, 400); await tick(); await tick();
  R.mig400 = b3.posts.map(p => p.body);
  process.stdout.write(JSON.stringify(R));
})().catch(e => { console.error(e); process.exit(1); });
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class UiPrefs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r = subprocess.run(node_e(SRC, ROOT), capture_output=True, text=True, timeout=30, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        cls.R = json.loads(r.stdout)

    def test_reads_from_uip(self):
        self.assertEqual(self.R["seed"], ["grey", "1", "1", None, True, ["mbTone", "sidereus.x"], 2, True, "grey", 0])

    def test_burst_is_one_post(self):
        self.assertEqual([self.R["burstBefore"], self.R["pend"]], [0, 1])
        self.assertEqual(self.R["burst"], [["/api/ui-prefs", "POST", {"set": {"a": "3", "b": "2"}, "del": ["sidereus.x"]}]])
        self.assertEqual(self.R["same"], 1)
        self.assertEqual(self.R["hide"], [2, {"set": {"c": "x"}, "del": []}, True, 0])
        self.assertEqual(self.R["big"], [3, 0, False])
        self.assertEqual(self.R["lsw1"], 0)

    def test_migration_once(self):
        n, body, tone = self.R["mig"]
        self.assertEqual(n, 1)
        self.assertEqual(body, {"set": {"mbTone": "blue", "sidereus.y": '{"a":1}', "agPH": "300", "dfW": "40",
                                        "mbTheme": "light", "_v": 1}, "del": []})   # relPaView (removed view) is not carried over
        self.assertEqual(tone, "white")   # head script turns mbTheme=light into mbTone=white (in UIS only)
        self.assertEqual(self.R["lsw2"], 0)   # localStorage is never written, even by later UIS writes
        self.assertEqual(self.R["migPosts"], 2)
        self.assertEqual(self.R["again"], [0, None, "white"])

    def test_failed_posts(self):
        self.assertEqual(self.R["r400"], [{"set": {"a": "1"}, "del": []}, {"set": {"b": "2"}, "del": []}])
        self.assertEqual(self.R["r500"], [{"set": {"a": "1"}, "del": []}, {"set": {"a": "1", "b": "2"}, "del": []}])
        self.assertEqual(self.R["huge"], [[{"set": {"ok": "1"}, "del": []}], 70000])
        self.assertEqual(self.R["mig400"], [{"set": {"mbTone": "blue", "_v": 1}, "del": []}, {"set": {"_v": 1}, "del": []}])

    def test_server_down(self):
        self.assertEqual(self.R["down"], [True, "1", 0, 0])

    def test_automation_never_posts(self):
        self.assertEqual(self.R["wd"], [True, "blue", 0, 0, 0])
        self.assertEqual(self.R["wdMig"], [0, "blue"])

    def test_nosave_query_never_posts(self):
        self.assertEqual(self.R["ns"], ["blue", 0, 0, "1"])
        self.assertEqual([self.R["nsNav"], self.R["nsMig"]], [0, 0])
        self.assertEqual(self.R["nsOff"], [1, 1])   # normal URL unchanged

    def test_reset_click(self):
        calls, n, gone = self.R["reset"]
        self.assertEqual(calls, [["post", "/api/ui-prefs/reset", {}], ["ss"], ["reload"]])
        self.assertEqual([n, gone, self.R["resetPosts"]], [0, True, 0])
        self.assertEqual(self.R["cancel"], [[], "grey"])


if __name__ == "__main__":
    unittest.main()
