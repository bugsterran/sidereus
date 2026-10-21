"""UI prefs store UIS (web/app-head.js): seeded from window.__UIP, debounced per-key delta POSTs, one-time localStorage
migration, no writes back to localStorage, the «Reset display settings» click path (web/js/90b-mypref.js mpUiReset),
and cross-tab sync: patch(), pull() on a BroadcastChannel ping or a changed /api/state uiRev (web/js/95-poll.js).
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
// Shared BroadcastChannel hub: a message reaches every other channel of the same name.
function hubOf(){ const chans = [], sent = [];
  class BC { constructor(n){ this.name = n; this.onmessage = null; chans.push(this); }
    postMessage(d){ sent.push(d); chans.filter(x => x !== this && x.name === this.name && x.onmessage).forEach(x => x.onmessage({data: d})); }
    close(){ const i = chans.indexOf(this); if(i >= 0) chans.splice(i, 1); } }
  return {BC, sent}; }
function boot(uip, ls, s0, wd, search, ss, o2){
  o2 = o2 || {};
  const posts = [], gets = [], timers = new Map(), hide = [], st = {v: s0 || 200, reply: o2.reply || null, remote: o2.remote || null}; let tid = 0, lsWrites = 0;
  const m = Object.assign({}, ls || {});
  const LS = {get length(){ return Object.keys(m).length; }, key: i => Object.keys(m)[i] ?? null, getItem: k => k in m ? m[k] : null,
              setItem(){ lsWrites++; }, removeItem(){ lsWrites++; }, clear(){ lsWrites++; }};
  const c = {console, Proxy, JSON, Object, String, Promise,
    window: {addEventListener: (ev, f) => { if(ev === 'pagehide') hide.push(f); }, localStorage: LS, navigator: {webdriver: !!wd},
             location: {search: search || ''}, sessionStorage: ss},
    document: {documentElement: {dataset: {}}}, matchMedia: () => ({matches: false}),
    fetch: (url, o) => {
      if(!o || o.method !== 'POST'){ gets.push(url); const v = typeof st.remote === 'function' ? st.remote() : st.remote; return Promise.resolve({ok: true, status: 200, json: () => Promise.resolve(v)}); }
      const body = JSON.parse(o.body); posts.push({url, body, keepalive: o.keepalive, method: o.method});
      const rp = typeof st.reply === 'function' ? st.reply(body) : st.reply;
      return Promise.resolve(Object.assign({ok: st.v < 300, status: st.v}, rp ? {json: () => Promise.resolve(rp)} : {})); },
    setTimeout: (f) => { timers.set(++tid, f); return tid; }, clearTimeout: id => { timers.delete(id); }};
  if(uip !== 'UNDEF') c.window.__UIP = uip;
  if(o2.rev !== undefined) c.window.__UIPREV = o2.rev;
  if(o2.hub) c.window.BroadcastChannel = o2.hub.BC;
  vm.createContext(c); vm.runInContext(head, c);
  const run = () => { const fs2 = [...timers.values()]; timers.clear(); fs2.forEach(f => f()); };
  return {c, U: c.UIS, posts, gets, run, hide, st, lsw: () => lsWrites, pending: () => timers.size};
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
  // 7. cross-tab sync
  const settle = async () => { for(let i = 0; i < 6; i++) await tick(); };
  // a POST from tab A pings tab B over BroadcastChannel; B pulls, A does not; A takes the new rev (prev matched)
  let hub = hubOf();
  const A = boot({mbTone: 'grey'}, null, 200, false, '', null, {hub, rev: 1, reply: {ok: true, rev: 2, prev: 1}});
  const B = boot({mbTone: 'grey'}, null, 200, false, '', null, {hub, rev: 1, remote: {rev: 2, prefs: {mbTone: 'blue'}}});
  const seenB = []; B.U.onChange(ks => seenB.push(ks));
  A.U.mbTone = 'blue'; A.run(); await settle();
  R.bcast = [hub.sent, A.U.rev(), A.gets.length, B.gets.length, B.U.mbTone, B.U.rev(), seenB];
  // a reply whose prev is not ours keeps `known` and pulls instead
  const A2 = boot({}, null, 200, false, '', null, {rev: 1, reply: {ok: true, rev: 4, prev: 3}, remote: {rev: 4, prefs: {}}});
  A2.U.x = '1'; A2.run(); await settle(); R.prevMiss = [A2.gets.length, A2.U.rev()];
  // a stubbed reply without rev/prev is tolerated: no pull, rev unchanged
  const A3 = boot({}, null, 200, false, '', null, {rev: 1, reply: {ok: true}});
  A3.U.x = '1'; A3.run(); await settle(); R.noRev = [A3.gets.length, A3.U.rev(), A3.posts.length];
  // the real poll line (95-poll.js): a different uiRev pulls, the same one does not
  const pollLine = fs.readFileSync(path.join(ROOT, 'web', 'js', '95-poll.js'), 'utf8').match(/^\s*try\{ if\(s\.uiRev.*$/m)[0];
  const P1 = boot({}, null, 200, false, '', null, {rev: 3, remote: {rev: 5, prefs: {mbLang: 'en'}}});
  P1.c.softErr = () => {};
  const poll = (s) => vm.runInContext('(function(s){' + pollLine + '\n})', P1.c)(s);
  poll({uiRev: 3}); await settle(); const g0 = P1.gets.length;
  poll({}); await settle(); const g1 = P1.gets.length;
  poll({uiRev: 5}); poll({uiRev: 5}); poll({uiRev: 5}); await settle(); const g2 = P1.gets.length;
  poll({uiRev: 5}); await settle();
  R.poll = [g0, g1, g2, P1.gets.length, P1.U.mbLang, P1.U.rev()];
  // pull keeps keys with a pending local write and reports exactly the changed keys
  const Q = boot({a: '1', b: '2', c: '3', k: 'same'}, null, 200, false, '', null, {rev: 1, remote: {rev: 7, prefs: {a: '1', b: 'R', d: '4', k: 'same'}}});
  const seenQ = []; Q.U.onChange(ks => seenQ.push(ks.slice().sort()));
  Q.U.b = 'local'; await Q.U.pull();
  R.keep = [Q.U.b, Q.U.c === undefined, Q.U.d, Q.U.rev(), seenQ];
  // patch posts only the patched entry; local map holds both; a later setItem drops the queued patch
  const X = boot({mbAttnAck: '{"x":{"s":"a","t":1}}'});
  X.U.patch('mbAttnAck', 'y', {s: 'b', t: 2}); X.run();
  X.U.patch('mbAttnAck', 'x', null); X.U.patch('mbAttnAck', 'nope', null); X.run();
  X.U.patch('mbAttnAck', 'z', 1); X.U.setItem('mbAttnAck', '{}'); X.run();
  R.patch = [X.posts.map(p => p.body), X.U.mbAttnAck];
  // a GET sent before this tab's POST was confirmed returns an older rev: not applied, one follow-up pull instead
  let rel; const gate = new Promise(r => { rel = r; });
  const S = boot({mbAttnAck: '{}'}, null, 200, false, '', null, {rev: 2, reply: {ok: true, rev: 3, prev: 2}});
  S.st.remote = () => gate; const pr = S.U.pull();
  S.U.patch('mbAttnAck', 'y', 1); S.run(); await settle();
  S.st.remote = {rev: 3, prefs: {mbAttnAck: '{"y":1}'}}; rel({rev: 2, prefs: {mbAttnAck: '{}'}}); await pr; await settle();
  R.stale = [S.U.mbAttnAck, S.gets.length, S.U.rev()];
  // a value over 64 KB stays local-only: a pull never deletes it; a normal write clears that mark
  const O = boot({}, null, 200, false, '', null, {rev: 1, remote: {rev: 2, prefs: {}}});
  O.U.huge = 'x'.repeat(70000); O.run(); await O.U.pull(); const kept = O.U.huge && O.U.huge.length;
  O.U.huge = 'small'; O.run(); await settle(); await O.U.pull();
  R.local = [kept, O.posts.map(p => p.body), O.U.huge];
  // no prefs file (prefs null): rev still taken, so the poll stops re-pulling
  const Z = boot({}, null, 200, false, '', null, {rev: 1, remote: {rev: 4, prefs: null}});
  await Z.U.pull(); R.nullPrefs = Z.U.rev();
  // nosave/automation: pulls, never posts or broadcasts; after wipe nothing at all
  hub = hubOf();
  const N = boot({mbTone: 'grey'}, null, 200, false, '?nosave=1', {getItem: () => null, setItem(){}}, {hub, rev: 1, remote: {rev: 2, prefs: {mbTone: 'white'}}});
  const peer = boot({}, null, 200, false, '', null, {hub, rev: 2, reply: {ok: true, rev: 3, prev: 2}, remote: {rev: 3, prefs: {}}});
  N.U.z = '1'; N.run(); N.hide.forEach(f => f()); await N.U.pull();
  const before = [N.posts.length, hub.sent.length, N.gets.length, N.U.mbTone];
  peer.U.q = '1'; peer.run(); await settle();
  const afterPing = N.gets.length;
  N.U.wipe(); await N.U.pull(); peer.U.q = '2'; peer.run(); await settle();
  R.nosave = [before, afterPing, N.gets.length, N.posts.length];
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

    def test_broadcast_triggers_pull(self):
        sent, arev, agets, bgets, btone, brev, seen = self.R["bcast"]
        self.assertEqual(sent, [{"rev": 2}])
        self.assertEqual([arev, agets, bgets, btone, brev, seen], [2, 0, 1, "blue", 2, [["mbTone"]]])
        self.assertEqual(self.R["prevMiss"], [1, 4])
        self.assertEqual(self.R["noRev"], [0, 1, 1])

    def test_poll_uirev(self):
        # same rev / missing uiRev: no GET; changed rev during a pull: exactly one follow-up GET; once synced, no more
        self.assertEqual(self.R["poll"], [0, 0, 2, 2, "en", 5])

    def test_pull_keeps_pending_and_reports_changes(self):
        self.assertEqual(self.R["keep"], ["local", True, "4", 7, [["c", "d"]]])

    def test_patch_posts_only_the_entry(self):
        bodies, final = self.R["patch"]
        self.assertEqual(bodies, [{"set": {}, "del": [], "patch": {"mbAttnAck": {"y": {"s": "b", "t": 2}}}},
                                  {"set": {}, "del": [], "patch": {"mbAttnAck": {"x": None}}},
                                  {"set": {"mbAttnAck": "{}"}, "del": []}])
        self.assertEqual(final, "{}")

    def test_stale_snapshot_not_applied(self):
        self.assertEqual(self.R["stale"], ['{"y":1}', 2, 3])

    def test_local_only_value_survives_pull(self):
        # after a normal write the key is synced again, so a remote snapshot without it removes it
        self.assertEqual(self.R["local"], [70000, [{"set": {"huge": "small"}, "del": []}], None])

    def test_null_prefs_sets_rev(self):
        self.assertEqual(self.R["nullPrefs"], 4)

    def test_nosave_pulls_never_posts(self):
        before, after_ping, gets, posts = self.R["nosave"]
        self.assertEqual(before, [0, 0, 1, "white"])
        self.assertEqual([after_ping, gets, posts], [2, 2, 0])   # a peer's ping still pulls; after wipe nothing

    def test_reset_click(self):
        calls, n, gone = self.R["reset"]
        self.assertEqual(calls, [["post", "/api/ui-prefs/reset", {}], ["ss"], ["reload"]])
        self.assertEqual([n, gone, self.R["resetPosts"]], [0, True, 0])
        self.assertEqual(self.R["cancel"], [[], "grey"])


if __name__ == "__main__":
    unittest.main()
