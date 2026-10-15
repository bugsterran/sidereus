"""Structure «Architecture» project checks (web/js/84l-structure-arch-checks.js): header badge + cut style, default-rules chip,
focus chip, missing-tool text, escaping in the issue list and node pills, DM body, no /api/dm call without confirm."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_fn
from tests._node import node_e

FNS = ["strHdBadge", "hhmm", "archWhyOff", "archBase", "archCands", "archHome", "archChkN", "archChkTools", "archChkSum", "archChkStat",
       "archChkBadge", "archChkOf", "archChkChip", "archChkSvg", "archChkTop", "archChkTopBtn", "archChkHelp", "archChkKey", "archChkSel", "archChkFixCands", "archChkCandLabel", "archChkPick", "archChkFixBody", "archDmBody", "archChkReqKey", "archChkGoLabel", "archChkSentHtml", "archChkWinHtml", "archChkDmBody", "archChkReqHtml", "archChkSentOf", "archChkStrip", "archChkBtn"]
_SRC_P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "js", "84l-structure-arch-checks.js")
with open(_SRC_P, encoding="utf-8") as fh:
    _SRC = fh.read()
SEND = re.search(r"^async function archChkSend\(.*?^}", _SRC, re.S | re.M).group(0)
FIXSEND = re.search(r"^async function archChkFixSend\(.*?^}", _SRC, re.S | re.M).group(0)
PRE = "\n".join([
    "let LANG = 'ko';", i18n_prelude("LANG", ("T", "KE", "U", "TV")), "function sid8(s){ return String(s).slice(0, 8); }",
    "const esc = s => String(s).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));",
    "const ARCH_PL = 'arch-map'; const ARCH_CHK_PL = 'project-checks'; const ARCH = { cache: {}, msg: '', creq: null, cop: false, csent: null };",
    "let SESS = [], POSTS = [], PAINTS = 0; function CLK(){ return '15:00'; } function paintStruct(){ PAINTS++; }",
    "function plMem(){ return {}; } function lsSetJson(){}",
    "async function postJSON(u, b){ POSTS.push([u, b]); return { ok: true }; }",
])

CHECKS = {"commit": "abcdef123", "at": 1700000000, "stale": False, "dirty": False, "src_changed": False,
          "tools": [{"id": "ruff", "rules": "project", "status": "ok", "ms": 120, "n": {"error": 2, "warning": 3}},
                    {"id": "mypy", "rules": "default", "status": "fail", "why": "exit 2", "ms": 900, "n": {"error": 1, "warning": 0}},
                    {"id": "eslint", "rules": "default", "status": "missing", "why": "install: npm i -D eslint", "ms": 0, "n": {}},
                    {"id": "tsc", "rules": "project", "status": "skipped", "why": "time budget used", "ms": 0, "n": {}}, {"id": "go", "rules": "project", "status": "skipped", "ms": 0, "n": {}}],
          "mods": {"a": {"error": 2, "warning": 1}, "b": {"error": 0, "warning": 0}},
          "other": {"error": 1, "warning": 2},
          "top": [{"tool": "ruff", "file": "b.py", "line": "x", "rule": "W2", "sev": "warning", "mod": "b"},
                  {"tool": "ru<f>f", "file": "a/<x>.py", "line": 7, "rule": "E<1>\"", "sev": "error", "mod": "<m>"}]}


def run(body, lang="ko"):
    pre = PRE if lang == "ko" else PRE.replace("let LANG = 'ko';", "let LANG = 'en';", 1)
    js = "process.env.TZ = 'UTC';\n" + pre + "\n" + "\n".join(js_fn(n) for n in FNS) + "\n" + SEND + "\n(async () => {\n" + body + "\n})().catch(e => { console.error(e); process.exit(1); });"
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class StructArchChecks(unittest.TestCase):
    def test_badge_text_and_cut(self):
        r = run("const d = {checks: " + json.dumps(CHECKS) + "}; const s = JSON.parse(JSON.stringify(d)); s.checks.stale = true;"
                "console.log(JSON.stringify([archChkBadge(d), archChkBadge(s), archChkBadge({checks: null}), archChkBadge({})]));")
        self.assertIn("검사 1종 · 오류 3 · 경고 3", r[0])
        self.assertNotIn("strbg-cut", r[0])
        self.assertIn("strbg-cut", r[1])
        self.assertEqual(r[2:], ["", ""])

    def test_english_badge(self):
        r = run("console.log(JSON.stringify(archChkBadge({checks: " + json.dumps(CHECKS) + "})));", lang="en")
        self.assertIn("Checks 1 · errors 3 · warnings 3", r)

    def test_default_rules_chip_only_for_default(self):
        r = run("const c = " + json.dumps(CHECKS) + "; const p = JSON.parse(JSON.stringify(c)); p.tools.forEach(t => { t.rules = 'project'; });"
                "console.log(JSON.stringify([archChkBadge({checks: c}), archChkBadge({checks: p})]));")
        self.assertIn("strbg-archckd", r[0])
        chip = r[0].split("strbg-archckd")[1].split("</em>")[0]
        self.assertIn('>기본 규칙', chip)                          # short text, tool ids in the tooltip
        self.assertIn("프로젝트 자체 기준이 아님\nmypy\"", chip)    # only mypy ran with default rules (eslint missing)
        self.assertNotIn("eslint", chip)
        self.assertNotIn("ruff", chip)
        self.assertNotIn("strbg-archckd", r[1])

    def test_tool_status_text(self):
        r = run("const c = " + json.dumps(CHECKS) + "; console.log(JSON.stringify([c.tools.map(archChkStat), archChkBadge({checks: Object.assign({}, c, {src_changed: true})})]));")
        self.assertEqual(r[0][2], "사용 불가: install: npm i -D eslint")   # no doubled «install:»
        self.assertEqual(r[0][3], "건너뜀: time budget used")
        self.assertEqual(r[0][4], "건너뜀")
        self.assertEqual(r[0][1], "실패: exit 2")
        self.assertIn("검사 중 소스가 바뀜", r[1])

    def test_chip_empty_when_zero(self):
        r = run("const d = {checks: " + json.dumps(CHECKS) + "}; console.log(JSON.stringify([archChkChip('a', d), archChkChip('b', d), archChkChip('zz', d), archChkChip('a', {})]));")
        self.assertIn("오류 2", r[0])
        self.assertIn("경고 1", r[0])
        self.assertEqual(r[1:], ["", "", ""])

    def test_top_badge_present_absent(self):
        r = run("const c = " + json.dumps(CHECKS) + "; const e = Object.assign({}, c, {top: []});"
                "console.log(JSON.stringify([archChkBadge({checks: c}), archChkBadge({checks: e}), archChkTopBtn({checks: c})]));")
        self.assertIn("data-arck", r[0])
        self.assertIn("주요 문제 2건", r[0])
        self.assertLess(r[0].index("검사 1종"), r[0].index("data-arck"))   # right after the checks badge
        self.assertNotIn("data-arck", r[1])
        self.assertTrue(r[2].startswith("<button"))
        self.assertNotIn("archckiw", r[0])                  # errors > 0 -> red
        w = run("const c = " + json.dumps(CHECKS) + "; c.tools.forEach(t => { t.n = {warning: 1}; }); console.log(JSON.stringify(archChkTopBtn({checks: c})));")
        self.assertIn("strbg-archckiw", w)                   # warnings only -> amber

    def test_popup_rows_escape_and_order(self):
        r = run("const d = {checks: " + json.dumps(CHECKS) + "}; console.log(JSON.stringify([archChkWinHtml('/r', d, {sel: {}, req: null}, []), archChkTop({checks: {}})]));")
        h = r[0]
        self.assertIn('data-af="a/&lt;x&gt;.py"', h)
        self.assertIn("a/<wbr>&lt;x&gt;.py", h)             # full path, breakable after «/»
        self.assertIn('title="a/&lt;x&gt;.py:7"', h)        # full-text tooltip fallback
        self.assertIn('<code title="E&lt;1&gt;&quot;">', h)
        self.assertIn("E&lt;1&gt;&quot;", h)
        self.assertIn("ru&lt;f&gt;f", h)
        self.assertIn('<em title="&lt;m&gt;">&lt;m&gt;</em>', h)
        self.assertNotIn("<x>", h)
        self.assertNotIn("<m>", h)
        self.assertIn("data-ckv", h)                       # row click -> code popup
        self.assertIn('data-al="1"', h)                    # bad line -> 1
        self.assertIn("data-ckfix disabled", h)            # no live session at all
        self.assertIn("열린 세션이 없습니다", h)
        self.assertNotIn("archckh", h)                     # no help data -> no help line
        self.assertLess(h.index('class="error"'), h.index('class="warning"'))   # errors first
        self.assertIn(">오류</b>", h)
        self.assertIn(">경고</b>", h)
        self.assertEqual(r[1], [])

    def test_rule_help_https_only(self):
        c = json.loads(json.dumps(CHECKS))
        c["top"][1]["rk"] = "ruff:E1"; c["rules"] = {"ruff:E1": {"desc": "Use <b>\n hooks", "url": "https://x.dev/r?a=1&b=\"2\""}}
        c["top"][0]["url"] = "javascript:alert(1)"
        c["rules"]["ruff:W2"] = {"desc": "W two", "url": "http://plain"}
        r = run("const d = {checks: " + json.dumps(c) + "}; console.log(JSON.stringify([archChkWinHtml('/r', d, {sel: {}, req: null}, []), archChkHelp(d.checks, Object.assign({}, d.checks.top[0], {url: ''}))]));")
        h = r[0]
        self.assertIn("<span>Use &lt;b&gt; hooks</span>", h)
        self.assertNotIn("x.dev", h)                       # quote inside -> not a valid https url, dropped
        self.assertNotIn("javascript:", h)
        self.assertNotIn("http://plain", h)
        self.assertEqual(r[1], {"desc": "W two", "url": ""})
        c["rules"]["ruff:E1"]["url"] = "https://docs.astral.sh/ruff/rules/x/"
        h = run("const d = {checks: " + json.dumps(c) + "}; console.log(JSON.stringify(archChkWinHtml('/r', d, {sel: {}, req: null}, [])));")
        self.assertIn('<a href="https://docs.astral.sh/ruff/rules/x/" target=_blank rel="noopener noreferrer">문서 ↗</a>', h)

    def test_fix_request_body_and_states(self):
        c = json.loads(json.dumps(CHECKS)); c["top"][1]["rk"] = "ruff:E1"; c["rules"] = {"ruff:E1": {"desc": "Bad thing"}}
        sess = [{"sid": "s-old", "cwd": "/r/sub", "mbox": "a", "mboxSrc": "identity", "state": "idle", "ageSec": 900},
                {"sid": "s-new", "cwd": "/r", "mbox": "b", "mboxSrc": "identity", "state": "idle", "ageSec": 5},
                {"sid": "s-out", "cwd": "/rx", "mbox": "c", "mboxSrc": "identity", "state": "idle", "ageSec": 1},
                {"sid": "s-done", "cwd": "/r", "mbox": "d", "mboxSrc": "identity", "state": "done", "ageSec": 0}]
        r = run("const d = {checks: " + json.dumps(c) + "}, c = archChkFixCands(" + json.dumps(sess) + ", '/r'), top = archChkTop(d);"
                "const S = {sel: {}, req: null}; const h0 = archChkWinHtml('/r', d, S, c);"
                "S.sel[archChkKey(top[0])] = 1; const h1 = archChkWinHtml('/r', d, S, c);"
                "S.req = {sid: c[0].sid, busy: false}; const h2 = archChkWinHtml('/r', d, S, c);"
                "S.sel[archChkKey(top[1])] = 1; const body = archChkFixBody('/r', d.checks, archChkSel(d, S.sel)); S.req = null; S.sent = {to: archChkCandLabel(c[0]), at: '14:05', key: 'k'};"
                "console.log(JSON.stringify([c.map(x => x.sid), h0, h1, h2, body, archChkWinHtml('/r', d, S, c)]));")
        self.assertEqual(r[0], ["s-new", "s-old", "s-out"])  # in-repo tier first (most recent first), then the rest
        self.assertIn("data-ckfix disabled", r[1])          # nothing selected
        self.assertIn("문제를 하나 이상 고르세요", r[1])
        self.assertNotIn("data-ckfix disabled", r[2])
        self.assertIn("개선 요청 (1)", r[2])
        self.assertIn("data-ckgo", r[3])
        self.assertNotIn("data-ckgo disabled", r[3])
        self.assertIn("Please fix these ru&lt;f&gt;f findings in /r (commit abcdef12):", r[3])   # escaped in the preview
        self.assertEqual(r[4], "Please fix these ru<f>f, ruff findings in /r (commit abcdef12):\n"
                               "Target repository: /r — work there (cd), not in your own cwd.\n"
                               "- error · E<1>\" · a/<x>.py:7 — Bad thing\n- warning · W2 · b.py:1\n"
                               "Fix the cause, keep behaviour, run the project's tests.\n"
                               "Once the fix is committed, request a re-analysis of /r so the architecture diagram reflects it — run:\n"
                               "파이프라인 arch-map 실행 — 요청: «/r 아키텍처 구조도 생성»\n대상 저장소: /r\n"
                               "읽기 전용, 저장소에 쓰지 않음 — 쓰기는 ${MAILBOX_DIR:-~/.mailbox-mcp}/arch/<key>/<commit>/ 아래만 (key: 파이프라인 rules)\n"
                               "파이프라인: .claude/pipelines/arch-map.json (읽기 계획 → 모듈 그리기 → 흐름 그리기 → 검증)\n"
                               "게이트: /usr/bin/python3 scripts/arch_verify.py --last")
        self.assertIn('class="archckst archsent"', r[5])   # success style, not the grey scanner status line
        self.assertIn("요청함 → r · s-new · b · idle · 14:05", r[5])
        self.assertIn('data-ckall checked', r[5])

    def test_fix_cands_repo_boundary(self):
        base = {"mbox": "m", "mboxSrc": "identity", "state": "idle", "ageSec": 1}
        sess = [dict(base, sid="root", cwd="/x/shop-api"), dict(base, sid="sub", cwd="/x/shop-api/src"),
                dict(base, sid="sib", cwd="/x/shop-origin", repos=["/x/shop-api"]),
                dict(base, sid="other", cwd="/u/.mailbox-mcp", repos=["/x/shop-api"]),
                dict(base, sid="wt", cwd="/private/tmp/w/shop-api", wt={"root": "/private/tmp/w/shop-api", "main": "/x/shop-api"}),
                dict(base, sid="wt2", cwd="/private/tmp/w2/shop-api", wt={"root": "/private/tmp/w2/shop-api", "main": ""})]
        r = run("console.log(JSON.stringify(archChkFixCands(" + json.dumps(sess) + ", '/x/shop-api').map(x => [x.sid, x.g]).sort()));")
        self.assertEqual(r, [["other", 1], ["root", 0], ["sib", 1], ["sub", 0], ["wt", 0], ["wt2", 2]])   # repos -> tier 1, never 0
        r = run("console.log(JSON.stringify(archChkFixCands(" + json.dumps(sess) + ", '/x/shop').map(x => x.g)));")
        self.assertEqual(r, [2] * 6)                           # prefix of a sibling is not a parent

    def test_fix_cands_tiers(self):
        sess = [{"sid": "o-new", "cwd": "/z", "project": "zed", "mbox": "zz", "mboxSrc": "identity", "state": "idle", "ageSec": 1, "task": "SECRET"},
                {"sid": "u1", "cwd": "/y", "repos": ["/r"], "mbox": "<u>", "mboxSrc": "identity", "state": "busy", "ageSec": 50},
                {"sid": "p-nolog", "cwd": "/r", "mbox": "", "state": "idle", "ageSec": 2},
                {"sid": "p-log", "cwd": "/r/a", "mbox": "pm", "mboxSrc": "identity", "state": "idle", "ageSec": 300, "model": "opus"},
                {"sid": "cx", "cwd": "/r", "plat": "codex", "state": "idle"}, {"sid": "dn", "cwd": "/r", "state": "done"}]
        r = run("const c = archChkFixCands(" + json.dumps(sess) + ", '/r'), d = {checks: " + json.dumps(CHECKS) + "};"
                "const h = archChkWinHtml('/r', d, {sel: {}, req: {sid: 'u1', busy: false}}, c);"
                "console.log(JSON.stringify([c.map(x => x.sid), c.map(archChkCandLabel), h]));")
        self.assertEqual(r[0], ["p-log", "p-nolog", "u1", "o-new"])   # tier, then logged-in, then age
        self.assertEqual(r[1][0], "a · p-log · pm · idle · opus")
        self.assertEqual(r[1][3], "zed · o-new · zz · idle")
        self.assertNotIn("SECRET", "".join(r[1]) + r[2])                # metadata only
        h = r[2]
        self.assertLess(h.index('label="이 프로젝트"'), h.index('label="이 저장소를 쓰는 세션"'))
        self.assertLess(h.index('label="이 저장소를 쓰는 세션"'), h.index('label="다른 세션"'))
        self.assertIn("y · u1 · &lt;u&gt; · busy", h)
        self.assertIn('value="u1" selected', h)
        r = run("const c = archChkFixCands(" + json.dumps(sess[:1]) + ", '/r'); console.log(JSON.stringify(archChkWinHtml('/r', {checks: " + json.dumps(CHECKS) + "}, {sel: {}, req: {sid: 'o-new', busy: false}}, c)));")
        self.assertNotIn("<optgroup label=\"이 프로젝트\"", r)            # empty group omitted
        self.assertIn('label="다른 세션"', r)

    def test_fix_btn_enabled_without_project_session(self):
        sess = [{"sid": "o1", "cwd": "/z", "mbox": "zz", "mboxSrc": "identity", "state": "idle", "ageSec": 1}]
        r = run("const d = {checks: " + json.dumps(CHECKS) + "}, top = archChkTop(d), S = {sel: {}, req: null}; S.sel[archChkKey(top[0])] = 1;"
                "console.log(JSON.stringify([archChkWinHtml('/r', d, S, archChkFixCands(" + json.dumps(sess) + ", '/r')), archChkWinHtml('/r', d, S, archChkFixCands([], '/r'))]));")
        self.assertNotIn("data-ckfix disabled", r[0])
        self.assertIn("data-ckfix disabled", r[1])
        self.assertIn("열린 세션이 없습니다", r[1])

    def test_fix_body_target_repo(self):
        r = run("console.log(JSON.stringify(archChkFixBody('/x/shop-api', {commit: ''}, [{tool: 'ruff', file: 'a.py', line: 3, rule: 'F1', sev: 'error'}])));")
        self.assertEqual(r.splitlines()[:2], ["Please fix these ruff findings in /x/shop-api:",
                                              "Target repository: /x/shop-api — work there (cd), not in your own cwd."])

    def test_fix_body_requests_remap(self):
        r = run("const it = [{tool: 'ruff', file: 'a.py', line: 3, rule: 'F1', sev: 'error'}], d = {sidereus: '/sid', checks: {commit: '', top: [{tool: 'ruff', file: 'a.py', line: 3, rule: 'F1', sev: 'error', mod: 'a'}]}};"
                "const S = {sel: {}, req: {sid: 's1', busy: false}}; S.sel[archChkKey(d.checks.top[0])] = 1;"
                "console.log(JSON.stringify([archChkFixBody('/x/shop-api', {commit: ''}, it, '/sid'), archChkWinHtml('/x/shop-api', d, S, [{sid: 's1', g: 0, login: 1}])]));")
        for s in ("Once the fix is committed, request a re-analysis of /x/shop-api", "/sid/.claude/pipelines/arch-map.json",
                  "/usr/bin/python3 /sid/scripts/arch_verify.py --last"):
            self.assertIn(s, r[0])
        self.assertIn("게이트: /usr/bin/python3 /sid/scripts/arch_verify.py --last</pre>", r[1])   # full text in the preview (rule 7)

    def test_fix_last_pick_preselect(self):
        sess = [{"sid": "a1", "cwd": "/r", "mbox": "a", "mboxSrc": "identity", "state": "idle", "ageSec": 1},
                {"sid": "b2", "cwd": "/z", "mbox": "b", "mboxSrc": "identity", "state": "idle", "ageSec": 1}]
        r = run("const MEM = {'/r': 'b2', '/q': 'dead'}; globalThis.lsJson = (k, d) => k === 'sidereus.ckfix' ? MEM : d;"
                "const c = archChkFixCands(" + json.dumps(sess) + ", '/r'), c2 = archChkFixCands(" + json.dumps(sess) + ", '/q');"
                "console.log(JSON.stringify([archChkPick(c, '/r'), archChkPick(c2, '/q'), archChkPick(c, '/none'), archChkPick([], '/r')]));")
        self.assertEqual(r, ["b2", "a1", "a1", ""])            # alive -> kept; dead/unknown -> first candidate

    def test_svg_pills(self):
        r = run("const R = {x: 10, y: 20, w: 100, h: 30};"
                "console.log(JSON.stringify([archChkSvg(R, {e: 3, w: 0}), archChkSvg(R, {e: 0, w: 120}), archChkSvg(R, {e: 0, w: 0})]));")
        self.assertIn("archcke", r[0])
        self.assertNotIn("archckw", r[0])
        self.assertIn(">99+<", r[1])
        self.assertEqual(r[2], "")

    def test_dm_body(self):
        r = run("console.log(JSON.stringify(archChkDmBody('/repo/x', '/home/sidereus/')));")
        self.assertIn("파이프라인 project-checks 실행", r)
        self.assertIn("대상 저장소: /repo/x", r)
        self.assertIn("읽기 전용", r)
        self.assertIn("/home/sidereus/.claude/pipelines/project-checks.json", r)

    def test_send_only_on_confirm(self):
        r = run("SESS = [{sid: 's1', cwd: '/r', mbox: 'me', mboxSrc: 'identity', state: 'idle'}];"
                "ARCH.cache['/r'] = {ok: true, sidereus: '/home/sidereus', checks_runnable: true};"
                "const c = archCands('/home/sidereus', SESS, '/r'); const h0 = archChkBtn('/r', '/home/sidereus', c);"
                "const s0 = archChkStrip('/r', ARCH.cache['/r'], '/home/sidereus', c);"
                "const n0 = POSTS.length; const nx = await archChkSend();"   # no preview open -> nothing
                "ARCH.creq = {p: '/r', sid: 's1', busy: false}; const h1 = archChkStrip('/r', ARCH.cache['/r'], '/home/sidereus', c);"
                "const b1 = archChkBtn('/r', '/home/sidereus', c);"
                "await archChkSend(); const h2 = archChkStrip('/r', ARCH.cache['/r'], '/home/sidereus', c);"
                "console.log(JSON.stringify([h0, n0, nx, POSTS.length, h1, POSTS[0], h2, ARCH.creq, s0, b1, archChkBtn('/r', '/home/sidereus', c)]));")
        self.assertIn("data-arcq", r[0])
        self.assertEqual(r[8], "")   # button lives in the header; no list -> no strip
        self.assertNotIn("data-arcq", r[4])
        self.assertIn(" on", r[9])
        self.assertEqual(r[10], "")   # hidden while the sent line shows
        self.assertEqual([r[1], r[2], r[3]], [0, False, 1])
        self.assertIn("data-arcgo", r[4])
        self.assertIn("project-checks", r[4])
        self.assertEqual(r[5][0], "/api/dm")
        self.assertEqual(r[5][1]["thread"], "pipeline:project-checks")
        self.assertEqual(r[5][1]["to"], "me")
        self.assertEqual(r[5][1]["plreq"], {"kind": "req", "pipeline": "project-checks", "repo": "/r"})   # R1: server records the recipient
        self.assertIn("검사 요청함", r[6])
        self.assertIsNone(r[7])

    def test_button_only_when_runnable(self):
        r = run("const c = []; ARCH.cache['/r'] = {ok: true, checks_runnable: false}; const a = archChkBtn('/r', '/h', c);"
                "ARCH.cache['/r'] = {ok: true}; const b = archChkBtn('/r', '/h', c);"
                "ARCH.cache['/r'] = {ok: true, checks_runnable: true}; const d = archChkBtn('/r', '/h', c);"
                "console.log(JSON.stringify([a, b, d]));")
        self.assertEqual(r[:2], ["", ""])
        self.assertIn("data-arcq", r[2])


    def test_fix_send_inflight_and_repeat_guard(self):
        sess = [{"sid": "s1", "cwd": "/r", "mbox": "me", "mboxSrc": "identity", "state": "idle", "ageSec": 1}]
        r = run("SESS = " + json.dumps(sess) + "; const d = {checks: " + json.dumps(CHECKS) + "}; ARCH.cache['/r'] = d;"
                "let HTML = [], NOTES = [], PEND = null; function lsJson(){ return {}; } function note(m){ NOTES.push(m); }"
                "const S = {p: '/r', sel: {}, req: null, sent: '', msg: ''}; let ARCH_CW = S; S.sel[archChkKey(archChkTop(d)[0])] = 1;"
                "function archChkWinPaint(){ HTML.push(archChkWinHtml(S.p, ARCH.cache[S.p], S, archChkFixCands(SESS, S.p))); }"
                "postJSON = (u, b) => { POSTS.push([u, b]); return new Promise(res => { PEND = res; }); };\n" + FIXSEND + "\n"
                "S.req = {sid: 's1', busy: false}; const p1 = archChkFixSend(); const busy = HTML[HTML.length - 1];"
                "const dup = await archChkFixSend(), n0 = POSTS.length; PEND({ok: true}); await p1; const ok = HTML[HTML.length - 1];"
                "S.req = {sid: 's1', busy: false}; archChkWinPaint(); const again = HTML[HTML.length - 1];"
                "const a1 = archChkFixSend(); const r1 = await a1; const armed = HTML[HTML.length - 1], n1 = POSTS.length;"
                "const p2 = archChkFixSend(); PEND({ok: false, error: 'boom'}); await p2;"
                "console.log(JSON.stringify([busy, dup, n0, ok, again, r1, armed, n1, HTML[HTML.length - 1], NOTES, POSTS.length]));")
        self.assertIn("data-ckgo disabled", r[0])        # confirm disabled while the POST is in flight
        self.assertIn("보내는 중", r[0])
        self.assertEqual([r[1], r[2]], [False, 1])     # a click during the flight sends nothing
        self.assertIn('class="archckst archsent"', r[3])
        self.assertRegex(r[3], r"요청함 → r · s1 · me · idle · \d\d:\d\d")
        self.assertIn("보냄 · 다시 보내기", r[4])       # same findings + same session -> marked as already sent
        self.assertEqual([r[5], r[7]], [False, 1])     # first click only arms
        self.assertIn("확인 — 보내기", r[6])
        self.assertIn('class="archmsg archerr" role=alert', r[8])   # failure stays visible in the error style
        self.assertIn("boom", r[8])
        self.assertEqual(len(r[9]), 1)
        self.assertEqual(r[10], 2)


if __name__ == "__main__":
    unittest.main()
