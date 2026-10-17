"""English-source i18n (web/js/05-i18n.js T/U, I18N.ko dictionaries, 06-i18n-g.js srvEn, scripts/i18n_flip.mjs).

★Equivalence: tests/fixtures/i18n_legacy_en.json is the old Korean-key -> English dictionary (1,597 keys; removed views' keys
dropped). Every old key must still
be reachable from an English source key with the same text in Korean and English (the bridge that translated Korean keys at
run time is gone, so T() of Korean text now returns it unchanged). Same for U() units; server Korean goes through srvEn().
Repo sources only, no live data.
"""
import json
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "i18n_legacy_en.json")

PRE = """
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
const lib = await import(pathToFileURL(%(lib)s).href);
const sb = lib.loadI18n(), map = lib.flipMap(sb);
const OLD = JSON.parse(readFileSync(%(fix)s, 'utf8'));
const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
const UNIT_EN_OLD = {'초':'s', '분':'m', '시간':'h', '일':'d', '개월':'mo', '주':'w',
                     '건':'', '개':'', '명':'', '회':'×', '줄':' lines', '종':' types', '단계':''};
const oldU = (L, n, ko, en) => { if (L !== 'en') return n + ko; const e = en != null ? en : UNIT_EN_OLD[ko]; return n + (e == null ? ko : e); };
const T = (L, s, c) => { sb.LANG = L; return c == null ? sb.T(s) : sb.T(s, c); };
const out = (x) => process.stdout.write(JSON.stringify(x));
"""


def _node(body):
    src = PRE % {"lib": json.dumps(os.path.join(ROOT, "scripts", "i18n_flip.mjs")), "fix": json.dumps(FIX)} + body
    r = subprocess.run(["node", "--input-type=module", "-e", src], capture_output=True, text=True, timeout=60, cwd=ROOT, encoding="utf-8")
    if r.returncode:
        raise AssertionError(r.stderr[-2000:])
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class I18nBridge(unittest.TestCase):
    def test_no_bridge_left(self):
        # No Korean-key map at run time: T() of Korean text is returned unchanged in both languages.
        r = _node("const ks = Object.keys(OLD).slice(0, 200);"
                  "out({en: 'en' in sb.I18N, legacy: '_legacy' in sb.I18N, bridge: typeof sb.i18nBridge, trx: typeof sb.TRX,"
                  "     bad: ks.filter(k => T('en', k) !== k || T('ko', k) !== k)});")
        self.assertEqual(r, {"en": False, "legacy": False, "bridge": "undefined", "trx": "undefined", "bad": []})

    def test_context_keys_well_formed(self):
        # 'text|ctx' keys only (ctx = lowercase word); a key never carries two contexts. No fixed count: slices add contexts.
        r = _node("const ks = Object.keys(sb.I18N.ko).filter(k => /\\|[a-z]+$/.test(k));"
                  "out({n: ks.length, bad: ks.filter(k => /\\|[a-z]+\\|[a-z]+$/.test(k) || !/^[\\s\\S]+\\|[a-z]+$/.test(k))});")
        self.assertEqual(r["bad"], [])
        self.assertGreaterEqual(r["n"], 33)

    def test_every_old_key_still_reachable(self):
        # For each old Korean key some English source key gives the same text in Korean and English (several keys may share
        # one Korean word; flipMap picks the first, so it must exist for every old key too).
        r = _node("const inv = {}, bad = [];"
                  "for (const K of Object.getOwnPropertyNames(sb.I18N.ko)) { const c = /^([\\s\\S]*)\\|([a-z]+)$/.exec(K);"
                  "  (inv[sb.I18N.ko[K]] = inv[sb.I18N.ko[K]] || []).push(c ? [c[1], c[2]] : [K, null]); }"
                  "for (const k of Object.keys(OLD)) {"
                  "  if (!map[k]) { bad.push([k, 'no flip']); continue; }"
                  "  if (!(inv[k] || []).some(([e, c]) => T('ko', e, c) === k && T('en', e, c) === OLD[k])) bad.push([k, OLD[k], inv[k]]);"
                  "}"
                  "out({bad: bad.slice(0, 20), n: Object.keys(OLD).length, ctx: Object.values(map).filter(f => f.ctx).length});")
        self.assertEqual(r["bad"], [])
        self.assertEqual(r["n"], 1545)   # -2: the old bell tooltip/aria texts are gone (now «Alerts — done · failed»)
        self.assertGreaterEqual(r["ctx"], 33)   # one English text with two Korean readings -> a context key (slices add more)

    def test_server_text_corpus(self):
        # Korean the server still sends (sidereus/failures_scan.py, failures.py, burn_scan.py, ext.py): srvEn() gives the English,
        # Korean mode and unknown or non-Korean text pass through unchanged.
        want = {"기타 3개": "Other (3)", "훅이 막음 — rm -rf": "Blocked by hook — rm -rf",
                "권한 거부 — 사용자가 거절": "Permission denied — rejected by user", "모델 일시 불가 — 529": "Model temporarily unavailable — 529",
                "에이전트 정지 — 600초 무진전(stream watchdog)": "Subagent stalled — no progress for 600s (stream watchdog)",
                "서브에이전트 정지 — 30초 무진전(stream watchdog)": "Subagent stalled — no progress for 30s (stream watchdog)",
                "절전 중 응답 끊김": "Response cut off by sleep", "연결 끊김(mid-response)": "Connection closed (mid-response)",
                "한도 도달 — 5h": "Limit reached — 5h", "백그라운드 명령 exit 2": "Background command exit 2",
                "감시 스크립트 exit 1": "Watch script exit 1", "시간 초과": "Timed out", "서브에이전트 killed": "Subagent killed",
                "감시 failed": "Watch failed", "백그라운드 failed": "Background failed", "중단 — 내가 멈춤": "Stopped — by me",
                "도구 오류": "Tool error", "도구 오류 — Bash <경로>/a.py": "Tool error — Bash <path>/a.py", "API 오류": "API error",
                "백그라운드 작업": "Background task", "알림 대기": "Waiting on notification", "(이름 없음)": "(unnamed)", "기타": "Other",
                "훅이 막음": "Blocked by hook", "임시(스크래치패드)": "Temporary (scratchpad)", "홈": "Home",
                "처음 보는 서버 문장": "처음 보는 서버 문장", "plain english": "plain english", "": "",
                "constructor": "constructor", "toString": "toString", "__proto__": "__proto__", "hasOwnProperty": "hasOwnProperty"}
        r = _node("const W = %s, bad = [];"
                  "for (const s of Object.keys(W)) { sb.LANG = 'en'; const e = sb.srvEn(s); sb.LANG = 'ko'; const k = sb.srvEn(s);"
                  "  if (e !== W[s] || k !== s) bad.push([s, e, k]); }"
                  "for (const L of ['ko', 'en']) { sb.LANG = L;"
                  "  const j = {msg: 'Show {n} more', vars: {n: 3}}, want = L === 'ko' ? '3개 더 보기' : 'Show 3 more';"
                  "  if (sb.TV(j) !== want) bad.push([L, 'TV', sb.TV(j), want]); }"
                  "out(bad);" % json.dumps(want, ensure_ascii=False))
        self.assertEqual(r, [])

    def test_units_same_text(self):
        # Every unit form web/js used before the flip: the flipped English call gives the old text in both languages.
        r = _node("const forms = [['초'], ['분'], ['시간'], ['일'], ['개월'], ['주'], ['건'], ['개'], ['명'], ['회'], ['줄'], ['종'], ['단계'],"
                  "  ['분째', 'm'], ['개', ' files'], ['개', ''], ['개까지', ' max'], ['분 남음', 'm left'], ['개', ' rooms']], bad = [];"
                  "for (const [ko, en] of forms) { const f = lib.unitFlip(sb, ko, en);"
                  "  if (!f) { bad.push([ko, en, 'no flip']); continue; }"
                  "  for (const L of ['ko', 'en']) for (const n of [0, 1, 7]) { sb.LANG = L;"
                  "    const want = oldU(L, n, ko, en), b = f.ctx ? sb.U(n, f.en, f.ctx) : sb.U(n, f.en);"
                  "    if (b !== want) bad.push([L, n, ko, en, b, want]); } }"
                  "out(bad);")
        self.assertEqual(r, [])

    def test_ko_context_falls_back(self):
        # A context with no entry reads the plain key; a non-string second argument (arr.map(T)) is ignored.
        r = _node("out([T('ko', 'Clear', 'tidy'), T('ko', 'Clear', 'nope'), T('ko', 'Clear', 1), T('en', 'Clear', 'tidy'),"
                  "     T('ko', 'Not a dictionary text'), T('en', 'Not a dictionary text')]);")
        self.assertEqual(r, ["정리", "해제", "해제", "Clear", "Not a dictionary text", "Not a dictionary text"])


@unittest.skipUnless(shutil.which("node"), "node not installed")
class I18nFlip(unittest.TestCase):
    def test_flip_rewrites_only_calls(self):
        src = ("const a = T('완료'), b = T(\"정리\"), c = T(`읽는 중…`), d = U(n, '분'), e = U(n,'분째','m'), f = U(k, '건');\n"
               "if (x === '완료' || '완료' !== y) z = {'완료': 1}; switch (s) { case '완료': break; }\n"
               "const g = '<b>' + T('없는 문장') + '</b>', h = `${T('완료')} ${n}개`, r = /완료/.test(s), k = KE('완료', 'Done');\n"
               "const s2 = \"T('완료')\"; // T('완료') in a comment\n"
               "Object.assign(I18N.en, { '완료': 'Done' });\n")
        r = _node("const r = lib.flipSource(%s, map, sb); out({out: r.out, flips: r.flips, why: r.manual.map(m => m.why + ': ' + m.text)});"
                  % json.dumps(src, ensure_ascii=False))
        o = r["out"]
        self.assertIn("const a = T('Done'), b = T('Clear', 'tidy'), c = T('Loading…', 'read'), d = U(n, 'm'), e = U(n,'m', 'ongoing'), f = U(k, '#msgs');", o)
        self.assertIn("if (x === '완료' || '완료' !== y) z = {'완료': 1}; switch (s) { case '완료': break; }", o)
        self.assertIn("T('없는 문장')", o)
        self.assertIn("${T('Done')} ${n}개", o)
        self.assertIn("r = /완료/.test(s)", o)
        self.assertIn("const s2 = \"T('완료')\"; // T('완료') in a comment", o)
        self.assertIn("Object.assign(I18N.en, { '완료': 'Done' });", o)
        self.assertEqual(r["flips"], 7)
        why = r["why"]
        self.assertIn("T literal without a dictionary entry: 없는 문장", why)
        self.assertIn("Korean in an interpolated template:  개", why)
        self.assertEqual(sum(w.startswith("Korean literal in a comparison or object key") for w in why), 4)

    def test_all_literals_opt_in(self):
        src = "const L = ['완료', '정리'], q = x === '완료';\n"
        r = _node("out(lib.flipSource(%s, map, sb, {allLiterals: true}).out);" % json.dumps(src, ensure_ascii=False))
        self.assertEqual(r, "const L = ['Done', '정리'], q = x === '완료';\n")   # context keys and comparisons stay manual

    def test_flipped_web_js_still_parses(self):
        # Dry run over the real files (nothing written): every rewritten file must still compile.
        r = _node("const vm = await import('node:vm'), bad = []; let flips = 0;"
                  "for (const f of readdirSync(lib.JD).filter(f => f.endsWith('.js') && !lib.isDict(f))) {"
                  "  const res = lib.flipSource(readFileSync(join(lib.JD, f), 'utf8'), map, sb); flips += res.flips;"
                  "  try { new vm.Script(res.out); } catch (e) { bad.push(f + ': ' + e.message); }"
                  "  for (const m of res.manual) if (/without a dictionary entry|second argument|UNIT_KO|non-literal/.test(m.why)"
                  "      && !own(sb.I18N.ko, m.text)) bad.push(f + ':' + m.line + ' ' + m.why); }"
                  "out({bad, flips});")
        self.assertEqual(r["bad"], [])   # flips is ~0 once the web files are converted, so it is not asserted


if __name__ == "__main__":
    unittest.main()
