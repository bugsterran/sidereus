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

FNS = ["mboxIn", "strHdBadge", "hhmm", "archBase", "archHome", "archNoHome", "archChkN", "archChkTools", "archChkLv", "archChkLvLbl", "archChkSevF", "archChkSum", "archChkStat", "archChkSec",
       "archChkTop", "archChkTopBtn", "archChkHelp", "archChkRule", "archChkKey", "archChkSel", "archChkFixCands", "archChkCandLabel", "archChkPick", "archChkFixBody", "archDmBody", "archChkReqKey", "archChkGoLabel", "archChkSentHtml", "archChkLogHtml", "archChkEntry", "archChkHdBtn", "archChkRunCands", "archChkRunBody", "archChkRunCmds", "archChkScanAt", "archChkRunHtml", "archChkWinHtml"]
FNS += ["archChkLast", "archChkLastHtml"]   # last-check line (window header, badge tooltip)
FNS.append("plCxHint")   # 48b: Codex recipient hint (archChkRunHtml calls it)
FNS += ["archChkRk", "archChkHidSet", "archChkHidPref", "archChkHidden", "archChkSetHidden", "archChkView", "archChkWinEv"]   # view filters + hidden rules
FNS += ["ago", "archRunOf", "archRunEl", "archRunHtml", "archReqMs", "archReqRows", "archReqLive", "archReqLast", "archReqStopOk", "archReqWho",
        "archReqRowHtml", "archChkProgHtml", "archChkFixRecHtml"]   # run progress line (84j archRun* shared with arch-map, 84l2 request rows)
FNS += ["archChkSplitGet", "archChkSplitGrip", "archChkSplitClamp", "archChkSplitEls", "archChkSplitAria", "archChkSplitSet", "archChkSplitMove", "archChkSplitReset", "archChkSplitKey"]   # issues | history grip
_SRC_P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "js", "84l-structure-arch-checks.js")
with open(_SRC_P, encoding="utf-8") as fh:
    _SRC = fh.read()
with open(os.path.join(os.path.dirname(_SRC_P), "84l2-structure-arch-req.js"), encoding="utf-8") as fh:
    _REQ_SRC = fh.read()
FIXSEND = re.search(r"^async function archChkFixSend\(.*?^}", _SRC, re.S | re.M).group(0)
PRE = "\n".join([
    "let LANG = 'ko';", i18n_prelude("LANG", ("T", "KE", "U", "TV", "AGO")), "function sid8(s){ return String(s).slice(0, 8); }", "function agoAt(s){ return '@' + s; }",
    "const esc = s => String(s).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));",
    "const ARCH_PL = 'arch-map', ARCH_SEC_PL = 'security-checks'; const ARCH = { cache: {}, msg: '' };",
    "let SESS = [], POSTS = []; function lsSetJson(){}",
    "let ARCHRUN = {}, SECRUN = {}, PLREQ = {};",
    re.search(r"^const ARCH_REQ_KEEP_MS = .*$", _REQ_SRC, re.M).group(0), re.search(r"^const ARCH_REQ_LBL = .*$", _REQ_SRC, re.M).group(0),
    re.search(r"^const CK_SPLIT_MIN = .*$", _SRC, re.M).group(0),
    "async function postJSON(u, b){ POSTS.push([u, b]); return { ok: true }; }",
])

# /api/arch `checks.security` (sidereus/sec_checks); CK = the whole `checks` object.
CHECKS = {"commit": "abcdef123", "at": 1700000000,
          "tools": [{"id": "gitleaks", "rules": "project", "status": "ok", "ms": 120, "n": {"high": 2, "medium": 3}},
                    {"id": "semgrep", "rules": "default", "status": "fail", "why": "exit 2", "ms": 900, "n": {"high": 1, "medium": 0}},
                    {"id": "osv", "rules": "default", "status": "missing", "why": "install: brew install osv-scanner", "ms": 0, "n": {}},
                    {"id": "npm-audit", "rules": "project", "status": "skipped", "why": "time budget used", "ms": 0, "n": {}}, {"id": "go", "rules": "project", "status": "skipped", "ms": 0, "n": {}}],
          "top": [{"tool": "ruff", "file": "b.py", "line": "x", "rule": "W2", "sev": "medium", "mod": "b"},
                  {"tool": "ru<f>f", "file": "a/<x>.py", "line": 7, "rule": "E<1>\"", "sev": "high", "mod": "<m>"}]}
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
        self.assertEqual(r[0], "실행됨 · 발견 5")             # «ok» means the scanner ran, not «no findings»

    def test_badge_is_security_button_only(self):
        q = {"commit": "abc", "tools": [{"id": "ruff", "status": "ok", "n": {"error": 1}}], "top": [{"tool": "ruff", "file": "a.py", "line": 1, "sev": "error"}]}
        r = run("console.log(JSON.stringify([archChkTopBtn({checks: " + json.dumps(CK) + "}), archChkTopBtn({checks: " + json.dumps(q) + "}),"
                "archChkTopBtn({checks: null}), archChkTopBtn({}), archChkTopBtn({checks: {security: {tools: [], top: []}}})]));")
        self.assertTrue(r[0].startswith("<button") and r[0].endswith("</button>"))
        self.assertEqual(r[0].count("<button"), 1)           # nothing besides the issues button
        self.assertIn("data-arck", r[0])
        self.assertIn(">보안 문제 2</button>", r[0])
        self.assertNotIn("<em", r[0])                         # no quality badges / chips
        self.assertNotIn("archckiw", r[0])                    # errors > 0 -> red
        self.assertEqual(r[1:4], ["", "", ""])                # a quality-only payload shows nothing
        self.assertIn(">보안 문제 0</button>", r[4])               # shown at 0 so missing scanners stay visible
        w = run("const c = " + json.dumps(CHECKS) + "; c.tools.forEach(t => { t.n = {warning: 1}; }); console.log(JSON.stringify(archChkTopBtn({checks: {security: c}})));")
        self.assertIn("strbg-archckiw", w)                   # warnings only -> amber

    def test_window_has_no_tablist(self):
        r = run("const d = {checks: " + json.dumps(CK) + "}; console.log(JSON.stringify(archChkWinHtml('/r', d, {sel: {}, req: null}, [])));")
        self.assertNotIn("tablist", r)
        self.assertNotIn("data-ckcat", r)
        self.assertIn("<div class=archckst>gitleaks · 실행됨 · 발견 5", r)   # scanner states line
        self.assertIn("점검한 적 없음", r)                        # security history section

    def test_header_buttons_wrap_together(self):
        # ⚠ an inline reason span in the header pushed «Run security check» alone onto line 2
        r = run("const d = {checks: " + json.dumps(CK) + "}; console.log(JSON.stringify(archChkWinHtml('/r', d, {sel: {}, req: null}, [])));")
        hd = r[r.index("<div class=ckwh>"):r.index("<div class=ckwf>")]
        self.assertNotIn("archwhy", hd)
        self.assertIn("data-ckfix disabled title=", hd)   # the reason stays on the disabled button
        m = re.search(r"<span class=ckwbtn>(.*?)</span></div>$", hd)
        self.assertIsNotNone(m)
        self.assertIn("data-ckfix", m.group(1))
        self.assertIn("data-ckrun", m.group(1))

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
        self.assertLess(h.index('class="high"'), h.index('class="medium"'))   # higher level first
        self.assertIn(">높음</b>", h)
        self.assertIn(">중간</b>", h)
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
                               "- high · E<1>\" · a/<x>.py:7 — Bad thing\n- medium · W2 · b.py:1\n"
                               "Fix the cause, keep behaviour, run the project's tests.\n"
                               "Once the fix is committed, re-run the security check on /r so the Security badge reflects it — run:\n"
                               "파이프라인 security-checks 실행 — 요청: «/r 보안 점검»\nTarget repository: /r\n"
                               "Pipeline: .claude/pipelines/security-checks.json (scanners → threat-model review); run it from the Sidereus repository with --repo /r\n"
                               "Gate: python3 scripts/arch_checks.py --verify --last --category security (Windows: py scripts/arch_checks.py --verify --last --category security)\n"
                               "Tag each stage dispatch description with [pl:security-checks/<stage title>] (not [pl:-]); a stage you run yourself: Bash description with the same tag.")
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

    def test_fix_body_requests_security_rerun(self):
        r = run("const it = [{tool: 'ruff', file: 'a.py', line: 3, rule: 'F1', sev: 'error'}], d = {sidereus: '/sid', checks: {security: {commit: '', top: [{tool: 'ruff', file: 'a.py', line: 3, rule: 'F1', sev: 'error', mod: 'a'}]}}};"
                "const S = {sel: {}, req: {sid: 's1', busy: false}}; S.sel[archChkKey(d.checks.security.top[0])] = 1;"
                "console.log(JSON.stringify([archChkFixBody('/x/shop-api', {commit: ''}, it, '/sid'), archChkWinHtml('/x/shop-api', d, S, [{sid: 's1', g: 0, login: 1}])]));")
        for s in ("Once the fix is committed, re-run the security check on /x/shop-api so the Security badge reflects it", "/sid/.claude/pipelines/security-checks.json",
                  "Gate: python3 /sid/scripts/arch_checks.py --verify --last --category security"):
            self.assertIn(s, r[0])
        self.assertNotIn("arch-map", r[0])                    # a remap does not move the Security badge
        self.assertNotIn("arch_verify", r[0])
        self.assertNotIn("(no subagents)", r[0])              # fix recipients are Claude sessions
        self.assertIn("security-checks.json", r[1])           # full text in the preview (rule 7)
        self.assertNotIn("arch-map.json", r[1])

    def test_badge_marks_stale_scan(self):
        sec = {"commit": "abc1234ffff", "stale": True, "tools": [{"id": "ruff", "status": "ok", "n": {"high": 1}}], "top": [{"tool": "ruff", "file": "a.py", "line": 1, "sev": "high"}]}
        fresh = dict(sec, stale=False)
        r = run("console.log(JSON.stringify([archChkTopBtn({head: 'def5678eeee', checks: {security: " + json.dumps(sec) + "}}, '/r'),"
                "archChkTopBtn({head: 'abc1234ffff', checks: {security: " + json.dumps(fresh) + "}}, '/r')]));")
        self.assertIn("strbg-cut", r[0])
        self.assertIn(">⚠ 보안 문제 1</button>", r[0])
        self.assertIn("점검 커밋 abc1234 · 현재 HEAD def5678", r[0])
        self.assertIn("보안 점검을 다시 실행하세요", r[0])
        self.assertNotIn("strbg-cut", r[1])
        self.assertNotIn("⚠", r[1])
        self.assertIn(">보안 문제 1</button>", r[1])

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
        tag = "\nTag each stage dispatch description with [pl:security-checks/<stage title>] (not [pl:-])"
        self.assertTrue(r[3].endswith("; a stage you run yourself: Bash description with the same tag."))
        self.assertIn(tag, r[3])                    # Claude recipient: stage-tag line (cross-repo sessions tagged [pl:-])
        self.assertTrue(r[2].startswith(r[3][:r[3].index(tag)] + "\n"))
        self.assertNotIn("Tag each stage dispatch", r[2])
        self.assertIn('echo "[pl:security-checks/<stage title>]"', r[2])
        self.assertIn("report once after the last stage", r[2])
        for w in ("Agent tool", "SendMessage", "Workflow"):
            self.assertNotIn(w, r[2])
        self.assertEqual(r[3], r[4])
        self.assertNotIn('echo "[pl:', r[3])
        self.assertIn("data-cxhint", r[5])
        self.assertIn("[pl:security-checks/", r[5])

    def test_run_cands_include_home_sessions(self):   # the run body names <home>/.claude/pipelines, so Sidereus-repo sessions can run it
        li = {"mboxSrc": "identity", "state": "idle"}
        sess = [dict(li, sid="h1", cwd="/sid", mbox="sid-a", ageSec=1), dict(li, sid="o1", cwd="/other", mbox="oth", ageSec=1),
                dict(li, sid="s1", cwd="/x/shop", mbox="shop", ageSec=9), {"sid": "h2", "cwd": "/sid", "state": "idle", "ageSec": 0}]
        r = run("const fc = archChkFixCands(" + json.dumps(sess) + ", '/x/shop', true);"
                "console.log(JSON.stringify([archChkRunCands(fc, '/sid').map(x => x.sid), archChkRunCands(fc, '').map(x => x.sid), archChkFixCands(" + json.dumps(sess) + ", '/x/shop').length]));")
        self.assertEqual(r[0], ["s1", "h1"])        # target repo first, then home; /other and the logged-out h2 excluded
        self.assertEqual(r[1], ["s1"])              # home unknown: no home tier
        self.assertEqual(r[2], 4)                   # fix-request picker unchanged (every live session)

    def test_last_report_button(self):
        rep = {"name": 'security-report-"<x>".md', "at": 1700000000}
        r = run("console.log(JSON.stringify([archChkLogHtml({}, null), archChkLogHtml({}, " + json.dumps(rep) + "),"
                "archChkWinHtml('/r', {checks: {security: Object.assign({}, " + json.dumps(CHECKS) + ", {report: " + json.dumps(rep) + "})}}, {sel: {}}, [])]));")
        self.assertNotIn("data-ckrep", r[0])                             # no report: no button
        self.assertIn("마지막 보고서 ", r[1])
        self.assertIn('data-ckrep="security-report-&quot;&lt;x&gt;&quot;.md"', r[1])
        self.assertNotIn("<x>", r[1])
        self.assertIn("data-ckrep=", r[2])                                # window passes security.report through


# Filter fixture: one item per scanner + two bandit:B110 items (R1..R5); v2 levels.
FT = {"commit": "c0ffee00", "tools": [{"id": t, "status": "ok", "n": {"high": 1, "medium": 1}} for t in ("gitleaks", "semgrep", "bandit", "osv-scanner", "npm-audit")],
      "top": [{"tool": "gitleaks", "file": "k.env", "line": 1, "rule": "aws-key", "sev": "critical"},
              {"tool": "semgrep", "file": "s.py", "line": 2, "rule": "py.eval", "sev": "medium"},
              {"tool": "bandit", "file": "b1.py", "line": 3, "rule": "B110", "sev": "low"},
              {"tool": "bandit", "file": "b2.py", "line": 4, "rule": "B110", "sev": "high"},
              {"tool": "bandit", "file": "b3.py", "line": 5, "rule": "B602", "sev": "medium"},
              {"tool": "osv-scanner", "file": "package-lock.json", "line": 1, "rule": "GHSA-x", "sev": "high"},
              {"tool": "npm-audit", "file": "package.json", "line": 1, "rule": "lodash", "sev": "low"}]}
# In-memory pref store; ⚠no live localStorage.
MEMJS = ("const MEM = {}, SETS = []; globalThis.lsJson = (k, d) => Object.prototype.hasOwnProperty.call(MEM, k) ? JSON.parse(MEM[k]) : d;"
         "lsSetJson = (k, v) => { SETS.push(k); MEM[k] = JSON.stringify(v); return true; }; const d = {checks: {security: " + json.dumps(FT) + "}};"
         "const rows = h => (h.split('<ol class=archckl>')[1] || '').split('</ol>')[0].split('<li ').length - 1;")
# Window event driver: ARCH_CW + stubbed paints (archChkWinEv is the real one).
EVJS = ("globalThis.ARCH_CW = null; let PAINTS = 0, TABS = 0; globalThis.archChkWinPaint = () => { PAINTS++; }; globalThis.archChkTabRepaint = () => { TABS++; };"
        "const W = {close(){}}; const ev = (type, attrs, extra) => ({type, target: Object.assign({closest(s){ const m = s.match(/^\\[data-([a-z]+)\\]$/); return m && Object.prototype.hasOwnProperty.call(attrs, m[1]) ? this : null; },"
        " matches(s){ return !!this.closest(s); }, dataset: attrs}, extra || {})});")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class StructArchCheckFilters(unittest.TestCase):
    def test_r2_severity_filters_and_counts(self):
        r = run(MEMJS + "const a = archChkWinHtml('/r', d, {sel: {}, sev: 'all', tool: ''}, []), e = archChkWinHtml('/r', d, {sel: {}, sev: 'high', tool: ''}, []);"
                "const c = archChkWinHtml('/r', d, {sel: {}, sev: 'critical', tool: ''}, []);"
                "console.log(JSON.stringify([rows(a), rows(e), a, e, archChkView(d, {sev: 'high'}, []).map(x => x.sev), archChkView(d, {sev: 'critical'}, []).map(x => x.sev),"
                "archChkView(d, {sev: 'error'}, []).map(x => x.sev), c, archChkTop(d).map(x => x.file)]));", lang="en")
        self.assertEqual([r[0], r[1]], [7, 3])
        self.assertIn("Top issues 7", r[2])
        self.assertIn("critical 1 · high 2 · medium 2 · low 2</span>", r[2])   # from the listed items; no «shown» without a filter
        self.assertIn("Top issues 3", r[3])
        self.assertIn("critical 1 · high 2 · medium 0 · low 0 · shown 3 of 7", r[3])
        self.assertNotIn('<li class="medium"', r[3])
        self.assertNotIn('<li class="low"', r[3])
        self.assertIn('<option value=high selected>High and above</option>', r[3])
        self.assertEqual(r[4], ["critical", "high", "high"])            # high = critical + high
        self.assertEqual(r[5], ["critical"])                            # critical only
        self.assertEqual(r[6], r[4])                                    # old "error" filter value -> high and above
        self.assertIn('<option value=critical selected>Critical only</option>', r[7])
        self.assertIn("critical 1 · high 0 · medium 0 · low 0 · shown 1 of 7", r[7])
        self.assertEqual(r[8], ["k.env", "b2.py", "package-lock.json", "s.py", "b3.py", "b1.py", "package.json"])   # by level, list order kept within
        self.assertIn('<li class="critical"', r[2])
        self.assertIn('<li class="low"', r[2])

    def test_r3_levels_legacy_and_labels(self):
        r = run("console.log(JSON.stringify([['critical', 'high', 'medium', 'low', 'error', 'warning', 'bogus', null].map(archChkLv),"
                "['all', 'high', 'critical', 'error', 'x', undefined].map(archChkSevF), ['critical', 'high', 'medium', 'low'].map(archChkLvLbl),"
                "archChkSum({tools: [{id: 'a', n: {critical: 1, high: 2, medium: 3, low: 4}}, {id: 'b', n: {error: 5, warning: 6}}]}),"
                "archChkLogHtml({open: [{file: 'a.py', line: 1, sev: 'error', key: 'ruff:E1'}, {file: 'b.py', line: 2, sev: 'low', key: 'ruff:L1'}]})]));")
        self.assertEqual(r[0], ["critical", "high", "medium", "low", "high", "medium", "medium", "medium"])
        self.assertEqual(r[1], ["all", "high", "critical", "high", "all", "all"])
        self.assertEqual(r[2], ["치명", "높음", "중간", "낮음"])
        self.assertEqual(r[3], {"c": 1, "h": 7, "m": 9, "l": 4})
        self.assertIn('<li class="high"><div class=ckwr>', r[4])       # legacy log row "error" -> high
        self.assertIn('<b class=archcks>높음</b>', r[4])
        self.assertIn('<li class="low">', r[4])

    def test_r3_badge_levels(self):
        def q(sev, n):
            return {"checks": {"security": {"tools": [{"id": "bandit", "status": "ok", "n": n}], "top": [{"tool": "bandit", "file": "a.py", "line": 1, "rule": "B1", "sev": sev}]}}}
        r = run(MEMJS + "const qs = " + json.dumps([q("high", {"high": 1}), q("medium", {"medium": 1}), q("low", {"low": 1}), q("critical", {"critical": 1}), q("error", {"error": 1})]) + ";"
                "const b = qs.map(x => archChkTopBtn(x, '/r')); archChkSetHidden('/r', ['bandit:B1']);"
                "console.log(JSON.stringify(b.concat([archChkTopBtn(qs[0], '/r'), archChkTopBtn(qs[3], '/r')])));", lang="en")
        self.assertNotIn("archckiw", r[0])                     # one high -> red
        self.assertIn("strbg-archckiw", r[1])                  # medium only -> amber
        self.assertIn("strbg-archckiw", r[2])                  # low only -> amber
        self.assertNotIn("archckiw", r[3])                     # critical -> red
        self.assertNotIn("archckiw", r[4])                     # legacy error -> high -> red
        self.assertIn(">Security issues 1</button>", r[0])
        self.assertIn("strbg-archckiw", r[5])                  # that rule hidden -> amber
        self.assertIn("strbg-archckiw", r[6])
        self.assertIn(">Security issues 0</button>", r[5])

    def test_r2_tool_filter_only_that_tool(self):
        r = run(MEMJS + "const T5 = ['gitleaks', 'semgrep', 'bandit', 'osv-scanner', 'npm-audit'];"
                "console.log(JSON.stringify([T5.map(t => [...new Set(archChkView(d, {sev: 'all', tool: t}, []).map(x => x.tool))]), T5.map(t => rows(archChkWinHtml('/r', d, {sel: {}, tool: t}, []))),"
                "archChkWinHtml('/r', d, {sel: {}, tool: 'osv-scanner'}, [])]));", lang="en")
        self.assertEqual(r[0], [["gitleaks"], ["semgrep"], ["bandit"], ["osv-scanner"], ["npm-audit"]])
        self.assertEqual(r[1], [1, 1, 3, 1, 1])
        self.assertIn('<option value="osv-scanner" selected>osv-scanner</option>', r[2])
        self.assertIn('data-cktool', r[2])
        self.assertIn("shown 1 of 7", r[2])

    def test_r3_hide_rule_removes_all_items_and_shows_line(self):
        r = run(MEMJS + EVJS + "ARCH.cache['/r'] = d; ARCH_CW = {p: '/r', w: W, sel: {}, sev: 'all', tool: ''};"
                "const h0 = archChkWinHtml('/r', d, ARCH_CW, []); archChkWinEv(ev('click', {ckhide: 'bandit:B110'}), W);"
                "const h1 = archChkWinHtml('/r', d, ARCH_CW, []);"
                "console.log(JSON.stringify([h0, h1, rows(h1), archChkHidden('/r'), PAINTS, TABS]));", lang="en")
        self.assertEqual(r[0].count('data-ckhide="bandit:B110"'), 2)
        self.assertNotIn("bandit:B110", r[1].split("<ol class=archckl>")[1])
        self.assertIn("B602", r[1])                               # other bandit rule stays
        self.assertEqual(r[2], 5)
        self.assertIn("1 rules hidden · <button type=button class=wkrgb data-ckunhide>Show</button>", r[1])
        self.assertNotIn("data-ckunhide", r[0])
        self.assertEqual(r[3:], [["bandit:B110"], 1, 1])         # window and tab badge repainted once

    def test_r4_hidden_persist_per_repo_and_show_restores(self):
        r = run(MEMJS + EVJS + "archChkSetHidden('/r', ['bandit:B110', 'bandit:B110', 'x'.repeat(201)]);"
                "const a = [archChkHidden('/r'), archChkHidden('/other'), rows(archChkWinHtml('/r', d, {sel: {}}, [])), rows(archChkWinHtml('/other', d, {sel: {}}, []))];"
                "const stored = MEM['sidereus.ckhide'];"   # a reopen / restart reads the same stored pref
                "ARCH.cache['/r'] = d; ARCH_CW = {p: '/r', w: W, sel: {}}; archChkWinEv(ev('click', {ckunhide: ''}), W);"
                "for(let i = 0; i < 45; i++) archChkSetHidden('/q' + i, ['a:b']); const keys = Object.keys(JSON.parse(MEM['sidereus.ckhide']));"
                "archChkSetHidden('/big', Array.from({length: 250}, (_, i) => 't:' + i));"
                "console.log(JSON.stringify([a, stored, archChkHidden('/r'), rows(archChkWinHtml('/r', d, {sel: {}}, [])), keys.length, keys[0], archChkHidden('/big').length]));", lang="en")
        self.assertEqual(r[0], [["bandit:B110"], [], 5, 7])      # per repo; over-long key dropped, duplicates merged
        self.assertEqual(json.loads(r[1]), {"/r": ["bandit:B110"]})
        self.assertEqual([r[2], r[3]], [[], 7])                   # «Show» restores
        self.assertEqual([r[4], r[5]], [40, "/q5"])               # 40 repos, oldest dropped
        self.assertEqual(r[6], 200)

    def test_r5_view_only_no_posts(self):
        r = run(MEMJS + EVJS + "const F = []; globalThis.fetch = u => { F.push(u); return Promise.resolve({json: () => ({})}); };"
                "ARCH.cache['/r'] = d; ARCH_CW = {p: '/r', w: W, sel: {}, sev: 'all', tool: ''};"
                "archChkWinEv(ev('change', {cksev: ''}, {}), W); ARCH_CW.sev = 'all';"
                "const tg = ev('change', {cksev: ''}); tg.target.value = 'error'; archChkWinEv(tg, W);"
                "const tt = ev('change', {cktool: ''}); tt.target.value = 'bandit'; archChkWinEv(tt, W);"
                "archChkWinEv(ev('click', {ckhide: 'bandit:B602'}), W); archChkWinEv(ev('click', {ckunhide: ''}), W);"
                "console.log(JSON.stringify([ARCH_CW.sev, ARCH_CW.tool, [...new Set(SETS)], POSTS, F]));")
        self.assertEqual(r[:2], ["high", "bandit"])   # an old "error" value maps to high
        self.assertEqual(r[2], ["sidereus.ckhide"])               # the only write: the view pref
        self.assertEqual([r[3], r[4]], [[], []])                  # no /api/arch* or /api/dm call

    def test_badge_respects_hidden(self):
        r = run(MEMJS + "const b0 = archChkTopBtn(d, '/r'); archChkSetHidden('/r', ['gitleaks:aws-key', 'bandit:B110', 'osv-scanner:GHSA-x']);"
                "const b1 = archChkTopBtn(d, '/r'), b2 = archChkTopBtn(d, '/other');"
                "const q = {checks: {security: {tools: [{id: 'bandit', status: 'ok', n: {error: 1}}], top: [{tool: 'bandit', file: 'a.py', line: 1, rule: 'B110', sev: 'error'}]}}};"
                "console.log(JSON.stringify([b0, b1, b2, archChkTopBtn(q, '/r')]));", lang="en")
        self.assertIn(">Security issues 7</button>", r[0])
        self.assertIn(">Security issues 3</button>", r[1])
        self.assertIn("3 rules hidden", r[1])                      # tooltip
        self.assertNotIn("archckiw", r[1])                        # tool totals still hold unlisted errors
        self.assertIn(">Security issues 7</button>", r[2])               # other repo unaffected
        self.assertIn("strbg-archckiw", r[3])                     # only error hidden -> amber
        self.assertIn(">Security issues 0</button>", r[3])

    def test_select_all_visible_only(self):
        r = run(MEMJS + EVJS + "ARCH.cache['/r'] = d; ARCH_CW = {p: '/r', w: W, sel: {}, sev: 'all', tool: 'bandit'}; archChkSetHidden('/r', ['bandit:B602']);"
                "const all = ev('change', {ckall: ''}); all.target.checked = true; archChkWinEv(all, W);"
                "ARCH_CW.tool = ''; ARCH_CW.sel[archChkKey(archChkTop(d)[0])] = 1; ARCH_CW.tool = 'bandit';"
                "const sel = archChkSel(d, ARCH_CW.sel, ARCH_CW, archChkHidden('/r'));"
                "const h = archChkWinHtml('/r', d, Object.assign({}, ARCH_CW, {req: {sid: 's1', busy: false}}), [{sid: 's1', g: 0, login: 1}]);"
                "console.log(JSON.stringify([Object.keys(ARCH_CW.sel).length, sel.map(x => x.file), h]));", lang="en")
        self.assertEqual(r[0], 3)                                 # 2 visible bandit:B110 + the gitleaks one set by hand
        self.assertEqual(r[1], ["b2.py", "b1.py"])                # selection = visible items only (high before low)
        self.assertIn("Request fix (2)", r[2])
        self.assertIn("data-ckall checked", r[2])
        pre = r[2].split("<pre class=archdm>")[1].split("</pre>")[0]
        self.assertIn("b1.py:3", pre)
        self.assertNotIn("k.env", pre)                            # filtered-out selection stays out of the request body
        self.assertNotIn("B602", pre)

    def test_run_progress_line(self):
        # R1: a live server run (state `secRun`) replaces «Waiting…» with stage n/of · title · elapsed (same line as arch-map);
        # stage title is a pipeline id (esc, never T()). R2: run gone + new scan -> no progress line. R3: a request record whose
        # session is gone shows «No session», never a spinner. ARCHRUN of the same repo must not leak into the security window.
        run_ = {"stage": "위협 모델 리뷰<b>", "n": 2, "of": 2, "t0": 1000, "sid": "s1234567890"}
        r = run("const S = {runSent: {to: 'shop · a1', at: '10:00', done: 0}}, now = 1000 * 1000 + 125000;"
                "ARCHRUN = {'/x': {stage: 'Draw', n: 1, of: 4, t0: 1, sid: 'z'}};"
                "const wait = archChkProgHtml('/x', S, now);"
                "SECRUN = {'/x': " + json.dumps(run_) + "}; const live = archChkProgHtml('/x', S, now), win = archChkRunHtml('/x', {}, S, []);"
                "SECRUN = {}; const fin = archChkProgHtml('/x', {runSent: Object.assign({}, S.runSent, {done: 1})}, now);"
                "PLREQ = {'/x': [{id: 'm1', pipeline: 'security-checks', sid: 's1', to: 'a', state: 'gone', at: now / 1000 - 60}]};"
                "const gone = archChkProgHtml('/x', S, now);"
                "PLREQ = {'/x': [{id: 'm1', pipeline: 'security-checks', sid: 's1', to: 'a', state: 'run', stage: 'S', at: now / 1000 - 60}]};"
                "const rec = archChkProgHtml('/x', {}, now);"
                "console.log(JSON.stringify([wait, live, win, fin, gone, rec]));")
        self.assertIn("보안 점검 결과를 기다리는 중", r[0])              # no run yet; arch-map run of the repo ignored
        self.assertNotIn("Draw", r[0])
        self.assertIn("archrun", r[1])
        self.assertIn("점검 중 · 2/2 단계 · 위협 모델 리뷰&lt;b&gt; · ", r[1])
        self.assertIn("<span data-arel>2분</span>", r[1])
        self.assertIn("이 프로젝트의 보안 점검이 진행 중입니다 — 세션 s1234567", r[1])
        self.assertNotIn("기다리는 중", r[2])
        self.assertIn("archrun", r[2])
        self.assertEqual(r[3], "")                                           # R2
        self.assertIn("archpr end", r[4])                                    # R3: no session -> muted end row
        self.assertNotIn("archspin", r[4])
        self.assertNotIn("data-arstop", r[5])                                # live record without a run: no Stop button in the window

    def test_run_request_records_receiver(self):   # R3: the run request carries plreq so pl_reqs tracks no session / done
        self.assertIn("plreq: { kind: 'req', pipeline: ARCH_SEC_PL, repo: S.p }", _SRC)

    def test_fix_request_line_survives_reload(self):   # S.sent is lost on reload: the plReq `checks-fix` record + ACK stand in
        self.assertIn("plreq: { kind: 'req', pipeline: 'checks-fix', repo: S.p }", FIXSEND)
        rec = {"id": "f1", "pipeline": "checks-fix", "sid": "s1abcdef99", "to": "me", "project": "r", "state": "sent", "at": 1700000000}
        r = run("const d = {checks: " + json.dumps(CK) + "}; PLREQ = {'/r': [" + json.dumps(rec) + "]}; const ACK = globalThis.ACK = {};"
                "const h0 = archChkWinHtml('/r', d, {sel: {}, req: null}, []);"
                "ACK.f1 = {delivered: ['me']}; const h1 = archChkWinHtml('/r', d, {sel: {}, req: null}, []);"
                "ACK.f1 = {ack: [{who: 'me', note: '<b>done</b>'}]}; const h2 = archChkWinHtml('/r', d, {sel: {}, req: null}, []);"
                "const h3 = archChkWinHtml('/r', d, {sel: {}, req: null, sent: {to: 'x', at: '1:00', key: 'k'}}, []);"
                "PLREQ = {}; const h4 = archChkWinHtml('/r', d, {sel: {}, req: null}, []);"
                "console.log(JSON.stringify([h0, h1, h2, h3, h4]));")
        self.assertIn('data-ckfx="f1"', r[0])
        self.assertIn("요청함 → r · s1abcdef · me · 22:13", r[0])
        self.assertIn("전달됨", r[1])
        self.assertIn("me — &lt;b&gt;done&lt;/b&gt;", r[2])                   # ack note escaped
        self.assertNotIn("<b>done", r[2])
        self.assertNotIn("data-ckfx", r[3])                                    # this tab's own send line wins
        self.assertNotIn("data-ckfx", r[4])

    def test_issues_history_split_grip(self):   # vertical grip between findings and history: markup, clamp, keys, saved px, reset
        log = {"at_scan": 1, "open": [{"file": "a.py", "line": 3, "sev": "high", "key": "semgrep:r1"}]}
        sec = dict(CHECKS, log=log)
        r = run("const MEM = {}, DEL = []; globalThis.lsJson = (k, d) => k in MEM ? MEM[k] : d; lsSetJson = (k, v) => { MEM[k] = v; };"
                "globalThis.lsDel = k => { DEL.push(k); delete MEM[k]; };"
                "const box = h => ({h, getBoundingClientRect(){ return {height: this.h}; }});"
                "const T0 = box(150), L0 = box(250), G = {attrs: {}, setAttribute(k, v){ this.attrs[k] = v; }};"
                "const root = {cls: new Set(), vars: {}, classList: {add(c){ root.cls.add(c); }, remove(c){ root.cls.delete(c); }},"
                " style: {setProperty(k, v){ root.vars[k] = v; T0.h = parseFloat(v); }, removeProperty(k){ delete root.vars[k]; }},"
                " querySelector(s){ return s.indexOf(':not(.ckwlog)') >= 0 ? T0 : s.indexOf('ckwlog') >= 0 ? L0 : s === '[data-ckgr]' ? G : null; }};"
                "const key = k => { const e = {key: k, prevented: 0, preventDefault(){ this.prevented = 1; }}; const ok = archChkSplitKey(e, root); return [ok, e.prevented]; };"
                "const win = archChkWinHtml('/r', {checks: {security: " + json.dumps(sec) + "}}, {sel: {}}, []);"
                "const bare = archChkWinHtml('/r', {checks: CKS}, {sel: {}}, []);"
                "const down = key('ArrowDown'), saved = MEM['sidereus.ckwh'], v1 = root.vars['--ckth'], now = G.attrs['aria-valuenow'];"
                "T0.h = 380; L0.h = 100; key('ArrowDown'); const capped = MEM['sidereus.ckwh'];"
                "const other = key('x'); key('Home');"
                "console.log(JSON.stringify([win, bare, [archChkSplitClamp(10, 400), archChkSplitClamp(390, 400), archChkSplitClamp(200, 400)],"
                " down, saved, v1, now, capped, other, DEL, root.cls.has('cksz'), '--ckth' in root.vars]));"
                .replace("CKS", json.dumps(CK)))
        win, bare = r[0], r[1]
        self.assertIn('<div class="plwgr ckwgr" data-ckgr tabindex=0 role=separator aria-orientation=horizontal', win)
        self.assertIn('aria-label="이슈 목록과 기록 목록 크기 조절"', win)
        self.assertLess(win.index("data-ckgr"), win.index('<ol class="archckl ckwlog">'))   # grip sits between the two lists
        self.assertGreater(win.index("data-ckgr"), win.index("<ol class=archckl>"))
        self.assertNotIn("data-ckgr", bare)                                   # no history rows: no grip
        self.assertEqual(r[2], [96, 304, 200])                                # ~3 rows minimum for each list
        self.assertEqual(r[3], [True, 1])
        self.assertEqual((r[4], r[5], r[6]), (174, "174px", 41))              # 150 + 24, saved in px; aria = share of the two lists
        self.assertEqual(r[7], 384)                                           # the history list keeps its minimum
        self.assertEqual(r[8], [False, 0])                                    # other keys pass through
        self.assertEqual(r[9], ["sidereus.ckwh"])                             # Home = default: pref dropped
        self.assertEqual((r[10], r[11]), (False, False))
        with open(os.path.join(os.path.dirname(_SRC_P), "..", "css", "79-structure-arch.css"), encoding="utf-8") as fh:
            css = fh.read()
        self.assertIn("#ckroot>.ckwgr{flex:0 0 auto;margin:-8px 0;cursor:row-resize}", css)
        self.assertIn("#ckroot.cksz>.archckl{box-sizing:border-box;min-height:96px}", css)
        self.assertIn("'pointerdown','dblclick'", _SRC)                     # the window forwards the drag and reset events


if __name__ == "__main__":
    unittest.main()

    def test_last_check_line(self):   # «Last check MM-DD HH:MM · Nd ago», overdue past 30 days, «Never checked» without a scan
        at = CHECKS["at"]
        d = "{checks: " + json.dumps(CK) + "}"
        r = run("const d = " + d + ", lg = {checks: {security: {tools: [], top: [], at: 1, log: {at_scan: %d}}}};"
                "console.log(JSON.stringify([archChkLastHtml(d, %d), archChkLastHtml(d, %d), archChkLastHtml({checks: {security: {tools: []}}}, %d),"
                "archChkLast(lg, %d).txt, archChkTopBtn(d), archChkEntry({ok: false})]));" % (at + 7200, at + 3 * 86400, at + 31 * 86400, at, at + 7200 + 7200))
        self.assertEqual(r[0], '<span class="ckwlast">마지막 점검 11-14 22:13 · 3일 전</span>')
        self.assertEqual(r[1], '<span class="ckwlast ckwold">마지막 점검 11-14 22:13 · 31일 전</span>')   # past the monthly cadence
        self.assertEqual(r[2], '<span class="ckwlast">점검한 적 없음</span>')
        self.assertEqual(r[3], "마지막 점검 11-15 00:13 · 2시간 전")   # newer log scan wins
        self.assertIn('title="마지막 점검 11-14 22:13 · ', r[4])
        self.assertIn('title="점검한 적 없음"', r[5])
        e = run("console.log(JSON.stringify(archChkLastHtml({checks: " + json.dumps(CK) + "}, %d)));" % (at + 3 * 86400), lang="en")
        self.assertEqual(e, '<span class="ckwlast">Last check 11-14 22:13 · 3d ago</span>')
