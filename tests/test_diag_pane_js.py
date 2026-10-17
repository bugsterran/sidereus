"""Settings «Diagnostics» pane (web/js/90e-diag.js + paintCfg categories in 90-settings.js): R1-R4 sections render from stub /api/diag data,
read-only (only «Refresh»), values escaped, ko entries present, category hidden when FEATS.diag === false."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = {"ok": True,
        "overlaps": [{"event": "Stop", "matcher": "", "src": "plugin", "name": "<evil>", "acct": "main", "cmd": "run <x>.sh"},
                     {"event": "Stop", "matcher": "Bash", "src": "user", "name": "notify", "acct": "work", "cmd": "say hi"},
                     {"event": "Stop", "matcher": "", "src": "user", "name": "inl", "acct": "main", "cmd": "inline shell"},
                     {"event": "Stop", "matcher": "", "src": "user", "name": "dict", "acct": "main", "cmd": "Plugins"}],
        "sidereus": {"Stop": ["mailbox_wake.py"], "PreToolUse": ["pl_flow.py"]},
        "silent": [{"plugin": "sp", "version": "1.2", "event": "SessionStart", "cmd": "sp.sh", "verdict": "never fires", "unread": ["tool_name", "x<y"]}],
        "plugins": [{"name": "sp", "market": "m", "version": "1.2", "accts": ["main", "work"], "on": True, "known": True, "checked": True},
                    {"name": "raw", "market": "m", "version": "0.1", "accts": ["main"], "on": True, "known": False, "checked": True}],
        "shadow": [{"proj": "/r/<p>", "claude": "/r/<p>/CLAUDE.md", "agents": "/r/<p>/AGENTS.md"}]}
TOOLS = {"ok": True, "tools": [
    {"id": "gitleaks", "installed": True, "version": "8.18.0<i>", "cmd": None, "net": "no"},
    {"id": "semgrep", "installed": True, "version": None, "cmd": None, "net": "registry"},
    {"id": "bandit", "installed": False, "version": None, "cmd": "pip install <bandit>", "net": "no"},
    {"id": "osv-scanner", "installed": False, "version": None, "cmd": "brew install osv-scanner", "net": "yes"},
    {"id": "npm", "installed": False, "version": None, "cmd": "nodejs.org", "net": "yes"}]}

SRC = i18n_prelude("'ko'", ("T",)) + r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
const js = f => fs.readFileSync(path.join(ROOT, 'web', 'js', f), 'utf8');
const c = {T, softErr: () => {}, tabGet: (k, d) => d, lsGet: (k, d) => d, lsSet: () => true,
  esc: s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'),
  matchMedia: () => ({matches: false, addEventListener: () => {}}),
  document: {documentElement: {dataset: {}, style: {setProperty(){}, removeProperty(){}}}, getElementById: () => null, querySelector: () => null},
  GETS: [], LANG: 'ko'};
c.getJSON = async u => { c.GETS.push(u); return u === '/api/sec-tools' ? TOOLS : DATA; };
vm.createContext(c);
vm.runInContext(js('90-settings.js') + '\n' + js('90e-diag.js'), c);
(async () => {
  const R = {};
  R.loading = vm.runInContext('cfgPaneDx()', c);
  await new Promise(r => setTimeout(r, 0));
  R.gets = c.GETS.slice();
  R.pane = vm.runInContext('cfgPaneDx()', c);
  R.gets2 = c.GETS.length;
  R.sec = vm.runInContext('dxSecTools(DXT.tools)', c);
  R.secErr = vm.runInContext("DXT = {err: '<t>'}; cfgPaneDx()", c);
  R.empty = vm.runInContext('DX = {ok: true}; cfgPaneDx()', c);
  R.err = vm.runInContext("DX = {err: '<boom>'}; cfgPaneDx()", c);
  const box = {querySelector: () => null, contains: () => false}, m = {hidden: false};
  c.document.getElementById = id => id === 'cfgm' ? m : id === 'cfgbox' ? box : null;
  vm.runInContext("vwLoad = () => []; cfgPaneMe = cfgPaneDisp = () => ''; cfgBind = () => {}; cfgShell = cats => { CATS = cats.map(x => x[0]); return ''; };", c);
  R.catsOn = vm.runInContext('FEATS = {}; paintCfg(); CATS', c);
  R.catsOff = vm.runInContext('FEATS = {diag: false}; paintCfg(); CATS', c);
  console.log(JSON.stringify(R));
})().catch(e => { console.error(e); process.exit(1); });
"""


def run():
    js = "const ROOT = " + json.dumps(ROOT) + ", DATA = " + json.dumps(DATA) + ", TOOLS = " + json.dumps(TOOLS) + ";\n" + SRC
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class DiagPane(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = run()

    def test_fetch_on_first_paint_only(self):
        self.assertIn("불러오는 중", self.r["loading"])
        self.assertEqual(self.r["gets"], ["/api/diag", "/api/sec-tools"])
        self.assertEqual(self.r["gets2"], 2)                      # repaint does not refetch

    def test_sections_r1_r4(self):
        h = self.r["pane"]
        self.assertIn("같은 이벤트의 훅", h)                        # R1
        self.assertLess(h.index("mailbox_wake.py"), h.index("notify"))   # Sidereus chips before other hooks
        self.assertIn("work · Bash", h)
        self.assertNotIn("pl_flow.py", h)                         # event without overlap is not listed
        self.assertIn("CLAUDE.md 가 AGENTS.md 를 가립니다", h)        # R2
        self.assertIn("/r/&lt;p&gt;/CLAUDE.md", h)
        self.assertIn("조용히 꺼짐", h)                            # R3
        self.assertIn("정적 추정", h)
        self.assertIn('class=dxw><b>sp 1.2</b> · SessionStart', h)
        self.assertIn("tool_name, x&lt;y", h)
        self.assertIn("플러그인", h)                               # R4
        self.assertEqual(h.count("확인됨"), 1)                     # unknown plugin gets no badge
        self.assertIn("main, work", h)

    def test_read_only_and_escaped(self):
        h = self.r["pane"]
        btns = re.findall(r"<button[^>]*>", h)
        self.assertEqual(len(btns), 3)                            # «Refresh» + «Copy» on the two missing rows with a command
        self.assertIn("data-dxr", btns[0])
        self.assertTrue(all("data-dxcp" in b for b in btns[1:]))
        self.assertIn(">갱신<", h)                              # shared ko entry (05-i18n.js)
        self.assertNotIn("<evil>", h)
        self.assertIn("&lt;evil&gt;", h)
        self.assertNotIn("<x>", h)
        self.assertIn("&lt;boom&gt;", self.r["err"])
        self.assertNotIn("<boom>", self.r["err"])

    def test_security_tools(self):
        h, rows = self.r["sec"], self.r["sec"].split("<li")[1:]
        self.assertIn("보안 도구", self.r["pane"])
        self.assertIn("설치됨 · 8.18.0&lt;i&gt;", rows[0])          # version escaped, never raw
        self.assertNotIn("<i>", h)
        self.assertIn("<span class=dxok>설치됨</span>", rows[1])     # installed, version null
        self.assertIn("레지스트리 규칙에 네트워크 필요", rows[1])
        self.assertIn("<code>pip install &lt;bandit&gt;</code>", rows[2])
        self.assertIn('data-dxcp="bandit"', rows[2])
        self.assertIn('data-dxcp="osv-scanner"', rows[3])
        self.assertIn("<code>nodejs.org</code>", rows[4])            # URL hint: plain text, no Copy
        self.assertNotIn("data-dxcp", rows[0] + rows[1] + rows[4])
        self.assertIn("Python 코드의 흔한 보안 문제", rows[2])
        self.assertIn("&lt;t&gt;", self.r["secErr"])

    def test_inline_cmd_allow_list(self):
        h = self.r["pane"]
        self.assertIn(">인라인 셸</code>", h)                      # fixed server label translated
        self.assertIn(">Plugins</code>", h)                       # arbitrary cmd is data: never through T()
        self.assertIn(">say hi</code>", h)

    def test_empty_states(self):
        h = self.r["empty"]
        for s in ("다른 훅이 없습니다", "CLAUDE.md 가 없습니다", "조용히 꺼진 훅이 없습니다", "설치된 플러그인이 없습니다"):
            self.assertIn(s, h)

    def test_category_gated_by_feature(self):
        self.assertIn("dx", self.r["catsOn"])
        self.assertNotIn("dx", self.r["catsOff"])

    def test_ko_entries(self):
        with open(os.path.join(ROOT, "web", "js", "90e-diag.js"), encoding="utf-8") as fh:
            src = fh.read()
        keys = set(re.findall(r"T\('([^']+)'\)", src))
        js = i18n_prelude("'ko'", ("T",)) + "console.log(JSON.stringify(" + json.dumps(sorted(keys)) + ".map(k => [k, T(k)])));"
        r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        for k, v in json.loads(r.stdout):
            self.assertNotEqual(k, v, k)


if __name__ == "__main__":
    unittest.main()
