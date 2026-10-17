"""OS notification on new attention / review items (web/js/43-notify.js): seed on first poll, fire on transition only,
suppressed while the tab is visible (unless opted in) or off, re-fire after the signal clears, rate-limited per session and overall."""
import json
import subprocess
import unittest

from tests._i18n_js import i18n_switch
from tests._load import js_fn
from tests._node import node_e

PRELUDE = """
let LANG = 'ko';
const note = () => {};
const store = {}; const localStorage = { getItem: k => store[k] ?? null, setItem: (k, v) => { store[k] = String(v); } };
let hid = true; const document = { get hidden(){ return hid; } };
const window = { focus(){} }; const cpGo = () => {}; let SS = null; const attnSess = () => SS;
let clock = 1e6; Date.now = () => clock;
const calls = [];
class Notification { constructor(t, o){ calls.push([t, o.body, o.tag]); } close(){} }
Notification.permission = 'granted';
const A = (...rows) => ({ at: 1000, rows });
const R = (sid, ...ks) => ({ sid, cwd: '/w/' + sid, project: 'p' + sid, branch: 'b' + sid, sigs: ks.map(k => ({ k, since: 880 })) });
const ON = () => { store['sidereus.notify'] = JSON.stringify({ on: true, visible: false }); };
"""
CONSTS = ("PAGE_NAME", "NTF_KINDS", "NTF_SID_MS", "NTF_SEEN")


def run(body):
    import re
    from tests._load import js_all
    src = js_all()
    decl = "".join(re.search(r"^(?:const|let) " + n + r"\b[^\n]*$", src, re.M).group(0) + "\n" for n in CONSTS)
    fns = ("attnName", "ntfPref", "ntfSave", "ntfOn", "ntfStep", "ntfGate", "ntfText", "ntfClick", "ntfTick", "ntfSet")
    src = PRELUDE + i18n_switch() + decl + re.search(r"^const ATTN_LBL = \{.*?\};", src, re.S | re.M).group(0) + "\n" + js_fn("attnLbl") + "\n" + "\n".join(js_fn(n) for n in fns) + "\n" + body
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


class Notify(unittest.TestCase):
    def test_seed_transition_clear_refire(self):
        out = run("ON(); const n = [ntfTick(A(R('a', 'ask'))),"       # first poll: seed only
                  " ntfTick(A(R('a', 'ask'))),"                        # still there: no repeat
                  " ntfTick(A(R('a', 'ask', 'done'), R('b', 'blocked', 'conflict'))),"   # b new; done/conflict not notified
                  " ntfTick(A(R('b', 'blocked'))),"                    # a cleared
                  " (clock += 130000, ntfTick(A(R('a', 'ask'), R('b', 'blocked'))))];"   # a back -> fires again
                  "process.stdout.write(JSON.stringify({n, calls}));")
        self.assertEqual(out["n"], [0, 0, 1, 0, 1])
        self.assertEqual(out["calls"][0], ["Sidereus — pb · bb", "막힘 · 2분 · b", "sidereus|b"])   # metadata only, tag = session
        self.assertEqual(out["calls"][1][2], "sidereus|a")

    def test_title_uses_board_worktree_name(self):
        out = run("const e = { sid: 'a', r: R('a'), ks: ['ask'], since: 1000 };"
                  "SS = { project: 'invoice-pdf', wt: { main: '/r/billing-api', name: 'x' } }; const a = ntfText(e, 1000).title;"
                  "SS = { project: 'p', wt: { main: '', name: 'web' } }; const b = ntfText(e, 1000).title;"
                  "process.stdout.write(JSON.stringify([a, b]));")
        self.assertEqual(out, ["Sidereus — invoice-pdf · ba", "Sidereus — web · ba"])

    def test_legacy_key_and_default_off(self):
        out = run("ntfTick(A()); const off = ntfTick(A(R('a', 'ask')));"
                  "store['sidereus.osntf'] = '1'; const legacy = ntfTick(A(R('a', 'ask'), R('b', 'fail')));"
                  "process.stdout.write(JSON.stringify([off, legacy]));")
        self.assertEqual(out, [0, 1])

    def test_suppressed_when_visible_or_off(self):
        out = run("ON(); ntfTick(A()); hid = false;"
                  "const f = ntfTick(A(R('a', 'abort'))); hid = true;"
                  "const again = ntfTick(A(R('a', 'abort')));"         # consumed while visible: no late fire
                  "store['sidereus.notify'] = JSON.stringify({ on: true, visible: true }); hid = false;"
                  "const vis = ntfTick(A(R('a', 'abort'), R('v', 'ask')));"   # opted in: fires while visible
                  "store['sidereus.notify'] = JSON.stringify({ on: false }); const off = ntfTick(A(R('c', 'ask')));"
                  "ON(); hid = true; Notification.permission = 'denied'; const denied = ntfTick(A(R('d', 'ask')));"
                  "process.stdout.write(JSON.stringify([f, again, vis, off, denied, calls.length]));")
        self.assertEqual(out, [0, 0, 1, 0, 0, 1])

    def test_null_state_keeps_seen(self):
        out = run("ON(); ntfTick(A(R('a', 'ask'))); ntfTick(null);"
                  "process.stdout.write(JSON.stringify(ntfTick(A(R('a', 'ask')))));")
        self.assertEqual(out, 0)

    def test_review_primed_then_pending_fires(self):
        out = run("ON(); ntfTick(A());"                               # review not in state yet
                  "const p = ntfTick(A(), [{sid: 'r1', cwd: '/w/r1', root: '/w/r1', done: 0, since: 700}]);"   # first review: seed
                  "const miss = ntfTick(A(), null);"                   # review missing: keep keys
                  "const n = ntfTick(A(), [{sid: 'r1', cwd: '/w/r1', done: 0}, {sid: 'r2', root: '/w/repo/', branch: 'x', done: 0, since: 940},"
                  " {sid: 'r3', done: 1}]);"                           # r2 new; r3 already reviewed
                  "process.stdout.write(JSON.stringify({c: [p, miss, n], calls}));")
        self.assertEqual(out["c"], [0, 0, 1])
        self.assertEqual(out["calls"], [["Sidereus — repo · x", "리뷰 대기 · 1분 · r2", "sidereus|r2"]])

    def test_rate_limit_and_coalesce(self):
        out = run("ON(); ntfTick(A());"
                  "const one = ntfTick(A(R('a', 'ask', 'fail')));"    # two signals, one session -> one notification
                  "clock += 1000; const same = ntfTick(A(R('a', 'fail', 'blocked')));"   # same session within 2 min: dropped
                  "const many = ntfTick(A(R('a', 'blocked'), R('b', 'ask'), R('c', 'ask'), R('d', 'ask'), R('e', 'ask'), R('f', 'ask')));"
                  "process.stdout.write(JSON.stringify({c: [one, same, many], calls}));")
        self.assertEqual(out["c"], [1, 0, 3])   # 4 per minute overall: a + b,c,d
        self.assertEqual(out["calls"][0][1], "질문 대기 · 실패 · 2분 · a")
        self.assertEqual(out["calls"][-1], ["Sidereus", "외 2개 세션이 기다립니다", "sidereus|more"])
        self.assertEqual(len(out["calls"]), 5)

    def test_permission_dismissed_vs_denied(self):
        out = run("const lsSetJson = (k, v) => { store[k] = JSON.stringify(v); }; globalThis.lsSetJson = lsSetJson;"
                  "const r = {}; const go = p => new Promise(res => { Notification.permission = 'default';"
                  " Notification.requestPermission = () => Promise.resolve(p); ntfSet(true, () => res([NTF_ERR, ntfPref().on])); });"
                  "(async () => { r.dismiss = await go('default'); r.deny = await go('denied'); r.ok = await go('granted');"
                  " process.stdout.write(JSON.stringify(r)); })();")
        self.assertEqual(out["dismiss"], ["알림 권한을 고르지 않아 켜지 않았습니다. 다시 켜면 권한을 다시 묻습니다.", False])
        self.assertEqual(out["deny"], ["알림 권한이 거부되어 켜지 않았습니다. 브라우저 사이트 설정에서 허용하세요.", False])
        self.assertEqual(out["ok"], ["", True])

    def test_fail_label_singular_in_english(self):
        out = run("LANG = 'en'; const e = { sid: 'abcdefghij', r: R('a'), ks: ['fail'], since: 1000 };"
                  "process.stdout.write(JSON.stringify(ntfText(e, 1000).body));")
        self.assertEqual(out, "Failed · 0m · abcdefgh")


class NotifyEpisode(unittest.TestCase):
    def test_new_prompt_time_fires_again(self):
        out = run("const B = ep => ({ sid: 'a', cwd: '/w/a', project: 'pa', branch: 'ba', sigs: [{ k: 'blocked', since: ep, ep }] });"
                  "let s = ntfStep(null, [B(900)]).seen; const same = ntfStep(s, [B(900)]); s = same.seen;"
                  "const nxt = ntfStep(s, [B(950)]);"
                  "process.stdout.write(JSON.stringify([same.fire.length, nxt.fire.length, nxt.fire[0].since]));")
        self.assertEqual(out, [0, 1, 950])


if __name__ == "__main__":
    unittest.main()
