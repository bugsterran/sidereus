"""Settings fixes: «Terminal integration» buttons never reach the session [data-term] jump (88d-term.js),
notify save/read share localStorage (43-notify.js), saver target time accepts a one-digit hour like sidereus/saver.py."""
import json
import os
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SRC = i18n_prelude("'en'", ("T",)) + r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
const js = f => fs.readFileSync(path.join(ROOT, 'web', 'js', f), 'utf8');
const L = [], store = {};
const c = {T, softErr: () => {}, tabGet: (k, d) => d, lsGet: (k, d) => d, lsSet: () => true,
  esc: s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'),
  matchMedia: () => ({matches: false, addEventListener: () => {}}),
  localStorage: {getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }},
  UIS: {setItem: () => { throw new Error('UIS used'); }, getItem: () => null},
  document: {addEventListener: (t, f, cap) => L.push([t, f, cap]), documentElement: {dataset: {}, style: {setProperty(){}, removeProperty(){}}},
    getElementById: () => null, querySelector: () => null},
  getJSON: async () => ({ok: true}), LANG: 'en',
  tonePref: () => 'black', sesdrPinned: () => false, FS_OPTS: [100], fsPref: () => 100, wkSide: () => true, mpActs: () => ({})};
vm.createContext(c);
vm.runInContext(js('88d-term.js') + '\n' + js('90-settings.js') + '\n' + js('43-notify.js'), c);
const R = {};
const html = vm.runInContext('cfgPaneDisp()', c);
// A minimal closest(): matches '[attr]' selectors against the attributes of one settings terminal button.
const btn = (html.match(/<button[^>]*data-termapp="iterm"[^>]*>/) || [''])[0];
const attrs = new Set((btn.match(/\s([a-z-]+)=/g) || []).map(s => s.trim().slice(0, -1)));
R.btn = btn;
R.hasOldAttr = /data-term="/.test(html);
let jumped = 0;
vm.runInContext('termGo = () => { __J(); }', Object.assign(c, {__J: () => { jumped++; }}));
const target = {closest: sel => { const m = /^\[([a-z-]+)\]$/.exec(sel); return m && attrs.has(m[1]) ? {getAttribute: () => 'x'} : null; }};
let stopped = false;
for(const [t, f, cap] of L) if(t === 'click' && cap) f({target, preventDefault(){}, stopPropagation(){ stopped = true; }});
R.jumped = jumped; R.stopped = stopped;
R.act = typeof vm.runInContext('cfgActs()', c).termapp;
vm.runInContext("ntfSave({on: true, visible: true})", c);
R.notify = vm.runInContext('ntfPref()', c);
const rx = new Function('return ' + js('90-settings.js').match(/if\((\/\^\(\[01\][^\n]*?\$\/)\.test\(t\)\)/)[1])();
R.hhmm = ['9:05', '09:05', '23:59', '25:00', '24:00', '9:5'].map(s => rx.test(s));
console.log(JSON.stringify(R));
"""


def run():
    r = subprocess.run(node_e("const ROOT = " + json.dumps(ROOT) + ";\n" + SRC), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SettingsS1Fixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = run()

    def test_terminal_setting_button_does_not_reach_term_jump(self):
        self.assertIn("data-termapp", self.r["btn"])
        self.assertFalse(self.r["hasOldAttr"])
        self.assertEqual(self.r["jumped"], 0)
        self.assertFalse(self.r["stopped"])
        self.assertEqual(self.r["act"], "function")

    def test_notify_save_then_read_round_trip(self):
        self.assertEqual(self.r["notify"], {"on": True, "visible": True})

    def test_saver_target_time_matches_server(self):
        from tests._load import sidereus
        srv = sidereus("saver")._SAVER_HHMM
        cases = ['9:05', '09:05', '23:59', '25:00', '24:00', '9:5']
        self.assertEqual(self.r["hhmm"], [True, True, True, False, False, False])
        self.assertEqual(self.r["hhmm"], [bool(srv.match(s)) for s in cases])


if __name__ == "__main__":
    unittest.main()
