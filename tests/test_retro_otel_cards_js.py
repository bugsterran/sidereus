"""Retro OTel cards (web/js/86-retro.js rtTime · rtCache): R1 time spent, R3 cache rewrites, R4 empty states."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_fn
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SRC = i18n_prelude("'ko'", ("T", "KE")) + r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
const c = {I18N: {en: {}}, LANG: 'ko', T, KE, thc: a => a};
vm.createContext(c);
// fixed clock: 2026-10-05 noon local, so the 7-day range starts 2026-09-29
vm.runInContext('Date = class extends Date { constructor(...a){ if(a.length) super(...a); else super(2026, 9, 5, 12); } };', c);
vm.runInContext(HELP + '\n' + fs.readFileSync(path.join(ROOT, 'web', 'js', '86-retro.js'), 'utf8')
  + ';this.X = {rtTime, rtCache, rtHeat, rtLv, rtModels, rtMdl, rtHooks};', c);
const X = c.X, R = {};
const time = {restN: 3,
  rows: [{n: '<img src=x>', calls: 2, ms: 95000, tms: 190000, fms: 21}, {n: 'Bash', calls: 40, ms: 2300, tms: 92000, fms: 7},
        {n: 'Read', calls: 8, ms: 40, tms: 320, fms: 0}, {n: 'Edit', calls: 1, ms: 50, tms: 50, fms: null}]};
R.time = X.rtTime({days: 7, time, rank: {from: '2026-09-07'}});
R.timeNone = X.rtTime({days: 7});
R.timeEmpty = X.rtTime({days: 7, time: {rows: [], restN: 0}});
R.timeNull = X.rtTime({days: 7, rank: null, time: null});
R.timeZero = X.rtTime({days: 7, time: {rows: [{n: 'Bash', calls: 0, ms: null, tms: 0, fms: 0}], rest: [], restN: 0}});
const cache = {days: [{d: '2026-10-04', read: 9000, create: 1000, pct: 10}, {d: '2026-10-05', read: 3000, create: 1000, pct: 25}],
  sessions: [{sid: 'abcdef12-3456-7890', path: '/x/<proj>', project: '<b>proj</b>', read: 3000, create: 1000, pct: 25},
             {sid: '99887766-aaaa', path: '/y/z', read: 10, create: 0, pct: 0}]};
R.cache = X.rtCache({days: 7, cache});
R.cacheNone = X.rtCache({days: 7});
R.cacheEmpty = X.rtCache({days: 7, cache: {days: [], sessions: []}});
R.cacheZero = X.rtCache({days: 7, cache: {days: [{d: '2026-10-05', read: 0, create: 0, pct: 0}], sessions: []}});
// R1 heat: Monday 14:00 = 1234 requests (max), Wednesday 09:00 = 1 (lowest non-empty); range start 2026-09-29 local
const cells = Array.from({length: 7}, () => Array.from({length: 24}, () => [0, 0]));
cells[0][14] = [1234, 2300000]; cells[2][9] = [1, 7];
const from = new Date(2026, 8, 29).getTime() / 1000;
R.heat = X.rtHeat({days: 7, heat: {from, since: from - 86400, n: 1235, cells}});
R.heatLate = X.rtHeat({days: 30, heat: {from: from - 23 * 86400, since: from, n: 1235, cells}});
R.heatNone = X.rtHeat({days: 7});
R.heatNull = X.rtHeat({days: 7, heat: null});
R.heatZero = X.rtHeat({days: 7, heat: {from, since: null, n: 0, cells: Array.from({length: 7}, () => Array.from({length: 24}, () => [0, 0]))}});
R.lv = [X.rtLv(0, 100), X.rtLv(1, 100), X.rtLv(20, 100), X.rtLv(100, 100)];
R.heatEsc = X.rtHeat({days: '<b>7', heat: {from, since: from, n: 1, cells}});
// R1/R2/R4 models: server order deliberately wrong to check the client sort; one unknown id with markup, one overflow row
const mk = (m, a, b, cc) => ({model: m, count: a[0] + b[0] + cc[0], tokens: a[1] + b[1] + cc[1], kinds: {main: a, agent: b, side: cc}});
R.models = X.rtModels({days: 7, models: {from, since: from - 86400, n: 99, rows: [
  mk('claude-haiku-4-5-20251001', [0, 0], [5, 100], [10, 100]), mk('claude-opus-5-5', [30, 600], [10, 200], [0, 0]),
  mk('<b>x', [1, 0], [0, 0], [0, 0]), mk('other', [0, 0], [0, 0], [1, 0])]}});
R.modelsNone = X.rtModels({days: 7});
R.modelsNull = X.rtModels({days: 7, models: null});
R.modelsZero = X.rtModels({days: 7, models: {from, since: null, n: 0, rows: []}});
R.mdl = ['claude-opus-5-5', 'claude-sonnet-4-5-20250929', 'claude-3-5-haiku-20241022', 'claude-opus-4', 'gpt-5'].map(m => X.rtMdl(m));
// R2/R3 hook cost: one markup event name, one row past an hour
R.hooks = X.rtHooks({days: 7, hooks: {from: '2026-09-29', n: 7, rows: [
  {ev: 'PreToolUse', count: 1200, ms: 3720000, avg: 3100, fail: 3}, {ev: '<b>Stop', count: 40, ms: 8000, avg: 200, fail: 0}]}});
R.hooksNone = X.rtHooks({days: 7});
R.hooksNull = X.rtHooks({days: 7, hooks: null});
R.hooksZero = X.rtHooks({days: 7, hooks: {from: '2026-09-29', n: 0, rows: []}});
process.stdout.write(JSON.stringify(R));
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class RetroOtelCards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "web", "js", "00-core.js"), encoding="utf-8") as f:
            core = f.read()
        esc = re.search(r"^const esc = .*?;$", core, re.S | re.M).group(0)   # arrow const: js_fn finds functions only
        help_ = esc + "\n" + js_fn("fmtPct") + "\n" + js_fn("fmtTok")
        r = subprocess.run(node_e("const ROOT = %s;\nconst HELP = %s;\n" % (json.dumps(ROOT), json.dumps(help_)) + SRC),
                           capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        cls.R = json.loads(r.stdout)

    def test_r1_time_escaped_ranked(self):
        t = self.R["time"]
        self.assertIn("소요 시간", t)
        self.assertIn("&lt;img src=x&gt;", t)
        self.assertNotIn("<img", t)
        self.assertLess(t.index("&lt;img"), t.index(">Bash<"))      # server order (tms desc) kept
        self.assertIn(">3m 10s<", t)                                # 190000 ms via rtMs
        self.assertIn(">1m 32s<", t)

    def test_r1_failed_share_shown(self):
        t = self.R["time"]
        self.assertIn('class="brv rterr">21%<', t)
        self.assertIn('class="brv rtwarn">7%<', t)
        self.assertIn('class="brv ">0%<', t)
        self.assertIn("<td class=brv>—</td>", t)                    # fms null -> dash, not 0%
        self.assertIn("외 3개는 표시하지 않았습니다", t)
        self.assertIn("실패 시간 수집을 시작한 날부터만", t)

    def test_r1_same_period_as_rank(self):
        self.assertIn("최근 7일 · 9/29~", self.R["time"])

    def test_r3_cache_days_and_sessions(self):
        c = self.R["cache"]
        self.assertIn("캐시 재작성", c)
        self.assertIn(">10%<", c)
        self.assertIn(">25%<", c)
        self.assertIn("&lt;b&gt;proj&lt;/b&gt;", c)
        self.assertNotIn("<b>proj", c)
        self.assertIn("<s>abcdef12</s>", c)                          # short sid only
        self.assertNotIn("abcdef12-3456", c.split("title=")[0])
        self.assertIn(">/y/z <s>", c)                                # no project -> path

    def test_r4_empty_states(self):
        for k in ("timeNone", "timeZero", "timeEmpty", "timeNull"):
            self.assertIn("아직 기록된 도구 시간이 없습니다", self.R[k])
            self.assertNotIn("<table", self.R[k])
        for k in ("cacheNone", "cacheEmpty", "cacheZero"):
            self.assertIn("아직 저장된 캐시 분할이 없습니다", self.R[k])
            self.assertNotIn("<table", self.R[k])
            self.assertNotIn("0%", self.R[k])


    def test_r1_heat_grid_168_cells(self):
        h = self.R["heat"]
        self.assertIn("시간대별 활동", h)
        self.assertEqual(h.count('<i class="rthc'), 168)
        self.assertEqual(h.count("class=rthd>"), 7)
        self.assertIn("class=rthd>월<", h)
        self.assertIn("class=rthd>일<", h)
        self.assertEqual(h.count("class=rthh>"), 24)
        self.assertIn("class=rthh>21<", h)
        self.assertIn("최근 7일 · 9/29~", h)

    def test_r1_heat_header_names_collection_start(self):
        self.assertIn("9/29", self.R["heatLate"])
        self.assertIn("수집 시작", self.R["heatLate"])

    def test_r2_heat_tooltip(self):
        self.assertIn('title="월 14:00–14:59 · 요청 1,234 · 토큰 2M"', self.R["heat"])
        self.assertIn('title="수 09:00–09:59 · 요청 1 · 토큰 7"', self.R["heat"])

    def test_r3_heat_empty_one_note(self):
        for k in ("heatNone", "heatNull", "heatZero"):
            self.assertIn("이 기간 OTel API 요청이 없습니다", self.R[k])
            self.assertEqual(self.R[k].count("class=hidnote"), 1)
            self.assertNotIn("rthc", self.R[k])

    def test_r4_heat_levels(self):
        self.assertEqual(self.R["lv"], [0, 1, 1, 5])
        h = self.R["heat"]
        self.assertEqual(h.count("rthc rth5"), 1)
        self.assertEqual(h.count("rthc rth1"), 1)
        self.assertEqual(h.count('<i class="rthc"'), 166)       # empty cells carry no level class

    def test_heat_escaped(self):
        self.assertNotIn("<b>7", self.R["heatEsc"])

    def test_r1_models_sorted_share(self):
        m = self.R["models"]
        self.assertIn("모델별", m)
        self.assertLess(m.index(">Opus 5.5<"), m.index(">Haiku 4.5<"))     # tokens 800 > 200, server order ignored
        self.assertIn(">80%<", m)                                             # 800 / 1000
        self.assertIn(">20%<", m)
        self.assertIn(">40<", m)                                              # request count
        self.assertEqual(m.count("class=rtms "), 4)

    def test_r2_models_kind_split(self):
        m = self.R["models"]
        self.assertIn('class="rtmk0" style="width:75.0%"', m)                # opus main 600 / 800
        self.assertIn('class="rtmk1" style="width:25.0%"', m)
        self.assertIn("메인 600 · 요청 30", m)
        self.assertIn("서브에이전트", m)
        self.assertIn("부가 호출", m)

    def test_r4_models_family_names_and_tooltip(self):
        self.assertEqual([x[1] for x in self.R["mdl"]], ["Opus 5.5", "Sonnet 4.5", "Haiku 3.5", "Opus 4", "gpt-5"])
        self.assertEqual([x[0] for x in self.R["mdl"]], ["opus", "sonnet", "haiku", "opus", None])
        m = self.R["models"]
        self.assertIn('title="claude-opus-5-5"', m)
        self.assertIn('title="claude-haiku-4-5-20251001"', m)
        self.assertIn(">기타<", m)
        self.assertIn("background:#b07acc", m)                                # fixed opus colour
        self.assertIn("background:#4fa8b8", m)

    def test_r3_models_empty_one_note(self):
        for k in ("modelsNone", "modelsNull", "modelsZero"):
            self.assertIn("이 기간 OTel API 요청이 없습니다", self.R[k])
            self.assertEqual(self.R[k].count("class=hidnote"), 1)
            self.assertNotIn("rtms", self.R[k])

    def test_models_escaped(self):
        m = self.R["models"]
        self.assertNotIn("<b>x", m)
        self.assertIn("&lt;b&gt;x", m)
    def test_r2_hooks_rows(self):
        m = self.R["hooks"]
        self.assertIn("훅 비용", m)
        self.assertIn("이벤트 종류별 OTel 훅 실행", m)
        self.assertLess(m.index(">PreToolUse<"), m.index("&lt;b&gt;Stop"))   # server order (ms desc) kept
        self.assertIn(">1,200<", m)                                           # runs
        self.assertIn(">1h 2m<", m)                                           # total >= 1h reads in hours
        self.assertIn(">3.1s<", m)                                            # average
        self.assertIn('class="brv rtwarn">3<', m)                             # failures > 0 coloured
        self.assertIn('class="brv">0<', m)
        self.assertNotIn("<b>Stop", m)

    def test_r3_hooks_empty_one_note(self):
        for k in ("hooksNone", "hooksNull", "hooksZero"):
            self.assertIn("아직 기록된 훅 실행이 없습니다", self.R[k])
            self.assertEqual(self.R[k].count("class=hidnote"), 1)
            self.assertNotIn("<table", self.R[k])

if __name__ == "__main__":
    unittest.main()
