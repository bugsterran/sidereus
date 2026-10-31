"""CLI hooks «Connect» notice (web/js/90f-hookconn.js): rows from a stub /api/hooks/connect, hidden when connected or after «Later»,
Connect -> dry preview -> «Apply» posts the base, 409 message, paths escaped, ko entries present, nothing at all when FEATS.diag === false."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = {"ok": True, "plats": [
    {"plat": "cursor", "name": "Cursor", "state": "missing", "file": "~/.cursor/<h>.json", "can": True, "why": "", "approve": ""},
    {"plat": "codex", "name": "Codex", "state": "partial", "file": "~/.codex/hooks.json", "can": True, "why": "", "approve": "/hooks"},
    {"plat": "gemini", "name": "Gemini", "state": "connected", "file": "~/.gemini/settings.json", "can": False, "why": "", "approve": ""}]}
DATA_NOCAN = {"ok": True, "plats": [{"plat": "cursor", "name": "Cursor", "state": "missing", "file": "~/.cursor/hooks.json", "can": False, "why": "no <ext-hooks>"}]}

SRC = i18n_prelude("'ko'", ("T",)) + r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
const js = f => fs.readFileSync(path.join(ROOT, 'web', 'js', f), 'utf8');
const LS = {}, W = [];
const c = {T, softErr: () => {}, lsGet: (k, d) => k in LS ? LS[k] : d, lsSet: (k, v) => { LS[k] = String(v); return true; },
  esc: s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'),
  aiLogo: k => '<i class="ailg ailg-' + k + '"></i>', diffHtml: s => '<table>' + c.esc(s) + '</table>', agLang: () => 'json',
  setHtml: (el, h) => { el.html = h; (el.hist = el.hist || []).push(h); return true; },
  document: {addEventListener: () => {}, activeElement: null, querySelectorAll: () => W},
  GETS: [], POSTS: [], REPLY: null, FEATS: {}};
c.getJSON = u => { c.GETS.push(u); const d = c.DATA; return c.HOLD ? new Promise(r => { c.release = () => r(d); }) : Promise.resolve(d); };   // HOLD: reply captured now, delivered later
c.postJSON = async (u, b) => { c.POSTS.push([u, b]); const r = c.REPLY; if(r instanceof Error) throw r; return r; };
c.DATA = DATA;
vm.createContext(c);
vm.runInContext(js('90f-hookconn.js'), c);
const tick = () => new Promise(r => setTimeout(r, 0));
(async () => {
  const R = {};
  R.first = vm.runInContext("hcRow('pl')", c);
  await tick();
  R.gets = c.GETS.slice();
  R.pl = vm.runInContext("hcInner('pl')", c);
  R.dx = vm.runInContext("hcInner('dx')", c);
  W.push({dataset: {hcw: 'dx'}, contains: () => false, querySelector: () => null});
  c.REPLY = {ok: true, diff: '+  "hooks": <x>', base: 'abc', adds: 2};
  await vm.runInContext("hcAct('go', 'cursor')", c);
  R.prev = vm.runInContext("hcInner('dx')", c);
  R.plPrev = vm.runInContext("hcInner('pl')", c);               // the list never shows the diff
  R.painted = W[0].html === R.prev;
  c.REPLY = {ok: true, changed: true};
  const g0 = c.GETS.length, conn = p => ({ok: true, plats: c.DATA.plats.map(x => x.plat === p ? Object.assign({}, x, {state: 'connected', can: false, why: ''}) : x)});
  c.DATA = conn('cursor');
  const ap = vm.runInContext("hcAct('apply', 'cursor')", c);
  R.posts = c.POSTS.slice();
  await ap;
  R.done = W[0].hist[W[0].hist.length - 1];                    // painted in place before the reload lands
  await tick();
  R.refetch = c.GETS.length - g0;
  R.afterReload = vm.runInContext("hcInner('pl')", c);
  c.REPLY = {ok: true, diff: '+x', base: 'b2'};
  await vm.runInContext("hcAct('go', 'codex')", c);
  c.HOLD = true;
  const stale = vm.runInContext("hcLoad(true)", c);            // poll in flight with the pre-write reply
  c.HOLD = false;
  c.REPLY = {ok: true, changed: true, approve: '/hooks'};
  c.DATA = conn('codex');
  const g1 = c.GETS.length;
  await vm.runInContext("hcAct('apply', 'codex')", c);
  c.release(); await stale; await tick(); await tick();
  R.raceRefetch = c.GETS.length - g1;                          // the forced reload ran after the stale reply
  R.raceState = vm.runInContext("HC.plats.find(x => x.plat === 'codex').state", c);
  R.approve = vm.runInContext("hcInner('pl')", c);
  R.approveDx = vm.runInContext("hcInner('dx')", c);
  await vm.runInContext("hcLoad(true)", c);
  R.approveNext = vm.runInContext("hcInner('pl')", c);       // still pinned: only «Close» drops it
  await vm.runInContext("hcAct('cancel', 'codex')", c);
  R.closed = vm.runInContext("hcInner('pl')", c);
  c.DATA = DATA;
  await vm.runInContext("hcLoad(true)", c);
  vm.runInContext("delete HCS.codex", c);
  c.REPLY = {ok: true, diff: '+x', base: 'b3'};
  await vm.runInContext("hcAct('go', 'codex')", c);
  const e = new Error('HTTP 409'); e.status = 409; e.body = {ok: false, err: 'changed'}; c.REPLY = e;
  await vm.runInContext("hcAct('apply', 'codex')", c);
  R.conflict = vm.runInContext("hcInner('pl')", c);
  await vm.runInContext("hcAct('later', 'codex')", c);
  R.later = vm.runInContext("hcInner('pl')", c);
  R.laterDx = vm.runInContext("hcInner('dx')", c);
  R.ls = Object.assign({}, LS);
  c.DATA = DATA_NOCAN;
  await vm.runInContext("hcLoad(true)", c);
  R.nocanPl = vm.runInContext("hcInner('pl')", c);
  R.nocanDx = vm.runInContext("hcInner('dx')", c);
  vm.runInContext("CFGCAT = 'disp'; OPENED = 0; TABS = {}; tabSet = (k, v) => { TABS[k] = v; }; cfgOpen = () => { OPENED++; }; delete HCS.cursor", c);
  c.DATA = DATA; await vm.runInContext("hcLoad(true)", c);
  c.REPLY = {ok: true, diff: '+o', base: 'b4'}; const p0 = c.POSTS.length;
  await vm.runInContext("hcAct('open', 'cursor')", c);
  R.open = vm.runInContext("[CFGCAT, OPENED, TABS['sidereus.cfgcat'], HCS.cursor.st]", c);
  R.openPosts = c.POSTS.slice(p0);
  c.GETS.length = 0;
  R.off = vm.runInContext("FEATS = {diag: false}; [hcRow('pl'), hcRow('dx'), hcInner('dx')]", c);
  await tick();
  R.offGets = c.GETS.length;
  console.log(JSON.stringify(R));
})().catch(e => { console.error(e); process.exit(1); });
"""


def run():
    js = "const ROOT = " + json.dumps(ROOT) + ", DATA = " + json.dumps(DATA) + ", DATA_NOCAN = " + json.dumps(DATA_NOCAN) + ";\n" + SRC
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class HookConnNotice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = run()

    def test_fetch_once_and_empty_wrapper_first(self):
        self.assertEqual(self.r["gets"], ["/api/hooks/connect"])
        self.assertIn('data-hcw="pl"></div>', self.r["first"])   # empty until the GET lands, filled in place

    def test_connected_hidden_others_shown(self):
        pl = self.r["pl"]
        self.assertIn('data-hcp="cursor"', pl)
        self.assertIn('data-hcp="codex"', pl)
        self.assertNotIn("gemini", pl)
        self.assertIn("Sidereus 훅이 연결되지 않음", pl)
        self.assertIn("일부만 연결됨", pl)
        self.assertIn("ailg-cu", pl)
        self.assertNotIn(">Cursor<", pl)                         # logo only, no CLI name text
        self.assertIn("나중에", pl)
        self.assertNotIn('data-hca=later', self.r["dx"])          # «Later» is a first-screen control only
        self.assertIn("CLI 훅", self.r["dx"])

    def test_paths_escaped(self):
        self.assertIn("~/.cursor/&lt;h&gt;.json", self.r["pl"])
        self.assertNotIn("<h>", self.r["pl"])

    def test_connect_previews_then_apply_posts_base(self):
        prev = self.r["prev"]
        self.assertIn("data-hca=apply", prev)
        self.assertIn("&lt;x&gt;", prev)                          # diff text escaped
        self.assertIn("적용을 누르기 전에는", prev)
        self.assertTrue(self.r["painted"])
        posts = self.r["posts"]
        self.assertEqual(posts[0], ["/api/hooks/connect", {"plat": "cursor", "dry": True}])
        self.assertEqual(posts[1], ["/api/hooks/connect", {"plat": "cursor", "dry": False, "base": "abc"}])
        self.assertIn("다시 시작하세요", self.r["done"])
        self.assertIn("/hooks", self.r["approve"])
        self.assertIn("data-hca=cancel", self.r["approve"])     # dismissable

    def test_apply_refetches_and_drops_connected_row(self):
        self.assertIn("다시 시작하세요", self.r["done"])
        self.assertEqual(self.r["refetch"], 1)
        self.assertNotIn('data-hcp="cursor"', self.r["afterReload"])
        self.assertIn('data-hcp="codex"', self.r["approve"])
        self.assertIn("/hooks", self.r["approveDx"])
        self.assertIn("/hooks", self.r["approveNext"])
        self.assertNotIn('data-hcp="codex"', self.r["closed"])

    def test_stale_inflight_reply_does_not_drop_hint(self):
        self.assertEqual(self.r["raceRefetch"], 1)
        self.assertEqual(self.r["raceState"], "connected")
        self.assertIn("/hooks", self.r["approve"])

    def test_pl_connect_opens_diagnostics(self):
        self.assertIn("data-hca=open", self.r["pl"])
        self.assertNotIn("data-hca=go", self.r["pl"])
        self.assertIn("data-hca=go", self.r["dx"])
        self.assertNotIn("<pre>", self.r["plPrev"])
        self.assertNotIn("data-hca=apply", self.r["plPrev"])
        self.assertEqual(self.r["open"], ["dx", 1, "dx", "prev"])
        self.assertEqual(self.r["openPosts"], [["/api/hooks/connect", {"plat": "cursor", "dry": True}]])   # dry only

    def test_conflict_message(self):
        self.assertIn("다시 미리보기", self.r["conflict"])

    def test_later_hides_on_first_screen_only(self):
        self.assertNotIn('data-hcp="codex"', self.r["later"])
        self.assertIn('data-hcp="cursor"', self.r["later"])
        self.assertIn('data-hcp="codex"', self.r["laterDx"])
        self.assertEqual(self.r["ls"].get("sidereus.hclater.codex"), "1")

    def test_cannot_connect_hint_in_diagnostics_only(self):
        self.assertEqual(self.r["nocanPl"], "")
        self.assertIn("no &lt;ext-hooks&gt;", self.r["nocanDx"])
        self.assertNotIn("data-hca=go", self.r["nocanDx"])

    def test_feature_off_renders_and_fetches_nothing(self):
        self.assertEqual(self.r["off"], ["", "", ""])
        self.assertEqual(self.r["offGets"], 0)

    def test_ko_entries(self):
        with open(os.path.join(ROOT, "web", "js", "90f-hookconn.js"), encoding="utf-8") as fh:
            src = fh.read()
        with open(os.path.join(ROOT, "web", "js", "06-i18n-zt-hookconn.js"), encoding="utf-8") as fh:
            ko = fh.read()
        for s in set(re.findall(r"T\('([^']+)'\)", src)) - {"Apply", "Cancel", "Close", "Later", "Could not load"}:
            self.assertIn("'" + s + "':", ko, s)


if __name__ == "__main__":
    unittest.main()
