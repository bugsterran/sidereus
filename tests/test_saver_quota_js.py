"""Quota/saver helpers (web/js/55-saver-quota.js): qcls/gauge thresholds, creditMoney currency/cents, creditRow,
buildCredit's `on` rule, svParts stage labels, svJudge, and the status-bar «목표보다 덜/더 씀» label (SB_JNAME).
One node run per class; real i18n (05*/06*) so en strings are the shipped ones. No clock: nowS/at are passed in."""
import glob
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import ROOT, js_all, js_fn
from tests._node import node_e


def jconst(name):
    """Top-level `const NAME = ...;` (may span lines)."""
    return re.search(r"^const %s\b.*?;(?:[ \t]*//[^\n]*)?$" % name, js_all(), re.S | re.M).group(0)


def i18n():
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "web", "js", "0[56]*.js"))):
        with open(p, encoding="utf-8") as fh:
            out.append(fh.read())
    return "\n".join(out)


BASE = """
var document = {getElementById: id => EL[id] || null};
const EL = {};
const setHtml = (el, h) => { el.innerHTML = h; };
const agoAt = at => 'AT' + at;
let QLAST = null, SV = null;
"""
FNS = ("fmtPct", "fmtMoney", "ageU", "creditMoney", "creditRow", "buildCredit", "svJudge", "svChip", "svRate",
       "svOver", "svParts")
CONSTS = ("esc", "qcls", "gauge", "SV_STALE", "SV_JLV", "SV_JREC", "SV_JTIP", "SV_JLONG", "svJName", "SB_JNAME")


def run(body):
    src = (BASE + i18n() + "\n" + "\n".join(jconst(c) for c in CONSTS) + "\n" + "\n".join(js_fn(f) for f in FNS)
           + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"), encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SaverQuota(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
R.qcls = [-5, 0, 39.9, 40, 59.99, 60, 84.9, 85, 99.9, 100, 250].map(qcls);
R.gauge = [-5, 50, 150].map(gauge);
R.money = [[null], [969], [20000], [50], [0], [1234, 'EUR'], [1234, 'USD'], [-500, 'JPY'], [123456, 'KRW']]
  .map(a => creditMoney(a[0], a[1]));
function credit(q){ EL.credit = {className: 'credit', innerHTML: '', title: ''}; buildCredit(q);
  return [EL.credit.className, EL.credit.innerHTML, EL.credit.title]; }
const ex = {pct: 4.8, used: 969, limit: 20000};
R.on = [
  credit(null), credit({}), credit({five_hour: {pct: 100}}),                         // no extra → off
  credit({extra: ex}),                                                               // extra, no 5h → off
  credit({extra: ex, five_hour: {pct: 99.9}}), credit({extra: ex, five_hour: {pct: null}}),
  credit({extra: ex, five_hour: {pct: 100}}), credit({extra: ex, five_hour: {pct: 130}}),
  credit({extra: Object.assign({seat: 'enterprise_usage_based'}, ex)}),              // metered seat: no 5h needed
  credit({extra: Object.assign({seat: 'pro'}, ex), five_hour: {pct: 50}}),
  credit({extra: Object.assign({seat: ['usage_based']}, ex)}),                       // non-string seat is not metered
].map(r => r[0]);
R.onHtml = credit({extra: ex, five_hour: {pct: 100}});
R.onUsedOnly = credit({extra: {used: 500}, five_hour: {pct: 100}})[1];
R.meterTip = credit({extra: Object.assign({seat: 'enterprise_usage_based'}, ex)})[2];
R.row = [creditRow(null), creditRow({extra: {}}), creditRow({extra: {pct: 4.8, used: 969, limit: 20000}}),
         creditRow({extra: {pct: 95, used: 19000, limit: 20000, approx: 1}}), creditRow({extra: {used: 100}}),
         creditRow({extra: {pct: 10, used: 1, limit: 2, age: 119}}), creditRow({extra: {pct: 10, used: 1, limit: 2, age: 120}}),
         creditRow({extra: {pct: 10, used: 1, limit: 2, age: 7200}})];
const N = 1000000;
const P = v => { const r = svParts(Object.assign({at: N}, v), N); return r && [r.cls, r.main, r.stage, r.sub]; };
R.st = [P({stage: 1, pct: 50}), P({stage: 2}), P({stage: 3, pct: 91.5}), P({mode: 'on'}), P({mode: 'on', stage: 1}),
        P({mode: 'off', stage: 2, pct: 50}), P({pct: null}), P({pct: 30}), P({mode: 'weird', pct: 30}),
        P({stage: 2, pct: 50, rec: 0}), P({stage: 2, pct: 50, rec: 2})];
R.stNone = [svParts(null, N), svParts('x', N)];
R.old = svParts({at: N - 121, pct: 30}, N).cls;
R.fresh = svParts({at: N - 120, pct: 30}, N).cls;
R.jlv = [2, 1, 0, -1, -2, 5].map(lv => { const j = svJudge({lv}); return j && j.k; });
R.jsay = ['크게 뒤처짐', '뒤처집니다', '너무 빠릅니다', '빠릅니다', '페이스 유지', '못 쟀습니다', '???']
  .map(g => { const j = svJudge({goalSay: g}); return j && j.k; });
R.jwait = [svJudge({mode: 'pace'}), svJudge({mode: 'auto'}), svJudge(null)];
const lab = lv => { const j = svJudge({lv}); return SB_JNAME[j.nm] ? T(SB_JNAME[j.nm]) : svJName(j); };
R.sb = [2, 1, 0, -1, -2].map(lab);
R.long = [2, -1].map(lv => svJName(svJudge({lv})));
LANG = 'en';
R.sbEn = [2, 1, 0, -1, -2].map(lab);
R.stEn = [P({stage: 2, pct: 50}), P({mode: 'off'}), P({pct: 30})].map(r => r[1]);
R.onEn = credit({extra: ex, five_hour: {pct: 100}})[1];
R.moneyEn = creditMoney(1234, 'EUR');
""")

    def test_qcls_thresholds(self):
        self.assertEqual(self.R["qcls"], ["qcool", "qcool", "qcool", "qok", "qok", "qmid", "qmid", "qhot2", "qhot2",
                                          "qover", "qover"])

    def test_gauge_clamps_width(self):
        self.assertIn('class="qg qcool"><i style="width:0%"', self.R["gauge"][0])
        self.assertIn('class="qg qok"><i style="width:50%"', self.R["gauge"][1])
        self.assertIn('class="qg qover"><i style="width:100%"', self.R["gauge"][2])

    def test_credit_money(self):
        self.assertEqual(self.R["money"], ["?", "$9.7", "$200", "$0.50", "$0", "12 EUR", "$12", "-5.0 JPY", "1.2K KRW"])
        self.assertEqual(self.R["moneyEn"], "12 EUR")

    def test_credit_badge_on_rule(self):
        # on = extra and (usage_based seat or 5h >= 100)
        self.assertEqual(self.R["on"], ["credit", "credit", "credit", "credit", "credit", "credit", "credit on",
                                        "credit on", "credit on", "credit", "credit"])

    def test_credit_badge_text(self):
        cls, html, tip = self.R["onHtml"]
        self.assertEqual(html, "<b>크레딧 모드</b><span>$190 남음</span>")
        self.assertIn("5시간 한도를 다 써서", tip)
        self.assertIn("월 한도 $200 중 $9.7 사용 (4.8%)", tip)
        self.assertIn("<span>$5.0 사용</span>", self.R["onUsedOnly"])
        self.assertTrue(self.R["meterTip"].startswith("쓴 만큼 과금되는 좌석입니다(enterprise_usage_based)"))
        self.assertNotIn("무료 구간", self.R["meterTip"])
        self.assertEqual(self.R["onEn"], "<b>Credit mode</b><span>$190 left</span>")

    def test_credit_row(self):
        r = self.R["row"]
        self.assertEqual(r[:2], ["", ""])
        self.assertIn('<b class="qcool">4.8%</b>', r[2])
        self.assertIn("$9.7 / $200", r[2])
        self.assertIn('<span class="">$190 남음</span>', r[2])
        self.assertIn('<span class="qhot">≈$10 남음</span>', r[3])      # p >= 90 reddens the remaining amount
        self.assertIn("≈$190 / $200", r[3])
        self.assertNotIn("qg", r[4])                                     # no pct → no gauge
        self.assertIn("$1.0 사용", r[4])
        self.assertNotIn("qold", r[5])                                   # age < 120 → no age span
        self.assertIn('<span class="qold" title=', r[6])
        self.assertIn(">2분 전 값</span>", r[6])
        self.assertIn('<span class="qold qhot"', r[7])
        self.assertIn(">2시간 전 값</span>", r[7])

    def test_saver_stage_labels(self):
        st = self.R["st"]
        self.assertEqual(st[0][:3], ["svwarn", "절약 1단계 · 50%", 1])
        self.assertEqual(st[1][:3], ["svwarn", "절약 2단계", 2])
        self.assertEqual(st[2][:3], ["svhot", "절약 3단계 · 92%", 3])
        self.assertEqual(st[3][:3], ["svhot", "절약 3단계", 3])          # manual on defaults to stage 3
        self.assertEqual(st[4][:3], ["svwarn", "절약 1단계", 1])
        self.assertEqual(st[5][:3], ["svoff", "절약 꺼짐", 0])           # off forces stage 0
        self.assertEqual(st[6][:3], ["svoff", "한도 모름", 0])
        self.assertEqual(st[7][:3], ["svfree", "제한 없음", 0])
        self.assertEqual(st[8][:3], ["svfree", "제한 없음", 0])           # unknown mode → auto
        self.assertIn("서브에이전트 금지", st[9][3])
        self.assertIn("동시 2개까지", st[10][3])
        self.assertEqual(self.R["stNone"], [None, None])
        self.assertEqual((self.R["old"], self.R["fresh"]), ("svfree svold", "svfree"))
        self.assertEqual(self.R["stEn"], ["Saver: level 2 · 50%", "Saver off", "No throttle"])

    def test_judge_levels(self):
        self.assertEqual(self.R["jlv"], ["fast2", "fast", "ok", "slow", "slow2", None])
        self.assertEqual(self.R["jsay"], ["slow2", "slow", "fast2", "fast", "ok", "wait", None])
        self.assertEqual(self.R["jwait"][0], {"nm": "Pending", "k": "wait"})
        self.assertEqual(self.R["jwait"][1:], [None, None])

    def test_status_bar_use_label(self):
        self.assertEqual(self.R["sb"], ["목표보다 많이 씀", "목표보다 더 씀", "목표대로 씀", "목표보다 덜 씀",
                                        "목표보다 많이 덜 씀"])
        self.assertEqual(self.R["sbEn"], ["Burning far above target", "Above target", "On target", "Below target",
                                          "Far below target"])
        self.assertEqual(self.R["long"], ["목표보다 많이 씀", "목표보다 덜 씀"])   # drawer badge = status-bar wording


if __name__ == "__main__":
    unittest.main()
