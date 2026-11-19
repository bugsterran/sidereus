"""Pipeline tab «Connections» view (web/js/47k-mcpconn.js · 47l-mcpconn-side.js): R1 orbit + fold · R2 state/edge/live/motion ·
R4 composed text and confirm-only send · R5 reconnect steps per CLI, no send. Pure functions under node, stubs only."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import ROOT, js_fn
from tests._node import node_e
from tests._i18n_js import i18n_switch

_JS = os.path.join(ROOT, "web", "js")
_FS = [os.path.join(_JS, f) for f in ("47k-mcpconn.js", "47l-mcpconn-side.js")]
_CSS = os.path.join(ROOT, "web", "css", "41c-mcpconn.css")
HANGUL = re.compile("[가-힣ㄱ-ㆎ]")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


# Stubs: listeners recorded per type, POSTS = every POST, COPIES = every copy; no timers, no DOM.
_PRE = ("let LANG = 'ko';\n" + i18n_switch(("T", "TV", "U", "AGO")) +
        "const LST = {}, POSTS = [], COPIES = [], NOTES = [], STORE = {};\n"
        "const document = {addEventListener(t, f){ (LST[t] = LST[t] || []).push(f); }, querySelector(){ return null; }, getElementById(){ return null; }, activeElement: null};\n"
        "let setInterval = () => 0, mainView = 'x', PLVIEW = 'x';\n"
        "const esc = s => String(s).replace(/[&<>\"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '\"': '&quot;', \"'\": '&#39;'}[c]));\n"
        "function lsGet(k, d){ return Object.prototype.hasOwnProperty.call(STORE, k) ? STORE[k] : d; }\n"
        "function lsSet(k, v){ STORE[k] = v; return true; }\n"
        "function lsJson(k, d){ try{ const v = JSON.parse(STORE[k] || 'null'); return v === null ? d : v; }catch(e){ return d; } }\n"
        "function lsSetJson(k, o){ STORE[k] = JSON.stringify(o); return true; }\n"
        "function softErr(){} function kbHold(){} function note(s){ NOTES.push(s); }\n"
        "function hhmm(){ return '10:00'; } function fetchErrMsg(){ return 'net'; }\n"
        "async function postJSON(u, b){ POSTS.push([u, b]); return {ok: true}; }\n"
        "function copyText(t){ COPIES.push(t); return Promise.resolve(true); }\n"
        "let GETS = [];\nlet getJSON = function(u){ return new Promise(r => GETS.push([u, r])); }\n"
        "let SESS = [];\n"
        + js_fn("ago") + "\n" + js_fn("sid8") + "\n" + js_fn("mboxIn") + "\n")

_ROW = {"sid": "sid-aaaa-1111", "plat": "cc", "project": "proj", "state": "think", "mbox": "mb-a", "mboxSrc": "identity", "cwd": "/w/proj"}
_SRV = {"name": "ctx7", "scope": "SCOPE-SENTINEL", "plug": "PLUG-SENTINEL", "transport": "TRANSPORT-SENTINEL", "on": True,
        "state": "fail", "err": "ERR-SENTINEL", "at": 111, "n": 4242, "last": 222}
_DATA = {"ok": True, "now": 10000, "sid": _ROW["sid"], "plat": "cc", "supported": True, "counts": True, "scanning": False, "checked": 9000,
         "servers": [
             {"name": "ctx7", "scope": "user", "plug": "", "transport": "stdio", "on": True, "state": "ok", "err": "", "at": 9000, "n": 3, "last": 9800},
             {"name": "<img src=x>", "scope": "project", "plug": "", "transport": "stdio", "on": True, "state": "fail", "err": "CONNECTION_CLOSED", "at": 9000, "n": 0, "last": 0},
             {"name": "idle", "scope": "plugin", "plug": "p1", "transport": "http", "on": True, "state": "unknown", "err": "", "at": 0, "n": None, "last": 0},
             {"name": "claude_ai_Docs", "scope": "cloud", "plug": "", "transport": "", "on": True, "state": "ok", "err": "", "at": 9000, "n": 0, "last": 0},
             {"name": "claude_ai_Drive", "scope": "cloud", "plug": "", "transport": "", "on": True, "state": "auth", "err": "", "at": 9000, "n": 0, "last": 0}],
         "totals": {"ok": 2, "fail": 1, "auth": 1, "unknown": 1}}


def _js(body):
    src = _PRE
    for p in _FS:
        src += _read(p) + "\n"
    r = subprocess.run(node_e(src + body), capture_output=True, text=True, encoding="utf-8", timeout=30)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


# Fake event target: closest(sel) answers for the attribute selectors named in `hits`.
_EV = ("function ev(hits){ const t = {dataset: hits.ds || {}, closest(s){ if(s === '.mcpc') return {};"
       " for(const k of Object.keys(hits)) if(k !== 'ds' && s.indexOf(k) >= 0) return {dataset: hits[k]}; return null; }}; return {target: t}; }\n"
       "function fire(type, hits){ for(const f of LST[type] || []) f(ev(hits)); }\n")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class McpConnJs(unittest.TestCase):
    def test_node_check(self):
        for p in _FS + [os.path.join(_JS, "06-i18n-zzx-mcpconn.js"), os.path.join(_JS, "46-tokens-tab.js")]:
            subprocess.run(["node", "--check", p], check=True)

    def test_R1_conn_view_in_pipeline_tab(self):
        s = _read(os.path.join(_JS, "48-pipeline.js"))
        self.assertIn("const PLVIEWS = ['pipe', 'harness', 'tools', 'conn'];", s)
        self.assertIn("['conn', 'Connections']", s)
        self.assertIn("if(PLVIEW === 'conn'){ paintMcpConn(box); return true; }", s)
        self.assertNotIn("paintMcpConn", _read(os.path.join(_JS, "46-tokens-tab.js")))

    def test_R1_strip_live_sessions_all_clis(self):
        out = _js("SESS = [{sid: 'a', plat: 'cc', state: 'think'}, {sid: 'b', plat: 'pi', state: 'wait'}, {sid: 'c', plat: 'cx', state: 'idle'},"
                  " {sid: 'd', plat: 'cc', state: 'done'}, {sid: 'e', plat: 'gm', state: 'gone'}, {plat: 'cc', state: 'think'}];"
                  " console.log(JSON.stringify(mcpcRows().map(x => x.sid)))")
        self.assertEqual(out, ["a", "b", "c"])

    def test_R1_orbit_nodes_and_cloud_fold(self):
        out = _js("const D = %s; MCPC.sid = D.sid;"
                  " const a = mcpcStage(%s, D, 1000, 620); MCPC.cloudOpen = true; const b = mcpcStage(%s, D, 1000, 620);"
                  " console.log(JSON.stringify([a, b]))" % (json.dumps(_DATA), json.dumps(_ROW), json.dumps(_ROW)))
        a, b = out
        self.assertEqual(len(re.findall(r"data-mcpcc[ >]", a)), 1)                       # one fold node for both connectors
        self.assertEqual(len(re.findall(r'<button[^>]*data-mcpcn=', a)), 3)    # ctx7 · <img> · idle; connectors folded
        self.assertNotIn('data-mcpcn="claude_ai_Docs"', a)
        self.assertIn('data-mcpcn="claude_ai_Docs"', b)                  # outer ring after the fold is opened
        self.assertIn('data-mcpcn="claude_ai_Drive"', b)
        self.assertIn('aria-expanded="true"', b)
        self.assertNotIn("<img src=x>", a)                               # server names are escaped
        self.assertIn("&lt;img src=x&gt;", a)

    def test_R2_node_state_classes_and_error_code_only(self):
        out = _js("const D = %s; MCPC.sid = D.sid; console.log(JSON.stringify(mcpcStage(%s, D, 1000, 620)))" % (json.dumps(_DATA), json.dumps(_ROW)))
        self.assertRegex(out, r'class="mcpcn st-ok used"[^>]*data-mcpcn="ctx7"')
        self.assertRegex(out, r'class="mcpcn st-fail"[^>]*data-mcpcn="&lt;img src=x&gt;"')
        self.assertRegex(out, r'class="mcpcn st-unknown"[^>]*data-mcpcn="idle"')
        self.assertIn("<span class=mcpcbad>CONNECTION_CLOSED</span>", out)
        self.assertIn("호출 3", out)                                      # this session's count on the used node

    def test_R2_edge_width_and_live_15min(self):
        out = _js("console.log(JSON.stringify({w: [mcpcEdgeW(0), mcpcEdgeW(null), mcpcEdgeW(1), mcpcEdgeW(7), mcpcEdgeW(1e6)],"
                  " l: [mcpcLive(10000 - 900, 10000), mcpcLive(10000 - 901, 10000), mcpcLive(0, 10000), mcpcLive(null, 10000), mcpcLive(9990, 0)],"
                  " e: [mcpcEdge({name: 'a', state: 'ok', n: 2, last: 9500}, {x: 1, y: 1, a: 0}, {cx: 5, cy: 5}, 10000, false, false),"
                  "     mcpcEdge({name: 'a', state: 'ok', n: 2, last: 9000}, {x: 1, y: 1, a: 0}, {cx: 5, cy: 5}, 10000, false, false)]}))")
        self.assertEqual(out["w"][:2], [1, 1])
        self.assertEqual(out["w"][2], 2.5)
        self.assertLess(out["w"][2], out["w"][3])
        self.assertEqual(out["w"][4], 6)
        self.assertEqual(out["l"], [True, False, False, False, False])
        self.assertIn("mcpcfl", out["e"][0])                             # call 500 s ago: flowing dots
        self.assertNotIn("mcpcfl", out["e"][1])                          # 1000 s ago: static edge
        self.assertIn('stroke-width="3.08"', out["e"][0])

    def test_R2_reduced_motion_rule(self):
        css = _read(_CSS)
        self.assertRegex(css, r"\.mcpcfl\{[^}]*animation:mcpcflow 4\.5s linear infinite")
        self.assertRegex(css, r"@media \(prefers-reduced-motion:reduce\)\{html\[data-ui=next\] \.mcpcfl\{animation:none\}\}")
        for p in _FS:
            self.assertNotIn("animateMotion", _read(p))                  # SMIL would ignore the media query

    def test_R2_late_reply_for_old_session_dropped(self):
        out = _js("MCPC.sid = 'one'; loadMcpConn('one', true); MCPC.sid = 'two';"
                  " GETS[0][1]({ok: true, sid: 'one', servers: []});"
                  " setTimeout(() => console.log(JSON.stringify([GETS[0][0], MCPC.data])), 0);")
        self.assertEqual(out[0], "/api/mcp-conn?sid=one")
        self.assertIsNone(out[1])

    def test_R2_failed_load_backs_off(self):
        out = _js("MCPC.sid = 'one'; loadMcpConn('one', false); GETS[0][1]({ok: false, msg: 'gone'});"
                  " setTimeout(() => { loadMcpConn('one', false); loadMcpConn('one', false); const quiet = GETS.length;"
                  " loadMcpConn('one', true); const forced = GETS.length;"
                  " MCPC.failAt.one = Date.now() - 11000; MCPC.busy = ''; loadMcpConn('one', false);"
                  " console.log(JSON.stringify([quiet, forced, GETS.length])); }, 0);")
        self.assertEqual(out, [1, 2, 3])                                 # repaints within 10 s do not refetch; a forced load does

    def test_R2_fetch_error_backs_off(self):
        out = _js("getJSON = () => Promise.reject(Object.assign(new Error('x'), {status: 502})); let n = 0; const g = getJSON;"
                  " getJSON = u => { n++; return g(u); }; MCPC.sid = 'one'; loadMcpConn('one', false);"
                  " setTimeout(() => { loadMcpConn('one', false); console.log(JSON.stringify([n, MCPC.err])); }, 0);")
        self.assertEqual(out, [1, "net"])

    def test_R4_thread_label_fits_bus_rule(self):
        out = _js("console.log(JSON.stringify([mcpcThread('ctx7'), mcpcThread('a/b;c`d'), mcpcThread('x'.repeat(100))]))")
        rx = re.compile(r"^[\w][\w .·:\-]{0,59}$")                     # sidereus/bus.py DM_THREAD (ASCII subset)
        self.assertEqual(out[0], "mcp:ctx7")
        self.assertEqual(out[1], "mcp:a-b-c-d")
        self.assertEqual(len(out[2]), 60)
        for t in out:
            self.assertRegex(t, rx)

    def test_R4_status_command_only_for_plain_names(self):
        out = _js("const R = %s; console.log(JSON.stringify([mcpcBody('diag', 'my.srv-1', R, ''), mcpcBody('diag', 'a;rm -rf x', R, ''),"
                  " mcpcStatusCmd('cx', 'a b'), mcpcStatusCmd('cx', 'ok_1')]))" % json.dumps(_ROW))
        self.assertIn("`claude mcp get my.srv-1`", out[0])
        self.assertNotIn("claude mcp get", out[1])
        self.assertIn("with your CLI's MCP status command", out[1])
        self.assertEqual(out[2:], ["", "codex mcp list"])

    def test_R4_body_name_and_note_only(self):
        out = _js("const S = %s, R = %s; console.log(JSON.stringify([mcpcBody('task', S, R, 'list open issues'),"
                  " mcpcBody('diag', S, R, 'line one\\nline two'), mcpcBody('restart', S, R, ''), mcpcBody('task', S, R, ''),"
                  " mcpcBody('diag', S, Object.assign({}, R, {plat: 'pi'}), ''), mcpcBody('reconn', S, R, 'x')]))" % (json.dumps(_SRV), json.dumps(_ROW)))
        task, diag, rst, empty, pi, rc = out
        for b in (task, diag, rst, empty, pi):
            self.assertIn("ctx7", b)
            self.assertIsNone(HANGUL.search(b))                          # English wire text under a Korean UI
            for s in ("SENTINEL", "4242", "proj", "sid-aaaa", "mb-a"):
                self.assertNotIn(s, b)
        self.assertTrue(task.endswith("list open issues"))
        self.assertIn("\nNote: line one line two", diag)                 # one line, newline folded
        self.assertNotIn("Note:", rst)
        self.assertIn("claude mcp get ctx7", diag)
        self.assertIn("pi mcp list", pi)
        self.assertEqual(rc, "")                                         # «Reconnect» composes nothing

    def test_R4_dm_only_from_confirm(self):
        both = "".join(_read(p) for p in _FS)
        self.assertEqual(both.count("postJSON("), 1)
        self.assertIn("postJSON(", js_fn("mcpcSend"))
        self.assertEqual(len(re.findall(r"(?<!function )\bmcpcSend\(\)", both)), 1)    # one caller: the [data-mcpcgo] click
        self.assertIn("if(t.closest('[data-mcpcgo]')) mcpcSend();", both)
        out = _js(_EV + "SESS = [%s]; const D = %s; MCPC.sid = D.sid; MCPC.data = D;"
                  " fire('click', {'data-mcpcn': {mcpcn: 'ctx7'}});"
                  " fire('click', {'data-mcpca': {mcpca: 'task'}});"
                  " fire('input', {'data-mcpcnote': {mcpcnote: 'ctx7'}, ds: {}});"
                  " MCPC.note.ctx7 = 'find the docs';"
                  " const before = POSTS.length; const want = mcpcBody('task', D.servers[0], SESS[0], 'find the docs');"
                  " fire('click', {'data-mcpcgo': {}});"
                  " setTimeout(() => console.log(JSON.stringify({before, posts: POSTS, want, log: MCPC.log, store: STORE['sidereus.mcpclog'] || ''})), 0);"
                  % (json.dumps(_ROW), json.dumps(_DATA)))
        self.assertEqual(out["before"], 0)                               # picking a node / action / typing sends nothing
        self.assertEqual(len(out["posts"]), 1)
        u, b = out["posts"][0]
        self.assertEqual(u, "/api/dm")
        self.assertEqual(b, {"to": "mb-a", "body": out["want"], "relay": True, "sid": _ROW["sid"], "thread": "mcp:ctx7"})
        self.assertEqual(out["log"][0]["a"], "task")
        self.assertEqual(out["log"][0]["s"], "ctx7")
        self.assertTrue(out["log"][0]["ok"])
        self.assertNotIn("find the docs", out["store"])                  # the log keeps no body

    def test_R4_not_logged_in_disables_send(self):
        row = dict(_ROW, mboxSrc="env")
        out = _js(_EV + "SESS = [%s]; const D = %s; MCPC.sid = D.sid; MCPC.data = D; MCPC.sel = 'ctx7'; MCPC.act.ctx7 = 'diag';"
                  " const h = mcpcDetailCard(D, SESS[0]); fire('click', {'data-mcpcgo': {}});"
                  " setTimeout(() => console.log(JSON.stringify({h, n: POSTS.length})), 0);" % (json.dumps(row), json.dumps(_DATA)))
        self.assertEqual(out["n"], 0)
        self.assertIn("data-mcpcgo disabled", out["h"])
        self.assertIn("메일박스에 로그인하지 않았습니다", out["h"])
        self.assertIn("<pre class=mcpcpv>", out["h"])                     # the preview still shows

    def test_R5_steps_per_cli_no_send(self):
        out = _js(_EV + "const k = []; for(const p of ['cc', 'cx', 'pi', 'gm']) k.push(mcpcSteps(p, 'ctx7', 'fail'));"
                  " k.push(mcpcSteps('cc', 'claude_ai_Drive', 'auth'));"
                  " const tpl = k.flatMap(x => x.steps.map(s => s.t)), miss = tpl.filter(t => T(t) === t);"
                  " SESS = [%s]; const D = %s; MCPC.sid = D.sid; MCPC.data = D; MCPC.sel = 'ctx7';"
                  " fire('click', {'data-mcpca': {mcpca: 'reconn'}}); const h = mcpcDetailCard(D, SESS[0]);"
                  " fire('click', {'data-mcpccp': {mcpccp: '/mcp'}});"
                  " setTimeout(() => console.log(JSON.stringify({k, miss, h, posts: POSTS.length, copies: COPIES})), 0);"
                  % (json.dumps(_ROW), json.dumps(_DATA)))
        cc, cx, pi, gm, auth = [" | ".join(s["t"] + " " + s.get("c", "") for s in x["steps"]) for x in out["k"]]
        self.assertIn("/mcp", cc)
        self.assertIn("Reconnect", cc)
        self.assertIn("codex resume", cx)
        self.assertIn("/mcp reconnect ctx7", pi)
        self.assertIn("/reload", pi)
        self.assertIn("Authenticate", auth)
        self.assertEqual([x["copy"] for x in out["k"]], ["/mcp", "codex resume", "/mcp reconnect ctx7", "", "/mcp"])
        self.assertEqual(out["miss"], [])                                # every step template has its Korean entry
        self.assertIn("<ol class=mcpcsteps>", out["h"])
        self.assertNotIn("data-mcpcgo", out["h"])                        # no send button on «Reconnect»
        self.assertEqual(out["posts"], 0)
        self.assertEqual(out["copies"], ["/mcp"])
        self.assertNotIn("postJSON", js_fn("mcpcSteps") + js_fn("mcpcReconnHtml"))

    def test_unknown_not_zero_core_subtitle(self):
        pi = dict(_DATA, plat="pi", counts=False, totals={"ok": 0, "fail": 0, "auth": 0, "unknown": 5},
                  servers=[dict(_DATA["servers"][2], name="s%d" % i, n=None, last=None) for i in range(5)])
        allu = dict(_DATA, totals={"ok": 0, "fail": 0, "auth": 0, "unknown": 2},
                    servers=[dict(_DATA["servers"][2], name="a"), dict(_DATA["servers"][2], name="b")])
        out = _js("console.log(JSON.stringify([mcpcCoreSum(%s), mcpcCoreSum(%s), mcpcCoreSum(%s), (LANG = 'en', mcpcCoreSum(%s))]))"
                  % (json.dumps(pi), json.dumps(allu), json.dumps(_DATA), json.dumps(pi)))
        self.assertEqual(out[0], "기록 없음 5")
        self.assertEqual(out[1], "기록 없음 2")
        self.assertEqual(out[2], "연결 2 · 실패 1")
        self.assertEqual(out[3], "5 unknown")

    def test_error_badge_not_clipped(self):
        css = _read(_CSS)
        self.assertIn(".mcpcn.st-fail .mcpcu{overflow:visible}", css)
        self.assertRegex(css, r"\.mcpcbad\{[^}]*white-space:nowrap")           # one line, never CONNECTION_CLOS / ED
        self.assertNotRegex(css, r"\.mcpcbad\{[^}]*overflow-wrap")
        self.assertIn(".mcpcn.st-fail{width:max-content;", css)                 # the failed node grows to fit the code

    def test_many_servers_never_overlap(self):
        # Rings while labels fit, the staggered grid past that; the stage grows instead of labels piling up.
        out = _js("const R = []; for(const [W, H] of [[1402, 834], [1000, 620], [700, 520]]) for(const [a, b] of [[8, 0], [16, 0], [24, 0], [40, 0], [60, 0], [16, 17], [30, 30]]){"
                  " const w = 68, h = mcpcGrowH(W, H, a, b), g = mcpcGeo(W, h, a, b), all = g.inner.concat(g.outer);"
                  " R.push([W, H, a, b, h, g.inner.length, g.outer.length, mcpcHits(all, w * 2), all.filter(p => p.x - w < 0 || p.x + w > W || p.y - 14 < 0 || p.y + 68 > h).length]); }"
                  " console.log(JSON.stringify(R))")
        for W, H, a, b, h, ni, no, hits, outside in out:
            self.assertEqual((ni, no, hits, outside), (a, b, 0, 0), (W, H, a, b, h))
            self.assertGreaterEqual(h, H)
        grown = dict(((W, a, b), h) for W, H, a, b, h, *_ in out)
        self.assertEqual(grown[(1402, 16, 0)], 834)                             # a normal count keeps the fitted height
        self.assertGreater(grown[(700, 60, 0)], 520)                            # a narrow stage with many servers grows

    def test_stage_height_fits_feed(self):
        out = _js("const B = (w, h) => ({clientWidth: w, clientHeight: h, scrollTop: 0, querySelector(){ return null; }});"
                  " console.log(JSON.stringify([mcpcFitH(B(1840, 936), null), mcpcFitH(B(1840, 400), null), mcpcFitH(B(1840, 3000), null),"
                  " mcpcFitH(B(1000, 936), null), mcpcFitH(B(800, 936), null)]))")
        self.assertEqual(out, [820, 520, 1000, 620, 520])                        # 936 - 70 top - 46 legend; side column below = fixed

    def test_unknown_not_zero(self):
        out = _js("console.log(JSON.stringify([mcpcStateCard(null), mcpcCallsCard(Object.assign({}, %s, {counts: false})), mcpcAgo(0, 100)]))"
                  % json.dumps(_DATA))
        self.assertIn("<b>—</b>", out[0])
        self.assertNotIn("<b>0</b>", out[0])
        self.assertIn("서버별 호출이 없습니다", out[1])
        self.assertEqual(out[2], "—")

    def test_partial_counts_say_since(self):
        out = _js("console.log(JSON.stringify([mcpcCallsCard(Object.assign({}, %s, {since: 0})), mcpcCallsCard(Object.assign({}, %s, {since: 1})), T('calls since {t} · last')]))"
                  % (json.dumps(_DATA), json.dumps(_DATA)))
        self.assertIn("호출 수 · 마지막", out[0])
        self.assertNotIn("부터", out[0])
        self.assertIn(out[2].split("{t}")[1].split(" ·")[0], out[1])        # "since" wording shown for a partial record


if __name__ == "__main__":
    unittest.main()
