"""Structure «Architecture» security issues (web/js/84l-structure-arch-checks.js): header badge is the security issues button only,
scanner status text, escaping in the issue list, issues window without tabs, fix request body, no /api/dm call without confirm."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_fn
from tests._node import node_e

FNS = ["mboxIn", "strHdBadge", "hhmm", "archBase", "archHome", "archChkN", "archChkTools", "archChkSum", "archChkStat", "archChkSec",
       "archChkTop", "archChkTopBtn", "archChkHelp", "archChkRule", "archChkKey", "archChkSel", "archChkFixCands", "archChkCandLabel", "archChkPick", "archChkFixBody", "archDmBody", "archChkReqKey", "archChkGoLabel", "archChkSentHtml", "archChkLogHtml", "archChkEntry", "archChkHdBtn", "archChkRunCands", "archChkRunBody", "archChkRunCmds", "archChkScanAt", "archChkRunHtml", "archChkWinHtml"]
FNS.append("plCxHint")   # 48b: Codex recipient hint (archChkRunHtml calls it)
_SRC_P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "js", "84l-structure-arch-checks.js")
with open(_SRC_P, encoding="utf-8") as fh:
    _SRC = fh.read()
FIXSEND = re.search(r"^async function archChkFixSend\(.*?^}", _SRC, re.S | re.M).group(0)
PRE = "\n".join([
    "let LANG = 'ko';", i18n_prelude("LANG", ("T", "KE", "U", "TV")), "function sid8(s){ return String(s).slice(0, 8); }", "function agoAt(s){ return '@' + s; }",
    "const esc = s => String(s).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));",
    "const ARCH_PL = 'arch-map', ARCH_SEC_PL = 'security-checks'; const ARCH = { cache: {}, msg: '' };",
    "let SESS = [], POSTS = []; function lsSetJson(){}",
    "async function postJSON(u, b){ POSTS.push([u, b]); return { ok: true }; }",
])

# /api/arch `checks.security` (sidereus/sec_checks); CK = the whole `checks` object.
CHECKS = {"commit": "abcdef123", "at": 1700000000,
          "tools": [{"id": "gitleaks", "rules": "project", "status": "ok", "ms": 120, "n": {"error": 2, "warning": 3}},
                    {"id": "semgrep", "rules": "default", "status": "fail", "why": "exit 2", "ms": 900, "n": {"error": 1, "warning": 0}},
                    {"id": "osv", "rules": "default", "status": "missing", "why": "install: brew install osv-scanner", "ms": 0, "n": {}},
                    {"id": "npm-audit", "rules": "project", "status": "skipped", "why": "time budget used", "ms": 0, "n": {}}, {"id": "go", "rules": "project", "status": "skipped", "ms": 0, "n": {}}],
          "top": [{"tool": "ruff", "file": "b.py", "line": "x", "rule": "W2", "sev": "warning", "mod": "b"},
                  {"tool": "ru<f>f", "file": "a/<x>.py", "line": 7, "rule": "E<1>\"", "sev": "error", "mod": "<m>"}]}
CK = {"security": CHECKS}


def run(body, lang="ko"):
    pre = PRE if lang == "ko" else PRE.replace("let LANG = 'ko';", "let LANG = 'en';", 1)
    js = "process.env.TZ = 'UTC';\n" + pre + "\n" + "\n".join(js_fn(n) for n in FNS) + "\n(async () => {\n" + body + "\n})().catch(e => { console.error(e); process.exit(1); });"
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class StructArchChecks(unittest.TestCase):
    def test_tool_status_text(self):
        r = run("const c = " + json.dumps(CHECKS) + "; console.log(JSON.stringify(c.tools.map(archChkStat)));")
        self.assertEqual(r[2], "사용 불가: install: brew install osv-scanner")   # no doubled «install:»
        self.assertEqual(r[3], "건너뜀: time budget used")
        self.assertEqual(r[4], "건너뜀")
        self.assertEqual(r[1], "실패: exit 2")

    def test_badge_is_security_button_only(self):
        q = {"commit": "abc", "tools": [{"id": "ruff", "status": "ok", "n": {"error": 1}}], "top": [{"tool": "ruff", "file": "a.py", "line": 1, "sev": "error"}]}
        r = run("console.log(JSON.stringify([archChkTopBtn({checks: " + json.dumps(CK) + "}), archChkTopBtn({checks: " + json.dumps(q) + "}),"
                "archChkTopBtn({checks: null}), archChkTopBtn({}), archChkTopBtn({checks: {security: {tools: [], top: []}}})]));")
        self.assertTrue(r[0].startswith("<button") and r[0].endswith("</button>"))
        self.assertEqual(r[0].count("<button"), 1)           # nothing besides the issues button
        self.assertIn("data-arck", r[0])
        self.assertIn(">보안 2</button>", r[0])
        self.assertNotIn("<em", r[0])                         # no quality badges / chips
        self.assertNotIn("archckiw", r[0])                    # errors > 0 -> red
        self.assertEqual(r[1:4], ["", "", ""])                # a quality-only payload shows nothing
        self.assertIn(">보안 0</button>", r[4])               # shown at 0 so missing scanners stay visible
        w = run("const c = " + json.dumps(CHECKS) + "; c.tools.forEach(t => { t.n = {warning: 1}; }); console.log(JSON.stringify(archChkTopBtn({checks: {security: c}})));")
        self.assertIn("strbg-archckiw", w)                   # warnings only -> amber

    def test_window_has_no_tablist(self):
        r = run("const d = {checks: " + json.dumps(CK) + "}; console.log(JSON.stringify(archChkWinHtml('/r', d, {sel: {}, req: null}, [])));")
        self.assertNotIn("tablist", r)
        self.assertNotIn("data-ckcat", r)
        self.assertIn("<div class=archckst>gitleaks · 정상", r)   # scanner states line
        self.assertIn("점검한 적 없음", r)                        # security history section

    def test_popup_rows_escape_and_order(self):
        r = run("const d = {checks: " + json.dumps(CK) + "}; console.log(JSON.stringify([archChkWinHtml('/r', d, {sel: {}, req: null}, []), archChkTop({checks: {}})]));")
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
        r = run("const d = {checks: {security: " + json.dumps(c) + "}}; console.log(JSON.stringify([archChkWinHtml('/r', d, {sel: {}, req: null}, []), archChkHelp(d.checks, Object.assign({}, d.checks.security.top[0], {url: ''}))]));")
        h = r[0]
        self.assertIn("<span>Use &lt;b&gt; hooks</span>", h)
        self.assertNotIn("x.dev", h)                       # quote inside -> not a valid https url, dropped
        self.assertNotIn("javascript:", h)
        self.assertNotIn("http://plain", h)
        self.assertEqual(r[1], {"desc": "W two", "url": ""})
        c["rules"]["ruff:E1"]["url"] = "https://docs.astral.sh/ruff/rules/x/"
        h = run("const d = {checks: {security: " + json.dumps(c) + "}}; console.log(JSON.stringify(archChkWinHtml('/r', d, {sel: {}, req: null}, [])));")
        self.assertIn('<a href="https://docs.astral.sh/ruff/rules/x/" target=_blank rel="noopener noreferrer">문서 ↗</a>', h)

    def test_fix_request_body_and_states(self):
        c = json.loads(json.dumps(CHECKS)); c["top"][1]["rk"] = "ruff:E1"; c["rules"] = {"ruff:E1": {"desc": "Bad thing"}}
        sess = [{"sid": "s-old", "cwd": "/r/sub", "mbox": "a", "mboxSrc": "identity", "state": "idle", "ageSec": 900},
                {"sid": "s-new", "cwd": "/r", "mbox": "b", "mboxSrc": "identity", "state": "idle", "ageSec": 5},
                {"sid": "s-out", "cwd": "/rx", "mbox": "c", "mboxSrc": "identity", "state": "idle", "ageSec": 1},
                {"sid": "s-done", "cwd": "/r", "mbox": "d", "mboxSrc": "identity", "state": "done", "ageSec": 0}]
        r = run("const d = {checks: {security: " + json.dumps(c) + "}}, c = archChkFixCands(" + json.dumps(sess) + ", '/r'), top = archChkTop(d);"
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
                               "게이트: python3 scripts/arch_verify.py --last (Windows: py scripts/arch_verify.py --last)")
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
        r = run("const c = archChkFixCands(" + json.dumps(sess) + ", '/r'), d = {checks: " + json.dumps(CK) + "};"
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
        r = run("const c = archChkFixCands(" + json.dumps(sess[:1]) + ", '/r'); console.log(JSON.stringify(archChkWinHtml('/r', {checks: " + json.dumps(CK) + "}, {sel: {}, req: {sid: 'o-new', busy: false}}, c)));")
        self.assertNotIn("<optgroup label=\"이 프로젝트\"", r)            # empty group omitted
        self.assertIn('label="다른 세션"', r)

    def test_fix_btn_enabled_without_project_session(self):
        sess = [{"sid": "o1", "cwd": "/z", "mbox": "zz", "mboxSrc": "identity", "state": "idle", "ageSec": 1}]
        r = run("const d = {checks: " + json.dumps(CK) + "}, top = archChkTop(d), S = {sel: {}, req: null}; S.sel[archChkKey(top[0])] = 1;"
                "console.log(JSON.stringify([archChkWinHtml('/r', d, S, archChkFixCands(" + json.dumps(sess) + ", '/r')), archChkWinHtml('/r', d, S, archChkFixCands([], '/r'))]));")
        self.assertNotIn("data-ckfix disabled", r[0])
        self.assertIn("data-ckfix disabled", r[1])
        self.assertIn("열린 세션이 없습니다", r[1])

    def test_fix_body_target_repo(self):
        r = run("console.log(JSON.stringify(archChkFixBody('/x/shop-api', {commit: ''}, [{tool: 'ruff', file: 'a.py', line: 3, rule: 'F1', sev: 'error'}])));")
        self.assertEqual(r.splitlines()[:2], ["Please fix these ruff findings in /x/shop-api:",
                                              "Target repository: /x/shop-api — work there (cd), not in your own cwd."])

    def test_fix_body_requests_remap(self):
        r = run("const it = [{tool: 'ruff', file: 'a.py', line: 3, rule: 'F1', sev: 'error'}], d = {sidereus: '/sid', checks: {security: {commit: '', top: [{tool: 'ruff', file: 'a.py', line: 3, rule: 'F1', sev: 'error', mod: 'a'}]}}};"
                "const S = {sel: {}, req: {sid: 's1', busy: false}}; S.sel[archChkKey(d.checks.security.top[0])] = 1;"
                "console.log(JSON.stringify([archChkFixBody('/x/shop-api', {commit: ''}, it, '/sid'), archChkWinHtml('/x/shop-api', d, S, [{sid: 's1', g: 0, login: 1}])]));")
        for s in ("Once the fix is committed, request a re-analysis of /x/shop-api", "/sid/.claude/pipelines/arch-map.json",
                  "python3 /sid/scripts/arch_verify.py --last (Windows: py /sid/scripts/arch_verify.py --last)"):
            self.assertIn(s, r[0])
        self.assertIn("게이트: python3 /sid/scripts/arch_verify.py --last (Windows: py /sid/scripts/arch_verify.py --last)</pre>", r[1])   # full text in the preview (rule 7)

    def test_fix_last_pick_preselect(self):
        sess = [{"sid": "a1", "cwd": "/r", "mbox": "a", "mboxSrc": "identity", "state": "idle", "ageSec": 1},
                {"sid": "b2", "cwd": "/z", "mbox": "b", "mboxSrc": "identity", "state": "idle", "ageSec": 1}]
        r = run("const MEM = {'/r': 'b2', '/q': 'dead'}; globalThis.lsJson = (k, d) => k === 'sidereus.ckfix' ? MEM : d;"
                "const c = archChkFixCands(" + json.dumps(sess) + ", '/r'), c2 = archChkFixCands(" + json.dumps(sess) + ", '/q');"
                "console.log(JSON.stringify([archChkPick(c, '/r'), archChkPick(c2, '/q'), archChkPick(c, '/none'), archChkPick([], '/r')]));")
        self.assertEqual(r, ["b2", "a1", "a1", ""])            # alive -> kept; dead/unknown -> first candidate

    def test_fix_send_inflight_and_repeat_guard(self):
        sess = [{"sid": "s1", "cwd": "/r", "mbox": "me", "mboxSrc": "identity", "state": "idle", "ageSec": 1}]
        r = run("SESS = " + json.dumps(sess) + "; const d = {checks: " + json.dumps(CK) + "}; ARCH.cache['/r'] = d;"
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

    def test_run_security_check(self):   # relay preview to a logged-in project session, else the terminal command; never sends by itself
        sess = [{"sid": "a1", "cwd": "/x/shop", "mbox": "a", "mboxSrc": "identity", "state": "idle", "ageSec": 1},
                {"sid": "b2", "cwd": "/z", "repos": ["/x/shop"], "mbox": "b", "state": "idle", "ageSec": 1},
                {"sid": "c3", "cwd": "/q", "mbox": "c", "mboxSrc": "identity", "state": "idle", "ageSec": 1}]
        r = run("const d = {ok: true, sidereus: '/sid', checks: null}, c = archChkFixCands(" + json.dumps(sess) + ", '/x/shop'), rc = archChkRunCands(c);"
                "const S = {sel: {}, req: null, run: {sid: rc[0].sid, busy: false}, runSent: null};"
                "const none = Object.assign({}, S, {run: {sid: '', busy: false}});"
                "console.log(JSON.stringify([rc.map(x => x.sid), archChkRunBody('/x/shop', '/sid/'), archChkRunCmds('/x/shop', '/sid'),"
                "archChkRunCmds('/x/\"; rm', '/sid'), archChkRunCmds('/x/shop', ''), archChkRunCmds('/x/%PATH%', '/sid'), archChkRunCmds('/x/!a!', '/sid'), archChkWinHtml('/x/shop', d, S, c), archChkWinHtml('/x/shop', d, none, []),"
                "archChkHdBtn(d), archChkHdBtn({ok: false}), archChkWinHtml('/x/shop', d, Object.assign({}, S, {run: Object.assign({}, S.run, {busy: true})}), c),"
                "archChkScanAt({checks: {security: {at: 5, log: {at_scan: 9}}}}), archChkScanAt({})]));")
        self.assertEqual(r[0], ["a1"])                       # repos-only session is not logged in; other projects never
        self.assertEqual(r[1].splitlines()[0], "파이프라인 security-checks 실행 — 요청: «/x/shop 보안 점검»")
        self.assertIn("/sid/.claude/pipelines/security-checks.json", r[1])
        self.assertIn("--repo /x/shop", r[1])
        self.assertNotIn("/usr/bin/python3", r[1])   # absent on Windows
        self.assertIn("Gate: python3 /sid/scripts/arch_checks.py --verify --last --category security (Windows: py /sid/scripts/arch_checks.py --verify --last --category security)", r[1])
        self.assertEqual(r[2], {"sh": 'python3 "/sid/scripts/arch_checks.py" --repo "/x/shop" --category security',
                                "win": 'py "/sid/scripts/arch_checks.py" --repo "/x/shop" --category security'})
        self.assertEqual(r[3:7], [None] * 4)                 # quoting-breaking path / unknown home / cmd %VAR% !VAR! -> no command
        del r[5:7]
        self.assertIn("data-ckrgo>", r[5])                    # confirm enabled, preview shown
        self.assertIn("security-checks.json", r[5])
        self.assertIn("아직 보안 점검 없음", r[5])
        self.assertNotIn("data-ckrgo", r[6])                  # no session: command + copy, no send button
        self.assertIn('data-ckcp="sh"', r[6])
        self.assertIn('data-ckcp="win"', r[6])
        self.assertIn("터미널에서 실행하세요", r[6])
        self.assertIn(">보안 점검</button>", r[7])
        self.assertEqual(r[8], "")                            # map header: ok payload only
        e = run("console.log(JSON.stringify([archChkEntry({ok: false, empty: true}), archChkEntry(null)]));")
        self.assertIn(">보안 점검</button>", e[0])            # no-map states still get the entry
        self.assertEqual(e[1], "")
        m = run("const S = {sel: {}, req: null, run: {sid: 'a1', busy: false}, runSent: null, runMsg: 'Could not send: boom', msg: ''};"
                "console.log(JSON.stringify(archChkRunHtml('/x/shop', {sidereus: '/sid'}, S, [{sid: 'a1', g: 0, login: true}])));")
        self.assertRegex(m, r'data-ckrx>.*</div></div><div class="archmsg archerr" role=alert>Could not send: boom</div>$')
        self.assertIn("data-ckrun aria-expanded=true disabled", r[9])   # busy: run toggle and confirm disabled
        self.assertIn("data-ckrgo disabled", r[9])
        self.assertEqual([r[10], r[11]], [9, 0])

    def test_run_security_check_codex(self):   # a logged-in Codex session of the repo is a run recipient, never a fix-request one
        sess = [{"sid": "x1", "plat": "cx", "cwd": "/x/shop", "mbox": "admin-codex", "mboxSrc": "identity", "state": "idle", "ageSec": 1}]
        r = run("const fc = archChkFixCands(" + json.dumps(sess) + ", '/x/shop'), rc = archChkRunCands(archChkFixCands(" + json.dumps(sess) + ", '/x/shop', true));"
                "const S = {sel: {}, req: null, run: {sid: 'x1', busy: false}, runSent: null};"
                "console.log(JSON.stringify([fc.length, rc.map(x => [x.sid, x.g, x.cx]), archChkRunBody('/x/shop', '/sid/', true), archChkRunBody('/x/shop', '/sid/'),"
                "archChkRunBody('/x/shop', '/sid/', false), archChkRunHtml('/x/shop', {sidereus: '/sid'}, S, rc)]));")
        self.assertEqual(r[0], 0)
        self.assertEqual(r[1], [["x1", 0, True]])
        self.assertTrue(r[2].startswith(r[3] + "\n"))
        self.assertIn('echo "[pl:security-checks/<stage title>]"', r[2])
        self.assertIn("report once after the last stage", r[2])
        for w in ("Agent tool", "SendMessage", "Workflow"):
            self.assertNotIn(w, r[2])
        self.assertEqual(r[3], r[4])
        self.assertNotIn("[pl:", r[3])
        self.assertIn("data-cxhint", r[5])
        self.assertIn("[pl:security-checks/", r[5])

    def test_last_report_button(self):
        rep = {"name": 'security-report-"<x>".md', "at": 1700000000}
        r = run("console.log(JSON.stringify([archChkLogHtml({}, null), archChkLogHtml({}, " + json.dumps(rep) + "),"
                "archChkWinHtml('/r', {checks: {security: Object.assign({}, " + json.dumps(CHECKS) + ", {report: " + json.dumps(rep) + "})}}, {sel: {}}, [])]));")
        self.assertNotIn("data-ckrep", r[0])                             # no report: no button
        self.assertIn("마지막 보고서 ", r[1])
        self.assertIn('data-ckrep="security-report-&quot;&lt;x&gt;&quot;.md"', r[1])
        self.assertNotIn("<x>", r[1])
        self.assertIn("data-ckrep=", r[2])                                # window passes security.report through


if __name__ == "__main__":
    unittest.main()
