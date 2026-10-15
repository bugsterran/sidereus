"""Status bar quota segments (60-statusbar.js buildSbar): remaining official % only, never a token used/headroom figure."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import i18n, jconst
from tests._node import node_e

STUBS = """
const fmtTok = n => Math.round(n / 1e6) + 'M';
const burnUsedTip = () => 'tip';
let OUT = '';
const EL = {title: '', clientWidth: 1000, classList: {contains: () => false}};
var document = {getElementById: id => EL};
const svParts = () => null, svLive = () => null, sbExt = () => '', sbFit = () => {}, buildQwho = () => {};
const setHtml = (el, h) => { OUT = h; return false; };
const aiLogo = () => '<i class=ailg>L</i>';
const popIsOpen = () => false;
let SV = null, SVSW = null, SBAR_SV = null, SDRW_OPEN = false, EXTU = null, SB_JNAME = {}, SV_JTIP = '';
let ACCTS = [], BURNM = null, BURNM_DIR = '';
const UIS = {getItem: () => null};
"""
STUBS += "\n".join(js_fn(f) for f in ("acctList", "mainAcct", "mainAcctOk", "knQ", "sbPctCls", "sbPrimNote", "burnMainDir", "burnFor")) + "\n"   # buildSbar reads the cards' window (knQ)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SbarPct(unittest.TestCase):
    def test_no_token_headroom(self):
        # Percent and time only: BURN.head token figures (used · eff · per_pct · wk) must not reach the bar.
        body = """
const N = Date.parse('2030-01-01T00:00:00Z');
let QLAST = {q: {five_hour: {pct: 38, resets_at: new Date(N + 9e6).toISOString()},
                 seven_day: {pct: 33, resets_at: new Date(N + 3e8).toISOString()}}};
let BURN = {ok: true, at: N / 1000, cur: {now_pct: 38, rate_pph: 10, used_local: 2.2e6, wk_used_local: null}, proj: {pct: 80, over_at: null},
            head: {tok: 6e6, used: 4e6, eff: 6e6, lim: 1e7, per_pct: 1e5, src: 'win', wk: {lim: 1.2e8, used: 4e7, pct: 33}}};
buildSbar();
process.stdout.write(JSON.stringify(OUT));
"""
        src = STUBS + i18n() + "\n" + jconst("esc") + "\n" + js_fn("fmtPct") + "\n" + js_fn("buildSbar") + "\n" + "\n".join(js_fn(f) for f in ("burnEst", "burnEstTip", "burnWkEst")) + "\n" + body
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"))
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        h = json.loads(r.stdout)
        self.assertIn("남음</small> <b class=sbok>62%</b>", h)   # remaining, like the KPI cards (38% used)
        self.assertIn("남음</small> <b class=sbok>67%</b>", h)
        self.assertNotIn(">38%<", h)
        self.assertIn("남은 ≈</small> <b>4M</b>", h)         # 2.2M / 38 * 62 = 3.6M (stub fmtTok rounds)
        self.assertIn("사용</small> <b>2M</b>", h)             # measured 5h used stays
        self.assertEqual(h.count("사용</small>"), 1)          # 7d: no measured sum -> no used figure
        self.assertNotRegex(h, r"여유|측정 중|\b(6|10|40|120)M\b")   # head's estimates never shown

    def test_low_remaining_warns(self):
        # Colour keeps its meaning on the remaining figure: 92% used = 8% left -> sberr, 75% used = 25% left -> sbwarn.
        body = """
let QLAST = {q: {five_hour: {pct: 92}, seven_day: {pct: 75}}};
let BURN = null;
buildSbar();
process.stdout.write(JSON.stringify(OUT));
"""
        src = STUBS + i18n() + "\n" + jconst("esc") + "\n" + js_fn("fmtPct") + "\n" + js_fn("buildSbar") + "\n" \
            + "\n".join(js_fn(f) for f in ("burnEst", "burnEstTip", "burnWkEst")) + "\n" + body
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"))
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        h = json.loads(r.stdout)
        self.assertIn("남음</small> <b class=sberr>8%</b>", h)
        self.assertIn("남음</small> <b class=sbwarn>25%</b>", h)

    def test_history_estimate(self):
        # «남은 ≈» from the account's history per-1% (`est`, >= 3 windows); 7d unmeasured gets «사용 ≈ · 남은 ≈».
        h = self._est(6, "med")
        self.assertIn("남은 ≈</small> <b>37M</b>", h)                # history, not the window average (4M)
        self.assertIn("사용 ≈</small> <b>106M</b><span class=sbd3> <small>· 남은 ≈</small> <b>214M</b></span>", h)
        self.assertIn("1%당 토큰 중앙값", h)                          # tooltip names the source

    def test_thin_history_uses_window_average(self):
        # < 3 history windows: 2.2M / 38% x 62% = 3.6M, so «사용 : 남은» matches the official %; tooltip says why.
        h = self._est(2, "pool")
        self.assertIn("남은 ≈</small> <b>4M</b>", h)
        self.assertIn("남은 ≈ 4M — 기록 2창 — 이번 창 평균으로 추정", h)
        self.assertIn("사용 ≈</small> <b>106M</b><span class=sbd3> <small>· 남은 ≈</small> <b>214M</b></span>", h)   # 7d unchanged

    def _est(self, n, src_kind):
        body = """
const N = Date.parse('2030-01-01T00:00:00Z');
let QLAST = {q: {five_hour: {pct: 38, resets_at: new Date(N + 9e6).toISOString()},
                 seven_day: {pct: 33, resets_at: new Date(N + 3e8).toISOString()}}};
let BURN = {ok: true, at: N / 1000, cur: {now_pct: 38, rate_pph: 10, used_local: 2.2e6, wk_used_local: null}, proj: {pct: 80, over_at: null},
            est: {h5_per_pct: 6e5, h5_n: %d, h5_src: '%s', wk_per_pct: 3.2e6, wk_n: 160, h5_left: 3.72e7, wk_left: 2.144e8, wk_used: 1.056e8}};
buildSbar();
process.stdout.write(JSON.stringify([OUT, EL.title]));
""" % (n, src_kind)
        src = STUBS + i18n() + "\n" + jconst("esc") + "\n" + js_fn("fmtPct") + "\n" + js_fn("buildSbar") + "\n" \
            + "\n".join(js_fn(f) for f in ("burnEst", "burnEstTip", "burnWkEst")) + "\n" + body
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"))
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        return json.loads(r.stdout)[0]

    def _proj(self, proj):
        body = """
let QLAST = {q: {five_hour: {pct: 38}}};
let BURN = {ok: true, at: 1, cur: {}, proj: %s};
buildSbar();
process.stdout.write(JSON.stringify(OUT));
""" % proj
        src = STUBS + i18n() + "\n" + jconst("esc") + "\n" + js_fn("fmtPct") + "\n" + js_fn("buildSbar") + "\n" \
            + "\n".join(js_fn(f) for f in ("burnEst", "burnEstTip", "burnWkEst")) + "\n" + body
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"))
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        return json.loads(r.stdout)

    def test_projection_remaining(self):
        # Projection at reset uses the remaining framing: 91% used -> «남음 ≈9%», colour still keyed on used.
        h = self._proj("{pct: 91, over_at: null, over_in: null}")
        self.assertIn("리셋 때 남음</small> <b class=sberr>≈9%</b>", h)
        self.assertIn("예상 사용 91%", h)
        self.assertNotIn("리셋 때 예상", h)
        self.assertIn("<b class=sbwarn>≈20%</b>", self._proj("{pct: 80, over_at: null, over_in: null}"))

    def test_projection_runs_out(self):
        # Hitting the limit before the reset shows «바닥» instead of a clamped 0%.
        h = self._proj("{pct: 130, over_at: 50, over_in: 40}")
        self.assertIn("리셋 때 남음</small> <b class=sberr>바닥</b>", h)
        self.assertIn("리셋 전에 바닥", h)
        self.assertNotIn("≈-", h)

    def test_saver_tip_english(self):
        # English tooltip is built from the snapshot's numeric fields (12h clock); '' keeps the Korean head/goalSay.
        body = """
LANG = 'en';
const o = [svWhyEn({mode: 'auto', pct: 62, leftMin: 185, lv: 2, earlyMin: 153, goal: 100, rec: 0,
                    overAt: Date.parse('2030-01-01T20:33:00Z') / 1000, stage: 1, end: 0}),
           svWhyEn({mode: 'auto', pct: null, head: '한도를 알 수 없습니다'}), svWhyEn(null), svWhyEn({mode: 'off'})];
process.stdout.write(JSON.stringify(o));
"""
        src = STUBS + i18n() + "\n" + js_fn("svWhyEn") + "\n" + body
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"))
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        full, nopct, none, off = json.loads(r.stdout)
        self.assertIn("Much too fast (runs out 153m before the target) — slow down", full)
        self.assertIn("5h limit 62% · resets in 3h 5m · at this pace runs out at 8:33 PM", full)
        self.assertIn("no new subagents", full)
        self.assertNotRegex(full, r"[가-힣]|20:33")
        self.assertEqual((nopct, none), ("", ""))
        self.assertEqual(off, "Saver off (auto start blocked too)")


if __name__ == "__main__":
    unittest.main()
