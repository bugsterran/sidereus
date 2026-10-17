"""Settings modal (web/js/90-settings.js + 90b-mypref.js): dependent rows disabled, per-kind alert rows only under
«사용자 지정», «고급» fold for server rows. One node run with stubbed globals (no live browser data)."""
import json
import os
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SRC = i18n_prelude("'ko'", ("T", "KE", "U")) + r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
const js = f => fs.readFileSync(path.join(ROOT, 'web', 'js', f), 'utf8');
const mem = {};
const c = {T, KE, U, softErr: () => {}, tabGet: (k, d) => d,
  lsGet: (k, d) => k in mem ? mem[k] : d, lsSet: (k, v) => { mem[k] = String(v); return true; },
  lsDel: k => { delete mem[k]; return true; },
  esc: s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'),
  matchMedia: () => ({matches: false, addEventListener: () => {}}),
  document: {documentElement: {dataset: {}, style: {p: {}, setProperty(k, v){ this.p[k] = v; }, removeProperty(k){ delete this.p[k]; }}}, getElementById: () => null, querySelector: () => null},
  APOL: {preset: 'imp', group: true, kinds: {}}, apolOf: () => 'badge', unreadOnly: false,
  NTF: false, ntfOn(){ return this.NTF; }, ntfPref: () => ({visible: false}), ntfHint: () => '',
  mpfPane: () => '', moonReal: () => false, SVSW: {mode: 'auto', goal: null}, SVST: {}, SVERR: '', LANG: 'ko'};
c.ntfOn = c.ntfOn.bind(c);
vm.createContext(c);
vm.runInContext('Date.now = () => 1790000000000', c);   // fixed clock inside the context (its own Date)
vm.runInContext(js('90-settings.js') + '\n' + js('90b-mypref.js'), c);
const R = {};
const row = (h, lab) => { const i = h.indexOf('<b>' + lab + '</b>'); return i < 0 ? '' : h.slice(h.lastIndexOf('<div class="cfgr', i), h.indexOf('</div></div>', i)); };
R.alImp = vm.runInContext('cfgPaneAl()', c);
c.APOL.preset = 'custom'; c.NTF = true;
R.alCustom = vm.runInContext('cfgPaneAl()', c);
R.svAuto = row(vm.runInContext('cfgPaneSv()', c), '목표 소진율');
c.SVSW = {mode: 'off', goal: null};
R.svOff = row(vm.runInContext('cfgPaneSv()', c), '목표 소진율');
R.osvOff = row(R.alImp, '탭이 보일 때도 알림');
R.osvOn = row(R.alCustom, '탭이 보일 때도 알림');
vm.runInContext("MPSRV = {ok: true, keys: {viewer_me: {value: 'me', default: '', src: 'default'}, port: {value: 8799, default: 8799, src: 'default'},"
  + " compact_history: {value: [['2026-09-01', 5]], default: [], src: 'file'}, saver_hook_dir: {value: '/x', default: '/x', src: 'default'}}}; MPSRV_AT = 1790000000000;", c);
R.me = vm.runInContext('cfgPaneMe()', c);
mem['sidereus.cfgadv'] = '1';
R.meOpen = vm.runInContext('cfgPaneMe()', c);
// saver mode row: one bar, «목표 시각» reveals the HH:MM input without sending
c.SVSW = {mode: 'auto', goal: null};
R.mode0 = row(vm.runInContext('cfgPaneSv()', c), '작동 모드');
R.paneSv = vm.runInContext('cfgPaneSv()', c);
const sent = []; c.svSet = b => { sent.push(b); };
vm.runInContext("cfgActs().svm('pace')", c);
R.modePick = row(vm.runInContext('cfgPaneSv()', c), '작동 모드');
c.SVSW = {mode: 'pace', until: '18:30', goal: null};
R.modePace = row(vm.runInContext('cfgPaneSv()', c), '작동 모드');
vm.runInContext("cfgActs().svm('auto')", c);
// «목표 한도 도달 시» saves on click like the other saver rows: confirm must not be called
c.confirm = () => { throw new Error('confirm called'); };
vm.runInContext("cfgActs().svl('block')", c);
R.svSent = sent;
vm.runInContext('SVOK = 1', c);
R.svOk = vm.runInContext('cfgPaneSv()', c);
vm.runInContext("SVOK = 0; SVERR = '저장 실패: x'", c);
R.svErr = vm.runInContext('cfgPaneSv()', c);
// «글자 크기»: fsPref normalisation, setFs writes --fs + mbFs, app-head seed agrees with fsPref
const st = c.document.documentElement.style;
R.fsNorm = ['90', '100', '110', '125', 'abc', '120', ''].map(v => { mem.mbFs = v; return vm.runInContext('fsPref()', c); });
delete mem.mbFs; R.fsNone = vm.runInContext('fsPref()', c);
vm.runInContext('setFs(110)', c); R.fs110 = [st.p['--fs'], mem.mbFs];
vm.runInContext('setFs(100)', c); R.fs100 = ['--fs' in st.p, 'mbFs' in mem];
Object.assign(c, {sesdrPinned: () => false, wkSide: () => true, BURN_OPEN: false, TERM_APP: 'auto'});
R.fsRow = row(vm.runInContext('cfgPaneDisp()', c), '글자 크기');
const seed = fs.readFileSync(path.join(ROOT, 'web', 'app-head.js'), 'utf8').split('\n').find(l => l.includes('UIS.mbFs'));
R.fsSeed = ['90', '100', '110', '125', 'abc', undefined].map(v => {
  const hp = {}, h = {UIS: v === undefined ? {} : {mbFs: v}, document: {documentElement: {style: {setProperty: (k, x) => { hp[k] = x; }}}}};
  vm.createContext(h); vm.runInContext(seed, h);
  if(v === undefined) delete mem.mbFs; else mem.mbFs = v;
  return [hp['--fs'] === undefined ? 1 : +hp['--fs'], vm.runInContext('fsPref()', c) / 100];
});
process.stdout.write(JSON.stringify(R));
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SettingsPane(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r = subprocess.run(node_e("const ROOT = %s;\n" % json.dumps(ROOT) + SRC), capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        cls.R = json.loads(r.stdout)

    def test_kind_rows_only_custom(self):
        self.assertNotIn("data-ak=", self.R["alImp"])
        self.assertEqual(self.R["alCustom"].count('data-ak="ask:'), 3)   # badge · list · hide
        self.assertIn("알림 목록에 보일 카드", self.R["alImp"])
        self.assertNotIn("알람", self.R["alImp"])

    def test_visible_row_depends_on_notify(self):
        self.assertIn(" dis", self.R["osvOff"])
        self.assertIn("disabled", self.R["osvOff"])
        self.assertNotIn("disabled", self.R["osvOn"])

    def test_goal_row_depends_on_auto(self):
        self.assertNotIn("disabled", self.R["svAuto"])
        self.assertIn("목표 없음", self.R["svAuto"])
        self.assertIn('<button disabled class="strp', self.R["svOff"])
        self.assertIn("<input disabled", self.R["svOff"])

    def test_advanced_fold(self):
        me = self.R["me"]
        self.assertNotIn("터미널 연동", me)
        self.assertNotIn("data-mpgo", me)
        self.assertIn("<details class=mpadv>", me)
        adv = me[me.index("<details"):me.index("</details>")]
        for k in ("port", "saver_hook_dir"):
            self.assertIn('data-mpin="%s"' % k, adv)
        self.assertNotIn('data-mpin="compact_history"', me)    # display-only
        self.assertIn("자동 압축 이력", adv)
        self.assertLess(me.index('data-mpin="viewer_me"'), me.index("<details"))
        self.assertIn("<details class=mpadv open>", self.R["meOpen"])

    def test_mode_row_merged(self):
        m0, pick, pace = self.R["mode0"], self.R["modePick"], self.R["modePace"]
        for v in ('auto', 'pace', 'on1', 'on4', 'off'):
            self.assertIn('data-svm="%s"' % v, m0)
        self.assertLess(m0.index('data-svm="pace"'), m0.index('data-svm="on1"'))
        self.assertLess(m0.index('data-svm="on4"'), m0.index('data-svm="off"'))
        self.assertNotIn("svpt", m0)
        self.assertNotIn("<b>목표 시각</b>", self.R["paneSv"])   # no separate row any more
        self.assertIn("id=svpt", pick)
        self.assertIn('class="strp on" data-svm="pace"', pick)
        self.assertNotIn('data-svp="clear"', pick)
        self.assertIn('value="18:30"', pace)
        self.assertIn('data-svp="clear"', pace)
        self.assertEqual(self.R["svSent"], [{"mode": "auto"}, {"limit": "block"}])   # picking 목표 시각 sends nothing; limit saves on click

    def test_saver_saved_note(self):
        self.assertIn("— 적용됨 · 모든 세션", self.R["svOk"])
        self.assertIn("— 저장 실패: x", self.R["svErr"])
        self.assertNotIn("적용됨", self.R["svErr"])

    def test_text_size(self):
        self.assertEqual(self.R["fsNorm"], [90, 100, 110, 125, 100, 100, 100])
        self.assertEqual(self.R["fsNone"], 100)
        self.assertEqual(self.R["fs110"], ["1.1", "110"])
        self.assertEqual(self.R["fs100"], [False, False])   # 100 = nothing stored, no --fs
        for n in (90, 100, 110, 125):
            self.assertIn('data-fs="%d"' % n, self.R["fsRow"])
        for a, b in self.R["fsSeed"]:   # first-paint seed == fsPref, or the page flashes
            self.assertEqual(a, b)

if __name__ == "__main__":
    unittest.main()
