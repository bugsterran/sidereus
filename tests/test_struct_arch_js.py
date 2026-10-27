"""Structure «아키텍처» view (web/js/84j-structure-arch.js): header rate/stale badges, est badge, evidence escaping,
empty state with the request button, DM body, and no /api/dm call without the confirm button."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_fn
from tests._node import node_e

FNS = ["mboxIn", "strHdBadge", "archRate", "archHeadNote", "archProvNote", "archEvHtml", "archEdgeRow", "archDmBody", "archHome", "archCands",
       "archNoHome", "archWhyOff", "archReqOf", "archReqBtn", "archReqHtml", "archPaint", "archIsTest", "archMq", "archPairs", "archReduce", "archRanks", "archSrc", "archBarHtml", "archKey", "archWaitHtml", "archDiagram", "archHov", "archHovPaint",
       "archSentRun", "archSentPh", "archEl", "archSentDone", "archSentHtml", "archSentFin", "archTick", "archBase", "archRunOf", "archRunEl", "archRunHtml", "archStatusHtml", "archLegHtml", "hhmm",
       "archStyleName", "archRoleName", "archFwParts", "archStyleParts", "archStyleNote", "archScrollPut", "archDgClick", "archFitOf",
       "archHasLayers", "archEntPair", "archBandSrc", "archBandFix", "archBandHint", "archFront", "archKindMap", "archKindLegHtml"]   # 84j2 (archPaint calls them)
FNS.append("plCxHint")   # 48b: Codex recipient hint (archReqHtml calls it)
def _read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


_SRC_P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "js", "84j-structure-arch.js")
_SRC = _read(_SRC_P)
SEND = re.search(r"^async function archSend\(.*?^}", _SRC, re.S | re.M).group(0)   # js_fn matches plain `function` only
PRE = "\n".join([
    "const LANG = 'ko';", i18n_prelude("LANG", ("T", "KE", "U", "TV")), "function sid8(s){ return String(s).slice(0, 8); }",
    "const esc = s => String(s).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));",
    "const ARCH_PL = 'arch-map', ARCH_DIR = 'TB'; const ARCH = { cache: {}, load: {}, op: '', req: null, msg: '', sel: null, tests: false, svg: {} };",
    "let ARCHRUN = {}, SESS = [], strOn = ['/r'], mainView = 'struct', strMode = 'arch', POSTS = [], PAINTS = 0;",
    "const ARCH_STAGES = ['읽기 계획', '모듈 그리기', '흐름 그리기', '검증'], TLPL_ICON = {done: '✓', run: '◉', wait: '·', fail: '✕'};",
    "function plStepper(st, ci, mod){ return '<STEP ' + mod + ' ci=' + ci + '>' + st.map(x => x.st + ':' + x.nm).join(',') + '</STEP>'; }",
    "function CLK(d){ return '15:00'; } function ago(s){ return s + 's'; } const ARCH_POLL_MS = 30000, NOTES = [], FETCHES = [];",
    "function note(m){ NOTES.push(m); } globalThis.document = { hidden: false, querySelector(){ return null; } };",
    "function archFetch(){} function mmdBlock(s){ return '<div class=mmd>' + esc(s) + '</div>'; }",
    "function paintStruct(){ PAINTS++; } function plMem(){ return {}; } const LS = {}; function lsSetJson(k, o){ LS[k] = JSON.stringify(o); }",
    "function lsJson(k, d){ return k in LS ? JSON.parse(LS[k]) : d; }",
    "function strSplitStyle(){ return ''; } function strSplitGrip(){ return ''; }",
    "async function postJSON(u, b){ POSTS.push([u, b]); return { ok: true }; }",
    "const head = (note, ex, pre) => '<H>' + note + (pre || '') + '</H>' + (ex || '');",
    re.search(r"^const ARCH_STYLE_LBL = .*?^const ARCH_ROLE_LBL = .*?};", _SRC, re.S | re.M).group(0),
    "\n".join(re.findall(r"^const ARCH_(?:LAYERS|LAYER_LBL|KIND_LBL) = .*$", _read(_SRC_P.replace("84j-structure-arch.js", "84j2-structure-arch-layers.js")), re.M)),
])


def run(body, lang="ko"):
    pre = PRE if lang == "ko" else PRE.replace("const LANG = 'ko';", "const LANG = 'en';", 1)
    js = "process.env.TZ = 'UTC';\n" + pre + "\n" + "\n".join(js_fn(n) for n in FNS) + "\n" + SEND + "\n(async () => {\n" + body + "\n})().catch(e => { console.error(e); process.exit(1); });"
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


EDGES = [{"from": "a", "to": "b", "kind": "uses", "label": "x", "ok": True, "est": False, "evidence": [{"file": "a.py", "line": 3, "symbol": "f"}]},
         {"from": "b", "to": "c", "kind": "imports", "label": "", "ok": True, "est": True, "evidence": []},
         {"from": "c", "to": "a", "kind": "uses", "label": "", "ok": False, "est": False, "evidence": []}]
MODS = [{"id": "a", "name": "A", "path": "a", "kind": "pkg"}, {"id": "b", "name": "B", "path": "b", "kind": "pkg"},
        {"id": "c", "name": "C", "path": "c", "kind": "pkg"}]


@unittest.skipUnless(shutil.which("node"), "node not installed")
class StructArch(unittest.TestCase):
    def test_rate_text(self):
        r = run("const d = " + json.dumps({"edges": EDGES, "modules": MODS}) + ";"
                "console.log(JSON.stringify([archRate(d), archHeadNote(d), archRate(Object.assign({rate: 0.5}, d)).pct]));")
        self.assertEqual(r[0], {"n": 2, "m": 3, "pct": 67})
        self.assertIn("검증 통과 2/3 (67%)", r[1])
        self.assertNotIn("오래됨", r[1])
        self.assertEqual(r[2], 50)

    def test_stale_badge(self):
        r = run("console.log(JSON.stringify(archHeadNote({edges: [], modules: [], stale: true, commit: 'abcdef123', head: '999888777'})));")
        self.assertIn("오래됨", r)
        self.assertIn("abcdef1", r)
        self.assertIn("9998887", r)

    def test_behind_badge(self):
        r = run("console.log(JSON.stringify(archHeadNote({edges: [], modules: [], stale: true, behind: 3, commit: 'abcdef123', head: '999888777'})));")
        self.assertIn('title="HEAD 가 3커밋 앞섬 · ', r)   # the count moved into the stamp's tooltip
        self.assertNotIn("오래됨", r)
        self.assertIn("abcdef1", r)                    # tooltip kept

    def test_version_stamp(self):
        # 1791469200 = 2026-10-08 14:20 UTC (run() pins TZ=UTC)
        js = ("const f = {edges: [], modules: [], stale: false, at: 1791469200, commit: 'abc1234ffff', head: 'abc1234ffff'};"
              "const s = Object.assign({}, f, {stale: true, behind: 5, head: '999888777'});"
              "console.log(JSON.stringify([archHeadNote(f), archHeadNote(s), archHeadNote(Object.assign({}, f, {at: null}))]));")
        ko, en = run(js), run(js, "en")
        self.assertIn('<em class="strbg" title="구조도 커밋', ko[0])
        self.assertIn(">10-08 14:20 생성 · abc1234</em>", ko[0])
        self.assertNotIn("strbg-cut", ko[0])
        self.assertIn('<em class="strbg strbg-cut" title="HEAD 가 5커밋 앞섬 · ', ko[1])
        self.assertIn(">⚠ 10-08 14:20 생성 · abc1234</em>", ko[1])
        self.assertIn(">Generated 10-08 14:20 · abc1234</em>", en[0])
        self.assertIn('title="HEAD is 5 commits ahead · Diagram commit abc1234 · HEAD now 9998887\nThe diagram is older than the code', en[1])
        self.assertIn(">abc1234</em>", ko[2])          # no time known: commit only
        self.assertNotIn("생성", ko[2])

    def test_legend_uses_diagram_classes(self):
        r = run("console.log(JSON.stringify(archLegHtml()));", "en")
        leg = r
        for c in ('class="mmde e-solid"', 'class="mmde e-dot"', 'class="mmdn s-stadium"', 'class="mmdfe arn arin"',
                  'class="mmdfe arn arout"', 'class="archsw archdim"', 'class="archleg mmd"'):
            self.assertIn(c, leg)
        for t in ("Direct reference", "Estimated", "External", "incoming", "calls, 2 steps down", "unrelated, dimmed"):
            self.assertIn(t, leg)
        # the diagram draws pairs with -.-> (e-dot) / --> (e-solid) and externals as ([..]) (s-stadium); hover tags .arin/.arout under svg.archdim
        self.assertIn("(p.est ? '-.->' : '-->')", _SRC)
        self.assertIn("m.kind === 'external' ? '(['", _SRC)
        self.assertIn("g.classList.toggle('arin', a); g.classList.toggle('arout', b);", _SRC)
        self.assertIn("svg.classList.toggle('archdim', !!S);", _SRC)
        css = _read(os.path.join(os.path.dirname(os.path.dirname(_SRC_P)), "css", "79-structure-arch.css"))
        self.assertIn(".archmap svg.archdim .mmdfe.arin .mmde", css)    # legend sits in .archmap, so the same rules colour it
        self.assertIn("t.closest('.archdg svg')", _SRC)                # hover handler ignores the legend svgs
        ko = run("console.log(JSON.stringify(archLegHtml()));")
        self.assertIn("직접 참조", ko)
        self.assertIn("두 단계 아래까지", ko)

    def test_fetch_error_fixed_key(self):
        self.assertIn(".catch(() => ({ ok: false, msg: 'Could not fetch — check the server' }))", _SRC)
        self.assertNotIn("e.message) || e) }))", _SRC)

    def test_first_paint_records_run_sig(self):
        # a run seen at first paint that ends before archTick's first look still refetches the map
        r = run("ARCH.cache['/r'] = {ok: true, empty: true, sidereus: '/r'}; ARCHRUN = {'/r': {stage: '검증', n: 3, of: 3, t0: 1, sid: 's1'}};"
                "const box = {innerHTML: '', querySelector(){ return null; }}; archPaint(box, head); archFetch = (p, f) => FETCHES.push([p, f]);"
                "ARCHRUN = {}; archTick(5e6); console.log(JSON.stringify([FETCHES]));")
        self.assertEqual(r[0], [["/r", True]])

    def test_est_badge_and_failed(self):
        r = run("const N = {a: 'A', b: 'B', c: 'C'}, E = " + json.dumps(EDGES) + ";"
                "console.log(JSON.stringify(E.map((e, i) => archEdgeRow(e, N, i, false))));")
        self.assertNotIn("archest", r[0])
        self.assertIn("archest", r[1])
        self.assertIn("추정", r[1])
        self.assertIn("검증 실패", r[2])

    def test_style_badge(self):
        st = {"style": "layered", "framework": "Spring <Boot>", "units": "a\"b", "ok": True,
              "evidence": [{"file": "pom.xml", "ok": True}, {"file": "x\"><img src=y>.java", "ok": True}]}
        d = {"edges": [], "modules": [], "style": st, "dev": []}
        js = ("const d = " + json.dumps(d) + ", e = Object.assign({}, d, {style: Object.assign({}, d.style, {ok: false})});"
              "console.log(JSON.stringify([archHeadNote(d), archHeadNote(e), archHeadNote(Object.assign({}, d, {style: null})),"
              " archHeadNote({edges: [], modules: []}), archHeadNote(Object.assign({}, d, {style: {style: 'zz<'}}))]));")
        ko, en = run(js), run(js, "en")
        self.assertIn('<em class="strbg strbg-asty">계층형</em>', ko[0])
        self.assertIn('<em class="strbg strbg-dat" title="Spring &lt;Boot&gt;">Spring &lt;Boot&gt;</em>', ko[0])
        self.assertIn('<em class="strbg" title="pom.xml', ko[0])
        self.assertIn(">근거 파일 2개</em>", ko[0])
        self.assertIn(">Layered</em>", en[0])
        self.assertIn(">Evidence 2 files</em>", en[0])
        long_fw = "modular python stdlib http.server + importlib"
        lf = run("const d = " + json.dumps(dict(d, style=dict(st, framework=long_fw))) + "; console.log(JSON.stringify([archHeadNote(d)]));", "en")
        self.assertIn('title="' + long_fw + '">modular python stdlib http.server</em>', lf[0])  # split, never truncated
        self.assertIn('title="' + long_fw + '">importlib</em>', lf[0])
        self.assertNotIn("…", lf[0])
        self.assertNotIn("<img", ko[0])                   # tooltip escaped
        self.assertIn("&quot;&gt;&lt;img", ko[0])
        self.assertIn("단위: a&quot;b", ko[0])
        self.assertIn('class="strbg strbg-cut strbg-asty"', ko[1])
        self.assertIn(">계층형 · 추정됨</em>", ko[1])
        self.assertTrue(ko[0].startswith('<em class="strbg strbg-asty">'))   # purple style group leads
        self.assertEqual(ko[2], ko[3])                    # style null == no key: header unchanged
        self.assertNotIn("asty", ko[2])
        self.assertIn(">기타</em>", ko[4])
        self.assertIn(">근거 파일 0개</em>", ko[4])
        self.assertNotIn("strbg-dat", ko[4])            # no framework -> no framework badge  # unknown id -> 'Other', never the raw id
        self.assertNotIn("zz", ko[4])

    def test_badge_colour_groups(self):
        # order = purple (style, framework) -> blue (verified) -> grey (evidence, modules, fresh stamp, drawn-by) -> warning
        st = {"style": "layered", "framework": "A + B", "ok": True, "evidence": [{"file": "pom.xml", "ok": True}]}
        d = {"edges": [], "modules": [], "style": st, "dev": [{"i": 0, "a": "web", "b": "data"}], "at": 1791469200,
             "commit": "abc1234ffff", "head": "abc1234ffff", "stale": False}
        js = ("const d = " + json.dumps(d) + ", s = Object.assign({}, d, {stale: true, head: '999888777'}),"
              " e = Object.assign({}, s, {style: Object.assign({}, d.style, {ok: false})});"
              "console.log(JSON.stringify([archHeadNote(d), archHeadNote(s), archHeadNote(e)]));")
        fresh, stale, est = run(js, "en")
        def order(h, keys):
            ix = [h.index(k) for k in keys]
            self.assertEqual(ix, sorted(ix), keys)
        order(fresh, ["strbg-asty", "strbg-dat", "strbg-n", ">Evidence 1 files<", ">0 modules<", "Generated", "Drawn by", "strbg-cy"])
        order(stale, ["strbg-asty", "strbg-dat", "strbg-n", ">Evidence 1 files<", ">0 modules<", "Drawn by", "strbg-cy", "strbg-cut"])
        order(est, ["strbg-dat", "strbg-n", ">Evidence 1 files<", "Drawn by", "strbg-cut strbg-asty", "strbg-cy", "⚠ Generated"])

    def test_framework_split_badges(self):
        def note(fw):
            d = {"edges": [], "modules": [], "dev": [], "style": {"style": "layered", "framework": fw, "ok": True, "evidence": []}}
            return run("console.log(JSON.stringify([archStyleNote(" + json.dumps(d) + ")]));", "en")[0]
        two = note("A + B")
        self.assertEqual(two.count("strbg-dat"), 2)
        self.assertIn('<em class="strbg strbg-dat" title="A + B">A</em><em class="strbg strbg-dat" title="A + B">B</em>', two)
        three = note("A, B + C")
        self.assertEqual(three.count("strbg-dat"), 3)
        self.assertEqual(three.count('title="A, B + C"'), 3)
        self.assertIn('<em class="strbg strbg-dat" title="Plain">Plain</em>', note("Plain"))
        self.assertEqual(note("Plain").count("strbg-dat"), 1)
        x = note("<b> + x&y")
        self.assertNotIn("<b>", x)
        self.assertIn('title="&lt;b&gt; + x&amp;y">&lt;b&gt;</em>', x)
        self.assertIn('>x&amp;y</em>', x)

    def test_dev_badges(self):
        d = {"edges": [], "modules": [], "style": {"style": "hexagonal", "framework": "", "ok": True, "evidence": []},
             "dev": [{"i": 0, "a": "adapter", "b": "web"}, {"i": 2, "a": "x<y", "b": "data"}]}
        r = run("const d = " + json.dumps(d) + ", N = {a: 'A', b: 'B', c: 'C'}, E = " + json.dumps(EDGES) + ";"
                "console.log(JSON.stringify([archHeadNote(d), archEdgeRow(E[0], N, 0, false, '', d.dev[0], archStyleName(d.style)),"
                " archEdgeRow(E[2], N, 2, false, '', d.dev[1], archStyleName(d.style)), archEdgeRow(E[1], N, 1, false)]));", "en")
        self.assertIn('class="strbg strbg-cy"', r[0])
        self.assertIn(">2 outside Hexagonal flow</em>", r[0])
        self.assertIn('<em class="archbg archdev">Adapter → Web is outside the Hexagonal flow</em>', r[1])
        self.assertIn("x&lt;y → Data", r[2])
        self.assertNotIn("archdev", r[3])
        self.assertNotIn("score", "".join(r).lower())

    def test_evidence_escaped(self):
        r = run("console.log(JSON.stringify(archEvHtml([{file: 'x\"><img src=y>.py', line: '2<b>', symbol: '<script>s'}], 0)));")
        self.assertNotIn("<img", r)
        self.assertNotIn("<script>", r)
        self.assertIn("&lt;script&gt;s", r)
        self.assertIn('data-al="2"', r)

    def test_empty_state_has_request(self):
        r = run("ARCH.cache['/r'] = {ok: true, modules: [], edges: [], sidereus: '/r'}; const box = {innerHTML: '', querySelector(){ return null; }};"
                "archPaint(box, head); console.log(JSON.stringify(box.innerHTML));")
        self.assertIn("아직 아키텍처 구조도가 없습니다", r)
        self.assertIn("data-arq", r)
        self.assertIn("열린 세션이 없습니다", r)   # no live session there -> reason shown

    def test_request_button_fixed_in_header(self):
        # Fresh, stale and empty maps: the request button sits in the header and nowhere below it.
        r = run("const box = {innerHTML: '', querySelector(){ return null; }}, out = [], m = " + json.dumps({"modules": MODS, "edges": EDGES}) + ";"
                "globalThis.archMmd = s => '<M/>';"
                "for(const d of [Object.assign({ok: true, commit: 'c1'}, m), Object.assign({ok: true, commit: 'c1', stale: true}, m), {ok: true, empty: true, modules: [], edges: []}]){"
                " ARCH.cache['/r'] = d; box._arsig = ''; archPaint(box, head); out.push(box.innerHTML); }"
                "console.log(JSON.stringify(out));")
        for h in r:
            self.assertIn("data-arq", h.split("</H>")[0])
            self.assertNotIn("data-arq", h.split("</H>")[1])

    def test_request_button_label_by_state(self):
        # Empty -> generate, stale -> update, built at HEAD -> redraw; the preview title follows, and so does the DM verb.
        js = ("const box = {innerHTML: '', querySelector(){ return null; }}, out = [], m = " + json.dumps({"modules": MODS, "edges": EDGES}) + ";"
              "globalThis.archMmd = s => '<M/>';"
              "for(const d of [{ok: true, empty: true, modules: [], edges: [], head: 'h1'}, Object.assign({ok: true, commit: 'c1', head: 'h2', stale: true}, m),"
              " Object.assign({ok: true, commit: 'h1', head: 'h1'}, m)]){"
              " ARCH.cache['/r'] = d; ARCH.req = {p: '/r', sid: '', busy: false}; box._arsig = ''; archPaint(box, head);"
              " const h = box.innerHTML, b = h.slice(h.indexOf('data-arq')), t = h.match(/<div class=archrqh><b>([^<]*)<\\/b>/);"
              " out.push([b.slice(b.indexOf('>') + 1, b.indexOf('</button>')), t ? t[1] : null, (h.match(/«\\/r 아키텍처 구조도 ([^»]*)»/) || [])[1] || null]); }"
              "console.log(JSON.stringify(out));")
        self.assertEqual(run(js), [["구조도 생성 요청", "구조도 생성 요청", "생성"], ["구조도 업데이트 요청", "구조도 업데이트 요청", "업데이트"],
                                   ["다시 그리기", "다시 그리기", "다시 그리기"]])
        self.assertEqual(run(js, "en"), [["Generate diagram", "Generate diagram", "생성"], ["Update diagram", "Update diagram", "업데이트"],
                                         ["Redraw", "Redraw", "다시 그리기"]])

    def test_stale_marker_on_stamp_no_chip(self):
        # Stale map / live run: no separate stale chip in the controls (it wrapped the header badges); the «Generated»
        # stamp carries the ⚠ marker, cut style and the explanation tooltip; run status inline; no band, no dismiss.
        r = run("const box = {innerHTML: '', querySelector(){ return null; }}, out = [], m = " + json.dumps({"modules": MODS, "edges": EDGES}) + ";"
                "globalThis.archMmd = s => '<M/>';"
                "const pt = d => { ARCH.cache['/r'] = d; box._arsig = ''; archPaint(box, head); out.push(box.innerHTML); };"
                "pt(Object.assign({ok: true, commit: 'c1'}, m)); pt(Object.assign({ok: true, commit: 'c1', stale: true}, m));"
                "ARCHRUN = {'/r': {stage: '검증', n: 4, of: 4, sid: 'abcdef123', t0: 1}}; pt(Object.assign({ok: true, commit: 'c1'}, m));"
                "console.log(JSON.stringify(out));")
        self.assertNotIn("구조도가 지금 코드보다 오래되었습니다", r[0])
        self.assertNotIn("⚠", r[0].split("</H>")[0])
        hd, body = r[1].split("</H>", 1)
        stamp = re.findall(r'<em class="strbg strbg-cut" title="([^"]*)">([^<]*)</em>', hd)
        self.assertEqual(len(stamp), 1, hd)                       # one cut badge: the stamp, no extra chip
        self.assertTrue(stamp[0][1].startswith("⚠ "), stamp)
        self.assertIn("c1", stamp[0][1])
        self.assertIn("구조도가 지금 코드보다 오래되었습니다", stamp[0][0])
        self.assertEqual(hd.count("구조도가 지금 코드보다 오래되었습니다"), 1)
        self.assertNotIn("구조도가 코드보다 오래됨", hd)
        for h in r:
            self.assertNotIn("archstale", h)
            self.assertNotIn("data-arsx", h)
        self.assertNotIn("오래되었습니다", body)
        self.assertIn("archrun", r[2].split("</H>")[0])   # run-only: status inline in the header
        self.assertNotIn("archrun", r[2].split("</H>", 1)[1])

    def test_empty_flag_either_shape(self):
        r = run("const box = {innerHTML: '', querySelector(){ return null; }}, out = [];"
                "for(const d of [{ok: false, msg: 'none', empty: true}, {ok: true, empty: true, modules: " + json.dumps(MODS) + ", edges: []}]){"
                " ARCH.cache['/r'] = d; box._arsig = ''; archPaint(box, head); out.push(box.innerHTML.includes('data-arq')); }"
                "console.log(JSON.stringify(out));")
        self.assertEqual(r, [True, True])

    def test_sent_one_line_states(self):
        # 요청됨 -> 분석 중 (spinner) once the session works -> line gone and one notice when a new map arrives.
        r = run("const box = {innerHTML: '', querySelector(){ return null; }}, out = [];"
                "ARCH.cache['/r'] = {ok: false, msg: 'none', empty: true}; ARCH.sent = {p: '/r', sid: 's1', id: 'Sidereus', at: 1000e3, base: ''};"
                "SESS = [{sid: 's1', state: 'idle'}]; archPaint(box, head); out.push(box.innerHTML);"
                "SESS[0].state = 'tool'; box._arsig = ''; archPaint(box, head); out.push(box.innerHTML);"
                "SESS[0].state = 'idle'; box._arsig = ''; archPaint(box, head); out.push(box.innerHTML);"
                "ARCH.cache['/r'] = Object.assign({ok: true, commit: 'c1'}, " + json.dumps({"modules": MODS, "edges": EDGES}) + ");"
                "globalThis.archMmd = s => '<M/>'; box._arsig = ''; archPaint(box, head); out.push(box.innerHTML, ARCH.sent, NOTES);"
                "box._arsig = ''; archPaint(box, head); out.push(NOTES.length);"
                "console.log(JSON.stringify(out));")
        self.assertIn("분석 요청됨 · Sidereus · 15:00", r[0])
        self.assertIn("data-arq aria-expanded=false disabled", r[0])   # fixed header button, off while the request is open
        self.assertNotIn("archspin", r[0])
        self.assertIn("분석 중 · ", r[1])
        self.assertIn("archspin", r[1])
        self.assertIn("분석 중", r[2])          # sticky through an idle gap between stages
        self.assertNotIn("archsent", r[3])
        self.assertIsNone(r[4])
        self.assertEqual(r[5], ["r 아키텍처 구조도 완성"])
        self.assertEqual(r[6], 1)               # exactly one alarm per request

    def test_request_button_says_it_sends_and_no_home_says_what_to_do(self):
        # The header button relays to a session (not a local redraw); an installed package has no repo to run the pipeline from.
        r = run("const c = [{sid: 's1', login: true}];"
                "console.log(JSON.stringify([archReqBtn('/r', '/h', c, null), archReqBtn('/r', '', c, null), archWhyOff('', c, c[0])]));")
        self.assertIn('title="열린 세션에 지도를 그려 달라고 요청합니다', r[0])
        self.assertIn("git clone 으로 받은 Sidereus 에서 실행해야 합니다", r[1])
        self.assertTrue(r[2].startswith("시데레우스 저장소 위치를 모릅니다 — git clone"))

    def test_server_run_after_fresh_load(self):
        # No ARCH.sent (page reloaded): state `archRun` alone shows the run and hides the request; a stale map too.
        r = run("const box = {innerHTML: '', querySelector(){ return null; }}, out = [];"
                "ARCH.cache['/r'] = {ok: true, empty: true, modules: [], edges: [], sidereus: '/r'};"
                "ARCHRUN = {'/r': {stage: '모듈 그리기', n: 2, of: 3, t0: Date.now() / 1000 - 90, sid: 'abcdef1234'}};"
                "archPaint(box, head); out.push(box.innerHTML);"
                "ARCH.cache['/r'] = Object.assign({ok: true, commit: 'c1', stale: true}, " + json.dumps({"modules": MODS, "edges": EDGES}) + ");"
                "globalThis.archMmd = s => '<M/>'; box._arsig = ''; archPaint(box, head); out.push(box.innerHTML);"
                "ARCHRUN = {}; box._arsig = ''; archPaint(box, head); out.push(box.innerHTML);"
                "console.log(JSON.stringify(out));")
        self.assertIn("archrun", r[0])
        self.assertIn("분석 중 · 2/3 단계 · 모듈 그리기 · <span data-arel>90s</span>", r[0])
        self.assertIn("abcdef12", r[0])
        self.assertIn("data-arq aria-expanded=false disabled", r[0])
        self.assertIn("archrun", r[1])
        self.assertIn("data-arq aria-expanded=false disabled", r[1])
        self.assertNotIn("archrun", r[2])
        self.assertIn("data-arq", r[2])
        self.assertNotIn("data-arq aria-expanded=false disabled", r[2])

    def test_server_run_blocks_send_and_end_refetches(self):
        r = run("ARCH.cache['/r'] = {ok: true, empty: true, sidereus: '/r'}; SESS = [{sid: 's1', cwd: '/r', mbox: 'x', mboxSrc: 'identity', state: 'idle'}];"
                "ARCHRUN = {'/r': {stage: '검증', n: 3, of: 3, t0: 1, sid: 's1'}}; ARCH.req = {p: '/r', sid: 's1', busy: false};"
                "const sent = await archSend(); archFetch = (p, f) => FETCHES.push([p, f]);"
                "archTick(5e6); const p0 = PAINTS; ARCHRUN = {}; archTick(5e6 + 5000);"
                "console.log(JSON.stringify([sent, POSTS.length, PAINTS - p0, FETCHES]));")
        self.assertEqual(r[0], False)
        self.assertEqual(r[1], 0)
        self.assertEqual(r[2], 1)
        self.assertEqual(r[3], [["/r", True]])

    def test_stale_map_not_done_until_new_commit(self):
        r = run("ARCH.sent = {p: '/r', sid: 's1', id: 'x', at: 1, base: 'old'}; const m = " + json.dumps(MODS) + ";"
                "console.log(JSON.stringify([archSentDone({ok: true, commit: 'old', modules: m}, ARCH.sent),"
                " archSentDone({ok: true, commit: 'new', modules: m}, ARCH.sent), archSentDone({ok: true, commit: 'new', modules: []}, ARCH.sent)]));")
        self.assertEqual(r, [False, True, False])

    def test_poll_every_30s_then_stops(self):
        r = run("archFetch = (p, f) => { FETCHES.push([p, f]); ARCH.cache[p] = Object.assign({ok: true, commit: 'c1', modules: [{id: 'a'}], edges: []}); archSentFin(p, ARCH.cache[p]); };"
                "ARCH.sent = {p: '/r', sid: 's1', id: 'x', at: 1000, base: '', ph: 'sent'}; const out = [];"
                "out.push(archTick(1000 + 5000));"                        # too soon
                "ARCH.load['/r'] = 1; out.push(archTick(1000 + 31000)); delete ARCH.load['/r'];"   # one in flight
                "mainView = 'tl'; out.push(archTick(1000 + 31000)); mainView = 'struct';"          # tab not visible
                "document.hidden = true; out.push(archTick(1000 + 31000)); document.hidden = false;"
                "out.push(archTick(1000 + 31000));"                       # fetch -> map -> request closed
                "out.push(archTick(1000 + 90000), FETCHES.length, NOTES.length, ARCH.sent);"
                "console.log(JSON.stringify(out));")
        self.assertEqual(r, [False, False, False, False, True, False, 1, 1, None])

    def test_server_message_shown(self):
        r = run("ARCH.cache['/r'] = {ok: false, msg: '<허용 목록에 없는 저장소>'}; const box = {innerHTML: '', querySelector(){ return null; }};"
                "archPaint(box, head); console.log(JSON.stringify(box.innerHTML));")
        self.assertIn("&lt;허용 목록에 없는 저장소&gt;", r)

    def test_dm_body(self):
        r = run("console.log(JSON.stringify(archDmBody(ARCH_PL, '/repo/x', '/sidereus/')));")
        self.assertTrue(r.startswith("파이프라인 arch-map 실행"))
        self.assertIn("/repo/x", r)
        self.assertIn("읽기 전용, 저장소에 쓰지 않음", r)
        self.assertIn("/sidereus/.claude/pipelines/arch-map.json", r)   # absolute: the recipient may sit in another repo
        self.assertNotIn("/usr/bin/python3", r)   # absent on Windows
        self.assertIn("게이트: python3 /sidereus/scripts/arch_verify.py --last (Windows: py /sidereus/scripts/arch_verify.py --last)", r)
        self.assertIn("/arch/<key>/<commit>/", r)

    def test_no_send_without_confirm(self):
        r = run("SESS = [{sid: 's1', cwd: '/sidereus', state: 'idle', mbox: 'me', mboxSrc: 'identity'}];"
                "ARCH.cache['/r'] = {ok: true, modules: [], edges: [], sidereus: '/sidereus'};"
                "const box = {innerHTML: '', querySelector(){ return null; }};"
                "archPaint(box, head); const before = POSTS.length, h1 = box.innerHTML;"   # painting alone sends nothing
                "const r0 = await archSend();"                                              # no open preview -> refused
                "ARCH.req = {p: '/r', sid: 's1', busy: false}; box._arsig = ''; archPaint(box, head); const h2 = box.innerHTML;"
                "const r1 = await archSend();"
                "console.log(JSON.stringify([before, r0, POSTS.length, h1.includes('data-argo'), h2.includes('data-argo') && !/data-argo disabled/.test(h2), r1, POSTS]));")
        self.assertEqual(r[0], 0)
        self.assertFalse(r[1])
        self.assertFalse(r[3])     # confirm button exists only inside the preview
        self.assertTrue(r[4])
        self.assertTrue(r[5])
        self.assertEqual(len(r[6]), 1)
        url, body = r[6][0]
        self.assertEqual(url, "/api/dm")
        self.assertEqual(body["thread"], "pipeline:arch-map")
        self.assertTrue(body["relay"])
        self.assertEqual(body["to"], "me")
        self.assertIn("arch-map", body["body"])

    def test_cands_order_and_default(self):
        r = run("SESS = [{sid: 'z1', cwd: '/other'}, {sid: 'a1', cwd: '/sidereus', mbox: 'ag', mboxSrc: 'identity'}, {sid: 'p1', cwd: '/r'},"
                " {sid: 'p2', cwd: '/r', mbox: 'pm', mboxSrc: 'identity'}, {sid: 'c', cwd: '/r', state: 'done'}, {sid: 'd', cwd: '/r', plat: 'cx', mbox: 'cxm', mboxSrc: 'identity'},"
                " {sid: 'g', cwd: '/r', plat: 'gm', mbox: 'gmm', mboxSrc: 'identity'}];"
                "ARCH.cache['/r'] = {ok: true, modules: [], edges: [], sidereus: '/sidereus'}; ARCH.req = {p: '/r', sid: 'gone', busy: false};"
                "const box = {innerHTML: '', querySelector(){ return null; }}; archPaint(box, head);"
                "console.log(JSON.stringify([archCands('/sidereus', SESS, '/r').map(c => c.sid), ARCH.req.sid, box.innerHTML, archCands('/sidereus', SESS, '/r').map(c => c.cx)]));")
        self.assertEqual(r[0], ["p2", "d", "p1", "a1", "z1"])   # live plat 'cx' (Codex) included · 'gm' not
        self.assertEqual(r[3], [False, True, False, False, False])
        self.assertEqual(r[1], "p2")                       # project session preselected
        self.assertIn('value="p2" selected>r · p2', r[2])  # folder name in the label
        self.assertIn(">other · z1", r[2])

    def test_dm_body_codex_markers(self):
        r = run("console.log(JSON.stringify([archDmBody('arch-map', '/r', '/sidereus/', '업데이트', false), archDmBody('arch-map', '/r', '/sidereus/', '업데이트'),"
                " archDmBody('arch-map', '/r', '/sidereus/', '업데이트', true)]));")
        self.assertEqual(r[0], ARCH_DM_CC + ARCH_DM_TAG)   # Claude recipient: frozen bytes + the stage-tag line
        self.assertEqual(r[1], ARCH_DM_CC + ARCH_DM_TAG)
        self.assertTrue(r[2].startswith(ARCH_DM_CC + "\n"))
        self.assertNotIn(ARCH_DM_TAG, r[2])
        self.assertIn('echo "[pl:arch-map/<stage title>]"', r[2])
        self.assertIn('echo "[pl-end:arch-map/<stage title>]"', r[2])
        for w in CLAUDE_ONLY:
            self.assertNotIn(w, r[2])

    def test_codex_recipient_preview_matches_send(self):
        r = run("SESS = [{sid: 'd1', cwd: '/r', plat: 'cx', mbox: 'cx', mboxSrc: 'identity'}];"
                "ARCH.cache['/r'] = {ok: true, modules: [], edges: [], sidereus: '/sidereus'}; ARCH.req = {p: '/r', sid: 'd1', busy: false};"
                "const box = {innerHTML: '', querySelector(){ return null; }}; archPaint(box, head); const h = box.innerHTML; await archSend();"
                "console.log(JSON.stringify([h, POSTS[0][1].body]));")
        self.assertIn("[pl:arch-map/", r[1])
        self.assertIn("re-read only the files the previous stage wrote (for arch-map: plan.json, then map.json, then flows.json)", r[1])
        self.assertIn("Run all stages back to back in this turn: do not end the turn or report between stages", r[1])
        self.assertIn(r[1].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;"), r[0])

    def test_codex_turn_end_hint(self):
        # Codex recipient: UI-only hint under the preview; a Claude recipient gets none and the body never carries it
        js = ("SESS = [{sid: 'd1', cwd: '/r', plat: 'cx', mbox: 'cx', mboxSrc: 'identity'}, {sid: 'p1', cwd: '/r', mbox: 'pm', mboxSrc: 'identity'}];"
              "ARCH.cache['/r'] = {ok: true, modules: [], edges: [], sidereus: '/sidereus'}; const out = [];"
              "for(const s of ['d1', 'p1']){ ARCH.req = {p: '/r', sid: s, busy: false}; POSTS = [];"
              " const box = {innerHTML: '', querySelector(){ return null; }}; archPaint(box, head); await archSend(); out.push([box.innerHTML, POSTS[0][1].body]); }"
              "console.log(JSON.stringify(out));")
        ko = "이 세션은 지금 턴이나 다음 턴이 끝날 때 받습니다"
        r = run(js)
        self.assertIn("data-cxhint", r[0][0])
        self.assertIn(ko, r[0][0])
        self.assertNotIn("data-cxhint", r[1][0])
        for _h, body in r:
            self.assertNotIn(ko, body)
            self.assertNotIn("turn ends", body)
        self.assertIn("picks it up when its current or next turn ends", run(js, lang="en")[0][0])

    def test_codex_launcher_env_id_sendable(self):
        # cx mboxSrc env = launcher id with a read cursor; the request goes to it
        r = run("SESS = [{sid: 'd1', cwd: '/r', plat: 'cx', mbox: 'r-codex', mboxSrc: 'env'}];"
                "ARCH.cache['/r'] = {ok: true, modules: [], edges: [], sidereus: '/sidereus'}; ARCH.req = {p: '/r', sid: 'd1', busy: false};"
                "const box = {innerHTML: '', querySelector(){ return null; }}; archPaint(box, head); await archSend();"
                "console.log(JSON.stringify([POSTS.length, POSTS[0] && POSTS[0][1].to]));")
        self.assertEqual(r, [1, "r-codex"])


# frozen output of archDmBody before Codex recipients existed (Claude request bytes must not change)
ARCH_DM_CC = ("파이프라인 arch-map 실행 — 요청: «/r 아키텍처 구조도 업데이트»\n대상 저장소: /r\n"
              "읽기 전용, 저장소에 쓰지 않음 — 쓰기는 ${MAILBOX_DIR:-~/.mailbox-mcp}/arch/<key>/<commit>/ 아래만 (key: 파이프라인 rules)\n"
              "파이프라인: /sidereus/.claude/pipelines/arch-map.json (읽기 계획 → 모듈 그리기 → 흐름 그리기 → 검증)\n"
              "게이트: python3 /sidereus/scripts/arch_verify.py --last (Windows: py /sidereus/scripts/arch_verify.py --last)")
# ⚠a Claude recipient in another repo tagged every dispatch [pl:-] without it, so no run was recorded
ARCH_DM_TAG = ("\nTag each stage dispatch description with [pl:arch-map/<stage title>] (not [pl:-]); "
               "a stage you run yourself: Bash description with the same tag.")
CLAUDE_ONLY = ("Agent tool", "subagent_type", "SendMessage", "Workflow", "pl-model", "AskUserQuestion")

MAP = {"modules": MODS + [{"id": "gates", "name": "Check scripts + tests", "kind": "module"},
                          {"id": "x", "name": "Ext \"q\" | <b>", "kind": "external"}],
       "edges": EDGES + [{"from": "a", "to": "b", "label": "y", "ok": True, "est": False, "evidence": []},
                         {"from": "a", "to": "a", "label": "self", "ok": True, "evidence": []},
                         {"from": "gates", "to": "a", "label": "t", "ok": True, "evidence": []},
                         {"from": "c", "to": "x", "label": "ext <i>", "ok": True, "est": True, "evidence": []}]}


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchOverview(unittest.TestCase):
    def test_pairs_collapse(self):
        r = run("const d = " + json.dumps(MAP) + "; console.log(JSON.stringify([archPairs(d.modules, d.edges, false), archPairs(d.modules, d.edges, true).length]));")
        self.assertEqual([(p["from"], p["to"], p["n"]) for p in r[0]], [("a", "b", 2), ("b", "c", 1), ("c", "x", 1)])   # failed c->a, self, gates dropped
        self.assertEqual(r[0][0]["est"], False)
        self.assertEqual(r[0][2]["est"], True)
        self.assertEqual(r[1], 4)

    def test_overview_src(self):
        r = run("const d = " + json.dumps(MAP) + "; console.log(JSON.stringify([archSrc(d.modules, d.edges, false, ''), archSrc(d.modules, d.edges, true, '')]));")
        off, on = r
        self.assertTrue(off.startswith("flowchart TB"))
        self.assertNotIn("Check scripts", off)
        self.assertIn("Check scripts", on)
        self.assertIn('m0 -->|"×2"| m1', off)
        self.assertIn("m1 -.-> m2", off)             # single pair: no label in the overview
        self.assertIn("m2 -.-> m4", off)             # inferred pair stays dashed
        self.assertIn('subgraph xg["외부"]', off)
        self.assertIn("m4([", off)
        self.assertNotIn("<b>", off)
        self.assertNotIn('"q"', off)

    def test_focus_only_neighbours(self):
        r = run("const d = " + json.dumps(MAP) + "; console.log(JSON.stringify(archSrc(d.modules, d.edges, false, 'b')));")
        self.assertTrue(r.startswith("flowchart LR"))
        self.assertEqual(sorted(set(re.findall(r"\bm\d\b", r))), ["m0", "m1", "m2"])
        self.assertIn('m0 -->|"x ×2"| m1', r)
        self.assertIn("m1 -.-> m2", r)                # unlabelled edge stays unlabelled

    def test_diagram_click(self):
        # module: first click focuses, second on the focused one opens its folder; edge group toggles its first ok edge
        r = run("ARCH.cache['/r'] = {ok: true, modules: " + json.dumps(MODS + [{"id": "n", "name": "N", "kind": "pkg"}]) + ", edges: " + json.dumps(EDGES) + "};"
                "const OPEN = []; globalThis.strPopOpenTree = (p, f) => OPEN.push([p, f]);"
                "const T_ = (sel, ds) => ({ closest: s => s === sel ? { dataset: ds } : null });"
                "const out = [], snap = () => out.push([JSON.stringify(ARCH.sel), ARCH.op, OPEN.length, PAINTS]);"
                "archDgClick('/r', T_('.archdg [data-p]', {p: 'm1'})); snap();"
                "archDgClick('/r', T_('.archdg [data-p]', {p: 'm1'})); snap();"
                "archDgClick('/r', T_('.archdg [data-p]', {p: 'm3'})); archDgClick('/r', T_('.archdg [data-p]', {p: 'm3'})); snap();"
                "archDgClick('/r', T_('.archdg .mmdfe', {f: 'm0', t: 'm1'})); snap();"
                "archDgClick('/r', T_('.archdg .mmdfe', {f: 'm0', t: 'm1'})); snap();"
                "archDgClick('/r', T_('.archdg .mmdfe', {f: 'm2', t: 'm0'})); snap();"   # failed edge is never drawn: no-op
                "out.push(archDgClick('/r', T_('.other', {})));"
                "console.log(JSON.stringify([out, OPEN]));")
        out, opened = r
        self.assertEqual(out[0], ['{"p":"/r","id":"b"}', "", 0, 1])       # unfocused click: focus only
        self.assertEqual(out[1], ['{"p":"/r","id":"b"}', "", 1, 1])       # focused again: tree opens, selection unchanged
        self.assertEqual(opened, [["/r", "b"]])
        self.assertEqual(out[2][2], 1)                                    # module without path: second click no-op
        self.assertEqual(out[3][1], "/r\t0")
        self.assertEqual(out[4][1], "")                                   # second edge click closes
        self.assertEqual(out[5][1], "")
        self.assertFalse(out[6])

    def test_tree_folder_or_file(self):
        js = (js_fn("strTreeIsDir") + "const L = {ok: true, files: [{p: 'src/a.py'}, {p: 'Makefile'}, {p: 'pkg.d/x'}]};"
              "console.log(JSON.stringify([strTreeIsDir(L, 'src', 0), strTreeIsDir(L, 'src/a.py', 0), strTreeIsDir(L, 'Makefile', 0),"
              " strTreeIsDir(L, 'pkg.d', 0), strTreeIsDir(null, 'lib/', 0), strTreeIsDir(null, 'lib', 0), strTreeIsDir(null, 'lib/a.js', 0),"
              " strTreeIsDir(null, 'Makefile', 3), strTreeIsDir(L, '', 0)]));")
        r = json.loads(subprocess.run(node_e(js), stdout=subprocess.PIPE, check=True).stdout)
        self.assertEqual(r, [True, False, False, True, True, True, False, False, False])

    def test_bar_and_rows(self):
        r = run("const d = " + json.dumps(MAP) + ", N = {a: 'A', b: 'B'};"
                "console.log(JSON.stringify([archBarHtml(d.modules, d.edges, '', false), archBarHtml(d.modules, d.edges, 'b', true),"
                " archBarHtml(MODS_, [], '', false), archEdgeRow(d.edges[0], N, 0, false, 'in')]));".replace("MODS_", json.dumps(MODS)))
        self.assertIn("data-art", r[0])
        self.assertNotIn(" checked", r[0])
        self.assertIn("data-arall", r[1])
        self.assertIn("들어옴 1", r[1])
        self.assertIn("나감 1", r[1])
        self.assertIn(" checked", r[1])
        self.assertNotIn("data-art", r[2])            # no test module -> no toggle
        self.assertIn('class="arche in"', r[3])

    def test_paint_keeps_selection(self):
        r = run("ARCH.cache['/r'] = Object.assign({ok: true}, " + json.dumps(MAP) + "); ARCH.sel = {p: '/r', id: 'b'};"
                "globalThis.archMmd = src => '<M>' + esc(src) + '</M>';"
                "const box = {innerHTML: '', querySelector(){ return null; }}; archPaint(box, head);"
                "await new Promise(r => setTimeout(r, 5)); box._arsig = ''; archPaint(box, head); const h1 = box.innerHTML;"
                "ARCH.sel = {p: '/r', id: 'gone'}; box._arsig = ''; archPaint(box, head); await new Promise(r => setTimeout(r, 5)); box._arsig = ''; archPaint(box, head);"
                "console.log(JSON.stringify([h1, box.innerHTML]));")
        self.assertIn("flowchart LR", r[0])
        self.assertEqual(r[0].count('class="arche'), 3)   # a->b, b->c, a->b: only b's edges listed
        self.assertIn("flowchart TB", r[1])                # missing module -> overview

    def test_scroll_kept_per_project(self):
        # Same project repaint keeps the map/list scroll; another project opens at 0,0.
        r = run("ARCH.cache['/r'] = Object.assign({ok: true}, " + json.dumps(MAP) + "); ARCH.cache['/b'] = ARCH.cache['/r'];"
                "globalThis.archMmd = src => '<M>' + esc(src) + '</M>';"
                "const map = {scrollTop: 0, scrollLeft: 0}, list = {scrollTop: 0, scrollLeft: 0};"
                "const box = {querySelector(q){ return q === '.archmap' ? map : q === '.archel-list' ? list : null; }}; let H = '';"
                "Object.defineProperty(box, 'innerHTML', {get(){ return H; }, set(v){ H = v; Object.assign(map, {scrollTop: 0, scrollLeft: 0}); list.scrollTop = 0; }});"
                "archPaint(box, head); map.scrollLeft = 2424; map.scrollTop = 949; list.scrollTop = 30;"
                "box._arsig = ''; archPaint(box, head); const a = [map.scrollLeft, map.scrollTop, list.scrollTop];"
                "strOn = ['/b']; archPaint(box, head); const b = [map.scrollLeft, map.scrollTop, list.scrollTop];"
                "console.log(JSON.stringify([a, b]));")
        self.assertEqual(r, [[2424, 949, 30], [0, 0, 0]])

    def test_toolbar_sticky_in_map(self):
        # Bar, notice and legend sit in one .archtop block that is sticky at the scroller's top-left.
        r = run("ARCH.cache['/r'] = Object.assign({ok: true}, " + json.dumps(MAP) + "); globalThis.archMmd = src => '<M>' + esc(src) + '</M>';"
                "const box = {innerHTML: '', querySelector(){ return null; }}; archPaint(box, head); console.log(JSON.stringify(box.innerHTML));")
        top = r.split("<div class=archtop>", 1)[1].split("<div class=archdg", 1)[0]
        self.assertIn("archbar", top)
        self.assertIn("archleg", top)
        self.assertIn("archnol", top)
        fb = run_flow("console.log(JSON.stringify(archFlowBody(" + json.dumps(FLOWS) + ", 0, {})));")   # flow view reuses .archtop
        self.assertIn("archfl", fb.split("<div class=archtop>", 1)[1].split("<div class=archfdg", 1)[0])
        css =_read(os.path.join(os.path.dirname(_SRC_P), "..", "css", "79-structure-arch.css"))
        rule = re.search(r"^\.archtop\{([^}]*)\}", css, re.M).group(1)
        self.assertIn("position:sticky", rule)
        self.assertIn("left:", rule)
        self.assertIn("top:", rule)
        # A flow pick adds buttons to the bar: the hint must shrink in its row, never wrap to a new one (bar height = map offset).
        self.assertIn("flex-wrap:nowrap", re.search(r"^\.archbar:not\(\.on\)\{([^}]*)\}", css, re.M).group(1))
        for sel in ("archhint", "archlitc"):
            rule = re.search(r"^\.archbar:not\(\.on\) \." + sel + r"\{([^}]*)\}", css, re.M).group(1)
            self.assertIn("text-overflow:ellipsis", rule)
        self.assertIn('class=archhint title="', top)   # cut hint keeps its full text on hover

    def test_loading_state(self):
        r = run("const box = {innerHTML: '', querySelector(){ return null; }}; archPaint(box, head); console.log(JSON.stringify(box.innerHTML));")
        self.assertIn("아키텍처 구조도를 불러오는 중…", r)
        self.assertIn("archspin", r)

    def test_diagram_deferred_then_cached(self):
        r = run("ARCH.cache['/r'] = Object.assign({ok: true, commit: 'c1'}, " + json.dumps(MAP) + "); let N = 0;"
                "globalThis.archMmd = src => { N++; return '<M>' + esc(src) + '</M>'; };"
                "const slot = {dataset: {}, innerHTML: ''}, box = {innerHTML: '', querySelector(q){ if(q === '.archdg'){ const m = /data-k=\"([^\"]*)\"/.exec(this.innerHTML);"
                " slot.dataset.k = m ? m[1].replace(/&#39;/g, \"'\") : ''; return slot; } return null; }};"
                "archPaint(box, head); const h1 = box.innerHTML, n1 = N;"
                "await new Promise(r => setTimeout(r, 5)); const filled = slot.innerHTML;"
                "ARCH.op = '/r\\t0'; archPaint(box, head);"                       # evidence click: full repaint, cached diagram
                "console.log(JSON.stringify([h1.includes('archwait'), h1.includes('<M>'), n1, filled.includes('<M>'), box.innerHTML.includes('<M>'), N]));")
        self.assertEqual(r, [True, False, 0, True, True, 1])

    def test_hover_sets(self):
        r = run("const E = [{f: 'm0', t: 'm1'}, {f: 'm1', t: 'm2'}, {f: 'm2', t: 'm0'}, {f: 'm3', t: 'm2'}];"
                "const s = x => Array.from(x).sort(), a = archHov(E, {node: 'm1'}), b = archHov(E, {edge: {f: 'm3', t: 'm2'}}), c = archHov(E, null);"
                "console.log(JSON.stringify([s(a.n), s(a.in), s(a.out), s(b.n), s(b.in), s(b.out), c.n.size + c.in.size + c.out.size]));")
        self.assertEqual(r[0], ["m0", "m1", "m2"])
        self.assertEqual(r[1], ["m0\u0001m1"])
        self.assertEqual(r[2], ["m1\u0001m2", "m2\u0001m0"])   # 2 hops down; m0 -> m1 would be the 3rd
        self.assertEqual(r[3], ["m2", "m3"])
        self.assertEqual(r[4], [])
        self.assertEqual(r[5], ["m3\u0001m2"])
        self.assertEqual(r[6], 0)

    def test_hover_downstream_cascade(self):
        r = run("const E = [{f: 'a', t: 'b'}, {f: 'b', t: 'c'}, {f: 'c', t: 'd'}, {f: 'd', t: 'e'}, {f: 'x', t: 'b'}, {f: 'y', t: 'x'}];"
                "const s = x => Array.from(x).sort(), h = archHov(E, {node: 'b'});"
                "console.log(JSON.stringify([s(h.n), s(h.in), s(h.out)]));")
        self.assertEqual(r[0], ["a", "b", "c", "d", "x"])   # y upstream of an incoming edge, e 3 hops down: not lit
        self.assertEqual(r[1], ["a\u0001b", "x\u0001b"])
        self.assertEqual(r[2], ["b\u0001c", "c\u0001d"])   # 2 hops, d -> e is not

    def test_hover_paint_classes_only(self):
        # fake DOM: classes toggle on nodes/edge groups; the cached SVG string and innerHTML are never touched
        r = run("const el = d => { const c = new Set(); return { dataset: d, classList: { toggle(k, on){ if(on) c.add(k); else c.delete(k); }, has: k => c.has(k) }, c }; };"
                "const N = ['m0', 'm1', 'm2', 'm3'].map(p => el({p})), G = [['m0', 'm1'], ['m1', 'm2'], ['m3', 'm2']].map(([f, t]) => el({f, t}));"
                "let set = 0; const svg = Object.assign(el({}), { querySelectorAll: q => q === '[data-p]' ? N : G }); Object.defineProperty(svg, 'innerHTML', { set(){ set++; } });"
                "ARCH.svg = {k: '<svg>x</svg>'}; archHovPaint(svg, {node: 'm1'});"
                "const L = xs => xs.map(x => Array.from(x.c).sort().join(' ')), on = [svg.c.has('archdim'), L(N), L(G)];"
                "archHovPaint(svg, null);"
                "console.log(JSON.stringify([on, svg.c.has('archdim'), L(N).join('') + L(G).join(''), ARCH.svg.k, set]));")
        self.assertEqual(r[0], [True, ["arin arn", "arh arn", "arn arout", ""], ["arin arn", "arn arout", ""]])
        self.assertEqual(r[1:], [False, "", "<svg>x</svg>", 0])

    def test_cache_key(self):
        r = run("const d = {commit: 'c1', modules: [1, 2], edges: [1]};"
                "console.log(JSON.stringify([archKey(d, '', false), archKey(d, '', false), archKey(d, 'a', false), archKey(d, '', true),"
                " archKey(Object.assign({}, d, {commit: 'c2'}), '', false)]));")
        self.assertEqual(r[0], r[1])
        self.assertEqual(len(set(r)), 4)

    def test_mode_default_and_order(self):
        src = _read(os.path.join(os.path.dirname(_SRC_P), "80-structure.js"))
        init = re.search(r"^let strMode = .*?\n\{.*?\}", src, re.S | re.M).group(0)
        out = []
        for saved in ("", "rel", "size", "arch", "junk"):
            js = "function tabGet(k, d){ return " + json.dumps(saved) + " || d; }\n" + init + "\nconsole.log(JSON.stringify(strMode));"
            out.append(json.loads(subprocess.run(node_e(js), stdout=subprocess.PIPE, check=True).stdout))
        self.assertEqual(out, ["arch", "arch", "size", "arch", "arch"])   # a saved 'rel' (removed view) falls back to arch
        order = re.search(r"\[\['(\w+)', '[^']+'\], \['(\w+)', '[^']+'\]\]\.map\(o => '<button data-m", src)
        self.assertEqual(order.groups(), ("arch", "size"))


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchMdRender(unittest.TestCase):
    def test_render_md_through_81e(self):
        # ⚠render_md emits a ```mermaid fence; mmdBlock takes the fence body (stripped here; the page builds src via archSrc).
        from tests._load import sidereus
        av = sidereus("arch_verify")
        m = {"modules": [{"id": "a.b", "name": "Server + config", "kind": "pkg"}, {"id": "c-d", "name": "Web UI", "kind": "pkg"},
                         {"id": "x", "name": "Claude Code", "kind": "external"}],
             "edges": [{"from": "a.b", "to": "c-d", "label": "serves", "evidence": []},
                       {"from": "c-d", "to": "x", "label": "", "evidence": [], "est": True}]}
        md = av.render_md(m, {"edges": [{"i": 0, "ok": True}, {"i": 1, "ok": True}]})
        fence = re.match(r"^\s*```\s*mermaid[^\n]*\n([\s\S]*?)\n?```\s*$", md)
        self.assertTrue(fence, "render_md no longer emits one mermaid fence")
        body = fence.group(1)
        web = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "js")
        files = [_read(os.path.join(web, f)) for f in sorted(os.listdir(web))
                 if f[:3] in ("81e", "81f", "81g")]   # the real renderer + the router it calls (81g0)
        js = "\n".join(["const document = {addEventListener(){}}, window = {addEventListener(){}};",
                        "const LANG = 'ko'; function T(s){ return s; } let ERR = null; function softErr(t, e){ ERR = String(e); }",
                        "const esc = s => String(s).replace(/[&<>\"']/g, c => '&#' + c.charCodeAt(0) + ';');",
                        "function codeBlock(s){ return '<pre class=cb>' + esc(s) + '</pre>'; }"]
                       + files
                       + ["const md = " + json.dumps(body) + ", g = mmdParse(md), h = mmdBlock(md);",
                          "console.log(JSON.stringify([g.ok, g.nlist.length, g.edges.length, h.indexOf('mmdsvg') >= 0, h.indexOf('mmdno') >= 0, ERR]));"])
        r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        self.assertEqual(json.loads(r.stdout), [True, 3, 2, True, False, None])

    def test_focus_render_in_out(self):
        web = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "js")
        files = [_read(os.path.join(web, f)) for f in sorted(os.listdir(web)) if f[:3] in ("81e", "81f", "81g")]
        js = "\n".join(["const document = {addEventListener(){}}, window = {addEventListener(){}};",
                        "const LANG = 'ko'; function T(s){ return s; } let ERR = null; function softErr(t, e){ ERR = String(e); }",
                        "const esc = s => String(s).replace(/[&<>\"']/g, c => '&#' + c.charCodeAt(0) + ';');",
                        "function codeBlock(s){ return '<pre class=cb>' + esc(s) + '</pre>'; } const ARCH_DIR = 'TB';"]
                       + files + [js_fn(n) for n in ("archIsTest", "archMq", "archPairs", "archReduce", "archSrc", "archRanks", "archMmd")]
                       + ["const d = " + json.dumps(MAP) + ", f = archMmd(archSrc(d.modules, d.edges, true, 'b'), d.modules, 1),"
                          " o = archMmd(archSrc(d.modules, d.edges, false, ''), d.modules, '');",
                          "console.log(JSON.stringify([ERR, (f.match(/data-p=\"m\\d\"/g) || []).sort(), (f.match(/data-c=\"in\"/g) || []).length,"
                          " (f.match(/data-c=\"out\"/g) || []).length, (f.match(/data-on=1/g) || []).length, f.indexOf('mmdsvg') >= 0,"
                          " o.indexOf('<b>') < 0 && o.indexOf('&#60;b&#62;') >= 0, (o.match(/class=\"mmde /g) || []).length, (o.match(/data-p=/g) || []).length]));"])
        r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        out = json.loads(r.stdout)
        self.assertIsNone(out[0])
        self.assertEqual(out[1], ['data-p="m0"', 'data-p="m1"', 'data-p="m2"'])
        self.assertEqual(out[2:6], [2, 1, 1, True])        # a->b in (edge + label), b->c out (no label)
        self.assertTrue(out[6])                            # external label escaped in the SVG
        self.assertEqual(out[7:], [3, 4])                  # overview: 3 pairs, 4 modules (gates hidden)


FLOW_FNS = ["archFlowKind", "archFlowName", "archFlowAt", "archFlowCur", "archFlowPick", "archFlowRate", "archFlowSrc", "archFlowGraph", "archFlowLay", "archFlowSvg", "archFlowMark",
            "archFlowRow", "archFlowBody", "archFlowOpen", "archFlowClick", "archFlowEntries", "archFlowBtn", "archFlowSet",
            "archLitOrder", "archLitNext", "archOffCount", "archLitText", "archScrollAt", "archViewRect", "archLitCount", "archLitGo", "archLitGoBtn",
            "codeBlock", "mmdLabel", "mmdSplit", "mmdChain", "mmdParse", "mmdTw", "mmdBox", "mmdSeqParse", "mmdSeqLayout", "mmdSeqSvg", "mmdBlock"]
FLOWS = [{"id": "login", "name": "Log <in>", "ok": True, "entry": {"kind": "http", "label": "POST /login; #x"},
          "steps": [{"from": "a", "to": "b", "label": "check<pw>", "ok": True, "est": 0, "why": "", "evidence": {"file": "a.py", "line": 3, "symbol": "chk"}},
                    {"from": "b", "to": "c", "label": "save", "ok": True, "est": 1, "why": "", "evidence": {"file": "b.py", "line": 9, "symbol": "put"}}]},
         {"id": "sync", "name": "Sync", "ok": False, "entry": {"kind": "job", "label": "cron"},
          "steps": [{"from": "c", "to": "a", "label": "pull", "ok": True, "est": 0, "why": "", "evidence": {"file": "c.py", "line": 1, "symbol": "pull"}},
                    {"from": "a", "to": "b", "label": "push\nnow", "ok": False, "est": 0, "why": "nosym", "evidence": {"file": "a.py", "line": 7, "symbol": "push"}}]}]
# Fake DOM: an svg whose message groups are read back from the rendered string; closest() over a fixed ancestor list.
FAKE = """
const OPENS = []; function strPopOpenRel(){ OPENS.push(Array.from(arguments)); }
function hl(s){ return esc(s); } function softErr(){}
globalThis.document = { hidden: false, querySelector(){ return null; }, addEventListener(){},
  createElementNS(ns, n){ return { ns, n, textContent: '' }; } };
function fakeSvg(html){ const gs = {}; (html.match(/class=mmdsqm data-i=\\d+/g) || []).forEach(m => { const i = m.split('=').pop();
  gs[i] = { kids: [], cls: [], classList: { add(c){ gs[i].cls.push(c); } }, get firstChild(){ return this.kids[0] || null; }, insertBefore(t){ this.kids.unshift(t); } }; });
  return { gs, querySelector(sel){ const m = sel.match(/data-i="(\\d+)"/); return m ? gs[m[1]] || null : null; } }; }
function el(map){ return { closest(sel){ return Object.prototype.hasOwnProperty.call(map, sel) ? map[sel] : null; } }; }
"""


def run_flow(body):
    ksrc = _read(_SRC_P.replace("84j-structure-arch.js", "84k-structure-arch-flow.js"))
    kinds = "\n".join(re.search(r"^const ARCH_(?:FLOW_KIND|LITGO) = .*$".replace("(?:FLOW_KIND|LITGO)", n), ksrc, re.M).group(0) for n in ("FLOW_KIND", "LITGO"))
    js = "\n".join([PRE, FAKE, kinds] + [js_fn(n) for n in FNS + FLOW_FNS] + ["(async () => {", body, "})().catch(e => { console.error(e); process.exit(1); });"])
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchFlow(unittest.TestCase):
    def test_src_escape_and_dashed_fail(self):
        r = run_flow("const N = {a: 'A <x>', b: 'B;b', c: 'C'}, F = " + json.dumps(FLOWS) + ";"
                     "console.log(JSON.stringify([archFlowSrc(F[0], N), archFlowSrc(F[1], N), archFlowName(N, 'constructor'), archFlowName(N, 'a')]));")
        self.assertEqual(r[0].split("\n"), ["sequenceDiagram", "actor e as POST /login   x", "participant p0 as A  x",
                                            "participant p1 as B b", "participant p2 as C", "e->>p0:", "autonumber", "p0->>p1: check pw", "p1->>p2: save"])
        self.assertIn("p1-->>p2: push now", r[1])         # failed step dashed, newline flattened
        self.assertIn("p0->>p1: pull", r[1])
        self.assertEqual(r[2:], ["constructor", "A <x>"])   # own keys only, never the prototype

    def test_picker_hidden_without_flows(self):
        d = {"ok": True, "commit": "c1", "modules": MODS, "edges": EDGES}
        r = run_flow("const box = {innerHTML: '', querySelector(){ return null; }}, out = [];"
                     "globalThis.archMmd = s => '<M/>';"
                     "for(const f of [undefined, []]){ const d = Object.assign({}, " + json.dumps(d) + "); if(f) d.flows = f;"
                     " ARCH.cache['/r'] = d; box._arsig = ''; archPaint(box, head); out.push(box.innerHTML); }"
                     "const d2 = Object.assign({flows: " + json.dumps(FLOWS) + "}, " + json.dumps(d) + "); ARCH.cache['/r'] = d2; box._arsig = ''; archPaint(box, head); out.push(box.innerHTML);"
                     "console.log(JSON.stringify(out));")
        self.assertEqual(r[0], r[1])
        self.assertNotIn("data-arfl", r[0])
        self.assertIn("data-arfl", r[2])
        self.assertIn("✗ Sync", r[2])
        self.assertIn("✓ Log &lt;in&gt;", r[2])              # names escaped, not translated
        self.assertIn("모듈 구조도", r[2])

    def test_flow_view_rows_and_mark(self):
        d = {"ok": True, "commit": "c1", "modules": MODS, "edges": EDGES, "flows": FLOWS}
        r = run_flow("let SVG = null; const box = {innerHTML: '', querySelector(s){ return s === '.archfdg svg' ? (SVG = fakeSvg(this.innerHTML)) : null; }};"
                     "ARCH.cache['/r'] = " + json.dumps(d) + "; ARCH.flow = {p: '/r', id: 'sync'}; archPaint(box, head);"
                     "const g = SVG.gs; console.log(JSON.stringify([box.innerHTML, Object.keys(g).sort(), g['2'].cls, g['2'].kids.map(k => k.textContent), g['1'].cls]));")
        h = r[0]
        self.assertIn("archfdg", h)
        self.assertNotIn("class=archdg", h)
        self.assertIn('data-afs="1"', h)
        self.assertIn('data-af="a.py"', h)                    # evidence reuses archEvHtml
        self.assertIn("검증 실패", h)
        self.assertIn("단계 1/2 증명", h)
        self.assertIn("작업", h)                               # entry kind translated by key
        self.assertEqual(r[1], ["0", "1", "2"])               # item 0 = entry arrow
        self.assertEqual(r[2], ["archfx"])                    # step 1 -> data-i 2
        self.assertEqual(r[3], ["증명 안 됨: nosym"])
        self.assertEqual(r[4], [])

    def test_layout_width_fits_self_label_and_caps_names(self):
        # 5 participants, last one long-named; the longest self label sits on the last lifeline (no next gap to widen).
        names = {"shell": "FE shell (app, components, lib)", "acl": "acl (FE)", "api": "FE api client", "be": "acl (BE)", "sec": "BE common security"}
        lab = "insert request row (mapper AclRequestMapper.insert)"
        steps = [{"from": a, "to": b, "label": l, "ok": True} for a, b, l in
                 [("shell", "acl", "open"), ("acl", "api", "post"), ("api", "be", "POST /acl/requests"),
                  ("be", "be", "controller - AclRequestService.create"), ("be", "sec", "check"), ("sec", "sec", lab)]]
        fl = {"id": "f", "entry": {"label": "POST /acl/requests"}, "steps": steps}
        r = run_flow("const g = archFlowGraph(" + json.dumps(fl) + ", " + json.dumps(names) + "), L = archFlowLay(g), M = mmdSeqLayout(g);"
                     "const it = g.items.find(x => x.k === 'msg' && x.a === 'p4' && x.b === 'p4'), i = g.pmap['p4'].i;"
                     "const end = L.cx[i] + L.dx + 30 + 6 + Math.max(...it.label.split('\\n').map(mmdTw));"
                     "const svg = archFlowSvg(" + json.dumps(fl) + ", " + json.dumps(names) + ", 0);"
                     "console.log(JSON.stringify([g.parts.map(p => p.label), g.parts.map(p => p.full || ''), L.w, end, M.w, svg, it.label]));")
        labels, full, w, end, wide, svg, wrapped = r
        self.assertEqual(wrapped, "insert request row\n(mapper\nAclRequestMapper.\ninsert)")   # wrapped at 20 chars, long words after the dot
        self.assertEqual(len(labels), 6)                       # entry actor + 5 modules
        self.assertTrue(all(len(x) <= 22 for x in labels))
        self.assertEqual(labels[1], "FE shell (app, compon…")
        self.assertEqual(full[1], "FE shell (app, components, lib)")
        self.assertGreaterEqual(w, end)                        # self label inside the total width
        self.assertLess(w, wide)                               # tighter than the md-preview gaps
        self.assertIn("<title>FE shell (app, components, lib)</title>", svg)
        self.assertIn("width:100%;height:auto;max-width:" + str(w) + "px;min-width:" + str(-(-w * 3 // 4)) + "px", svg)
        self.assertIn("class=mmdsqm data-i=6", svg)            # step 5 -> data-i 6 still

    def test_click_opens_code(self):
        d = {"ok": True, "commit": "c1", "modules": MODS, "edges": EDGES, "flows": FLOWS}
        r = run_flow("ARCH.cache['/r'] = " + json.dumps(d) + "; ARCH.flow = {p: '/r', id: 'sync'}; const tab = {};"
                     "const msg = el({'.archtab': tab, '.archfdg .mmdsqm[data-i]': {dataset: {i: '2'}}}),"
                     " row = el({'.archtab': tab, '[data-afs]': {dataset: {afs: '0'}}}), ent = el({'.archtab': tab, '.archfdg .mmdsqm[data-i]': {dataset: {i: '0'}}}),"
                     " ev = el({'.archtab': tab, '[data-aev]': {}, '[data-afs]': {dataset: {afs: '0'}}});"
                     "const out = [archFlowClick(msg), archFlowClick(row), archFlowClick(ent), archFlowClick(ev)];"
                     "ARCH.flow = null; out.push(archFlowClick(row)); console.log(JSON.stringify([out, OPENS]));")
        self.assertEqual(r[0], [True, True, False, False, False])
        self.assertEqual(r[1], [["/r", "a.py", 7, 80, "push"], ["/r", "c.py", 1, 80, "pull"]])


    def test_R2_picker_sets_lit_not_flow(self):
        d = {"ok": True, "commit": "c1", "modules": MODS, "edges": EDGES, "flows": FLOWS}
        r = run_flow("ARCH.cache['/r'] = " + json.dumps(d) + "; ARCH.flow = null; ARCH.lit = null; const o = [];"
                     "archFlowSet('/r', 'sync'); o.push([ARCH.lit, ARCH.flow]);"
                     "globalThis.archMmd = () => '<M/>'; const box = {innerHTML: '', querySelector(){ return null; }}; archPaint(box, head); o.push(box.innerHTML);"
                     "ARCH.flow = {p: '/r', id: 'login'}; archFlowSet('/r', 'sync'); o.push([ARCH.lit, ARCH.flow]);"
                     "archFlowSet('/r', ''); o.push([ARCH.lit, ARCH.flow]); console.log(JSON.stringify(o));")
        self.assertEqual(r[0], [{"p": "/r", "flow": "sync"}, None])   # map stays: only the highlight is set
        self.assertNotIn("archfdg", r[1])
        self.assertIn('value="sync" selected', r[1])
        self.assertIn('data-arseq="sync" aria-pressed=false', r[1])
        self.assertIn("data-arlitx", r[1])
        self.assertEqual(r[2], [{"p": "/r", "flow": "sync"}, {"p": "/r", "id": "sync"}])   # in the sequence view the picker switches it
        self.assertEqual(r[3], [None, None])

    def test_R3_seq_toggle_and_clear(self):
        r = run_flow("ARCH.flow = null; ARCH.lit = {p: '/r', flow: 'sync'}; const tab = {}, o = [];"
                     "const seq = el({'.archtab': tab, '[data-arseq],[data-arlitx]': {dataset: {arseq: 'sync'}}}), clr = el({'.archtab': tab, '[data-arseq],[data-arlitx]': {dataset: {arlitx: ''}}});"
                     "o.push(archFlowBtn(seq), ARCH.flow, ARCH.lit); archFlowBtn(seq); o.push(ARCH.flow, ARCH.lit); archFlowBtn(seq); archFlowBtn(clr); o.push(ARCH.flow, ARCH.lit);"
                     "const F = " + json.dumps(FLOWS) + "; o.push(archFlowPick(F, 'sync', true), archFlowPick(F, 'nope'), archFlowPick(F, ''), archFlowBtn(el({'.archtab': tab})));"
                     "console.log(JSON.stringify(o));")
        self.assertTrue(r[0])
        self.assertEqual(r[1:3], [{"p": "/r", "id": "sync"}, {"p": "/r", "flow": "sync"}])   # toggle on: sequence view of the lit flow
        self.assertEqual(r[3:5], [None, {"p": "/r", "flow": "sync"}])                         # toggle off: back to the lit map
        self.assertEqual(r[5:7], [None, None])                                                 # «Clear flow» clears both
        self.assertIn("aria-pressed=true", r[7])
        self.assertIn("시퀀스 다이어그램", r[7])
        self.assertIn("흐름 해제", r[7])
        self.assertNotIn("data-arseq", r[8])                                                   # a flow gone from the map: no buttons
        self.assertNotIn("data-arlitx", r[9])
        self.assertFalse(r[10])

    def test_R1_off_count_text_and_toolbar(self):
        F = json.dumps(FLOWS)
        r = run_flow("const v = {left: 0, top: 40, right: 500, bottom: 400}, R = (l, t, w, h) => ({left: l, top: t, right: l + w, bottom: t + h});"
                     "console.log(JSON.stringify([archOffCount([R(10, 50, 50, 20), R(600, 50, 50, 20), R(10, 0, 50, 30), R(480, 380, 50, 50), R(10, 420, 5, 5)], v),"
                     " archLitText(3, 0), archLitText(5, 2), archFlowPick(" + F + ", 'sync'), archFlowPick(" + F + ", 'sync', true), archFlowPick(" + F + ", '')]));")
        self.assertEqual(r[0], 3)                                # wholly outside (right · under the sticky bar · below); a partial one counts as visible
        self.assertEqual(r[1], "")                               # m = 0: the line hides
        self.assertEqual(r[2], "5개 강조 · 2개 화면 밖")
        self.assertIn("data-arlitn>다음 강조</button>", r[3])
        self.assertIn("data-arlitc role=status hidden", r[3])
        self.assertNotIn("data-arlitn", r[4])                    # sequence view: no map, no count
        self.assertNotIn("data-arlitc", r[5])

    def test_R1_count_reads_rects_never_scrolls(self):
        r = run_flow("const R = (l, t) => ({left: l, top: t, right: l + 40, bottom: t + 20}), cls = on => ({contains(){ return on; }});"
                     "const nodes = [R(10, 60), R(900, 60), R(10, 900)].map(b => ({getBoundingClientRect(){ return b; }}));"
                     "const c = {textContent: '', hidden: true}, moves = [];"
                     "const am = {scrollLeft: 7, scrollTop: 9, clientWidth: 500, clientHeight: 400, getBoundingClientRect(){ return {left: 0, top: 0}; },"
                     " scrollTo(o){ moves.push(o); }, querySelector(q){ return q === '[data-arlitc]' ? c : q === '.archtop' ? {offsetHeight: 40}"
                     "  : q === '.archdg svg' ? {querySelectorAll(){ return nodes; }} : null; }};"
                     "archLitCount(am); const a = [c.textContent, c.hidden]; nodes.length = 1; archLitCount(am);"
                     "console.log(JSON.stringify([a, c.textContent, c.hidden, am.scrollLeft, am.scrollTop, moves]));", )
        self.assertEqual(r[0], ["3개 강조 · 2개 화면 밖", False])
        self.assertEqual(r[1:3], ["", True])                     # all lit nodes visible: hidden
        self.assertEqual(r[3:], [7, 9, []])                      # counting never moves the view

    def test_R1_R2_no_view_move_outside_next(self):
        src = _read(_SRC_P.replace("84j-structure-arch.js", "84k-structure-arch-flow.js"))
        det = _read(_SRC_P.replace("84j-structure-arch.js", "84j3-structure-arch-detail.js"))
        self.assertNotIn("scrollIntoView", src + det)
        body = re.search(r"^function archLitGo\(.*?^}", src, re.S | re.M).group(0)
        rest = src.replace(body, "")
        self.assertIn("am.scrollTo(", body)
        self.assertNotIn("scrollTo(", rest)                       # pick · Esc · Clear · count never scroll
        self.assertNotIn("scrollLeft =", rest)
        self.assertIn("archLitCount(slot.closest('.archmap'))", det)   # recount on lit paint

    def test_R2_R3_next_lit_cycles_scrolls_archmap_and_flashes(self):
        d = {"ok": True, "commit": "c1", "modules": MODS, "edges": EDGES, "flows": FLOWS}
        r = run_flow("ARCH.cache['/r'] = " + json.dumps(d) + "; ARCH.lit = {p: '/r', flow: 'login'}; ARCH.tests = false;"
                     "const ord = [archLitOrder(ARCH.cache['/r'], 'login', false), archLitOrder(ARCH.cache['/r'], 'sync', false), archLitOrder(ARCH.cache['/r'], 'nope', false)];"
                     "const T0 = []; globalThis.setTimeout = (f, ms) => { T0.push(ms); f(); return 0; };"
                     "const pos = {en0: [40, 20], m0: [900, 500], m1: [100, 900], m2: [1200, 1300]}, flash = [];"
                     "const mk = k => { const s = new Set(); return {k, classList: {add(c){ s.add(c); flash.push(k + '+' + c); }, remove(c){ s.delete(c); }, has(c){ return s.has(c); }},"
                     " getBoundingClientRect(){ const [x, y] = pos[k]; return {left: x - am.scrollLeft, top: y - am.scrollTop, right: x - am.scrollLeft + 40, bottom: y - am.scrollTop + 20}; }}; };"
                     "const N = {}; ['en0', 'm0', 'm1', 'm2'].forEach(k => { N[k] = mk(k); });"
                     "const am = {scrollLeft: 0, scrollTop: 0, clientWidth: 500, clientHeight: 440, getBoundingClientRect(){ return {left: 0, top: 0}; },"
                     " scrollTo(o){ this.scrollLeft = o.left; this.scrollTop = o.top; }, querySelector(q){ return q === '.archtop' ? {offsetHeight: 40} : q === '.archdg svg' ? svg : null; }};"
                     "let drawn = ['en0', 'm0', 'm1', 'm2']; const svg = {querySelector(q){ const k = q.match(/data-p=\"(\\w+)\"/)[1]; return drawn.indexOf(k) >= 0 ? N[k] : null; }};"
                     "const tab = {}, b = {closest(q){ return q === '.archmap' ? am : null; }}, t = el({'.archtab': tab, '[data-arlitn]': b});"
                     "const seen = []; for(let i = 0; i < 5; i++){ archLitGoBtn(t); seen.push([ARCH_LITGO.k, am.scrollLeft, am.scrollTop]); }"
                     "drawn = ['m0', 'm2']; ARCH_LITGO.k = 'm0'; archLitGoBtn(t); seen.push(ARCH_LITGO.k);"
                     "const other = archLitGoBtn(el({'.archtab': tab})); ARCH.lit = null; const off = archLitGoBtn(t);"
                     "console.log(JSON.stringify([ord, seen, flash.slice(0, 2), N.m0.classList.has('arflash'), T0[0], other, off]));")
        ord, seen, flash, still, ms, other, off = r
        self.assertEqual(ord[0], ["en0", "m0", "m1", "m2"])      # entry first, then step order
        self.assertEqual(ord[1], ["en1", "m2", "m0", "m1"])
        self.assertEqual(ord[2], [])
        self.assertEqual([x[0] for x in seen[:5]], ["en0", "m0", "m1", "m2", "en0"])   # wraps after the last
        self.assertEqual(seen[1][1:], [670, 270])                # m0 centred in the area under the 40px bar (x 920-250, y 510-240)
        self.assertEqual(seen[0][1:], [0, 0])                    # clamped at the origin
        self.assertEqual(seen[5], "m2")                          # keys not drawn in this view are skipped
        self.assertEqual(flash, ["en0+arflash", "m0+arflash"])
        self.assertFalse(still)                                  # flash removed after its timer
        self.assertEqual(ms, 1100)
        self.assertFalse(other)
        self.assertFalse(off)                                    # nothing lit: not handled

    def test_R4_kind_label_ko(self):
        r = run_flow("console.log(JSON.stringify([archFlowKind('hook'), archFlowKind('mcp'), archFlowKind('<x>')]));")
        self.assertEqual(r, ["훅", "MCP", "<x>"])
        with open(os.path.join(os.path.dirname(_SRC_P), "06-i18n-zs-arch.js"), encoding="utf-8") as fh:
            ko = fh.read()
        for k in ("'Hook|arch flow kind'", "'MCP|arch flow kind'", "'Clear flow'", "'Sequence diagram'"):
            self.assertIn(k, ko)

    def test_R5_v1_or_no_flows_no_entries(self):
        lm = [dict(m, layer=ly) for m, ly in zip(MODS, ("entry", "api", "data"))]
        v2 = {"ok": True, "v": 2, "commit": "c1", "modules": lm, "edges": EDGES}
        r = run_flow("globalThis.archMmd = s => '<M/>'; const S = [], box = {innerHTML: '', querySelector(){ return null; }}, H = [];"
                     "const _bs = archBandSrc; archBandSrc = function(){ S.push(arguments[5] || null); return _bs.apply(null, arguments); };"
                     "for(const f of [undefined, [], " + json.dumps(FLOWS) + "]){ const d = Object.assign({}, " + json.dumps(v2) + "); if(f) d.flows = f;"
                     " ARCH.cache['/r'] = d; ARCH.svg = {}; box._arsig = ''; archPaint(box, head); H.push(box.innerHTML); }"
                     "const v1 = {ok: true, commit: 'c1', modules: " + json.dumps(MODS) + ", edges: " + json.dumps(EDGES) + ", flows: " + json.dumps(FLOWS) + "};"
                     "ARCH.cache['/r'] = v1; box._arsig = ''; archPaint(box, head);"
                     "await new Promise(f => setTimeout(f, 20)); console.log(JSON.stringify([H, S.map(x => x && x.map(e => e.k + ':' + e.label)), box.innerHTML.indexOf('en0') < 0]));")
        html, ents, v1 = r
        self.assertEqual(html[0], html[1])                      # flows absent or empty: same page
        self.assertEqual(ents, [None, None, ["en0:POST /login; #x", "en1:cron"]])
        self.assertNotEqual(html[1], html[2])                   # entry nodes change the diagram key
        self.assertTrue(v1)                                     # v1 map: no band source, no entry nodes

    def test_R5_key_changes_with_entries(self):
        r = run_flow("const d = {commit: 'c', modules: [1], edges: [1]}, en = [{kind: 'http', label: 'GET /', to: new Set([0])}];"
                     "console.log(JSON.stringify([archKey(d, '', false, false), archKey(d, '', false, false, null), archKey(d, '', false, false, []),"
                     " archKey(d, '', false, false, en), archKey(d, '', false, false, [Object.assign({}, en[0], {to: new Set([1])})])]));")
        self.assertEqual(len(set(r[:3])), 1)
        self.assertEqual(len(set(r)), 3)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchClick(unittest.TestCase):
    def test_module_click_sets_focus(self):
        # The real 84j document click listener, run on a fake .archdg node target.
        js = "\n".join([
            "const H = {}; globalThis.document = {addEventListener(k, f){ (H[k] = H[k] || []).push(f); }};",
            "globalThis.setInterval = () => 0; let strMode = 'arch', strOn = ['/r'], mainView = 'struct', PAINTS = 0;",
            "function paintStruct(){ PAINTS++; } function strPopOpenRel(){} function strStop(){} function tabSet(){}",
            _SRC,
            "ARCH.cache['/r'] = {modules: " + json.dumps(MODS) + "};",
            "const node = {dataset: {p: 'm1'}}, t = {closest(sel){ return sel === '.archtab' ? {} : sel === '.archdg [data-p]' ? node : null; }};",
            "H.click.forEach(f => f({target: t}));",
            "console.log(JSON.stringify([ARCH.sel, PAINTS]));"])
        r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        self.assertEqual(json.loads(r.stdout), [{"p": "/r", "id": "b"}, 1])


# Self-map modules [id, name] and verified edges [from, to, ok, est] (copied: tests never read the arch store).
# ⚠Names set the box widths, so they stay: with ids only the full overview drops to 57 crossings.
SELF_MODS = [["server", "Server entry + config"], ["routes", "HTTP routes + page assembly"], ["state", "State snapshot + attention/cards"],
             ["sessions", "Sessions, agents, transcripts"], ["pipeline", "Pipelines + stage-mark hooks"], ["harness", "Harness, failures, tool index"],
             ["quota", "Quota, saver, burn, usage"], ["structure", "Structure scan/views"], ["arch", "Architecture map + verifier"],
             ["timeline", "Timeline + history"], ["git", "Git info, branches, review"], ["mailbox", "Mailbox core, bus, rooms, hooks, MCP"],
             ["platforms", "CLI adapters + external platforms"], ["web", "Web UI (HTML/CSS/JS)"], ["gates", "Check scripts + tests"],
             ["ext.claude_code", "Claude Code (transcripts, hooks)"], ["ext.git", "git CLI"], ["ext.mailbox_store", "Mailbox store (bus.jsonl)"]]
SELF_EDGES = [["server", "routes", 1, 0], ["server", "state", 1, 0], ["server", "mailbox", 1, 0], ["server", "timeline", 1, 0],
              ["server", "quota", 1, 0], ["server", "structure", 1, 0], ["server", "harness", 1, 0], ["server", "git", 1, 0],
              ["web", "routes", 0, 0], ["routes", "web", 1, 1], ["routes", "state", 1, 0], ["routes", "sessions", 1, 0],
              ["routes", "pipeline", 1, 0], ["routes", "harness", 1, 0], ["routes", "quota", 1, 0], ["routes", "structure", 1, 0],
              ["routes", "arch", 1, 0], ["routes", "timeline", 1, 0], ["routes", "git", 1, 0], ["routes", "mailbox", 1, 0],
              ["routes", "platforms", 1, 0], ["state", "sessions", 1, 0], ["state", "mailbox", 1, 0], ["state", "quota", 1, 0],
              ["state", "git", 1, 0], ["state", "harness", 1, 0], ["state", "platforms", 1, 0], ["sessions", "state", 1, 0],
              ["sessions", "pipeline", 1, 0], ["sessions", "platforms", 1, 0], ["sessions", "git", 1, 0], ["sessions", "ext.claude_code", 1, 0],
              ["timeline", "sessions", 1, 0], ["structure", "sessions", 1, 0], ["structure", "git", 1, 0], ["arch", "structure", 1, 0],
              ["arch", "git", 1, 0], ["harness", "pipeline", 1, 0], ["pipeline", "harness", 1, 0], ["git", "sessions", 1, 0],
              ["git", "ext.git", 1, 0], ["mailbox", "ext.mailbox_store", 1, 0], ["mailbox", "routes", 0, 0], ["quota", "ext.claude_code", 1, 0],
              ["ext.claude_code", "pipeline", 1, 1], ["ext.claude_code", "mailbox", 1, 1], ["gates", "server", 1, 0], ["gates", "arch", 0, 0]]


def _pairs(r):
    return [(p["from"], p["to"]) for p in r]


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchReduce(unittest.TestCase):
    def test_reduce(self):
        r = run("const P = (f, t, est) => ({from: f, to: t, n: 1, est: !!est, label: ''});"
                "console.log(JSON.stringify([archReduce([P('a', 'b'), P('b', 'c'), P('a', 'c')]), archReduce([P('a', 'b'), P('b', 'a')]),"
                " archReduce([P('a', 'c', 1), P('a', 'b'), P('b', 'c')]), archReduce([P('a', 'c'), P('a', 'b'), P('b', 'c')]),"
                " archReduce([P('a', 'b'), P('b', 'c'), P('c', 'a'), P('a', 'c')]), archReduce([])]));")
        self.assertEqual(_pairs(r[0]), [("a", "b"), ("b", "c")])
        self.assertEqual(_pairs(r[1]), [("a", "b"), ("b", "a")])          # a cycle keeps both directions
        self.assertEqual(_pairs(r[2]), [("a", "b"), ("b", "c")])          # the est shortcut goes
        self.assertEqual(_pairs(r[3]), [("a", "b"), ("b", "c")])          # input order kept
        self.assertEqual(_pairs(r[4]), [("a", "b"), ("b", "c"), ("c", "a")])
        self.assertEqual(r[5], [])

    def test_ranks(self):
        r = run("const R = (ids, es) => archRanks(ids, es.map(e => ({from: e[0], to: e[1]})));"
                "const cyc = () => R(['a', 'b', 'c', 'e'], [['a', 'b'], ['b', 'c'], ['c', 'a'], ['e', 'a']]);"
                "console.log(JSON.stringify([R(['a', 'b', 'c'], [['a', 'b'], ['b', 'c']]),"
                " R(['a', 'b', 'c', 'd'], [['a', 'b'], ['a', 'c'], ['b', 'd'], ['c', 'd']]),"
                " R(['a', 'x', 'b', 'c', 'd'], [['a', 'x'], ['a', 'b'], ['b', 'c'], ['c', 'd']]),"
                " cyc(), cyc(), R(['a', 'b', 'z'], [['a', 'b']]),"
                " R(['a', 'b', 'xg'], [['a', 'b'], ['b', 'xg']]), R(['a', 'xg'], [])]));")
        self.assertEqual(r[0], {"a": 0, "b": 1, "c": 2})
        self.assertEqual(r[1], {"a": 0, "b": 1, "c": 1, "d": 2})
        self.assertEqual(r[2]["x"], 1)                     # short sink keeps its longest-path depth (not pinned)
        self.assertEqual(r[3], r[4])                       # cycle: deterministic
        self.assertEqual(r[3]["e"], 0)
        self.assertEqual(r[3], {"e": 0, "a": 1, "b": 2, "c": 3})
        self.assertEqual(r[5]["z"], 0)                     # isolated stays on top
        self.assertEqual(r[6], {"a": 0, "b": 1, "xg": 2})
        self.assertEqual(r[7], {"a": 0, "xg": 0})          # every root id ranked, or the layout drops rankFix

    def test_src_bar_key(self):
        d = {"modules": MODS, "edges": [{"from": "a", "to": "b", "ok": True}, {"from": "b", "to": "c", "ok": True}, {"from": "a", "to": "c", "ok": True}]}
        r = run("const d = " + json.dumps(d) + ", k = {commit: 'c1', modules: [1], edges: [1]};"
                "console.log(JSON.stringify([archSrc(d.modules, d.edges, false, ''), archSrc(d.modules, d.edges, false, '', 1), archSrc(d.modules, d.edges, false, 'a'),"
                " archBarHtml(d.modules, d.edges, '', false, false), archBarHtml(d.modules, d.edges, '', false, true), archBarHtml(MODS_, [], '', false, false),"
                " archKey(k, '', false, false), archKey(k, '', false, true)]));".replace("MODS_", json.dumps(MODS)))
        self.assertNotIn("m0 --> m2", r[0])
        self.assertIn("m0 --> m2", r[1])
        self.assertIn("m0 --> m2", r[2])                  # focus view: every direct edge
        self.assertIn("간접 연결 1개 생략", r[3])
        self.assertIn("data-arfull>", r[3])
        self.assertIn("data-arfull checked", r[4])
        self.assertNotIn("간접 연결", r[4])
        self.assertNotIn("data-arfull", r[5])             # nothing implied -> no toggle
        self.assertNotEqual(r[6], r[7])

    def test_self_map_ranks(self):
        # Overview rankFix must rank every root item (nodes + External box) or 81f silently ignores it.
        from tests.test_structure_mermaid_js import PRE as MPRE, FNS as MFNS
        ROUTER = _read(os.path.join(os.path.dirname(_SRC_P), "81g0-structure-grid-router.js"))
        mods = [{"id": m, "name": n, "kind": "external" if m.startswith("ext.") else "module"} for m, n in SELF_MODS]
        edges = [{"from": f, "to": t, "ok": bool(ok), "est": bool(est)} for f, t, ok, est in SELF_EDGES]
        js = "\n".join([MPRE, "const MMD_BUDGET = 1e9, MMD_UNCROSS = 1e9, ARCH_DIR = 'TB'; let ERR = null; function softErr(t, e){ ERR = String(e); }",
                        "function codeBlock(s){ return s; }", ROUTER] + [js_fn(f) for f in MFNS]
                       + [js_fn(n) for n in ("archIsTest", "archMq", "archPairs", "archReduce", "archSrc", "archRanks", "archMmd")]
                       + ["const M = " + json.dumps(mods) + ", E = " + json.dumps(edges) + ", _L = mmdLayout; let G = null, Q = null;",
                          "mmdLayout = g => { const L = _L(g); G = g; Q = mmdQuality(g, L); return L; };",
                          "archMmd(archSrc(M, E, false, ''), M, '');",
                          "const root = G.nlist.filter(k => !G.nodes[k].sg).concat(G.slist.filter(s => !G.sgs[s].parent));",
                          "const ents = root.filter(k => k !== 'xg' && !G.edges.some(e => e.to === k) && G.edges.some(e => e.from === k));",
                          "process.stdout.write(JSON.stringify([ERR, root.filter(k => !(G.rankFix && isFinite(G.rankFix[k]))), ents.map(k => G.rankFix[k]),"
                          " G.rankFix.xg - Math.max(...root.filter(k => k !== 'xg').map(k => G.rankFix[k])), Q]));"])
        r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        err, missing, ents, xgap, q = json.loads(r.stdout)
        self.assertIsNone(err)
        self.assertEqual(missing, [])
        self.assertTrue(ents and all(x == 0 for x in ents))   # entries on top
        self.assertEqual(xgap, 1)                              # External box below every module
        self.assertEqual(q["boxHits"], 0)

    def test_self_map_crossings(self):
        # Deterministic: unlimited routing budget, same steps as archMmd (archSrc -> mmdParse -> mmdLayout -> mmdQuality).
        from tests.test_structure_mermaid_js import PRE as MPRE, FNS as MFNS
        ROUTER = _read(os.path.join(os.path.dirname(_SRC_P), "81g0-structure-grid-router.js"))
        mods = [{"id": m, "name": n, "kind": "external" if m.startswith("ext.") else "module"} for m, n in SELF_MODS]
        edges = [{"from": f, "to": t, "ok": bool(ok), "est": bool(est)} for f, t, ok, est in SELF_EDGES]
        js = "\n".join([MPRE, "const MMD_BUDGET = 1e9, MMD_UNCROSS = 1e9, ARCH_DIR = 'TB';", ROUTER] + [js_fn(f) for f in MFNS]
                       + [js_fn(n) for n in ("archIsTest", "archMq", "archPairs", "archReduce", "archSrc", "archRanks")]
                       + ["const M = " + json.dumps(mods) + ", E = " + json.dumps(edges) + ";",
                          "const q = (full, fix) => { const g = mmdParse(archSrc(M, E, false, '', full)), top = k => g.nodes[k] && g.nodes[k].sg ? g.nodes[k].sg : k;",
                          " if(fix) g.rankFix = archRanks(g.nlist.filter(k => !g.nodes[k].sg).concat(g.slist), g.edges.map(e => ({from: top(e.from), to: top(e.to)})));",
                          " return mmdQuality(g, mmdLayout(g)); };",
                          "process.stdout.write(JSON.stringify([q(false), q(true), q(false, 1)]));"])
        r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        red, full, fixed = json.loads(r.stdout)
        self.assertEqual(red["boxHits"], 0)
        self.assertLessEqual(red["crossings"], 5)
        self.assertEqual(fixed["boxHits"], 0)            # overview as drawn: fixed ranks (archMmd)
        self.assertLessEqual(fixed["crossings"], 5)      # ★2 at the time of writing; sink pinning made it 6
        self.assertGreaterEqual(full["crossings"], 80)   # ★109 -> 2 at the time of writing


PAN = re.search(r"^const ARCH_PAN_PX = .*?^document\.addEventListener\('click'.*?$", _SRC, re.S | re.M).group(0)
# Fake DOM: document listeners (capture first), a scroller map, a background target and a module target.
PAN_PRE = """
const L = {}, SEL = []; let strMode = 'arch';
globalThis.document = { addEventListener(t, f, c){ (L[t] = L[t] || []).push([f, !!c]); },
  removeEventListener(t, f){ L[t] = (L[t] || []).filter(x => x[0] !== f); }, querySelector(){ return null; } };
globalThis.setTimeout = f => f();
function softErr(){}
const fire = (t, ev) => { ev.stopPropagation = () => { ev.stopped = true; }; ev.preventDefault = () => {};
  for(const [f] of (L[t] || []).filter(x => x[1]).concat((L[t] || []).filter(x => !x[1]))){ if(ev.stopped) break; f(ev); } return ev; };
const map = { scrollLeft: 100, scrollTop: 50, cls: new Set(), classList: null, setPointerCapture(){} };
map.classList = { add: c => map.cls.add(c), remove: c => map.cls.delete(c) };
const bg = { closest: s => s === '.archtab .archmap' ? map : null };
const mod = { closest: s => s.indexOf('[data-p]') >= 0 ? mod : s === '.archtab .archmap' ? map : null };
document.addEventListener('click', ev => { if(ev.target === mod) SEL.push('mod'); });   // stands in for the selection handler
const drag = (t, dx, dy) => { fire('pointerdown', { button: 0, target: t, clientX: 10, clientY: 10, pointerId: 1 });
  fire('pointermove', { buttons: 1, clientX: 10 + dx, clientY: 10 + dy }); fire('pointerup', {}); fire('click', { target: t }); };
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchPan(unittest.TestCase):
    def run_pan(self, body):
        js = PAN_PRE + js_fn("dragTrack") + "\n" + PAN + "\n" + body
        r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        return json.loads(r.stdout)

    def test_drag_pans_and_swallows_click(self):
        r = self.run_pan("drag(bg, -30, -20); process.stdout.write(JSON.stringify([map.scrollLeft, map.scrollTop, SEL, [...map.cls]]));")
        self.assertEqual(r, [130, 70, [], []])

    def test_small_move_is_a_click(self):
        r = self.run_pan("drag(bg, 2, 3); const a = [map.scrollLeft, map.scrollTop]; drag(mod, 30, 30);"
                         "process.stdout.write(JSON.stringify([a, map.scrollLeft, SEL]));")
        self.assertEqual(r, [[100, 50], 100, ["mod"]])   # a module never starts a pan; its click still selects

    def test_after_pan_next_click_selects(self):
        r = self.run_pan("drag(bg, 40, 0); fire('click', { target: mod }); process.stdout.write(JSON.stringify([map.scrollLeft, SEL]));")
        self.assertEqual(r, [60, ["mod"]])


if __name__ == "__main__":
    unittest.main()
