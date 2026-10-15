"""«내 방식» screen prefs (web/js/90b-mypref.js + 05-i18n.js mainView): normalisers, 'time' unhideable, day clamps,
start view 'last' default. One node run; UIS is an in-memory stub (no live browser data)."""
import json
import os
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_fn
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SRC = i18n_prelude("'ko'", ("T", "KE")) + r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
const R = {}, js = f => fs.readFileSync(path.join(ROOT, 'web', 'js', f), 'utf8');
const store = init => { const m = Object.assign({}, init);
  return {getItem: k => k in m ? m[k] : null, setItem: (k, v) => { m[k] = String(v); }, removeItem: k => { delete m[k]; }, _m: m,
          get mbMainView(){ return m.mbMainView; }, get mbStartView(){ return m.mbStartView; }, get mbLang(){ return m.mbLang; }}; };
function ctx(init, ss){
  const c = {T, softErr: () => {}, UIS: store(init), sessionStorage: ss ? store(ss) : undefined, document: {documentElement: {dataset: {}}, getElementById: () => null}};
  vm.createContext(c); return c;
}
// mainView at load (05-i18n.js)
const mv = (init, ss) => { const c = ctx(init, ss); vm.runInContext(TABF + '\n' + js('05-i18n.js') + ';this.MV = mainView;', c); return c.MV; };
R.mv = [mv({}), mv({mbMainView: 'chat'}), mv({mbMainView: 'chat', mbStartView: 'last'}), mv({mbMainView: 'chat', mbStartView: 'token'}),
        mv({mbMainView: 'br', mbStartView: 'bogus'}), mv({mbStartView: 'fail'})];
// per tab: this tab's own view beats mbStartView and the shared last view; a bogus one falls through
R.mvTab = [mv({mbMainView: 'chat', mbStartView: 'token'}, {mbMainView: 'struct'}), mv({mbMainView: 'chat'}, {mbMainView: 'nope'})];
// 90b helpers
const c = ctx({}); vm.runInContext(js('90b-mypref.js') + ';this.X = {mpStart, mpOrder, mpOrderAct, mpTabs, mpStock, mpParse, MP_TABS};', c);
const X = c.X;
R.start = [X.mpStart(undefined), X.mpStart('last'), X.mpStart('retro'), X.mpStart('work'), X.mpStart('constructor')];
R.tabs0 = X.mpTabs();
c.UIS.setItem('mbTabs', JSON.stringify({order: ['retro', 'chat', 'nope', 'chat'], hide: ['time', 'chat', 'zz', 'chat']}));
R.tabs1 = X.mpTabs();
c.UIS.setItem('mbTabs', '{broken');
R.tabs2 = X.mpTabs();
R.hideTime = X.mpOrderAct(X.mpOrder(null, X.MP_TABS, 'time'), X.MP_TABS, 'time', 'time', 'hide');
R.up = X.mpOrderAct(X.mpOrder(null, X.MP_TABS, 'time'), X.MP_TABS, 'time', 'pipe', 'up');
R.upTop = X.mpOrderAct(X.mpOrder(null, X.MP_TABS, 'time'), X.MP_TABS, 'time', 'time', 'up');
R.allHidden = X.mpOrder({hide: X.MP_TABS}, X.MP_TABS, null);
R.stock = [X.mpStock(X.mpOrder(null, X.MP_TABS, 'time'), X.MP_TABS), X.mpStock(R.up, X.MP_TABS)];
R.parse = [X.mpParse('300', 300), X.mpParse('abc', 300)[0], X.mpParse('[["2026-09-01", 5]]', []), X.mpParse('[', [])[0], X.mpParse(' me ', 'x')];
// client copies of the prefs.py validators: the confirm preview is the stored value
const Y = vm.runInContext('({mpCheck, mpSrvErr})', c);
R.check = [Y.mpCheck('port', 1000), Y.mpCheck('port', 70000), Y.mpCheck('port', 8801), Y.mpCheck('port', 80)[0],
           Y.mpCheck('port', 8800), Y.mpCheck('port', 8800.5)[0], Y.mpCheck('viewer_me', '')[0], Y.mpCheck('default_room', 'a/b')[0],
           Y.mpCheck('default_room', 'cart'), Y.mpCheck('saver_hook_dir', 'rel/dir')[0], Y.mpCheck('saver_hook_dir', '~/a/../b')[0],
           Y.mpCheck('saver_hook_dir', '~/.claude/hooks'), Y.mpCheck('compact_history', []),
           Y.mpCheck('viewer_me', '   ')[0], Y.mpCheck('viewer_me', ' me '), Y.mpCheck('saver_hook_dir', '~foo/x')[0],
           Y.mpCheck('saver_hook_dir', '/' + 'a'.repeat(512))[0], Y.mpCheck('saver_hook_dir', '~'),
           Y.mpCheck('port', 99999), Y.mpCheck('cc_compact_window', 10), Y.mpCheck('cc_compact_window', 450000)];
R.srvErr = [Y.mpSrvErr('port must be an integer 1024..65535'), Y.mpSrvErr('weird')];
// «Preferences» Claude Code pane + confirm with other accounts' settings.json (stub renderers; no DOM)
Object.assign(c, {esc: s => String(s).replace(/</g, '&lt;'), cfgSet: (a, b, x) => '[' + a + '|' + b + '|' + x + ']', cfgSeg: (a, x) => x,
  cfgOpt: (a, v, l, on) => '<' + v + (on ? '*' : '') + '>', paintCfg: () => {}, fmtTok: String,
  confirm: m => { c.CONF = m; return false; }, postJSON: async () => ({ok: true})});
const cc = (accts) => { vm.runInContext('MPSRV = ' + JSON.stringify({ok: true, cc_path: '/p/settings.json',
  keys: {cc_auto_compact: {value: true, path: '/p/settings.json'}, cc_compact_window: {value: 450000, path: '/p/settings.json'}}}) + ';'
  + (accts ? 'MPSRV.cc_accts = ' + JSON.stringify(accts) + ';' : '') + "MPERR = {}; MPDONE = {}; MPACON = null; MPACD = {}; MPANOTE = '';", c); return vm.runInContext('mpCcPane()', c); };
const same = {label: 'work', path: '/w/settings.json', auto: true, window: 450000, err: null};
R.ccPane = [cc(null), cc([]), cc([same]), cc([Object.assign({}, same, {window: 300000})]), cc([Object.assign({}, same, {label: '<x>', err: 'symlink'})])];
// «Per account»: forced off shows the old note line; an err row shows its reason
cc([Object.assign({}, same, {window: 300000})]); R.ccOff = vm.runInContext('MPACON = false; mpCcPane()', c);
// dry preview lists only "change" rows, skipped rows name the reason; nothing changed -> note, no confirm, no real POST
const POSTS = []; let DRY = null;
c.postJSON = async (u, b) => { POSTS.push(b); return b.dry ? DRY : {ok: true, files: []}; };
const fl = (label, path, st, err) => ({label: label, path: path, primary: label === 'me', before: {auto: true, window: 450000},
  after: {auto: true, window: st === 'change' ? 300000 : 450000}, status: st, err: err || null});
cc([same, {label: 'gone', path: '/g/settings.json', auto: true, window: 450000, err: null}]);
DRY = {ok: true, dry: true, files: [fl('me', '/p/settings.json', 'same'), fl('work', '/w/settings.json', 'change'), fl('gone', '/g/settings.json', 'skipped', 'symlink')]};
c.CONF = null;
vm.runInContext('mpAcctApply()', c).then(() => {
  R.prev = c.CONF; R.prevPosts = POSTS.map(b => [b.key, b.dry, b.accts.length]);
  POSTS.length = 0; c.CONF = null;
  DRY = {ok: true, dry: true, files: [fl('me', '/p/settings.json', 'same'), fl('gone', '/g/settings.json', 'skipped', 'symlink')]};
  return vm.runInContext('mpAcctApply()', c);
}).then(() => {
  R.none = [c.CONF, POSTS.length, vm.runInContext('MPANOTE', c), vm.runInContext('MPACON = true; mpCcPane()', c)];
  POSTS.length = 0;
  vm.runInContext("MPACD = {'/w/settings.json': {auto: true, win: '10'}}", c);
  return vm.runInContext('mpAcctApply()', c);
}).then(() => { R.badWin = [POSTS.length, vm.runInContext('MPERR.cc_acct1', c)]; process.stdout.write(JSON.stringify(R)); });
cc([same, {label: 'bad', path: '/b/settings.json', auto: true, window: null, err: 'settings.json not found'}]);
vm.runInContext("mpCcSet('cc_auto_compact', false)", c);
R.ccConf = c.CONF;
// «Main account» select (acctList stub: null under 2 accounts); mpma writes / clears mbMainAcct and repaints
Object.assign(c, {cfgSel: (k, lab, items, cur) => k + '{' + items.map(x => c.esc(x[0]) + '=' + c.esc(x[1]) + (x[0] === cur ? '*' : '')).join(',') + '}',
  buildSessions: () => { c.RD = (c.RD || 0) + 1; }, sesdrBadge: () => { c.BD = (c.BD || 0) + 1; }});
c.acctList = () => null;
for(const f of ['mainAcct', 'mainAcctOk']) vm.runInContext(js('40b-sessions-list.js').match(new RegExp('^function ' + f + '\\(.*(?:\\n(?!function ).*)*', 'm'))[0], c);
R.maNone = vm.runInContext('mpMainAcctRow()', c);
c.acctList = () => [{label: 'me', primary: true}, {label: 'work'}, {label: '<x>'}];
R.maRow = vm.runInContext('mpMainAcctRow()', c);
c.UIS.setItem('mbMainAcct', 'work');
R.maSel = vm.runInContext('mpMainAcctRow()', c);
c.UIS.setItem('mbMainAcct', 'me');
R.maPrim = vm.runInContext('mainAcct()', c);
c.UIS.setItem('mbMainAcct', 'gone');
R.maGone = vm.runInContext('mainAcct()', c);
const A = vm.runInContext('mpActs()', c);
A.mpma('work'); R.maPut = c.UIS.getItem('mbMainAcct');
A.mpma(''); R.maClr = c.UIS.getItem('mbMainAcct'); R.maRd = c.RD;
// The old «Only main account» row is gone (replaced by the per-view account picker, 40b acctPickHtml)
R.omRow = vm.runInContext('mpMainAcctRow()', c); R.omAct = 'mpom' in A;
"""

TABS = ['time', 'pipe', 'struct', 'br', 'token', 'hist', 'retro', 'chat']


@unittest.skipUnless(shutil.which("node"), "node not installed")
class MyPref(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tabf = "\n".join(js_fn(f) for f in ("tabRead", "tabStores", "tabOwn"))
        r = subprocess.run(node_e("const ROOT = %s;\nconst TABF = %s;\n" % (json.dumps(ROOT), json.dumps(tabf)) + SRC),
                           capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        cls.R = json.loads(r.stdout)

    def test_start_view_last_default(self):
        self.assertEqual(self.R["mv"], ["time", "chat", "chat", "token", "br", "time"])
        self.assertEqual(self.R["start"], ["last", "last", "retro", "last", "last"])
        self.assertEqual(self.R["mvTab"], ["struct", "chat"])

    def test_tabs_normalise(self):
        self.assertEqual(self.R["tabs0"], {"order": TABS, "hide": []})
        self.assertEqual(self.R["tabs1"]["order"], ["retro", "chat", "time", "pipe", "struct", "br", "token", "hist"])
        self.assertEqual(self.R["tabs1"]["hide"], ["chat"])     # 'time' dropped, unknown/dupes dropped
        self.assertEqual(self.R["tabs2"], {"order": TABS, "hide": []})

    def test_time_unhideable(self):
        self.assertEqual(self.R["hideTime"]["hide"], [])

    def test_order_move_and_stock(self):
        self.assertEqual(self.R["up"]["order"], ["pipe", "time"] + TABS[2:])
        self.assertEqual(self.R["upTop"]["order"], TABS)
        self.assertEqual(self.R["allHidden"]["hide"], [])
        self.assertEqual(self.R["stock"], [True, False])

    def test_parse_by_default_type(self):
        p = self.R["parse"]
        self.assertEqual(p[0], [True, 300])
        self.assertFalse(p[1])
        self.assertEqual(p[2], [True, [["2026-09-01", 5]]])
        self.assertFalse(p[3])
        self.assertEqual(p[4], [True, "me"])

    def test_check_matches_server_bounds(self):
        c = self.R["check"]
        # one rule for numbers: out of range is refused with the bound, never clamped
        self.assertEqual(c[0], [False, "최소 1024"])
        self.assertEqual(c[1], [False, "최대 65535"])
        self.assertEqual(c[2], [True, 8801])
        self.assertFalse(c[3])
        self.assertEqual(c[4], [True, 8800])
        self.assertEqual(c[5:8], [False, False, False])
        self.assertEqual(c[8], [True, "cart"])
        self.assertEqual(c[9:11], [False, False])
        self.assertEqual(c[11], [True, "~/.claude/hooks"])
        self.assertEqual(c[12], [True, []])
        self.assertFalse(c[13])                                    # blank after trim
        self.assertEqual(c[14], [True, "me"])                      # preview shows the trimmed text
        self.assertEqual(c[15:17], [False, False])                 # "~foo" and >512 chars, like prefs._v_dir
        self.assertEqual(c[17], [True, "~"])
        self.assertEqual(c[18], [False, "최대 65535"])
        self.assertEqual(c[19], [False, "최소 50000"])
        self.assertEqual(c[20], [True, 450000])

    def test_cc_pane_other_accounts(self):
        p = self.R["ccPane"]
        self.assertEqual(p[0], p[1])                     # no / empty cc_accts: same markup as before
        self.assertNotIn("<off*>", p[0])                 # no extras: no «Per account» switch
        self.assertIn("<off*><on>", p[2])                # same values: switch starts off, single-value rows stay
        self.assertIn("cc_compact_window:set", p[2])
        self.assertNotIn("work:", p[2])
        self.assertIn("<off*>", p[4])                    # an err row does not count as a difference
        self.assertIn("&lt;x>: symlink", p[4])           # label escaped
        self.assertIn("<div class=cfgpd>work: autoCompactWindow 300000</div>", self.R["ccOff"])

    def test_per_account_starts_on_when_different(self):
        p = self.R["ccPane"][3]
        self.assertIn("<off><on*>", p)
        self.assertIn("<go>", p)                         # «Apply to changed accounts»
        self.assertNotIn("cc_compact_window:set", p)     # single-value rows replaced
        self.assertIn('data-mpacct=0', p)
        self.assertIn('data-mpacct=1 type=number', p)
        self.assertIn('value="300000"', p)               # prefilled from the account's own value
        self.assertIn("[work|/w/settings.json|", p)

    def test_per_account_preview_only_changed(self):
        m = self.R["prev"]
        self.assertIn("work /w/settings.json\ntrue,450000 → true,300000", m)
        self.assertNotIn("me /p/settings.json", m)        # "same" rows are not listed
        self.assertIn("gone /g/settings.json\n건너뜀: symlink", m)
        self.assertEqual(self.R["prevPosts"], [["cc_accounts", True, 3]])   # confirm stub cancels: no real POST

    def test_per_account_none_changed(self):
        conf, posts, note, pane = self.R["none"]
        self.assertIsNone(conf)
        self.assertEqual(posts, 1)                        # dry only
        self.assertIn("바뀐 계정이 없습니다", note)
        self.assertIn("건너뜀: symlink", note)
        self.assertIn("바뀐 계정이 없습니다", pane)
        self.assertEqual(self.R["badWin"][0], 0)          # client check refuses before any POST
        self.assertIn("50000", self.R["badWin"][1])

    def test_cc_confirm_lists_every_file(self):
        m = self.R["ccConf"]
        self.assertLess(m.index("/p/settings.json\ntrue\n→ false"), m.index("/w/settings.json\ntrue\n→ false"))
        self.assertIn("/b/settings.json\n건너뜀: settings.json not found", m)

    def test_main_account_select(self):
        self.assertEqual(self.R["maNone"], "")                      # <2 accounts: no row
        self.assertIn("mpma{=", self.R["maRow"])
        self.assertIn(",work=work,", self.R["maRow"])
        self.assertIn("&lt;x>", self.R["maRow"])                   # label escaped (cfgSel esc), never through T()
        self.assertNotIn("me=me", self.R["maRow"])                 # primary is the default option only
        self.assertIn("mpma{=", self.R["maSel"])
        self.assertIn("work=work*", self.R["maSel"])
        self.assertEqual([self.R["maPrim"], self.R["maGone"]], ["", ""])

    def test_main_account_act(self):
        self.assertEqual(self.R["maPut"], "work")
        self.assertIsNone(self.R["maClr"])
        self.assertEqual(self.R["maRd"], 2)                        # repaint after each change

    def test_only_main_row_removed(self):
        self.assertNotIn("mpom", self.R["omRow"])
        self.assertFalse(self.R["omAct"])

    def test_server_error_korean(self):
        self.assertEqual(self.R["srvErr"], ["저장 실패: 1024~65535 사이 정수를 적으세요", "저장 실패: weird"])


if __name__ == "__main__":
    unittest.main()
