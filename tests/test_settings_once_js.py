"""Settings writes run once per action (web/js/90b-mypref.js mpOnce) and focus survives a paintCfg repaint
(web/js/90-settings.js cfgFocusSel/cfgFocusBack). Fake DOM, stubbed confirm/postJSON; no live files or network."""
import json
import os
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_fn
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ONCE = i18n_prelude("'en'", ("T",)) + r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
const R = {}, CONF = [], POSTS = [];
const c = {T, softErr: () => {}, UIS: {getItem: () => null, setItem(){}, removeItem(){}}, esc: String, paintCfg: () => {},
  setTimeout: () => 0, document: {documentElement: {dataset: {}}, getElementById: () => null, querySelector: () => null},
  confirm: m => { CONF.push(m); return true; },
  postJSON: async (u, b) => { POSTS.push([u, b.key, b.dry === true]); await null;
    return b.key === 'cc_accounts' ? {ok: true, files: [{label: 'w', path: '/w', status: b.dry ? 'change' : 'written', before: {auto: true, window: null}, after: {auto: false, window: null}}]}
      : {ok: true, value: b.key === 'cc_auto_compact' ? false : 9}; }};
vm.createContext(c);
vm.runInContext(fs.readFileSync(path.join(ROOT, 'web', 'js', '90b-mypref.js'), 'utf8'), c);
const srv = () => vm.runInContext("MPSRV = {ok: true, cc_path: '/p', keys: {cc_auto_compact: {value: true, path: '/p'}, cc_compact_window: {value: null, path: '/p'},"
  + " port: {value: 8800, default: 9, src: 'file'}}, cc_accts: [{label: 'w', path: '/w', auto: true, window: null, err: null}]}; MPACD = {};", c);
(async () => {
  srv(); const A = vm.runInContext('mpActs()', c);
  await Promise.all([A.mpcc('cc_auto_compact:off'), A.mpcc('cc_auto_compact:off')]);   // double-click
  R.cc = [CONF.length, POSTS.slice()]; CONF.length = 0; POSTS.length = 0;
  srv(); await Promise.all([A.mpacs(), A.mpacs()]);
  R.acct = [CONF.length, POSTS.slice()]; CONF.length = 0; POSTS.length = 0;
  srv(); await Promise.all([A.mps('port:reset'), A.mps('port:reset')]);
  R.srv = [CONF.length, POSTS.slice()]; CONF.length = 0; POSTS.length = 0;
  srv(); await A.mpcc('cc_auto_compact:off');   // flag released after the first write
  R.again = [CONF.length, POSTS.length, vm.runInContext('Object.keys(MPBUSY).length', c)];
  process.stdout.write(JSON.stringify(R));
})();
"""

# Fake DOM: box children are plain objects; querySelector understands tag[attr="v"][attr]:not([disabled]) and [id="x"].
FOCUS = r"""
const document = {activeElement: null, body: {tag: 'body'}};
const mk = (tag, ds, id, dis) => ({tagName: tag.toUpperCase(), id: id || '', dataset: ds, disabled: !!dis,
  getAttribute(a){ return this.dataset[a.slice(5).replace(/-([a-z])/g, (_, x) => x.toUpperCase())]; }, focus(){ document.activeElement = this; }});
let kids = [];
const match = (e, s) => { let t = s.replace(/:not\(\[disabled\]\)$/, ''); if(t !== s && e.disabled) return false;
  const tag = /^[a-z]*/.exec(t)[0]; if(tag && e.tagName.toLowerCase() !== tag) return false;
  for(const m of t.matchAll(/\[([a-z-]+)(?:="([^"]*)")?\]/g)){ const v = m[1] === 'id' ? e.id || undefined : e.getAttribute(m[1]);
    if(v === undefined || (m[2] !== undefined && v !== m[2])) return false; }
  return true; };
const fresh = () => [mk('button', {mpcc: 'cc_auto_compact:on'}), mk('button', {mpcc: 'cc_auto_compact:off'}), mk('button', {cat: 'me'})];
const box = {focus(){ document.activeElement = this; }, contains: e => e === box || kids.includes(e),
  querySelector: s => kids.find(e => match(e, s)) || null, set innerHTML(v){ kids = fresh(); }};
document.getElementById = id => id === 'cfgm' ? {hidden: false} : box;
const CFGCAT = 'me', vwLoad = () => [], T = s => s, esc = s => s;
const cfgPaneDisp = () => '', cfgPaneAl = cfgPaneDisp, cfgPaneSv = cfgPaneDisp, cfgPaneTl = cfgPaneDisp,
  cfgPaneMe = cfgPaneDisp, cfgPaneVw = cfgPaneDisp, cfgShell = () => '', cfgBind = () => {};
""" + "\n".join(js_fn(f) for f in ("cfgFocusSel", "cfgFocusBack", "paintCfg")) + r"""
const R = {};
kids = fresh(); kids[1].focus(); paintCfg();
R.same = kids.indexOf(document.activeElement);                     // the new «Off» button, not BODY
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SettingsOnce(unittest.TestCase):
    def test_one_confirm_one_post_per_action(self):
        r = subprocess.run(node_e("const ROOT = %s;\n" % json.dumps(ROOT) + ONCE), capture_output=True, text=True, timeout=20, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        R = json.loads(r.stdout)
        self.assertEqual(R["cc"], [1, [["/api/prefs/set", "cc_auto_compact", False]]])
        self.assertEqual(R["acct"], [1, [["/api/prefs/set", "cc_accounts", True], ["/api/prefs/set", "cc_accounts", False]]])
        self.assertEqual(R["srv"], [1, [["/api/prefs/set", "port", False]]])
        self.assertEqual(R["again"], [1, 1, 0])

    def test_focus_survives_repaint(self):
        src = FOCUS + r"""
document.activeElement = document.body; paintCfg(); R.body = document.activeElement === document.body;   // focus was outside: untouched
kids = fresh(); kids[2].focus(); paintCfg(); R.tab = kids.indexOf(document.activeElement);
document.activeElement = kids[0]; kids[0].dataset = {mpx: 'gone'};
paintCfg(); R.box = document.activeElement === box;                // no equivalent control: the dialog box, never BODY
process.stdout.write(JSON.stringify(R));
"""
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        R = json.loads(r.stdout)
        self.assertEqual(R["same"], 1)
        self.assertTrue(R["body"])
        self.assertEqual(R["tab"], 2)
        self.assertTrue(R["box"])


if __name__ == "__main__":
    unittest.main()
