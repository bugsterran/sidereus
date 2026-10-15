"""Pipeline tab «하네스» view (web/js/47b-harness.js): node --check, lane order, escaping, no /api/tools/file fetch on paint."""
import json
import os
import subprocess
import unittest

from tests._i18n_js import i18n_switch

from tests._load import ROOT
from tests._node import node_e

_F = os.path.join(ROOT, "web", "js", "47b-harness.js")
_STUB = """
const NOW = 1790000000000; Date.now = () => NOW;   // fixed clock: HN.at below is set from NOW, so the data reads as fresh
var LANG = 'ko', mainView = 'pipe', PLVIEW = 'harness', TKVIEW = 'use', SESS = [], URLS = [], PAINTS = 0;
const PLS = {proj: '/w/a'};
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'})[c]);
function stamp(s){ return 'T' + s; } function fmtTok(n){ return String(n); }
function lsGet(k, d){ return d; } function lsSet(){} function plPaint(){ PAINTS++; } function setMainView(){}
function strShort(p){ return p.split('/').pop(); } function strProjList(){ return [{p: '/w/a'}]; }
function getJSON(u){ URLS.push(u); return new Promise(() => {}); }
function fetch(u){ URLS.push(u); return new Promise(() => {}); }
const AILG = {cc: ['클로드', '<svg>c</svg>'], cx: ['Codex', '<svg>x</svg>'], gm: ['Gemini', '<svg>g</svg>']};
function platName(k){ return AILG[k][0]; }
"""


def _js(body):
    with open(_F, encoding="utf-8") as f:   # the whole file: it is self-contained apart from the stubs above
        src = _STUB + i18n_switch() + "const document = {addEventListener(){}};\n" + f.read() + "\n" + body
    return json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True).stdout)


class Harness(unittest.TestCase):
    def test_node_check(self):
        subprocess.run(["node", "--check", _F], check=True)

    def test_lane_order(self):
        ev = [{"ev": "Stop", "hooks": [{"cmd": "a"}]}, {"ev": "SessionStart", "hooks": [{"cmd": "b"}]},
              {"ev": "Zeta", "hooks": [{"cmd": "c"}]}, {"ev": "PreToolUse", "hooks": []}]
        r = _js("console.log(JSON.stringify(hnLanes(%s).map(c => [c.evs.join('/'), c.hooks.length])))" % json.dumps(ev))
        self.assertEqual(r, [["SessionStart", 1], ["UserPromptSubmit", 0], ["PreToolUse", 0], ["", 0], ["PostToolUse", 0],
                             ["Stop/SubagentStop", 1], ["PreCompact/PostCompact", 0], ["Notification", 0], ["Zeta", 1]])

    def test_chip_escapes(self):
        h = {"scope": "<s>", "src": "/x/<b>.json", "matcher": "<img onerror=1>", "cmd": "python3 /h/\"q<x>.py", "timeout": "<9>",
             "eff": "<e>", "n": "<n>", "last": 5}
        out = _js("console.log(JSON.stringify(hnChip(%s)))" % json.dumps(h))
        self.assertNotIn("<img", out)
        self.assertNotIn("<x>", out)
        self.assertNotIn("<9>", out)
        self.assertNotIn("<n>", out)
        self.assertNotIn("<s>", out)
        self.assertIn("hne-unknown", out)   # unknown effect value never reaches the class attribute
        self.assertIn("&lt;img onerror=1&gt;", out)

    def test_reconnect_tip_and_dup_scope(self):
        r = _js("console.log(JSON.stringify([hnStat({status: 'ok', last: 0, fail_at: 5, ok_at: 9})[0],"
                " hnVdTxt({why: 'dup', lvl: 'check', vp: {srcs: ['user', 'project-local', 'x']}})]))")
        self.assertIn('title="재연결됨: T9 · 이전 실패: T5"', r[0])
        self.assertNotIn("실패 기록 없음", r[0])
        self.assertEqual(r[1], "같은 명령이 한 번 더 등록됨 (사용자, 프로젝트 로컬, x)")

    def test_chip_desc(self):
        r = _js("console.log(JSON.stringify([hnChip({cmd: 'a.py', desc: 'blocks <b>rm</b> \"x\"'}), hnChip({cmd: 'a.py', desc: ''}),"
                " hnChip({cmd: 'a.py'})]))")
        self.assertNotIn("hncd", r[0])   # tooltip only, no inline line
        self.assertNotIn("<b>rm", r[0])
        self.assertIn('title="blocks &lt;b&gt;rm&lt;/b&gt; &quot;x&quot;\na.py"', r[0])
        self.assertIn('title="a.py"', r[1])
        self.assertIn('title="a.py"', r[2])

    def test_clickable_only_with_ref(self):
        r = _js("console.log(JSON.stringify([hnChip({cmd: 'a.py', eff: 'block', open: 'h:Stop:0\"><x>'}), hnChip({cmd: 'b', eff: 'ext', open: ''}),"
                " hnRules([{path: '/r', order: 1, open: 'r:0'}, {path: '/s', order: 2}]),"
                " hnAgents([{name: 'a', scope: 'user', open: 'a:a'}, {name: 'b', scope: '', open: ''}])]))")
        self.assertIn('class="hnc hne-block hnco" data-hnref="h:Stop:0&quot;&gt;&lt;x&gt;"', r[0])
        self.assertNotIn("data-hnref", r[1])
        self.assertNotIn("hnco", r[1])
        self.assertEqual(r[2].count("data-hnref"), 1)
        self.assertIn('data-hnref="r:0"', r[2])
        self.assertEqual(r[3].count("data-hnref"), 1)
        self.assertIn('data-hnref="a:a"', r[3])

    def test_open_uses_code_window(self):
        # hnOpen fetches by ref and hands the text to 81's code window; a failed read opens it with the message.
        body = ("const OPENED = [], SET = []; function strPopOpenText(f){ OPENED.push([f, URLS.length]); } function strPopTextSet(f){ SET.push(f); }"
                " fetch = u => { URLS.push(u); const j = u.includes('bad') ? {ok: false, msg: 'bad ref'}"
                " : {ok: true, name: 'g.py', path: '~/h/g.py', text: 'x', lang: 'python'};"
                " return Promise.resolve({status: u.includes('bad') ? 400 : 200, json: () => Promise.resolve(j)}); };"
                " (async () => { await hnOpen('h:Stop:0', ' guard.py '); await hnOpen('a:bad'); console.log(JSON.stringify({u: URLS, o: OPENED, s: SET})); })();")
        r = _js(body)
        self.assertEqual(r["u"], ["/api/harness/file?plat=cc&proj=%2Fw%2Fa&ref=h%3AStop%3A0", "/api/harness/file?plat=cc&proj=%2Fw%2Fa&ref=a%3Abad"])
        self.assertEqual(r["o"][0], [{"key": "cc\n/w/a\nh:Stop:0", "name": "guard.py", "text": "불러오는 중…"}, 0])   # card name, opened before the fetch
        self.assertEqual(r["o"][1][0]["name"], "a:bad")   # no name -> ref
        self.assertEqual(r["s"][0], {"key": "cc\n/w/a\nh:Stop:0", "name": "g.py", "path": "~/h/g.py", "text": "x", "lang": "python"})
        self.assertEqual(r["s"][1]["key"], "cc\n/w/a\na:bad")
        self.assertIn("잘못된 파일 참조", r["s"][1]["text"])   # 4xx body msg kept and mapped to a T() key

    def test_server_msgs_translated(self):
        r = _js("console.log(JSON.stringify([hnMsg('unknown project'), hnMsg('bad days'), hnMsg('파일이 너무 큽니다.'), hnMsg('')]))")
        self.assertEqual(r, ["알 수 없는 프로젝트", "잘못된 기간", "파일이 너무 큽니다.", ""])
        with open(os.path.join(ROOT, "web", "js", "06-i18n-x.js"), encoding="utf-8") as f:
            x = f.read()
        for k in ("알 수 없는 프로젝트", "잘못된 기간", "잘못된 파일 참조", "열 수 있는 파일이 없습니다.", "파일이 너무 큽니다.",
                  "텍스트 파일이 아닙니다.", "파일이 없습니다."):
            self.assertIn(": '%s'" % k, x)   # I18N.ko value

    def test_other_events_open_state(self):
        ev = json.dumps([{"ev": "Zeta", "hooks": [{"cmd": "c"}]}])
        r = _js("const a = hnLaneHtml(%s); HN.exOpen = true; console.log(JSON.stringify([a, hnLaneHtml(%s)]))" % (ev, ev))
        self.assertIn("<details class=hnex><summary", r[0])
        self.assertIn("<details class=hnex open><summary", r[1])
        with open(os.path.join(ROOT, "web", "js", "48-pipeline.js"), encoding="utf-8") as f:
            self.assertIn("fe.closest('.hnw')) return;", f.read())   # poll repaint skipped while a chip/row has focus

    def test_counts_hidden_when_tools_off(self):
        r = _js("const a = hnCounts({skill: 1}); var FEATS = {tools: false}; console.log(JSON.stringify([a, hnCounts({skill: 1})]))")
        self.assertIn("data-hntools", r[0])
        self.assertEqual(r[1], "")

    def test_code_window_entry(self):
        with open(os.path.join(ROOT, "web", "js", "81-structure-panel.js"), encoding="utf-8") as f:
            sp = f.read()
        self.assertIn("function strPopOpenText(f)", sp)
        self.assertIn("if(sp.text) return ['x', sp.text.key ||", sp)
        self.assertIn("function strPopTextSet(f)", sp)   # one window per file
        self.assertIn("body.innerHTML = strCodeTable(q.text, q.lang, 1);", sp)   # hl() escapes every token
        with open(_F, encoding="utf-8") as f:
            self.assertNotIn("hnfv", f.read())

    def test_legend(self):
        data = {"ok": True, "events": [], "rules": [], "agents": [], "counts": {}}
        h = _js("HN.data[hnKey('/w/a')] = %s; HN.at[hnKey('/w/a')] = NOW; console.log(JSON.stringify(hnHtml()))" % json.dumps(data))
        self.assertIn("class=hnlg", h)
        for k in ("inject", "block", "log", "ext", "bin"):
            self.assertIn('class="hnef hne-%s"' % k, h)
        self.assertIn("응답 종료 순서로 훅이 돈다", h)
        self.assertLess(h.index("훅 흐름"), h.index("hnlg"))
        self.assertLess(h.index("hnlg"), h.index("class=hnl>"))

    def test_no_tool_file_fetch_on_paint(self):
        data = {"ok": True, "events": [{"ev": "PreToolUse", "hooks": [{"scope": "user", "cmd": "/h/guard.py", "eff": "block", "n": 3}]}],
                "rules": [{"path": "/w/a/AGENTS.md", "size": 900, "order": 1}],
                "agents": [{"name": "impl", "scope": "project", "pipes": [{"pipe": "change", "stage": "구현"}], "n": 2}],
                "counts": {"skill": 1, "cmd": 2, "mcp": 3}, "scanning": False}
        body = ("HN.data[hnKey('/w/a')] = %s; HN.at[hnKey('/w/a')] = NOW; const h1 = hnHtml(); HN.data = {}; const h2 = hnHtml();"
                "console.log(JSON.stringify({urls: URLS, html: h1.includes('guard.py'), wait: h2.includes('불러오는 중'),"
                " chips: h1.includes('data-hnp') || h1.includes('토큰 리포트')}))") % json.dumps(data)
        r = _js(body)
        self.assertTrue(r["html"])
        self.assertTrue(r["wait"])
        self.assertFalse(r["chips"])   # header and project chips belong to the pipeline tab
        self.assertTrue(r["urls"])
        self.assertTrue(all(u.startswith("/api/harness?plat=cc&proj=") for u in r["urls"]), r["urls"])
        self.assertFalse(any("/api/tools/file" in u for u in r["urls"]))

    def test_mcp_skill_boxes(self):
        mc = [{"name": "<m>", "scope": "user", "transport": "http", "on": True, "n": 4, "last": 7, "open": "x:1"},
              {"name": "off", "scope": "project", "plug": "<p>", "transport": "<t>", "on": False}]
        sk = [{"name": "s<b>", "scope": "user", "open": "s:1\"", "n": 2, "pipes": [{"pipe": "<pp>", "stage": "<st>"}]},
              {"name": "t", "scope": "user", "open": ""},
              {"name": "pk", "scope": "plugin", "plug": "<plug>", "on": False, "open": "s:2", "pipes": []}]
        r = _js("console.log(JSON.stringify([hnTools(%s), hnSkills(%s), hnSkills([]), hnToolBox(undefined, 'a', 'b')]))"
                % (json.dumps(mc), json.dumps(sk)))
        self.assertNotIn("<m>", r[0])
        self.assertNotIn("<p>", r[0])
        self.assertNotIn("<t>", r[0])
        self.assertIn("&lt;m&gt;", r[0])
        self.assertIn("hntr-http", r[0])
        self.assertNotIn("hntr-&lt;", r[0])   # unknown transport never reaches the class attribute
        self.assertNotIn("data-hnref", r[0])   # MCP rows are not clickable
        self.assertEqual(r[0].count("hnoff"), 2)   # row class + badge, only on the off row
        self.assertIn("꺼짐", r[0])
        self.assertIn('title="T7"', r[0])
        self.assertIn("4회", r[0])
        self.assertNotIn("s<b>", r[1])
        self.assertNotIn("<pp>", r[1])
        self.assertNotIn("<plug>", r[1])
        self.assertIn("&lt;pp&gt; · &lt;st&gt;", r[1])
        self.assertEqual(r[1].count("data-hnref"), 2)   # only rows with an open ref
        self.assertIn('data-hnref="s:1&quot;"', r[1])
        self.assertIn('data-hnref="s:2"', r[1])
        self.assertEqual(r[1].count("파이프라인에 없음"), 1)   # "t" has no pipes key (other platforms): empty cell
        self.assertIn('<span class=hnps></span>', r[1])
        self.assertLess(r[1].index(">s&lt;b&gt;<"), r[1].index(">t<"))
        o = _js("console.log(JSON.stringify(hnSkills([{name: 'a', scope: 'user'}, {name: 'b', scope: 'user', n: 1}])))")
        self.assertLess(o.index(">b<"), o.index(">a<"))   # no pipes key: used only when n > 0
        self.assertNotIn("파이프라인에 없음", o)
        q = _js("console.log(JSON.stringify(hnSkills([{name: 'c1', scope: 'user', n: 5, pipes: []}, {name: 'z', scope: 'user', pipes: []},"
                " {name: 'l1', scope: 'user', pipes: [{pipe: 'p', stage: 's'}]}, {name: 'c2', scope: 'user', n: 1, pipes: []},"
                " {name: 'off', scope: 'user', on: false, pipes: [{pipe: 'p', stage: 't'}]}])))")
        self.assertEqual([q.index(">%s<" % n) for n in ("l1", "off", "c1", "c2", "z")],
                         sorted(q.index(">%s<" % n) for n in ("l1", "off", "c1", "c2", "z")))   # linked, counted, rest; stable
        self.assertLess(q.index("class=hnps", q.index(">off<")), q.index("hnoffb"))   # 꺼짐 after the chip cell, not before it
        self.assertNotIn("hntl", r[1])   # ⚠.hntl overrides the 52px badge column
        self.assertIn("꺼짐", r[1])
        self.assertEqual(r[1].count('class="hnar hnoff'), 1)
        self.assertIn("없음", r[2])
        self.assertEqual(r[3], "")

    def test_mcp_status_dot(self):
        mc = [{"name": "a", "scope": "user", "status": "fail", "err": "<E>", "fail_at": 5, "last": 3},
              {"name": "b", "scope": "user", "status": "ok", "last": 9, "fail_at": 4}, {"name": "c", "scope": "user", "status": "<x>"},
              {"name": "d", "scope": "user", "status": "ok", "last": 0}]
        r = _js("console.log(JSON.stringify([hnTools(%s), hnSkills(%s)]))" % (json.dumps(mc), json.dumps(mc)))
        self.assertEqual((r[0].count("hnst-fail"), r[0].count("hnst-ok"), r[0].count("hnst-none")), (1, 2, 1))
        self.assertIn("마지막 실패: T5 · &lt;E&gt;", r[0])
        # 'ok' never claims success: the call result is not read
        self.assertIn("마지막 호출: T9 (결과는 확인하지 않음) · 이전 실패: T4", r[0])
        self.assertNotIn("성공", r[0])
        self.assertIn("연결 실패 기록 없음 · 호출 기록 없음", r[0])   # last = 0 must not render as a date
        self.assertEqual(r[0].count("hnfailb"), 1)   # one «연결 실패» badge; tooltips may say it too
        self.assertNotIn("<E>", r[0])
        self.assertNotIn("hnst", r[1])   # skills carry no status

    def test_plat_lane_grouping(self):
        ev = [{"ev": "BeforeTool", "lane": "PreToolUse", "hooks": [{"cmd": "a.py", "n": None}]},
              {"ev": "Notification", "lane": "", "hooks": [{"cmd": "b.py"}]},
              {"ev": "BeforeModel", "lane": "", "hooks": [{"cmd": "c.py"}]},
              {"ev": "Stop", "hooks": [{"cmd": "d.py", "n": 0}]}]
        r = _js("const c = hnLanes(%s); console.log(JSON.stringify({cols: c.map(x => [x.evs, x.hooks.map(h => h.ev)]), "
                "html: hnLaneHtml(%s)}))" % (json.dumps(ev), json.dumps(ev)))
        cols = dict((tuple(e), h) for e, h in r["cols"])
        self.assertEqual(cols[("PreToolUse",)], ["BeforeTool"])
        self.assertEqual(cols[("Stop", "SubagentStop")], ["Stop"])           # cc rows (no lane) group by ev
        self.assertEqual(cols[("BeforeModel", "Notification")], ["BeforeModel", "Notification"])   # lane "" folds
        self.assertEqual(cols[("Notification",)], [])
        self.assertIn("BeforeTool · ", r["html"])   # native name shown on a lane chip
        self.assertIn('<i class="hncr"></i>', r["html"])   # n null = blank
        self.assertIn('<i class="hncr" title="출력을 남긴 실행만 집계">—</i>', r["html"])   # n 0 = dash

    def test_group_count_marked(self):
        r = _js("console.log(JSON.stringify([hnChip({cmd: 'a.py', n: null, quiet: 1}), hnChip({cmd: 'b.py', n: 4, last: 3}), hnChip({cmd: 'c.py', n: null})]))")
        self.assertIn('<i class="hncr hncrg" title="출력 없는 실행은 기록되지 않아 횟수를 알 수 없음">?</i>', r[0])
        self.assertIn('title="출력을 남긴 실행만 집계 · T3">4회', r[1])
        self.assertIn('<i class="hncr"></i>', r[2])   # other platforms: no records, no tooltip

    def test_fold_long_lists(self):
        ag = [{"name": "a%d" % i, "scope": "user", "pipes": [], "n": 0} for i in range(5)] + [{"name": "used", "scope": "user", "pipes": [{"pipe": "p", "stage": "s"}]}]
        sk = [{"name": "s%d" % i, "scope": "user", "n": 1 if i == 9 else 0} for i in range(10)]
        sk[4]["pipes"] = [{"pipe": "p", "stage": "s"}]
        r = _js("const a = hnAgents(%s); HN.fold.sk = true; console.log(JSON.stringify([a, hnSkills(%s), hnTools(%s)]))"
                % (json.dumps(ag), json.dumps(sk), json.dumps(sk)))
        self.assertLess(r[0].index("used"), r[0].index("<details"))   # used agent first, outside the fold
        self.assertIn("나머지 5개", r[0])
        self.assertNotIn("<details class=hnmore data-hnmore=ag open", r[0])
        self.assertIn("data-hnmore=sk open", r[1])                      # open state survives a repaint
        self.assertLess(r[1].index(">s9<"), r[1].index("<details"))
        self.assertLess(r[1].index(">s4<"), r[1].index(">s9<"))       # used rows keep server order
        self.assertIn("나머지 8개", r[1])
        self.assertNotIn("<details", r[2])                              # MCP list never folds

    def test_plat_switch(self):
        base = {"ok": True, "events": [], "rules": [], "agents": [], "counts": {}, "mcps": [], "skills": []}
        one = _js("HN.data[hnKey('/w/a')] = %s; HN.at[hnKey('/w/a')] = NOW; HN.plats = ['cc']; console.log(JSON.stringify(hnHtml()))" % json.dumps(base))
        self.assertNotIn("data-hnplat", one)
        sw = _js("console.log(JSON.stringify(hnPlatSwitch(['cc', 'cx', 'gm'])))")
        self.assertEqual(sw.count("data-hnplat"), 3)
        self.assertIn('aria-label="Codex"', sw)
        import re
        text = re.sub(r"<[^>]*>", "", sw)   # visible text only
        for nm in ("Codex", "Gemini", "클로드", "Claude"):
            self.assertNotIn(nm, text)
        self.assertIn('class="hnpb ailg-cc on"', sw)

    def test_mcp_skill_missing_fields(self):
        data = {"ok": True, "events": [], "rules": [], "agents": [], "counts": {}}
        h = _js("HN.data[hnKey('/w/a')] = %s; HN.at[hnKey('/w/a')] = NOW; console.log(JSON.stringify(hnHtml()))" % json.dumps(data))
        self.assertNotIn("MCP 서버", h)
        data.update(mcps=[], skills=[{"name": "sk", "scope": "user"}])
        h = _js("HN.data[hnKey('/w/a')] = %s; HN.at[hnKey('/w/a')] = NOW; console.log(JSON.stringify(hnHtml()))" % json.dumps(data))
        self.assertIn("MCP 서버", h)
        self.assertIn(">sk<", h)

    def test_flow_summary(self):
        ev = [{"ev": "PreToolUse", "hooks": [{"cmd": "python3 /h/guard.py", "n": 5, "eff": "block"}, {"cmd": "b.sh", "n": None, "eff": "inject"}]},
              {"ev": "Stop", "hooks": [{"cmd": "c.sh", "n": 3, "eff": "inject"}, {"cmd": "<q>.sh", "quiet": True, "eff": "log"}]}]
        h = _js("console.log(JSON.stringify(hnSum(%s)))" % json.dumps(ev))
        for t in ("훅 4개", "8회", "기록 없음 2", "차단 가능 1", "출력이 가장 많은 훅: guard.py PreToolUse 5회", "출력을 남긴 실행만 집계", "b class=warn"):
            self.assertIn(t, h)
        ev[0]["hooks"][0]["eff"] = "log"
        self.assertNotIn("warn", _js("console.log(JSON.stringify(hnSum(%s)))" % json.dumps(ev)))

    def test_flow_fold(self):
        data = {"ok": True, "events": [{"ev": "Stop", "hooks": [{"cmd": "c.sh", "n": 3}]}], "rules": [], "agents": []}
        pre = "HN.data[hnKey('/w/a')] = %s; HN.at[hnKey('/w/a')] = NOW;" % json.dumps(data)
        a, b = _js(pre + " const a = hnHtml(); HN.flowOpen = false; console.log(JSON.stringify([a, hnHtml()]))")
        self.assertIn("<details class=hnflow data-hnflow open><summary>", a)
        self.assertIn("<details class=hnflow data-hnflow><summary>", b)
        summ = a.split("<summary>", 1)[1].split("</summary>", 1)[0]
        self.assertIn("훅 흐름", summ)
        self.assertIn("class=hnsum", summ)
        self.assertNotIn("class=hnl>", summ)

    def test_verdict_line_and_rows(self):
        from sidereus import demo
        code, d = demo._demo_harness(1e9, "/api/harness")
        self.assertEqual(code, 200)
        whys = set()
        for rows in [h for e in d["events"] for h in e["hooks"]], d["rules"], d["agents"], d["mcps"], d["skills"]:
            whys.update(r["vd"]["why"] for r in rows if r.get("vd"))
        self.assertEqual(whys, {"hook_missing", "mcp_fail", "ref_missing", "idle", "dup", "slow_block", "rule_big"})   # demo shows every code
        self.assertEqual(demo._demo_harness(1e9, "/api/harness/file")[0], 404)
        d["agents"][1]["vd"]["vp"]["pipe"] = "<x>"
        d["mcps"][0]["vd"] = {"lvl": "<bad>", "why": "mcp_fail", "id": "v9"}   # unknown lvl is ignored, never reaches a class
        h = _js("HN.data[hnKey('/w/a')] = %s; HN.at[hnKey('/w/a')] = NOW; console.log(JSON.stringify(hnHtml()))" % json.dumps(d))
        self.assertLess(h.index("점검 결과"), h.index("훅 흐름"))
        self.assertIn('data-hnvdgo=bad title="다음 항목으로 이동">문제 <b>3</b>', h)
        self.assertIn('data-hnvdgo=check', h)
        self.assertIn("정상 8", h)
        self.assertEqual(h.count('data-hnvdl=bad'), 3)
        self.assertEqual(h.count('data-hnvdl=check'), 4)
        self.assertEqual(h.count("class=\"hnvdr"), 7)
        for t in ("스크립트 파일이 없음", "matcher «Edit|Write»", "settings.json, .claude/settings.json", "Stop 에서 최대 90초",
                  "큰 규칙 파일 (52000B)", "파이프라인 &lt;x&gt; · 배포", "연결 실패 기록이 마지막"):
            self.assertIn(t, h)
        self.assertNotIn("<x>", h)
        self.assertNotIn("<bad>", h)
        self.assertNotIn("connection refused</span>", h)   # err stays in the status tooltip, not the reason line
        e = _js("LANG = 'en'; console.log(JSON.stringify(%s.map(v => hnVdTxt(v))))"
                % json.dumps([{"lvl": "check", "why": w, "vp": {"days": 3, "matcher": "m", "srcs": ["a"], "ev": "Stop", "timeout": 60,
                                                                  "bytes": 9, "pipe": "p", "stage": "s"}}
                              for w in ("hook_missing", "mcp_fail", "ref_missing", "idle", "dup", "slow_block", "rule_big", "zz")]))
        for t in e:
            self.assertFalse(any("가" <= c <= "힣" for c in t), t)   # every reason has English
        with open(os.path.join(ROOT, "web", "js", "06-i18n-x.js"), encoding="utf-8") as f:
            x = f.read()
        for k in ("점검 결과", "다음 항목으로 이동"):
            self.assertIn(": '%s'" % k, x)   # I18N.ko value

    def test_results_empty_state(self):
        r = _js("console.log(JSON.stringify([hnRes([]), hnRes(undefined)]))")
        for h in r:
            self.assertIn("아직 기록이 없습니다 — scripts/check.sh 를 실행하면 쌓입니다", h)
            self.assertNotIn("hnrun", h)
        with open(os.path.join(ROOT, "web", "js", "06-i18n-x.js"), encoding="utf-8") as f:
            x = f.read()
        for k in ("결과", "구성 지도", "변경 있음", "아직 기록이 없습니다 — scripts/check.sh 를 실행하면 쌓입니다"):
            self.assertIn(": '%s'" % k, x)   # I18N.ko value

    def test_results_fail_row_escaped(self):
        ev = [{"v": 1, "kind": "check", "ts": 1790000000, "mode": "fast", "repo": "/w/a", "head": "abcdef1234567", "dirty": True, "rc": 1,
               "steps": [{"name": "tests", "rc": 1, "n": 912, "failed": 3, "secs": 41.2}, {"name": "<b>x</b>", "rc": 0, "secs": 0.42}],
               "screen": [{"w": 900, "lang": "ko", "ok": False, "diff": 17}]},
              {"ts": 1789990000, "mode": "full", "head": "0123", "rc": 0, "steps": []}]
        h = _js("console.log(JSON.stringify(hnRes(%s)))" % json.dumps(ev))
        self.assertIn("tests rc=1 · 실패 3/912 · 41s", h)
        self.assertIn("&lt;b&gt;x&lt;/b&gt; rc=0 · 0.4s", h)
        self.assertNotIn("<b>x", h)
        self.assertIn("900 ko ", h)
        self.assertIn("(diff 17)", h)
        self.assertIn("변경 있음", h)
        self.assertIn(">abcdef12<", h)
        self.assertEqual(h.count('class="hnrun hnng"'), 1)
        self.assertLess(h.index("FAIL"), h.index("PASS"))   # newest first, server order kept

    def test_step_without_count_shows_no_zero_ratio(self):
        h = _js("console.log(JSON.stringify([hnStep({name:'page',rc:0,n:0,failed:0,secs:1}), hnStep({name:'bash-n',rc:1,n:0,failed:1,secs:0})]))")
        self.assertNotIn("실패", h[0])
        self.assertIn("실패 1/0", h[1])

    def test_config_fold(self):
        data = {"ok": True, "events": [], "rules": [], "agents": [], "verdict": {"bad": 2, "check": 0, "ok": 5}, "evidence": []}
        pre = "HN.data[hnKey('/w/a')] = %s; HN.at[hnKey('/w/a')] = NOW; HN.plats = ['cc', 'cx'];" % json.dumps(data)
        a, b = _js(pre + " const a = hnHtml(); HN.cfgOpen = true; console.log(JSON.stringify([a, hnHtml()]))")
        self.assertIn("<details class=hncfg><summary", a)
        self.assertIn("<details class=hncfg open><summary", b)
        self.assertLess(a.index("결과"), a.index("hncfg"))   # results first
        self.assertLess(a.index("hncfg"), a.index("data-hnplat"))   # switch folds with the map
        summ = a.split("<summary class=hncfgs>", 1)[1].split("</summary>", 1)[0]
        self.assertIn("구성 지도", summ)
        self.assertIn("문제 2", summ)
        self.assertNotIn("<button", summ)

    # Pinned trail shape (same keys as tests/test_harness_trail.py).
    _TRAIL = {"fixes": [{"mode": "fast", "fail": {"ts": 1790000000, "head": "abcd1234ffff", "dirty": False},
                         "pass": {"ts": 1790000600, "head": "ef567890aaaa", "dirty": True}, "commits": 2,
                         "flipped": ["tests"], "still": ["<img onerror=1>"]}],
              "held": [{"mode": "fast", "ts": 1790000600, "head": "ef567890aaaa", "dirty": False, "state": "held", "steps": [], "at": 0, "git": True},
                       {"mode": "full", "ts": 1790000700, "head": "\"><x>", "dirty": False, "state": "broke", "steps": ["<b>s</b>"], "at": 1790000900, "git": True},
                       {"mode": "full", "ts": 1790000800, "head": "1", "dirty": False, "state": "evil\" onclick=1", "steps": [], "at": 0, "git": False}]}

    def test_trail_escapes_and_whitelist(self):
        h = _js("console.log(JSON.stringify(hnTrail(%s)))" % json.dumps(self._TRAIL))
        for bad in ("<img", "<x>", "<b>s", "onclick=1\""):
            self.assertNotIn(bad, h)
        self.assertIn("tests FAIL→PASS", h)
        self.assertIn("커밋 2개", h)
        self.assertIn(">abcd1234<", h)
        self.assertIn("변경 있음", h)
        self.assertIn("Stable 1 · Regressed 1", h)
        self.assertEqual(h.count("class=hntip tabindex=0"), 2)
        self.assertIn("같은 점검이 FAIL 뒤 PASS", h)
        self.assertIn("Unverified = 미커밋 변경 상태의 PASS.", h)
        self.assertIn('class="hntrs hntrs-ok"', h)
        self.assertIn('class="hntrs hntrs-ng"', h)
        self.assertIn("<b class=hntrs>evil&quot; onclick=1</b>", h)   # unknown state: text only, no state class
        self.assertEqual(h.count("hntrs-"), 2)

    def test_trail_empty_and_in_body(self):
        r = _js("console.log(JSON.stringify([hnTrail(undefined), hnTrail({fixes: [], held: []})]))")
        for h in r:
            self.assertIn("FAIL→PASS 전환 기록이 없습니다", h)
            self.assertIn("PASS 기록이 없습니다", h)
            self.assertNotIn("hnrun", h)
        data = {"ok": True, "events": [], "rules": [], "agents": [], "evidence": [], "trail": self._TRAIL}
        pre = "HN.data[hnKey('/w/a')] = %s; HN.at[hnKey('/w/a')] = NOW; HN.plats = ['cc'];" % json.dumps(data)
        a, urls = _js(pre + " const a = hnHtml(); console.log(JSON.stringify([a, URLS]))")
        self.assertLess(a.index("hnres"), a.index("class=hntr>"))
        self.assertLess(a.index("class=hntr>"), a.index("hncfg"))
        self.assertEqual(urls, [])   # trail rides the cached /api/harness body: no extra fetch on paint
        with open(os.path.join(ROOT, "web", "js", "06-i18n-x.js"), encoding="utf-8") as f:
            x = f.read()
        for k in ("FAIL→PASS 전환 기록이 없습니다", "PASS 기록이 없습니다", "그대로"):
            self.assertIn(": '%s'" % k, x)   # I18N.ko value

    def test_trail_one_column_narrow(self):
        with open(os.path.join(ROOT, "web", "css", "41b-harness.css"), encoding="utf-8") as f:
            css = f.read()
        self.assertIn(".hntr{display:grid;grid-template-columns:1fr 1fr", css)
        self.assertIn("@media (max-width:1060px){.hntr{grid-template-columns:1fr}}", css)
        self.assertNotIn("opacity:", css.split("«Red→Green»", 1)[1])

    def test_lives_in_pipeline_tab(self):
        with open(os.path.join(ROOT, "web", "js", "46-tokens-tab.js"), encoding="utf-8") as f:
            tk = f.read()
        with open(os.path.join(ROOT, "web", "js", "48-pipeline.js"), encoding="utf-8") as f:
            pl = f.read()
        self.assertIn("const TKVIEWS = ['use', 'tools'];", tk)
        self.assertNotIn("paintHarness", tk)
        self.assertIn("data-plv", pl)
        self.assertIn("FEATS.harness === false", pl)   # toggle hidden when the feature is off


if __name__ == "__main__":
    unittest.main()
