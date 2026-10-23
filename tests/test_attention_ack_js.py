"""web/js/17-attention.js attnRows: click-dismiss survives server `since` jitter, any badge signal
makes a badge row, and rows with an empty sid keep independent ack slots. Cross-tab: acks/snoozes are written per entry
(UIS.patch), so two tabs' acks both survive, and a pulled mbAttn* change repaints."""
import json
import os
import re
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

FNS = ("attnPolOf", "attnWhy", "attnAckLoad", "attnAckSave", "attnRowId", "attnAckKey", "attnAckParse",
       "attnAckHit", "attnSnzLoad", "attnSnzSave", "attnRows")


def run(rows, ack, polls=1):
    """-> [{shown:[ids], quiet, badges, ack}] per poll; `rows` is a list per poll or one list reused."""
    src = js_all()
    consts = "\n".join(re.search(r"^const " + n + r"\b.*?;$", src, re.M | re.S).group(0)
                       for n in ("ATTN_APOL", "ATTN_LIST_ONLY", "ATTN_ACK_TOL"))
    per = rows if isinstance(rows[0], list) else [rows] * polls
    js = ("const LS = {mbAttnAck: %s}; const LANG = 'ko'; function T(s){ return s; }\n"
          "function lsJson(k, d){ return k in LS ? JSON.parse(JSON.stringify(LS[k])) : d; }\n"
          "function lsSetJson(k, v){ LS[k] = JSON.parse(JSON.stringify(v)); }\n"
          "function apolOf(k){ return {ask:'badge', abort:'badge', fcheck:'badge', agent:'list', bgdone:'list'}[k] || 'badge'; }\n"
          "let ATTN = null;\n" % json.dumps(ack, ensure_ascii=False)
          + consts + "\n" + "\n".join(js_fn(n) for n in FNS)
          + "\nconst out = []; for(const rs of %s){ ATTN = {rows: rs}; const a = attnRows();"
            " out.push({shown: a.shown.map(x => x.id), quiet: a.quiet, badges: a.shown.filter(x => x.badge).length,"
            " keys: a.shown.map(x => x.key), ack: LS.mbAttnAck}); }"
            " console.log(JSON.stringify(out));" % json.dumps(per, ensure_ascii=False))
    return json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


def row(sid, *sigs, cwd="/w/p"):
    return {"sid": sid, "cwd": cwd, "sigs": [dict(k=k, pts=p, since=t) for k, p, t in sigs]}


class AckJitter(unittest.TestCase):
    def test_since_jitter_stays_dismissed(self):
        ack = {"s1": {"s": "ask", "t": 1000}}
        for t in (999, 1000, 1001, 1002):
            self.assertEqual(run([row("s1", ("ask", 80, t))], ack)[0]["shown"], [], t)

    def test_new_episode_or_signal_returns(self):
        ack = {"s1": {"s": "ask", "t": 1000}}
        self.assertEqual(run([row("s1", ("ask", 80, 1600))], ack)[0]["shown"], ["s1"])
        out = run([row("s1", ("ask", 80, 1000), ("abort", 70, 1000))], ack)[0]
        self.assertEqual(out["shown"], ["s1"])
        self.assertEqual(out["ack"], {})   # changed signal set prunes the ack

    def test_legacy_string_ack_migrates(self):
        out = run([row("s1", ("ask", 80, 1001))], {"s1": "s1|ask|1000"})[0]
        self.assertEqual(out["shown"], [])
        self.assertEqual(out["ack"], {"s1": {"s": "ask", "t": 1000}})

    def test_ack_kept_across_polls(self):
        polls = [[row("s1", ("ask", 80, t))] for t in (1000, 1001, 999, 1001)]
        self.assertTrue(all(p["shown"] == [] for p in run(polls, {"s1": {"s": "ask", "t": 1000}})))


class BlockedSinceMoves(unittest.TestCase):
    def test_older_or_same_stays_newer_returns(self):
        ack = {"s1": {"s": "blocked", "t": 470}}
        for t, shown in ((354, []), (470, []), (472, []), (600, ["s1"])):
            self.assertEqual(run([row("s1", ("blocked", 90, t))], ack)[0]["shown"], shown, t)

    def test_ack_survives_sibling_churn(self):
        polls = [[row("s1", ("blocked", 90, t))] for t in (354, 470, 354)]
        out = run(polls, {"s1": {"s": "blocked", "t": 470}})
        self.assertTrue(all(p["shown"] == [] for p in out))
        self.assertEqual(out[-1]["ack"], {"s1": {"s": "blocked", "t": 470}})

    def test_other_kind_still_exact(self):
        self.assertEqual(run([row("s1", ("ask", 80, 354))], {"s1": {"s": "ask", "t": 470}})[0]["shown"], ["s1"])


class BadgeAny(unittest.TestCase):
    def test_stall_plus_toolfail_counts(self):
        out = run([row("s1", ("stall", 55, 1000), ("toolfail", 45, 1000))], {})[0]
        self.assertEqual((out["shown"], out["badges"], out["quiet"]), (["s1"], 1, 0))

    def test_only_list_signals_stay_low(self):
        out = run([row("s1", ("stall", 55, 1000), ("done", 10, 1000))], {})[0]
        self.assertEqual((out["shown"], out["quiet"]), ([], 1))


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Two tabs = two vm contexts running the real app-head.js against one fake server that merges patches.
TWO_TABS = r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
const ROOT = process.argv[1], head = fs.readFileSync(path.join(ROOT, 'web', 'app-head.js'), 'utf8');
const FNS = %s;
const srv = {rev: 1, prefs: {}, bodies: []};
function post(b){
  const prev = srv.rev; srv.bodies.push(b);
  Object.assign(srv.prefs, b.set || {}); (b.del || []).forEach(k => { delete srv.prefs[k]; });
  for(const k in (b.patch || {})){ let o = {}; try{ o = JSON.parse(srv.prefs[k] || '{}') || {}; }catch(e){}
    for(const u in b.patch[k]){ if(b.patch[k][u] === null) delete o[u]; else o[u] = b.patch[k][u]; } srv.prefs[k] = JSON.stringify(o); }
  srv.rev++; return {ok: true, rev: srv.rev, prev};
}
function tab(){
  const timers = [];
  const c = {console, Proxy, JSON, Object, String, Promise, Math, Array,
    window: {addEventListener(){}, navigator: {webdriver: false}, location: {search: ''}, __UIP: {}, __UIPREV: 1},
    document: {documentElement: {dataset: {}, style: {setProperty(){}}}}, matchMedia: () => ({matches: false}),
    setTimeout: f => { timers.push(f); return timers.length; }, clearTimeout(){}, softErr(){},
    fetch: (url, o) => Promise.resolve(o && o.method === 'POST'
      ? {ok: true, status: 200, json: () => Promise.resolve(post(JSON.parse(o.body)))}
      : {ok: true, status: 200, json: () => Promise.resolve({rev: srv.rev, prefs: Object.assign({}, srv.prefs)})})};
  vm.createContext(c); vm.runInContext(head + '\n' + FNS, c);
  c.run = () => { const f = timers.splice(0); f.forEach(x => x()); };
  return c;
}
const tick = () => new Promise(r => setImmediate(r));
(async () => {
  const A = tab(), B = tab();
  A.attnDone('s1', 'ask|1000'); B.attnDone('s2', 'abort|2000'); A.run(); B.run();
  for(let i = 0; i < 6; i++) await tick();
  await A.UIS.pull(); await B.UIS.pull();
  console.log(JSON.stringify({a: A.attnAckLoad(), b: B.attnAckLoad(), srv: JSON.parse(srv.prefs.mbAttnAck), bodies: srv.bodies}));
})().catch(e => { console.error(e); process.exit(1); });
"""


class CrossTab(unittest.TestCase):
    def test_two_tabs_ack_different_rows(self):
        fns = "\n".join(js_fn(n) for n in ("lsJson", "lsSetJson", "attnAckParse", "attnAckLoad", "attnAckSave", "attnDone"))
        r = subprocess.run(node_e(TWO_TABS % json.dumps(fns), ROOT), capture_output=True, text=True, timeout=30, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        both = {"s1": {"s": "ask", "t": 1000}, "s2": {"s": "abort", "t": 2000}}
        self.assertEqual([out["a"], out["b"], out["srv"]], [both, both, both])
        self.assertTrue(all("set" in b and not b["set"] and "patch" in b for b in out["bodies"]), out["bodies"])

    def harness(self, body):
        src = js_all()
        consts = "\n".join(re.search(r"^const " + n + r"\b.*?;$", src, re.M | re.S).group(0)
                           for n in ("ATTN_APOL", "ATTN_LIST_ONLY", "ATTN_ACK_TOL"))
        js = ("const M = {}, CALLS = [], BUILT = []; const LANG = 'ko'; function T(s){ return s; }\n"
              "const UIS = {getItem: k => k in M ? M[k] : null, setItem(k, v){ CALLS.push(['set', k]); M[k] = String(v); },\n"
              "  patch(k, u, v){ CALLS.push([k, u, v]); const o = JSON.parse(M[k] || '{}'); if(v === null) delete o[u]; else o[u] = v; M[k] = JSON.stringify(o); }};\n"
              "function lsJson(k, d){ return k in M ? JSON.parse(M[k]) : d; }\n"
              "function apolOf(k){ return 'badge'; } function buildAlarm(){ BUILT.push(1); }\n"
              "let ATTN = null, attnLow = false; const document = {activeElement: null};\n"
              + consts + "\n" + "\n".join(js_fn(n) for n in FNS + ("attnPrefSync",)) + "\n" + body)
        return json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True, encoding="utf-8").stdout)

    def test_prune_patches_null_only_removed(self):
        out = self.harness("""
          M.mbAttnAck = JSON.stringify({s1: {s: 'ask', t: 1000}, gone: {s: 'ask', t: 5}});
          M.mbAttnSnooze = JSON.stringify({'s9|ask': 1, 's1|zz': 'clear', 'keep|ask': Date.now() + 9e6});
          ATTN = {rows: [{sid: 's1', cwd: '/w', sigs: [{k: 'ask', pts: 80, since: 1000}]},
                         {sid: 'keep', cwd: '/k', sigs: [{k: 'ask', pts: 80, since: 7}]}]};
          attnRows(); console.log(JSON.stringify({calls: CALLS, ack: JSON.parse(M.mbAttnAck), snz: Object.keys(JSON.parse(M.mbAttnSnooze))}));
        """)
        self.assertEqual(sorted(out["calls"]), [["mbAttnAck", "gone", None], ["mbAttnSnooze", "s1|zz", None], ["mbAttnSnooze", "s9|ask", None]])
        self.assertEqual(out["ack"], {"s1": {"s": "ask", "t": 1000}})
        self.assertEqual(out["snz"], ["keep|ask"])

    def test_pulled_attn_change_repaints(self):
        out = self.harness("""
          const r = [];
          attnPrefSync(['mbTone']); r.push(BUILT.length);
          M.mbAttnLow = '1'; attnPrefSync(['mbTone', 'mbAttnAck']); r.push(BUILT.length, attnLow);
          document.activeElement = {matches: s => s === '.atrpi'}; M.mbAttnLow = '';
          attnPrefSync(['mbAttnLow']); r.push(BUILT.length, attnLow);
          console.log(JSON.stringify(r));
        """)
        self.assertEqual(out, [0, 1, True, 1, False])   # reply box focused: state updated, no repaint


class EmptySid(unittest.TestCase):
    def test_independent_rows(self):
        rs = [row("", ("ask", 80, 1000), cwd="/w/a"), row("", ("ask", 80, 1000), cwd="/w/b")]
        out = run(rs, {"cwd:/w/a": {"s": "ask", "t": 1000}})[0]
        self.assertEqual(out["shown"], ["cwd:/w/b"])


if __name__ == "__main__":
    unittest.main()
