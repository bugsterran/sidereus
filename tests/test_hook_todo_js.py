"""Header «CLI hooks not connected» chip: 90f hcTodo (connectable, not connected, not «Later»), 25 buildTodo cell + click ->
hcAct('open', plat), hcPaint repaints the chip, ko entries present. Node vm with stubs; no live files."""
import json
import os
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_fn
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = {"ok": True, "plats": [
    {"plat": "cursor", "name": "Cursor", "state": "missing", "can": True},
    {"plat": "copilot", "name": "Copilot <x>", "state": "partial", "can": True},
    {"plat": "codex", "name": "Codex", "state": "missing", "can": False},
    {"plat": "gemini", "name": "Gemini", "state": "connected", "can": True}]}

SRC = i18n_prelude("'en'", ("T", "TV")) + r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
const LS = {}, ACTS = [];
const bar = {html: '', els: [], querySelectorAll(){ return this.els; }};
const bar2 = {html: '', querySelector: () => null, querySelectorAll: () => []};
const c = {T, TV, softErr: () => {}, lsGet: (k, d) => k in LS ? LS[k] : d, lsSet: (k, v) => { LS[k] = String(v); return true; },
  esc: s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'),
  setHtml: (el, h) => { el.html = h; return true; }, FEATS: {}, DATA: null,
  document: {addEventListener: () => {}, activeElement: null, querySelectorAll: () => [],
             getElementById: id => id === 'todo' ? bar : id === 'todo2' ? bar2 : null},
  alarmBadgeN: () => 0, staleThreads: () => [], attnBadgeN: () => 0, SESS: [], stFil: '', todoOpen: false, todoAsk: false,
  sesdrBadge: () => {}, rvTick: () => {}};
c.getJSON = async () => c.DATA;
vm.createContext(c);
vm.runInContext(fs.readFileSync(path.join(ROOT, 'web', 'js', '90f-hookconn.js'), 'utf8') + '\n' + FN, c);
c.hcAct = (a, p) => { ACTS.push([a, p]); };   // ⚠after load: the click must reach hcAct, not run the real preview
const cells = () => (bar.html.match(/class="td hk"[^>]*>.*?<\/b><\/span>/g) || []);
(async () => {
  const R = {};
  vm.runInContext('buildTodo()', c);
  R.none = cells().length;                          // nothing loaded yet: no chip
  c.DATA = DATA;
  vm.runInContext('hcLoad(true)', c);
  await new Promise(r => setTimeout(r, 0));
  R.todo = vm.runInContext('hcTodo()', c);
  R.cell = cells();                                 // hcPaint -> buildTodo painted it
  bar.els = [{dataset: {go: 'hooks'}}];
  vm.runInContext('buildTodo()', c);
  bar.els[0].onclick();
  R.acts = ACTS.slice();
  LS['sidereus.hclater.cursor'] = '1';
  vm.runInContext('hcPaint()', c);
  R.later = cells();
  LS['sidereus.hclater.copilot'] = '1';
  vm.runInContext('hcPaint()', c);
  R.allLater = cells().length;
  delete LS['sidereus.hclater.cursor']; delete LS['sidereus.hclater.copilot'];
  vm.runInContext("HC = {ok: true, plats: HC.plats.map(x => Object.assign({}, x, {state: 'connected'}))}; hcPaint()", c);
  R.connected = cells().length;
  vm.runInContext('FEATS = {diag: false}', c);
  R.off = vm.runInContext('hcTodo()', c).length;
  console.log(JSON.stringify(R));
})().catch(e => { console.error(e); process.exit(1); });
"""


def run():
    src = "const ROOT = %s, FN = %s, DATA = %s;\n" % (json.dumps(ROOT), json.dumps(js_fn("buildTodo")), json.dumps(DATA)) + SRC
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=30, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class HookTodoChip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run()

    def test_names_for_connectable_rows(self):
        R = self.R
        self.assertEqual(R["none"], 0)
        self.assertEqual([x["plat"] for x in R["todo"]], ["cursor", "copilot"])   # can:false and connected rows left out
        self.assertEqual(len(R["cell"]), 1)
        self.assertIn("CLI hooks not connected: Cursor · Copilot &lt;x&gt;", R["cell"][0])   # server name escaped
        self.assertIn("<b>2</b>", R["cell"][0])
        self.assertIn('data-go="hooks"', R["cell"][0])

    def test_click_opens_first_preview(self):
        self.assertEqual(self.R["acts"], [["open", "cursor"]])

    def test_later_drops_plat(self):
        R = self.R
        self.assertEqual(len(R["later"]), 1)
        self.assertNotIn("Cursor", R["later"][0])
        self.assertIn("<b>1</b>", R["later"][0])
        self.assertEqual(R["allLater"], 0)

    def test_zero_when_connected_or_off(self):
        self.assertEqual(self.R["connected"], 0)
        self.assertEqual(self.R["off"], 0)

    def test_ko_entries(self):
        with open(os.path.join(ROOT, "web", "js", "06-i18n-zzi-hooktodo.js"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("'CLI hooks not connected: {names}'", src)
        self.assertIn("State read from {name}'s record file", src)


if __name__ == "__main__":
    unittest.main()
