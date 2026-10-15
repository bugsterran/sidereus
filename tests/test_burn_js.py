"""Burndown helpers (web/js/55-saver-quota.js + 55b-burn-state.js + 57-burn.js): bnDur/bnHM, burnSum pace line, burnHead %-only rows,
the status bar's quota segments (no token headroom), and ageU edge cases. One node run; real i18n (05*/06*); TZ=UTC and nowS passed in (no clock)."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e
from tests.test_saver_quota_js import i18n, jconst

BASE = """
var document = {getElementById: () => null, documentElement: {dataset: {}}};
const thc = (dk, lt) => document.documentElement.dataset.theme === 'light' ? lt : dk;
const fmtTok = n => n >= 1e6 ? Math.round(n/1e6) + 'M' : n >= 1e3 ? Math.round(n/1e3) + 'K' : String(n);
"""
FNS = ("fmtPct", "ageU", "burnSum", "burnHead", "burnUsedTip", "burnEst", "burnEstTip", "burnWkEst", "burnWkTxt", "burnCol", "burnCurve", "burnOut", "burnOutLab", "burnX")
CONSTS = ("esc", "bnDur", "bnHM", "BURN_W")


def run(body, fns=FNS):
    src = (BASE + i18n() + "\n" + "\n".join(jconst(c) for c in CONSTS) + "\n" + "\n".join(js_fn(f) for f in fns)
           + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"))
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


AGES = [None, 0, 59, 60, 119, 120, 3599, 3600, 7199, 7200, 86400]


@unittest.skipUnless(shutil.which("node"), "node not installed")
class Burn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
const AGES = %s;
const ages = () => ({s60: AGES.map(s => ageU(s, 60, false)), s120: AGES.map(s => ageU(s, 120, false)),
                     hrs: AGES.map(s => ageU(s, 0, true))});
R.age = ages();
R.dur = [-30, 0, 29, 30, 59 * 60, 3600, 3629, 3631, 86400 + 3660].map(bnDur);
R.hm = [0, 3600 * 13 + 5 * 60].map(bnHM);
R.sum = [burnSum({pct: null}), burnSum({pct: 87.4}), burnSum({pct: 4.25}), burnSum({pct: 0.3})];
const N = 1000000 * 60;   // minute-aligned now
const cur = {now_pct: 38, reset: N + 150 * 60}, wk = {now_pct: 33, left: 3 * 86400 + 12 * 3600};
const tokHead = {tok: 6e6, used: 4e6, eff: 6e6, lim: 1e7, per_pct: 1e5, src: 'win', wk: {lim: 1.2e8, used: 4e7, pct: 33}};
R.head = [burnHead(null, N), burnHead({}, N),
          burnHead({cur}, N),
          burnHead({cur, proj: {over_at: N + 90 * 60}}, N),
          burnHead({cur, wk}, N),
          burnHead({cur, wk: {now_pct: 33, left: 0}}, N),
          burnHead({cur: {now_pct: 100.4, reset: N}, head: tokHead}, N),
          burnHead({cur: Object.assign({used_local: 2.2e6, wk_used_local: 3.1e7}, cur), wk, head: tokHead}, N)];
const est = {h5_per_pct: 6e5, h5_n: 6, h5_src: 'med', wk_per_pct: 3.2e6, wk_n: 160, h5_left: 3.72e7, wk_left: 2.144e8, wk_used: 1.056e8};
R.est = [burnHead({cur: Object.assign({used_local: 2.2e6}, cur), wk, est}, N),
         burnHead({cur: Object.assign({used_local: 2.2e6}, cur), wk, est: Object.assign({}, est, {h5_src: 'pool'})}, N),
         burnHead({cur: Object.assign({used_local: 2.2e6}, cur), wk, est: Object.assign({}, est, {h5_src: 'pool', h5_n: 2})}, N)];
function burnSvg(){ return ''; }
R.plan = [burnCurve({base: {why: 'plan', n: 0}}),
          burnHead({cur: Object.assign({used_local: 2.2e6}, cur), est: null, est_why: 'plan'}, N)];
LANG = 'en';
R.ageEn = ages();
R.planEn = burnCurve({base: {why: 'plan', n: 0}});
const bandB = {n: 4, band: [[0, 1, 2], [60, 2, 3]], pts: [[0, 1], [60, 2]]};
R.leg = [burnCurve({base: bandB, proj: {raw: 40}}), burnCurve({base: bandB, proj: {raw: 120}})];
R.durEn = [3631].map(bnDur);
R.sumEn = [burnSum({pct: null}), burnSum({pct: 87.4})];
R.headEn = [burnHead({cur, proj: {over_at: N + 90 * 60}, wk}, N)];
""" % json.dumps(AGES))

    def test_age_edges_ko(self):
        a = self.R["age"]
        # ⚠null is not guarded: null < sUnder is true, so it prints «null초» — callers check null first (backfill '?').
        self.assertEqual(a["s60"], ["null초", "0초", "59초", "1분", "1분", "2분", "59분", "60분", "119분", "120분", "1440분"])
        self.assertEqual(a["s120"], ["null초", "0초", "59초", "60초", "119초", "2분", "59분", "60분", "119분", "120분", "1440분"])
        self.assertEqual(a["hrs"], ["0분", "0분", "0분", "1분", "1분", "2분", "59분", "1시간", "1시간", "2시간", "24시간"])

    def test_age_edges_en(self):
        a = self.R["ageEn"]
        self.assertEqual(a["s60"][2:5], ["59s", "1m", "1m"])
        self.assertEqual(a["s120"][4:6], ["119s", "2m"])
        self.assertEqual(a["hrs"][6:], ["59m", "1h", "1h", "2h", "24h"])

    def test_duration_and_clock(self):
        self.assertEqual(self.R["dur"], ["0분", "0분", "0분", "1분", "59분", "1시간 0분", "1시간 0분", "1시간 1분", "1일 1시간"])
        self.assertEqual(self.R["durEn"], ["1h 1m"])
        self.assertEqual(self.R["hm"], ["오전 12:00", "오후 01:05"])

    def test_pace_line(self):
        s = self.R["sum"]
        self.assertEqual(s[0], "아직 속도를 못 쟀습니다")
        self.assertEqual(s[1], "이 속도면 리셋 때 <em class=bpj>87%</em>")
        self.assertEqual(s[2], "이 속도면 리셋 때 <em class=bpj>4.3%</em>")
        self.assertEqual(s[3], "이 속도면 리셋 때 <em class=bpj>&lt;1%</em>")
        self.assertNotIn("아직", self.R["sumEn"][1])
        self.assertIn("<em class=bpj>87%</em>", self.R["sumEn"][1])

    def test_percent_rows(self):
        h = self.R["head"]
        self.assertEqual(h[:2], ["", ""])                   # no cur → nothing
        self.assertEqual(h[2], "<span class=bhead><b class=blab>5h</b> 38% · 리셋 2시간 30분 뒤</span>")
        self.assertEqual(h[3], "<span class=bhead><b class=blab>5h</b> 38% · 이 속도면 오후 12:10 바닥</span>")
        self.assertIn("<span class=\"bhead bheadwk\"><b class=blab>7d</b> 33% · 리셋 3일 12시간 뒤</span>", h[4])
        self.assertNotIn("bheadwk", h[5])                  # no reset time → no weekly row
        self.assertIn("100%", h[6])                        # over 100% clamps at 100
        self.assertEqual(self.R["headEn"], ["<span class=bhead><b class=blab>5h</b> 38% · runs out 12:10 PM at this pace</span>"
                                            "<span class=\"bhead bheadwk\"><b class=blab>7d</b> 33% · resets in 3d 12h</span>"])

    def test_measured_used_shown(self):
        h = self.R["head"][7]
        self.assertIn(" · <span title=\"이 PC 기록 기준 · 다른 기기·claude.ai 미포함\">사용 2M</span> · <span title=\"이번 창 평균(사용 ÷ %) × 남은 % — 쓰는 방식에 따라 크게 달라집니다\">남은 ≈ 4M</span> · 리셋", h)
        self.assertIn(">사용 31M</span> · <span title=\"이번 창 평균(사용 ÷ %) × 남은 % — 쓰는 방식에 따라 크게 달라집니다\">남은 ≈ 63M</span> · 리셋 3일", h)            # 7d only from the measured `wk_used_local`

    def test_history_estimate_wins(self):
        h = self.R["est"][0]
        tip5 = "이 계정 기록 6개 창의 1%당 토큰 중앙값 × 남은 % — 추정"
        self.assertIn(">사용 2M</span> · <span title=\"" + tip5 + "\">남은 ≈ 37M</span> · 리셋", h)   # not 2.2/38*62 = 4M
        self.assertIn("<span title=\"이 계정 7일 기록(160%p)의 1%당 토큰 × 남은 % — 추정\">사용 ≈ 106M · 남은 ≈ 214M</span>", h)
        self.assertNotIn("이번 창 평균", h)
        self.assertIn("6개 창 구간의 1%당 토큰", self.R["est"][1])   # pooled fallback says so
        # < 3 history windows: window average (2.2M / 38 x 62 = 3.6M) so «사용 : 남은» = official %
        self.assertIn("기록 2창 — 이번 창 평균으로 추정\n이번 창 평균(사용 ÷ %)", self.R["est"][2])
        self.assertIn("남은 ≈ 4M</span>", self.R["est"][2])
        self.assertIn("사용 ≈ 106M · 남은 ≈ 214M", self.R["est"][2])        # 7d unchanged

    def test_plan_change_low_accuracy(self):
        self.assertIn("<span>기록 부족 — 정확도 낮음</span>", self.R["plan"][0])
        self.assertIn("— 쓰는 방식에 따라 크게 달라집니다 · 기록 부족 — 정확도 낮음\">남은 ≈ 4M", self.R["plan"][1])
        self.assertIn("<span>Not enough history — low accuracy</span>", self.R["planEn"])

    def test_legend_glyph_colours(self):
        # Legend glyphs carry the chart stroke colours: curve green/red on ━ and «this pace» ┄, the median grey on ▨ and median ┄.
        ok, warn = self.R["leg"]
        for h, col in ((ok, "#6fd39a"), (warn, "#e0725f")):
            self.assertIn('color:' + col + ';font-weight:inherit">━</b>', h)
            self.assertIn('color:' + col + ';font-weight:inherit">┄</b> At this rate', h)
            self.assertIn('color:#8b95a7;font-weight:inherit">▨</b>', h)
            self.assertIn('color:#8b95a7;font-weight:inherit">┄</b> median', h)
            self.assertNotIn("#5f6a7a", h)   # 3.17:1 on the panel

    def test_median_stroke_matches_legend_glyph(self):
        # Median dash in burnSvg and the legend ┄ use the same thc() twins (dark/light).
        svg, cur = js_fn("burnSvg"), js_fn("burnCurve")
        tw = "thc('#8b95a7','#61656c')"
        self.assertIn("stroke=\"'+" + tw + "+'\" stroke-width=\"1.2\"", svg)
        self.assertIn("gr = " + tw, cur)
        self.assertNotIn('stroke="#5f6a7a"', svg)

    def test_modal_tooltip_is_hover_card(self):
        # Inside the modal: no native title (unstyled, covers the modal title); hcShow card with no «Click the row» line.
        bb, bind = js_fn("buildBurn"), js_fn("burnHcBind")
        modal = bb.split("closest('.sdrw')", 1)[1].split("} else {", 1)[0]
        self.assertNotIn("el.title", modal)
        self.assertIn("removeAttribute('title')", modal)
        self.assertIn("hcShow('bnhc'", bind)
        self.assertIn("burnTitle(bd, true)", bind)
        self.assertIn("hcHide('bnhc')", bind)
        self.assertIn("(noToggle ? ''", js_fn("burnTitle"))

    def test_no_token_headroom(self):
        # Percent and time only: only measured «사용 NM» — never head's limit/headroom/estimated used.
        for h in self.R["head"] + self.R["headEn"]:
            self.assertNotRegex(h, r"여유|\b(6|10|40|120)M\b")   # ≈ only for «남은 ≈» (used ÷ % × left %)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class RunOut(unittest.TestCase):
    """Projected run-out marker: vertical line + «Out at» label only when the projection hits 100% before the reset."""
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
const S = 1000000 * 60, W = 5 * 3600;
const cur = e => ({start: S, reset: S + W, elapsed: 3600, now_pct: 40, pts: [[S, 0], [S + 3600, 40]]});
const mk = (raw, at) => ({cur: cur(), proj: Object.assign({raw: raw, pct: Math.min(raw, 100)}, at ? {over_at: at} : {})});
const cases = {mid: mk(150, S + W / 2), late: mk(110, S + W - 600), atReset: mk(120, S + W),
               none: mk(80, null), noProj: {cur: cur(), proj: {raw: null, pct: null}}};
for(const k in cases){ R[k] = {o: burnOut(cases[k]), svg: burnSvg(cases[k]), leg: burnCurve(cases[k])}; }
LANG = 'en';
R.midEn = burnCurve(cases.mid); R.noneEn = burnCurve(cases.none);
""", FNS + ("burnSvg",))

    def test_marker_before_reset(self):
        m = self.R["mid"]
        self.assertEqual(m["o"]["e"], 9000)
        self.assertIn('<line class=bnoutl x1="100.0" y1="3" x2="100.0" y2="43" stroke="#e0725f"', m["svg"])   # X(2.5h) = 3 + 97
        self.assertIn('<div class=bnout><span style="left:50.00%;color:#e0725f">소진 예상 ', m["leg"])
        self.assertNotIn("리셋 전 소진 없음", m["leg"])
        self.assertIn(">Out at ", self.R["midEn"])

    def test_one_x_mapping(self):
        # Label and line share burnX — no second copy of the pad/width arithmetic.
        self.assertIn("burnX(o.e)/BURN_W", js_fn("burnOutLab"))
        self.assertIn("X = burnX", js_fn("burnSvg"))
        self.assertNotIn("194", js_fn("burnOutLab"))

    def test_label_flips_near_right_edge(self):
        lg = self.R["late"]["leg"]
        self.assertIn('class=bnoutl', self.R["late"]["svg"])
        self.assertIn('<span style="right:', lg)
        self.assertNotIn('<span style="left:', lg)

    def test_no_marker_at_or_after_reset(self):
        for k in ("atReset", "none"):
            r = self.R[k]
            self.assertEqual(r["o"], {"none": 1})
            self.assertNotIn("bnoutl", r["svg"])
            self.assertIn("<div class=bnout></div>", r["leg"])   # row reserved, empty
            self.assertIn("<span>리셋 전 소진 없음</span>", r["leg"])
        self.assertIn("<span>No run-out before reset</span>", self.R["noneEn"])

    def test_nothing_without_projection(self):
        r = self.R["noProj"]
        self.assertIsNone(r["o"])
        self.assertNotIn("bnoutl", r["svg"])
        self.assertIn("<div class=bnout></div>", r["leg"])
        self.assertNotIn("리셋 전 소진 없음", r["leg"])


@unittest.skipUnless(shutil.which("node"), "node not installed")
class BurnIdle(unittest.TestCase):
    """No current 5h window (`why` stale/no-data): a muted one-line note instead of an empty block."""

    def test_note_text_ko_en(self):
        R = run("R.ko = burnIdle(); LANG = 'en'; R.en = burnIdle();", fns=FNS + ("burnIdle",))
        self.assertEqual(R["ko"], "<div class=bleg><span>기본 계정에 진행 중인 5h 창이 아직 없습니다 — 다음 사용부터 그래프가 그려집니다.</span></div>")
        self.assertIn("No active 5h window on the default account yet", R["en"])

    def test_build_uses_note_only_when_idle(self):
        src = js_fn("buildBurn")
        self.assertIn("b.why === 'stale' || b.why === 'no-data'", src)
        self.assertIn("idle ? burnIdle(un.dir ? un.label : '') : ''", src)


if __name__ == "__main__":
    unittest.main()
