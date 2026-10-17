"""74c timeline pipeline strip/bands: run stacking (<=3 live, «+N», «+N done» fold), outcome icons, fin, bands, loop ticks, escaping."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_switch
from tests._load import js_fn, js_all
from tests._node import node_e


def _const(name):
    return re.search(r"^const " + name + r" = .*$", js_all(), re.M).group(0)


def _LEG():
    return re.search(r"^const TLPL_LEGEND = [\s\S]*?\]\];$", js_all(), re.M).group(0)   # spans two lines


HEAD_KO = "let LANG = 'ko';\n" + i18n_switch()   # real dictionaries (T/KE/U/TV follow LANG)
PRE = "\n".join([
    HEAD_KO,
    "const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\"/g, '&quot;');",
    "const sid8 = s => String(s).slice(0, 8); let plgShow = t => t; const plgFam = t => 'impl'; const ago = s => Math.floor(s / 60) + '분'; const AGO = t => t + ' 전';",
    "const plWhy = v => ''; const plAgLab = a => ''; const plEvRows = p => []; let plEvLine = (r, L) => ''; const plEvCommits = p => [{h: 'abc1234', ct: 1}];",
    "let LOADS = []; const plLoad = p => LOADS.push(p); const PLS = { data: {} };",
    "const PL_OUTCOME = { run: '진행 중', done: '완료', skip: '건너뜀', back: '되돌림', fail: '실패', hold: '멈춤' };",
    "const plOc = st => T(PL_OUTCOME[st], 'stage');",
])


def _run(sess, expr, feats=None, g=None, pls=None, attn=None):
    g = g or {"cwd": "/p", "items": [{"sid": "s1"}]}
    src = "\n".join([PRE, "const FEATS = " + json.dumps(feats or {}) + ";", "const SESS = " + json.dumps(sess) + ";",
                     "const ATTN = " + json.dumps(attn) + ";",
                     _const("PL_OS"), _const("TLPL_REQ"), _const("TLPL_ICON"), _const("TLPL_EXP"), _const("TLPL_MAX"), "let TLPL_FO = '';",
                     js_fn("plTk"), js_fn("plPrLive"), js_fn("plPrLt"), js_fn("plAgLabs"), js_fn("plPsOk"), js_fn("tlPlRun"), js_fn("tlPlOne"), js_fn("tlPlLine"), js_fn("tlPlEnd"), js_fn("tlPlExp"), js_fn("tlPlOc"), js_fn("tlPlCur"), js_fn("tlPlSt"), js_fn("tlPlRowCls"),
                     js_fn("plStepper"), _LEG(), js_fn("tlPlLegend"), js_fn("tlPlLegendFor"), js_fn("tlPlStrip"), _const("TLPL_WMAX"), js_fn("tlPlWork"), js_fn("tlPlBands"), js_fn("tlPlLoad"), js_fn("tlPlEvSig"), js_fn("tlPlEvWatch"),
                     _const("TLPL_EVW"), _const("TLPL_RECENT_S"), _const("TLPL_STALL_S"), _const("TLPL_HK"), js_fn("tlPlHead"), js_fn("tlPlHeadHtml"), js_fn("tlPlHeadBtn"), js_fn("tlPlOffNote"), "let TLPL_HS = [];", "const PLEV = {}; let PAINTS = 0; const tlPlRepaint = () => PAINTS++;",
                     "const g = " + json.dumps(g) + ";",
                     "const L = { t0: 1000, now: 3000, pct: v => (v - 1000) / 20 };",
                     "PLS.data = " + json.dumps(pls or {}) + ";",
                     "const pl = tlPlRun(g, L);",
                     "console.log(JSON.stringify(" + expr + "));"])
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def _pr(name, t1, end=0, stages=None):
    return {"name": name, "proj": "/p", "t0": 1100, "t1": t1, "end": end, "stages": stages or {}}


OPEN = _pr("open", 1500, 0, {"설계": {"o": "done", "t0": 1100, "t1": 1300}, "구현": {"o": "run", "t0": 1300, "t1": 1500}})
ENDED = _pr("ended", 2500, 2500, {"설계": {"o": "done", "t0": 1200, "t1": 1400}, "검증": {"o": "run", "t0": 1400, "t1": 2500}})
OLD = _pr("old", 900, 900, {"설계": {"o": "done", "t0": 800, "t1": 900}})


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TlPlRun(unittest.TestCase):
    def test_open_beats_ended(self):
        self.assertEqual(_run([{"sid": "s1", "plrun": [ENDED, OPEN]}], "[pl.runs[0].name, pl.runs[0].fin, pl.ended.map(r => r.name)]"), ["open", False, ["ended"]])

    def test_ended_only_inside_window(self):
        self.assertEqual(_run([{"sid": "s1", "plrun": [ENDED, OLD]}], "[pl.runs.map(r => r.name), pl.ended]"), [["ended"], []])
        self.assertIsNone(_run([{"sid": "s1", "plrun": [OLD]}], "pl"))

    def test_no_plrun_empty(self):
        self.assertEqual(_run([{"sid": "s1"}], "[tlPlStrip(pl), tlPlBands(pl, L)]"), ["", ""])
        self.assertEqual(_run([{"sid": "other", "plrun": [OPEN]}], "tlPlStrip(pl)"), "")

    def test_feature_off(self):
        self.assertEqual(_run([{"sid": "s1", "plrun": [OPEN]}], "tlPlStrip(pl)", feats={"pipeline": False}), "")

    def test_icons_and_fin(self):
        h = _run([{"sid": "s1", "plrun": [OPEN]}], "tlPlStrip(pl)")
        self.assertIn('class="tlpl tlpl-run"', h)
        self.assertIn('class="tlpls pl-done p pf-impl" title="설계 · 완료"><i class=tlpd aria-hidden=true></i>', h)   # segment; title = stage + state
        self.assertIn('pl-run cur pf-impl"', h)
        self.assertNotIn("◉", h)   # glyphs are no longer drawn
        self.assertIn("<i class=tlpc><strong>구현</strong> · 28분</i>", h)   # current stage + elapsed (3000-1300 s)
        self.assertIn('id="tlpl-s1-open"', h)
        e = _run([{"sid": "s1", "plrun": [ENDED]}], "tlPlStrip(pl)")
        self.assertIn('class="tlpl tlpl-fin fin"', e)
        self.assertNotIn("pl-run", e)   # an ended run's open stage shows its outcome
        st = {t: {"o": o, "t0": 1100 + i, "t1": 1200 + i} for i, (t, o) in enumerate(
            [("a", "skip"), ("b", "back"), ("c", "fail"), ("d", "hold"), ("e", "run")])}
        h2 = _run([{"sid": "s1", "plrun": [_pr("x", 1500, 0, st)]}], "tlPlStrip(pl)")
        for cls in ("skip", "back", "fail", "hold"):
            self.assertIn('pl-' + cls + ' p pf-impl"', h2)   # all before the running stage e
        self.assertIn('class="tlpl tlpl-fail"', h2)   # a failed stage colours the whole run

    def test_row_accent_class(self):
        self.assertEqual(_run([{"sid": "s1", "plrun": [OPEN]}], "tlPlRowCls(pl)"), " tlrpl tlrpl-run")
        self.assertEqual(_run([{"sid": "s1", "plrun": [ENDED]}], "tlPlRowCls(pl)"), " tlrpl tlrpl-fin")
        st = {"a": {"o": "fail", "t0": 1100, "t1": 1200}}
        self.assertEqual(_run([{"sid": "s1", "plrun": [_pr("x", 1500, 1500, st)]}], "tlPlRowCls(pl)"), " tlrpl tlrpl-fail")
        self.assertEqual(_run([{"sid": "s1"}], "tlPlRowCls(pl)"), "")

    def test_ended_run_reads_done(self):
        e = _run([{"sid": "s1", "plrun": [ENDED]}], "tlPlStrip(pl)")
        self.assertIn('<i class="tlpc tlpe tlpe-ok"><strong><i aria-hidden=true>✓</i> 완료</strong> · 검증 · 8분 전</i>', e)   # 3000-2500 s
        self.assertNotIn("pl-run", e)
        self.assertNotIn("tlpl-run", e)
        st = {"a": {"o": "fail", "t0": 1100, "t1": 1200}}
        f = _run([{"sid": "s1", "plrun": [_pr("x", 1500, 1500, st)]}], "tlPlStrip(pl)")
        self.assertIn('tlpe-fail"><strong><i aria-hidden=true>✕</i> 실패</strong>', f)
        st = {"a": {"o": "done", "t0": 1100, "t1": 1200}, "b": {"o": "hold", "t0": 1200, "t1": 1300}}
        s = _run([{"sid": "s1", "plrun": [_pr("x", 1500, 1500, st)]}], "tlPlStrip(pl)")
        self.assertIn('tlpe-stop"><strong><i aria-hidden=true>⏸</i> 중단</strong> · b', s)

    def test_run_ended_early_reads_stopped(self):
        pls = {"/p": {"pipelines": [{"name": "ended", "stages": [{"title": "설계"}, {"title": "검증"}, {"title": "리뷰"}]}]}}
        e = _run([{"sid": "s1", "plrun": [ENDED]}], "tlPlStrip(pl)", pls=pls)
        self.assertIn('tlpe-stop"><strong><i aria-hidden=true>⏸</i> 중단</strong> · 검증 · 8분 전', e)   # 리뷰 never reached
        self.assertNotIn("tlpe-ok", e)

    def test_looped_run_reaching_last_stage_is_done(self):
        oc = [("a", "skip"), ("b", "skip"), ("c", "done"), ("d", "back"), ("e", "done"), ("f", "done"), ("g", "run")]
        st = {t: {"o": o, "t0": 1100 + i * 10, "t1": 1105 + i * 10} for i, (t, o) in enumerate(oc)}
        pls = {"/p": {"pipelines": [{"name": "x", "stages": [{"title": t} for t, _ in oc]}]}}
        h = _run([{"sid": "s1", "plrun": [_pr("x", 1500, 1500, st)]}], "tlPlStrip(pl)", pls=pls)
        self.assertIn('tlpe-ok"><strong><i aria-hidden=true>✓</i> 완료</strong> · g', h)   # cut last stage + earlier back

    def test_parallel_running_stages_both_named(self):
        st = {"설계": {"o": "done", "t0": 1100, "t1": 1200}, "구현": {"o": "run", "t0": 1200, "t1": 1500},
              "검증": {"o": "run", "t0": 1800, "t1": 2500}, "리뷰": {"o": "wait"}}
        h = _run([{"sid": "s1", "plrun": [_pr("x", 2500, 0, st)]}], "tlPlStrip(pl)")
        self.assertIn("<i class=tlpc><strong>구현 · 검증</strong> · 30분</i>", h)   # longest elapsed: 3000-1200 s
        self.assertEqual(h.count(" pl-run "), 2)
        self.assertIn('pl-run cur pf-impl"', h)   # cur stays on the first running stage
        for t in ("설계", "구현", "검증"):
            self.assertIn("<i class=tlpn>" + t + "</i>", h)   # name under each segment

    def test_stage_names_en(self):
        h = _run([{"sid": "s1", "plrun": [OPEN]}], "(plgShow = t => ({설계: 'Design', 구현: 'Build'})[t] || t, tlPlStrip(pl))")
        self.assertIn("<i class=tlpn>Design</i>", h)
        self.assertIn("<i class=tlpn>Build</i>", h)
        self.assertIn("<strong>Build</strong>", h)

    def test_drop_order_and_nine_stages_fit_260(self):
        sts = ["done", "done", "done", "skip", "back", "run", "wait", "wait", "wait"]
        names = ["설계", "테스트 작성", "구현", "정적 분석", "검증", "리뷰", "보안 점검", "재검증", "라이브 검증"]
        src = "\n".join([js_fn("tlPlDrop"), js_fn("tlPlFit"), """
const sts = %s, names = %s, W = n => Math.max(22, [...n].length * 12 + 3);
// Fake layout: a named segment is its name width (long names floor at 2 chars + «…» = 3em+3px), .nn = 22px, gap 2px.
const segs = sts.map((st, i) => { const c = new Set(); return { className: 'tlpls pl-' + st, classList: { add: x => c.add(x), remove: x => c.delete(x) }, c, i }; });
const w = s => s.c.has('nn') ? 22 : sts[s.i] === 'run' || [...names[s.i]].length <= 2 ? W(names[s.i]) : 39;
const el = { children: segs, clientWidth: 260, get scrollWidth(){ return segs.reduce((m, s) => m + w(s), 0) + 2 * (segs.length - 1); } };
tlPlFit(el);
console.log(JSON.stringify({ order: tlPlDrop(sts), nn: segs.filter(s => s.c.has('nn')).map(s => s.i), sw: el.scrollWidth, n: segs.length }));
""" % (json.dumps(sts), json.dumps(names))])
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        r = json.loads(r.stdout)
        self.assertEqual(r["order"], [0, 1, 2, 3, 4, 8, 7, 6])   # done/skip farthest first, then back, then waiting farthest first
        self.assertLessEqual(r["sw"], 260)   # all 9 segments inside the cell
        self.assertEqual(r["n"], 9)
        self.assertNotIn(5, r["nn"])   # the running stage keeps its name

    def test_live_run_has_no_end_label(self):
        h = _run([{"sid": "s1", "plrun": [OPEN]}], "tlPlStrip(pl)")
        self.assertNotIn("tlpe", h)
        self.assertIn("<i class=tlpc><strong>구현</strong> · 28분</i>", h)

    def test_end_label_en(self):
        src = "\n".join([js_fn("tlPlEnd"), "const LANG = 'en'; const T = s => s; const KE = (k, e) => e;",
                         "const esc = s => s; const plgShow = t => t; const ago = s => '3m'; const AGO = t => t + ' ago';",
                         "const tlPlSt = r => 'fin';",
                         "console.log(JSON.stringify(tlPlEnd({ pr: { end: 100 }, titles: ['a'], lt: { a: { st: 'done' } }, now: 280 }, '')));"])
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        self.assertEqual(json.loads(r.stdout), '<i class="tlpc tlpe tlpe-ok"><strong><i aria-hidden=true>✓</i> Done</strong> · 3m ago</i>')

    def test_more_chip(self):
        o2 = dict(OPEN, name="open2", t1=1400)
        h = _run([{"sid": "s1", "plrun": [OPEN, o2]}], "tlPlStrip(pl)")
        self.assertEqual(h.count('<div class="tlpl '), 2)   # two live runs: one line each, no «+N»
        self.assertNotIn("tlplm", h)

    def test_name_label_only_when_stacked(self):
        o2 = dict(OPEN, name="<o2>", t1=1400)
        h = _run([{"sid": "s1", "plrun": [OPEN, o2]}], "tlPlStrip(pl)")
        self.assertEqual(re.findall(r"<i class=tlpnm>([^<]*)</i>", h), ["open", "&lt;o2&gt;"])   # escaped, one per line
        self.assertNotIn("tlpnm", _run([{"sid": "s1", "plrun": [OPEN]}], "tlPlStrip(pl)"))
        self.assertNotIn("tlpnm", _run([{"sid": "s1", "plrun": [OPEN, ENDED]}], "tlPlStrip(pl)"))   # ended folded: one line
        e = _run([{"sid": "s1", "plrun": [OPEN, ENDED]}], "(TLPL_EXP.add('s1'), tlPlStrip(pl))")
        self.assertEqual(re.findall(r"<i class=tlpnm>([^<]*)</i>", e), ["open", "ended"])
        top = h.split('<div class="tlpl ')[1]
        self.assertLess(top.index("tlpnm"), top.index("tlpst"))   # name heads its own run's line

    def test_stack_three_live_fold_rest(self):
        lv = [dict(OPEN, name="L%d" % i, t1=1500 - i * 10) for i in range(4)]
        sess = [{"sid": "s1", "plrun": lv + [ENDED]}]
        r = _run(sess, "[pl.runs.map(r => r.name), pl.more, pl.ended.map(r => r.name), tlPlStrip(pl)]")
        self.assertEqual(r[:3], [["L0", "L1", "L2"], 1, ["ended"]])
        h = r[3]
        self.assertEqual(h.count('<div class="tlpl '), 3)
        self.assertEqual(h.count(">+1</i>"), 1)
        self.assertIn('data-tlplx="s1" aria-expanded=false>+1 완료</button>', h)
        self.assertNotIn('data-tlpln="ended"', h)
        e = _run(sess, "(tlPlExp('s1'), [TLPL_EXP.has('s1'), PAINTS, tlPlStrip(pl)])")
        self.assertEqual(e[:2], [True, 1])
        self.assertIn('data-tlpln="ended"', e[2])
        self.assertIn('aria-expanded=true>접기</button>', e[2])
        self.assertEqual(_run(sess, "(tlPlExp('s1'), tlPlExp('s1'), TLPL_EXP.size)"), 0)

    def test_chip_never_scrolls(self):
        src = js_fn("tlPlExp") + js_fn("tlPlWire")
        self.assertNotIn("scrollIntoView", src)
        self.assertEqual(src.count(".focus("), src.count(".focus({ preventScroll: true })"))

    def test_row_status_priority(self):
        fail = _pr("f", 2000, 2000, {"a": {"o": "fail", "t0": 1100, "t1": 1200}})
        self.assertEqual(_run([{"sid": "s1", "plrun": [OPEN, fail]}], "pl.st"), "fail")          # ended fail in window wins
        self.assertEqual(_run([{"sid": "s1", "plrun": [OPEN, dict(fail, t1=900, end=900)]}], "pl.st"), "run")   # outside window
        self.assertEqual(_run([{"sid": "s1", "plrun": [OPEN, ENDED]}], "pl.st"), "run")
        self.assertEqual(_run([{"sid": "s1", "plrun": [ENDED]}], "pl.st"), "fin")

    def test_ended_run_never_animated(self):
        h = _run([{"sid": "s1", "plrun": [OPEN, ENDED]}], "(TLPL_EXP.add('s1'), tlPlStrip(pl))")
        lines = h.split('<div class="tlpl ')[1:]
        live, done = [x for x in lines if 'data-tlpln="open"' in x], [x for x in lines if 'data-tlpln="ended"' in x]
        self.assertIn('<i class="tlpst">', live[0])
        self.assertIn('<i class="tlpst fin">', done[0])
        self.assertNotIn("pl-run", done[0])
        import os
        css = open(os.path.join(os.path.dirname(__file__), "..", "web", "css", "21-timeline-plrun.css"), encoding="utf-8").read()
        anim = [ln.split("{")[0] for ln in css.splitlines() if "animation:tlplstripe" in ln]
        self.assertEqual(anim, [".tlpst:not(.fin) > .tlpls.pl-run .tlpd::before"])   # stripes move only on a live stepper
        self.assertIn("@media (prefers-reduced-motion:reduce){.tlpst:not(.fin) > .tlpls.pl-run .tlpd::before{animation:none}}", css)

    def test_gate_line_inside_top_run(self):
        o2 = dict(OPEN, name="open2", t1=1400)
        h = _run([{"sid": "s1", "plrun": [OPEN, o2]}], "(plEvLine = () => '<div class=plev>G</div>', tlPlStrip(pl))")
        lines = h.split('<div class="tlpl ')[1:]
        self.assertEqual(h.count("<div class=plev>G</div>"), 1)
        self.assertTrue(lines[0].endswith("<div class=plev>G</div></div>"))   # inside the first run's line, after its counter

    def test_run_line_is_block_under_name(self):
        import os
        css = open(os.path.join(os.path.dirname(__file__), "..", "web", "css", "21-timeline-plrun.css"), encoding="utf-8").read()
        rule = re.search(r"^\.tlnm > \.tlpl\{([^}]*)\}", css, re.M).group(1)
        self.assertIn("flex:0 0 100%", rule)   # every run takes a full line under the name — no inline placement
        self.assertIn(".tlnm:has(> .tlpl){flex-wrap:wrap", css)
        self.assertNotIn(".tlpl ~ .tlpl", css)   # no first-run-inline special case

    def test_band_geometry(self):
        b = _run([{"sid": "s1", "plrun": [ENDED]}], "tlPlBands(pl, L)")
        self.assertIn('left:10.00%;width:10.00%', b)    # 설계 1200..1400
        self.assertIn('left:20.00%;width:55.00%', b)    # 검증 1400..2500
        self.assertNotIn("tlplk", b)
        self.assertIn("단계 18분 중 작업 0분", b)   # work vs span in the tooltip; no its -> no work
        self.assertNotIn("tlplw", b)

    def test_work_pieces_merge_and_clip(self):
        st = {"검증": {"o": "done", "t0": 1400, "t1": 2200, "ag": [{"t0": 1500, "t1": 1600}, {"t0": 1595, "t1": 1700}]}}
        its = [{"segs": [[1300, 1450], [1705, 1710], [1800, 1900], [2100, 2400]]}]
        b = _run([{"sid": "s1", "plrun": [_pr("x", 2200, 2200, st)]}], "tlPlBands(pl, L, %s)" % json.dumps(its))
        # band 20%..60%; work 1400-1450 | 1500-1710 (ag union 1500-1700 + seg 5 s later = 0.25% gap, merged) | 1800-1900 | 2100-2200
        self.assertEqual(re.findall(r'class=tlplw style="left:([\d.]+)%;width:([\d.]+)%"', b),
                         [("0.00", "6.25"), ("12.50", "26.25"), ("50.00", "12.50"), ("87.50", "12.50")])
        self.assertIn("단계 13분 중 작업 7분", b)   # 455 s of 800 s
        self.assertLess(b.index("tlplw"), b.index("</div>"))   # pieces sit inside the band

    def test_work_piece_cap(self):
        its = [{"segs": [[1100 + i * 20, 1105 + i * 20] for i in range(60)]}]
        st = {"a": {"o": "done", "t0": 1100, "t1": 2300}}
        b = _run([{"sid": "s1", "plrun": [_pr("x", 2300, 2300, st)]}], "tlPlBands(pl, L, %s)" % json.dumps(its))
        self.assertEqual(b.count("class=tlplw"), 40)
        self.assertEqual(_run([], "tlPlWork([], [], 0, 10, v => v).pc"), [])

    def test_work_tooltip_en(self):
        src = "\n".join([PRE.replace(HEAD_KO, "let LANG = 'en';\n" + i18n_switch()).replace("+ '분'", "+ 'm'"),
                         "const tlPlOc = s => s;", _const("TLPL_WMAX"), js_fn("plTk"), js_fn("tlPlWork"), js_fn("tlPlBands"),
                         "const S = {a: {t0: 1000, t1: 3400, k: 2, p0: 2000, ag: [{t0: 1000, t1: 1720}]}};",
                         "const row = {runs: [{name: 'x', titles: ['a'], lt: {a: {st: 'done'}}, pr: {stages: S}}]};",
                         "console.log(JSON.stringify(tlPlBands(row, {t0: 0, now: 5000, pct: v => v / 50})));"])
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        h = json.loads(r.stdout)
        self.assertIn("work 12m of 40m", h)
        self.assertIn("↺ pass 2", h)

    def test_loop_tick_only_when_k2(self):
        st = {"구현": {"o": "done", "t0": 1100, "t1": 1800, "p0": 1600, "k": 2, "from": {"검증": 1}}}
        b = _run([{"sid": "s1", "plrun": [_pr("x", 1800, 1800, st)]}], "tlPlBands(pl, L)")
        self.assertIn('class="tlplk pf-impl" style="left:30.00%"', b)
        self.assertIn("↺ 검증에서 1 · 2번째", b)
        st["구현"]["k"] = 1
        b1 = _run([{"sid": "s1", "plrun": [_pr("x", 1800, 1800, st)]}], "tlPlBands(pl, L)")
        self.assertNotIn("tlplk", b1)

    def test_title_escaped(self):
        st = {"<img>": {"o": "done", "t0": 1100, "t1": 1200}}
        h = _run([{"sid": "s1", "plrun": [_pr("x", 1500, 1500, st)]}], "tlPlStrip(pl) + tlPlBands(pl, L)")
        self.assertIn("&lt;img&gt;", h)
        self.assertNotIn("<img>", h)

    def test_stage_order(self):
        sess = [{"sid": "s1", "plrun": [OPEN]}]
        self.assertEqual(_run(sess, "[pl.runs[0].titles, LOADS]"), [["설계", "구현"], ["/p"]])   # by start; list requested once
        pls = {"/p": {"pipelines": [{"name": "open", "stages": [{"title": "구현"}, {"title": "설계"}, {"title": "리뷰"}]}]}}
        self.assertEqual(_run(sess, "[pl.runs[0].titles, LOADS]", pls=pls), [["구현", "설계", "리뷰"], []])

    def test_stage_order_live_verify_shape(self):
        # Unrun leading file stage stays first; a stage the file lacks is appended, not dropped; no t0 sorts last.
        st = {"트리아지": {"o": "skip", "t0": 1400, "t1": 1400}, "라이브 검증": {"o": "run", "t0": 1100, "t1": 1500},
              "옛 단계": {"o": "done", "t0": 1050, "t1": 1060}}
        sess = [{"sid": "s1", "plrun": [_pr("live-verify", 1500, 0, st)]}]
        pls = {"/p": {"pipelines": [{"name": "live-verify", "stages": [{"title": "배포 확인"}, {"title": "라이브 검증"}, {"title": "트리아지"}]}]}}
        self.assertEqual(_run(sess, "pl.runs[0].titles", pls=pls), ["배포 확인", "라이브 검증", "트리아지", "옛 단계"])
        st2 = {"b": {"o": "done"}, "a": {"o": "done", "t0": 1200, "t1": 1300}, "c": {"o": "run", "t0": 1100, "t1": 1500}}
        sess2 = [{"sid": "s1", "plrun": [_pr("x", 1500, 0, st2)]}]
        self.assertEqual(_run(sess2, "pl.runs[0].titles"), ["c", "a", "b"])
        self.assertEqual(_run(sess2, "pl.runs[0].titles", pls={"/p": {"ok": False}}), ["c", "a", "b"])


def _async(body, sess=None):
    """Repaint triggers: stubs for plLoad/PLEV/paintTl, timers real (no clock reads in the asserted logic)."""
    src = "\n".join(["let PAINTS = 0; const paintTl = () => PAINTS++; const TLPL_REQ = new Set(); const PLS = { data: {}, busy: {} };",
                     "const SESS = " + json.dumps(sess or []) + "; let TLPL_SIG = '';", js_fn("tlPlSig"), js_fn("tlPlSync"),
                     "let LOADRES; const plLoad = p => new Promise(r => { LOADRES = r; }); const PLEV = {};",
                     js_fn("tlPlRepaint").replace("function", "let TLPL_RP = 0; function", 1), js_fn("tlPlLoad"),
                     _const("TLPL_EVW"), js_fn("tlPlEvSig"), js_fn("tlPlEvWatch"), body])
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TlPlRepaint(unittest.TestCase):
    def test_stage_list_load_repaints_once(self):
        out = _async("TLPL_REQ.add('/p'); tlPlLoad('/p'); PLS.data['/p'] = {}; LOADRES();"
                     "setTimeout(() => console.log(JSON.stringify([PAINTS, TLPL_REQ.has('/p')])), 200);")
        self.assertEqual(out, [1, True])

    def test_busy_elsewhere_rearms_without_repaint(self):
        out = _async("TLPL_REQ.add('/p'); tlPlLoad('/p'); LOADRES();"
                     "setTimeout(() => console.log(JSON.stringify([PAINTS, TLPL_REQ.has('/p')])), 200);")
        self.assertEqual(out, [0, False])

    def test_evidence_arrival_repaints_once(self):
        out = _async("PLEV['/p'] = { busy: true, rows: [] }; tlPlEvWatch('/p'); tlPlEvWatch('/p');"
                     "setTimeout(() => { PLEV['/p'].rows = [{ ts: 5 }]; PLEV['/p'].busy = false; }, 100);"
                     "setTimeout(() => console.log(JSON.stringify(PAINTS)), 700);")
        self.assertEqual(out, 1)

    def test_plrun_change_repaints_once(self):
        # The first sync repaints (a Timeline painted before the first poll has no lane yet); elapsed-only changes do not.
        out = _async("const r = SESS[0].plrun[0], seen = []; tlPlSync();"
                     "setTimeout(() => { seen.push(PAINTS); r.t1 = 1600; r.stages['구현'].t1 = 1600; tlPlSync(); }, 100);"
                     "setTimeout(() => { seen.push(PAINTS); r.stages['구현'].o = 'done'; r.stages['검증'] = { o: 'run', t0: 1600, t1: 1600 }; tlPlSync(); tlPlSync(); }, 200);"
                     "setTimeout(() => console.log(JSON.stringify(seen.concat(PAINTS))), 400);", sess=[{"sid": "s1", "plrun": [json.loads(json.dumps(OPEN))]}])
        self.assertEqual(out, [1, 1, 2])

    def test_sync_wired_into_poll_marker_update(self):
        self.assertIn("tlPlSync()", js_fn("tlSyncState"))

    def test_unchanged_evidence_no_repaint(self):
        out = _async("PLEV['/p'] = { busy: true, rows: [{ ts: 5 }] }; tlPlEvWatch('/p');"
                     "setTimeout(() => { PLEV['/p'].busy = false; }, 100);"
                     "setTimeout(() => console.log(JSON.stringify(PAINTS)), 700);")
        self.assertEqual(out, 0)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TlPlLegend(unittest.TestCase):
    STATES = ["done", "run", "back", "fail", "wait", "skip"]

    def test_only_with_a_run(self):
        self.assertEqual(_run([{"sid": "s1"}], "tlPlLegendFor([g], L)"), "")
        self.assertEqual(_run([{"sid": "s1", "plrun": [OPEN]}], "tlPlLegendFor([g], L)", feats={"pipeline": False}), "")
        self.assertIn('class=tlplg', _run([{"sid": "s1", "plrun": [OPEN]}], "tlPlLegendFor([{cwd: '/q', items: [{sid: 'x'}]}, g], L)"))

    def test_six_items_same_classes_as_rows(self):
        h = _run([{"sid": "s1", "plrun": [OPEN]}], "tlPlLegendFor([g], L)")
        # Key before the «Runs N» chip: the chip ends the header so it stays pinned right instead of floating mid-header.
        self.assertLess(h.index("<div class=tlplg>"), h.index('class="tlplhb '))
        h = h[h.index("<div class=tlplg>"):h.index('class="tlplhb ')]
        self.assertIn('<i class="tlpst tlplgs">', h)   # live stepper root: running swatch animates, no .fin
        cls = re.findall(r'class="tlpls ([^"]*)"', h)
        self.assertEqual(cls, ["pl-" + s for s in self.STATES])
        self.assertEqual(h.count("<i class=tlpd aria-hidden=true></i>"), 6)
        self.assertEqual(re.findall(r"<i class=tlpn>([^<]*)</i>", h), ["완료", "진행 중", "되돌림", "실패", "대기", "건너뜀"])   # Korean UI, real dictionaries
        self.assertIn('title="되돌림: 이 단계에서 앞 단계로 되돌려 보냄"', h)   # server marks the later stage that sent work back

    def test_en_labels(self):
        src = "\n".join([PRE.replace(HEAD_KO, "let LANG = 'en';\n" + i18n_switch()),
                         _const("TLPL_ICON"), _LEG(), js_fn("plStepper"), js_fn("tlPlLegend"),
                         "console.log(JSON.stringify(tlPlLegend()));"])
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        h = json.loads(r.stdout)
        self.assertEqual(re.findall(r"<i class=tlpn>([^<]*)</i>", h), ["Done", "Running", "Sent back", "Failed", "Waiting", "Skipped"])
        self.assertIn(">Pipeline</i>", h)
        self.assertIn('title="Sent back: this stage sent the run back to an earlier stage"', h)
        self.assertNotRegex(h, r"[\uac00-\ud7a3]")   # no Korean left in en


class TlPlCss(unittest.TestCase):
    """Repo CSS only: states differ by shape, not hue alone (WCAG 1.4.1); waiting keeps the 3:1 field token."""
    with open(os.path.join(os.path.dirname(__file__), "..", "web", "css", "21-timeline-plrun.css"), encoding="utf-8") as f:
        CSS = f.read()

    def _rule(self, sel):
        m = re.search(r"(?m)^" + re.escape(sel) + r"\{([^}]*)\}", self.CSS)
        self.assertIsNotNone(m, sel)
        return m.group(1)

    def test_shape_cues(self):
        self.assertIn("--s-clip:polygon(", self._rule(".tlpst > .tlpls.pl-back"))
        self.assertIn("--s-pat:linear-gradient(", self._rule(".tlpst > .tlpls.pl-fail"))
        self.assertIn("--s-bd:inset", self._rule(".tlpst > .tlpls.pl-skip"))
        base = self._rule(".tlpst .tlpd")
        self.assertIn("var(--s-pat,none),var(--s-bg)", base)
        self.assertIn("clip-path:var(--s-clip,none)", base)
        self.assertIn("--b-clip:polygon(", self._rule(".tlrs .tlt .tlplb.pl-back"))
        self.assertIn("--b-h:4px", self._rule(".tlrs .tlt .tlplb.pl-fail"))

    def test_wait_uses_field_token(self):
        self.assertIn("--tlpl-wait:var(--nx-field", self._rule(".tlpst"))
        self.assertNotIn("--tlpl-wait", self._rule("html[data-theme=light] .tlpst"))


def _st(o, t0, t1=None, **kw):
    return dict({"o": o, "t0": t0, "t1": t1 or t0}, **kw)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TlPlHead(unittest.TestCase):
    """Run summary chips at the timeline head (tlPlHead / tlPlHeadHtml)."""

    def _ks(self, sess, now=3000, attn=None):
        return _run(sess, "tlPlHead(SESS, ATTN, %d).map(h => [h.name, h.k, h.why])" % now, attn=attn)

    def test_empty_and_old_ended_dropped(self):
        self.assertEqual(_run([{"sid": "s1"}], "[tlPlHead(SESS, null, 3000), tlPlHeadHtml([])]"), [[], ""])
        self.assertEqual(_run([{"sid": "s1", "plrun": [ENDED]}], "tlPlHead(SESS, null, 3101).length"), 0)   # 601 s after end
        self.assertEqual(self._ks([{"sid": "s1", "plrun": [ENDED]}], now=3100), [["ended", "ok", ""]])
        self.assertEqual(_run([{"sid": "s1", "plrun": [ENDED]}], "tlPlLegendFor([], { now: 3101 })"), "")

    def test_order_and_cap(self):
        fail = _pr("f", 1400, 0, {"a": _st("fail", 1100, 1200), "b": _st("run", 1200)})
        back = _pr("b", 1300, 0, {"a": _st("run", 1100, k=2, p0=1250)})
        runs = [ENDED, OPEN, back, fail, dict(OPEN, name="o2", t1=1200)]
        self.assertEqual([x[:2] for x in self._ks([{"sid": "s1", "plrun": runs}])],
                         [["f", "fail"], ["b", "back"], ["open", "run"], ["o2", "run"], ["ended", "ok"]])
        h = _run([{"sid": "s1", "plrun": runs}], "tlPlHeadHtml(tlPlHead(SESS, null, 3000))")
        self.assertEqual(re.findall(r'data-tlpln="([^"]*)"', h), ["f", "b", "open"])
        self.assertIn(">+2</i>", h)
        self.assertIn("실행 2개 더", h)
        self.assertIn('id="tlplh-s1-f"', h)
        d = _run([{"sid": "s1", "plrun": [OPEN, dict(OPEN, t1=1400)]}], "tlPlHeadHtml(tlPlHead(SESS, null, 3000))")
        self.assertEqual(re.findall(r'id="(tlplh-[^"]*)"', d), ["tlplh-s1-open", "tlplh-s1-open-1"])   # duplicate name: run index
        self.assertIn('class="tlplc tlplc-back"', h)

    def test_stuck_triggers(self):
        quiet = _pr("q", 1500, 0, {"a": _st("run", 1300)})   # stage pass 1900 s old at now=3200
        self.assertEqual(self._ks([{"sid": "s1", "state": "", "ageSec": 1860, "plrun": [quiet]}], now=3200), [["q", "stuck", "31분 동안 기록 없음"]])
        self.assertEqual(self._ks([{"sid": "s1", "state": "wait", "ageSec": 60, "plrun": [quiet]}], now=3200)[0][1:], ["run", ""])   # old stage, session active a minute ago
        self.assertEqual(self._ks([{"sid": "s1", "state": "think", "ageSec": 1860, "plrun": [quiet]}], now=3200)[0][1], "run")
        busy = _pr("q", 1500, 0, {"a": _st("run", 1300, ag=[{"run": 1}])})
        self.assertEqual(self._ks([{"sid": "s1", "ageSec": 1860, "plrun": [busy]}], now=3200)[0][1], "run")
        self.assertEqual(self._ks([{"sid": "s1", "state": "ask", "plrun": [OPEN]}]), [["open", "stuck", "답을 기다리는 중"]])
        self.assertEqual(self._ks([{"sid": "s1", "state": "abort", "plrun": [OPEN]}])[0][1], "stuck")
        attn = {"rows": [{"sid": "s1", "sigs": [{"k": "stall"}]}]}
        self.assertEqual(self._ks([{"sid": "s1", "plrun": [OPEN]}], attn=attn), [["open", "stuck", "서브에이전트 멈춤"]])
        self.assertEqual(self._ks([{"sid": "s1", "plrun": [OPEN]}], attn={"rows": [{"sid": "s2", "sigs": [{"k": "stall"}]}]})[0][1], "run")
        h = _run([{"sid": "s1", "state": "ask", "plrun": [OPEN]}], "tlPlHeadHtml(tlPlHead(SESS, null, 3000))")
        self.assertIn("<strong class=tlplcw>멈춤</strong>", h)
        self.assertIn("답을 기다리는 중", re.search(r'title="([^"]*)"', h).group(1))   # reason in the tooltip

    def test_back_and_fail_beat_stuck(self):
        back = _pr("b", 1500, 0, {"a": _st("run", 1300, via="c")})
        self.assertEqual(self._ks([{"sid": "s1", "state": "ask", "plrun": [back]}])[0][1:], ["back", ""])
        fail = _pr("f", 1500, 0, {"x": _st("fail", 1100, 1200), "a": _st("run", 1300)})
        self.assertEqual(self._ks([{"sid": "s1", "state": "ask", "plrun": [fail]}])[0][1], "fail")

    def test_ended_and_fail_chips_carry_evidence_with_commits(self):
        stub = "(plEvLine = (r, L, c) => '<div class=plev>' + (L ? L.st : '-') + JSON.stringify(c) + '</div>', %s)"
        h = _run([{"sid": "s1", "plrun": [OPEN, ENDED]}], stub % "tlPlHeadHtml(tlPlHead(SESS, null, 3000))")
        chips = h.split('<div class="tlplc ')[1:]
        self.assertNotIn("plev", chips[0])   # open, not failing: no evidence
        self.assertIn('<div class=plev>done[{"h":"abc1234","ct":1}]</div>', chips[1])
        self.assertIn("tlpe-ok", chips[1])
        self.assertIn('<i class="tlpst fin">', chips[1])
        fail = _pr("f", 1500, 0, {"x": _st("fail", 1100, 1200), "a": _st("run", 1300)})
        self.assertIn("abc1234", _run([{"sid": "s1", "plrun": [fail]}], stub % "tlPlHeadHtml(tlPlHead(SESS, null, 3000))"))
        # Row strip gate line passes the commits too.
        self.assertIn('[{"h":"abc1234","ct":1}]', _run([{"sid": "s1", "plrun": [OPEN]}], stub % "tlPlStrip(pl)"))

    def test_escaped_and_metadata_only(self):
        st = {"<img>": _st("run", 1300, ag=[{"lab": "SECRETLAB", "desc": "SECRETDESC", "aid": "SECRETAID", "run": 1}])}
        h = _run([{"sid": "s1", "plrun": [_pr("<x>", 1500, 0, st)]}], "tlPlHeadHtml(tlPlHead(SESS, null, 3000))")
        self.assertIn("&lt;x&gt;", h)
        self.assertIn("&lt;img&gt;", h)
        self.assertNotIn("<img>", h)
        self.assertNotIn("<x>", h)
        for w in ("SECRETLAB", "SECRETDESC", "SECRETAID"):
            self.assertNotIn(w, h)

    def test_feature_off_and_wire(self):
        self.assertEqual(_run([{"sid": "s1", "plrun": [OPEN]}], "tlPlHead(SESS, null, 3000)", feats={"pipeline": False}), [])
        self.assertIn(".tlplc[data-tlpln]", js_fn("tlPlWire"))


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TlPlHeadChip(unittest.TestCase):
    """R1-R3: one «Runs N» chip in the header, chips in a click popover; R4: «Pipeline recording off» row note."""

    def test_r1_one_chip_coloured_by_worst(self):
        fail = _pr("f", 1400, 0, {"a": _st("fail", 1100, 1200), "b": _st("run", 1200)})
        back = _pr("b", 1300, 0, {"a": _st("run", 1100, k=2, p0=1250)})
        h = _run([{"sid": "s1", "plrun": [OPEN, back, fail]}], "tlPlLegendFor([], L)")
        self.assertIn('class="tlplhb tlplhb-fail"', h)
        self.assertIn(">실행 3</button>", h)
        self.assertNotIn("tlplc", h)   # no always-on run chips in the header
        self.assertIn("tlplhb-back", _run([{"sid": "s1", "plrun": [OPEN, back]}], "tlPlLegendFor([], L)"))
        self.assertIn("tlplhb-stuck", _run([{"sid": "s1", "state": "ask", "plrun": [OPEN]}], "tlPlLegendFor([], L)"))
        self.assertIn("tlplhb-none", _run([{"sid": "s1", "plrun": [OPEN]}], "tlPlLegendFor([], L)"))

    def test_r2_popover_lists_the_chips(self):
        src = js_fn("tlPlHeadToggle") + js_fn("tlPlHeadFill") + js_fn("tlPlHeadClose")
        self.assertIn("tlPlHeadHtml(TLPL_HS)", src)
        self.assertIn("popAnchor(", src)
        self.assertIn("preventScroll: true", src)
        self.assertIn("popReg('tlplhp', '#tlplhp, #tlplhb', tlPlHeadClose)", js_all())   # Esc + outside click (08-ui-kit)
        self.assertIn("tlPlHeadToggle(hb)", js_fn("tlPlWire"))
        self.assertIn("tlPlHeadFill(hp)", js_fn("tlPlWire"))   # an open popover follows repaints

    def test_r3_zero_runs_no_chip(self):
        self.assertEqual(_run([{"sid": "s1"}], "[tlPlLegendFor([], L), tlPlHeadBtn([])]"), ["", ""])

    def test_r4_recording_off_note(self):
        h = _run([{"sid": "s1", "plOff": True}], "tlPlOffNote(g)")
        self.assertIn("<i class=tlploff", h)
        self.assertIn("파이프라인 기록 꺼짐", h)
        self.assertIn("파이프라인 › 적용", h)
        self.assertEqual(_run([{"sid": "s1"}], "tlPlOffNote(g)"), "")
        self.assertEqual(_run([{"sid": "s2", "plOff": True}], "tlPlOffNote(g)"), "")
        self.assertEqual(_run([{"sid": "s1", "plOff": True}], "tlPlOffNote(g)", feats={"pipeline": False}), "")
        self.assertIn("tlPlOffNote(g)", js_fn("tlSessRow"))


if __name__ == "__main__":
    unittest.main()
