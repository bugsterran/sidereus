"""«Data delayed» busiest-session suffix (web/js/60-statusbar.js sbBusy/sbBusyHtml, srvLoad.top): shown only while busy,
repo/exe names escaped and never translated, odd shapes dropped. One node run; real i18n; no clock."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e
from tests.test_saver_quota_js import i18n

BASE = r"""
var document = {getElementById: () => null, documentElement: {dataset: {}, classList: {add(){}, remove(){}}}};
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
"""
FNS = ("sbBusy", "sbBusyHtml")


def run(body):
    src = js_all()
    consts = "\n".join(re.search(r"^(?:const|let|var) " + n + r"\b[^\n]*", src, re.M).group(0)
                       for n in ("SB_SNAP_OLD_S", "SB_STEPS", "SB_LOAD_X"))
    js = (BASE + i18n() + "\n" + consts + "\n" + "\n".join(js_fn(f) for f in FNS)
          + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SbBusyTop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
const ok = {fails: 0, next: 0, okAt: 100000, bad: false, slow: false, pend: 0};
const top = {repo: 'a<b>', cpu: 187.4, rssMb: 2150, n: 11, exe: [['node', 11], ['<x>', 2]], unowned: {cpu: 12.6, rssMb: 512}};
const busy = srv => sbBusy(Object.assign({load1: 50, snapAge: 12, slow: []}, srv), ok, 101000);
R.ko = sbBusyHtml(busy({top: top}));
R.nul = sbBusyHtml(busy({top: null}));
R.bare = sbBusyHtml(busy({}));
R.badCpu = sbBusyHtml(busy({top: Object.assign({}, top, {cpu: 'x'})}));
R.noRepo = sbBusy({snapAge: 12, top: Object.assign({}, top, {repo: ''})}, ok, 101000).top;
R.calm = sbBusy({load1: 50, snapAge: 1, slow: [], top: top}, ok, 101000);
// Load trigger: 2x cores, no delay -> «Machine busy»; at or under 2x, or ncpu unknown -> only the delay path.
const fresh = {load1: 30, ncpu: 12, snapAge: 1, slow: [], top: top};
R.mbKo = sbBusyHtml(sbBusy(fresh, ok, 101000));
R.under = sbBusy(Object.assign({}, fresh, {load1: 20}), ok, 101000);
R.noCpu = sbBusy(Object.assign({}, fresh, {ncpu: undefined}), ok, 101000);
R.both = sbBusy(Object.assign({}, fresh, {snapAge: 12}), ok, 101000);
R.bothHtml = sbBusyHtml(R.both);
LANG = 'en';
R.mbEn = sbBusyHtml(sbBusy(Object.assign({}, fresh, {top: Object.assign({}, top, {repo: 'proj'})}), ok, 101000));
R.en = sbBusyHtml(busy({top: Object.assign({}, top, {repo: 'proj', unowned: null})}));
""")

    def test_suffix_while_busy(self):
        en = self.R["en"]
        self.assertIn("mostly proj · CPU 187% · 2.1 GB", en)
        # the repo name drops last (sbd4 = SB_STEPS end), the numbers first (sbd9); the tooltip always carries both
        self.assertRegex(en, r"<small class=sbd4>· mostly proj</small><small class=sbd9> · CPU 187% · 2.1 GB")
        self.assertIn("mostly proj · CPU 187% · 2.1 GB", en.split('"><b')[0])
        self.assertIn("processes: node ×11", en)
        self.assertNotIn("outside Claude sessions", en)

    def test_not_busy_or_null_top_unchanged(self):
        self.assertIsNone(self.R["calm"])
        self.assertEqual(self.R["nul"], self.R["bare"])
        self.assertNotIn("<small", self.R["nul"])

    def test_names_escaped_not_translated(self):
        ko = self.R["ko"]
        self.assertIn("주로 a&lt;b&gt; · CPU 187% · 2.1 GB", ko)
        self.assertNotIn("<b>", ko.replace("<b class=sbwarn>", ""))
        self.assertIn("프로세스: node ×11, &lt;x&gt; ×2", ko)
        self.assertIn("Claude 세션 밖: CPU 13% · 0.5 GB", ko)

    def test_machine_busy_by_load(self):
        en = self.R["mbEn"]
        self.assertIn("● Machine busy · load 30</b>", en)
        self.assertIn("mostly proj · CPU 187%", en)
        self.assertIn("Load is above twice the CPU count", en)
        self.assertNotIn("answering slowly", en)
        self.assertIn("시스템 과부하 · 평균 부하 30", self.R["mbKo"])
        self.assertIn("주로 a&lt;b&gt;", self.R["mbKo"])

    def test_load_under_or_unknown_ncpu_is_quiet(self):
        self.assertIsNone(self.R["under"])
        self.assertIsNone(self.R["noCpu"])

    def test_both_delayed_label_wins(self):
        self.assertTrue(self.R["both"]["delayed"])
        h = self.R["bothHtml"]
        self.assertIn("데이터 수신 지연 · 12초 전", h)
        self.assertNotIn("시스템 과부하", h)
        self.assertIn("부하 30", h)   # load stays in the tooltip
        self.assertIn("주로 a&lt;b&gt;", h)

    def test_odd_shape_dropped(self):
        self.assertEqual(self.R["badCpu"], self.R["bare"])
        self.assertNotIn("noRepo", self.R)   # undefined -> key absent in JSON


if __name__ == "__main__":
    unittest.main()
