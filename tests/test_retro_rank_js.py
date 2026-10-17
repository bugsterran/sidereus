"""Retro card ① «도구 순위» (web/js/86-retro.js rtRank): escaped names, fold count, success class, empty state."""
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
  + ';this.X = {rtRank, rtMs};', c);
const X = c.X, R = {};
const rank = {calls: 120, from: '2026-09-07', restN: 2,
  top: [{n: '<b>Bash</b>', calls: 100, ok: 99.5, ms: 800}, {n: 'Read', calls: 15, ok: 92, ms: 120}, {n: 'Edit', calls: 3, ok: 50, ms: null}],
  rest: [{n: 'Grep', calls: 1, ok: null, ms: 40}, {n: 'Glob', calls: 1, ok: 100, ms: 2}]};
R.full = X.rtRank({days: 7, rank});
R.none = X.rtRank({days: 7});
R.live = X.rtRank({days: 7, rank: {calls: 0, top: [], rest: [], restN: 0, from: null, live: true}});
R.start = X.rtRank({days: 7, rank: Object.assign({}, rank, {from: '2026-10-02'})});
R.capped = X.rtRank({days: 7, rank: Object.assign({}, rank, {restN: 5})});
R.round = [97.6, 98.2, 89.6, 89.4].map(p => X.rtRank({days: 7, rank: {calls: 1, restN: 0, rest: [], top: [{n: 'A', calls: 1, ok: p}]}}));
R.zero = X.rtRank({days: 30, rank: {calls: 0, top: [], rest: [], restN: 0, from: null}});
R.nofold = X.rtRank({days: 7, rank: Object.assign({}, rank, {rest: [], restN: 0, from: null})});
R.ms = [X.rtMs(800), X.rtMs(120), X.rtMs(null), X.rtMs(2500), X.rtMs(59900), X.rtMs(1095100), X.rtMs(119600), X.rtMs(203135000), X.rtMs(3599000)];
R.big = X.rtRank({days: 7, rank: {calls: 178783, restN: 0, rest: [], top: [{n: 'Bash', calls: 178783, ok: 99, ms: 10}]}});
process.stdout.write(JSON.stringify(R));
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class RetroRank(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        core = open(os.path.join(ROOT, "web", "js", "00-core.js"), encoding="utf-8").read()
        esc = re.search(r"^const esc = .*?;$", core, re.S | re.M).group(0)   # arrow const: js_fn finds functions only
        help_ = esc + "\n" + js_fn("fmtPct")
        r = subprocess.run(node_e("const ROOT = %s;\nconst HELP = %s;\n" % (json.dumps(ROOT), json.dumps(help_)) + SRC),
                           capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        cls.R = json.loads(r.stdout)

    def test_escaped_names(self):
        f = self.R["full"]
        self.assertIn("&lt;b&gt;Bash&lt;/b&gt;", f)
        self.assertNotIn("<b>Bash", f)

    def test_heading_and_fold(self):
        f = self.R["full"]
        self.assertIn("도구 순위", f)
        self.assertIn("최근 7일 · 9/29~", f)     # from before the range never shows (was «9/7~»)
        self.assertNotIn("9/7", f)
        self.assertIn("10/2부터 (수집 시작)", self.R["start"])
        self.assertIn("나머지 2개", f)
        self.assertIn("<tbody class=rtrest hidden>", f)
        self.assertEqual(f.count("<tr>"), 6)      # head + 3 top + 2 rest
        self.assertNotIn("rtrest", self.R["nofold"])
        self.assertNotIn("~", self.R["nofold"])

    def test_success_class(self):
        f = self.R["full"]
        self.assertIn('class="brv rtok"', f)
        self.assertIn('class="brv rtwarn"', f)
        self.assertIn('class="brv rterr"', f)

    def test_success_class_on_rounded_value(self):
        a, b, c, d = self.R["round"]
        self.assertIn("rtok", a)
        self.assertIn("rtok", b)
        self.assertIn("rtwarn", c)
        self.assertIn("rterr", d)

    def test_capped_rest_names_omitted_rows(self):
        self.assertIn("나머지 5개", self.R["capped"])
        self.assertIn("외 3개는 표시하지 않았습니다", self.R["capped"])
        self.assertNotIn("표시하지 않았습니다", self.R["full"])

    def test_live_but_no_tool_calls(self):
        self.assertIn("OTel 은 받고 있습니다", self.R["live"])
        self.assertNotIn("OTEL 데이터 없음", self.R["live"])

    def test_ms_format(self):
        self.assertEqual(self.R["ms"], ["0.8s", "120ms", "—", "2.5s", "59.9s", "18m 15s", "2m 0s", "56h 26m", "59m 59s"])

    def test_calls_thousands_separator(self):
        self.assertIn(">178,783<", self.R["big"])

    def test_empty_state(self):
        for k in ("none", "zero"):
            self.assertIn("OTEL 데이터 없음", self.R[k])
            self.assertNotIn("<table", self.R[k])


if __name__ == "__main__":
    unittest.main()
