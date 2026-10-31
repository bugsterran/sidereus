"""Harness «Runtime behind latest patch» card (47d hnRuntime): R1 two lines per runtime · R2 stale · R3 no record · R4 next step + limit note."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import BASE, i18n, jconst
from tests._node import node_e

FNS = ("hnN", "hnPl", "hnWhen", "hnRtGet", "hnRtCls", "hnRtBrew", "hnRtCmd", "hnRtItem", "hnRtWorst", "hnRuntime")
CONSTS = ("esc", "HN_RTL", "HN_RTP", "HN_RTN", "HN_RTF")

SCEN = r"""
var HN = {fold: {}};
const it = (o) => Object.assign({rt: 'nodejs', path: '/opt/homebrew/bin/node', cls: 'homebrew', viewer: true, cur: '20.1.0', cycle: '20', level: 'fail',
  patch: {level: 'fail', target: '20.18.1', security: true, eol: '2026-04-30', eol_past: true},
  newest: {level: 'info', target: '24.2.0', behind_n: 2}, fix: 'brew-node'}, o);
const py = it({rt: 'python', path: '/usr/bin/python3', cls: 'system', viewer: false, cur: '3.9.6', cycle: '3.9', level: 'warn',
  patch: {level: 'warn', target: '3.9.23', security: false, eol: '2025-10-31', eol_past: true}, newest: {level: 'info', target: '3.14.0', behind_n: 5}, fix: 'system-python'});
const base = {state: 'behind', at: 1761600000, age_d: 1, stale: false, report: 'sec-2026.json', dev: false, offline: false, cmd: 'scripts/arch_checks.py --category security'};
R.none = hnRuntime({});
const keg = (o) => hnRtItem(it(Object.assign({patch: {level: 'warn', target: '20.18.1', security: false, eol: '2027-04-30', eol_past: false}}, o)), false);   // supported cycle: upgrade in place
R.cmds = [keg({path: '/opt/homebrew/opt/node@20/bin/node'}), keg({path: '/opt/homebrew/opt/node/bin/node'}),
  keg({rt: 'python', fix: 'brew-python', cycle: '3.12', path: '/opt/homebrew/opt/python@3.12/bin/python3.12', viewer: true}),
  keg({rt: 'python', fix: 'brew-python', cycle: '3.13', path: '/opt/homebrew/bin/python3', viewer: false}),
  keg({level: 'ok', patch: {level: 'ok', target: '20.1.0'}})];
// patch-ok + newer cycle: no command; EOL brew-python: install the newest cycle; system-python keeps its own line.
R.newer = keg({rt: 'python', fix: 'brew-python', cycle: '3.14', path: '/opt/homebrew/opt/python@3.14/bin/python3.14', level: 'info',
  patch: {level: 'ok', target: '3.14.10', eol: '2030-10-31', eol_past: false}, newest: {level: 'info', target: '3.15.1', behind_n: 1}});
R.eolpy = keg({rt: 'python', fix: 'brew-python', cycle: '3.10', path: '/opt/homebrew/opt/python@3.10/bin/python3.10', viewer: false,
  patch: {level: 'fail', target: '3.10.19', eol: '2026-10-31', eol_past: true}, newest: {level: 'info', target: '3.15.1', behind_n: 5}});
R.syspy = hnRtItem(py, false);
R.behind = hnRuntime({runtime: Object.assign({}, base, {items: [it({}), py]})});
R.stale = hnRuntime({runtime: Object.assign({}, base, {state: 'ok', stale: true, age_d: 12,
  items: [it({level: 'ok', patch: {level: 'ok', target: '20.1.0'}, newest: {level: 'ok', target: '20.1.0', behind_n: 0}})]})});
R.fresh = hnRuntime({runtime: Object.assign({}, base, {state: 'ok', items: [it({level: 'ok', patch: {level: 'ok', target: '20.1.0'}, newest: {level: 'ok', target: '20.1.0'}})]})});
R.rec = hnRuntime({runtime: {state: 'none', items: [], cmd: 'scripts/arch_checks.py --category security'}});
R.proto = hnRuntime({runtime: Object.assign({}, base, {items: [it({level: 'constructor', patch: {level: 'toString'}, fix: '__proto__', rt: 'constructor'})]})});
R.closed = R.behind;
HN.fold.rt = true;   // what 47b's toggle listener stores when the person opens it
R.reopen = hnRuntime({runtime: Object.assign({}, base, {items: [it({}), py]})});
HN.fold.rt = false;
R.warnonly2 = hnRuntime({runtime: Object.assign({}, base, {items: [it({patch: {level: 'warn', target: '20.18.1', eol: '2027-04-30', eol_past: false}, level: 'warn'})]})});
R.infoonly = hnRuntime({runtime: Object.assign({}, base, {state: 'ok', items: [it({level: 'info', patch: {level: 'ok', target: '24.2.0', eol: '2028-04-30', eol_past: false}, newest: {level: 'info', target: '25.1.0', behind_n: 1}})]})});
R.bad = hnRuntime({runtime: Object.assign({}, base, {state: 'unknown', items: [it({level: 'zz', patch: {level: 'x"y', target: '<b>1</b>'}, newest: {level: 'evil'}, fix: 'rm -rf', cur: '<i>2</i>', cycle: '<s>'})]})});
"""


def run():
    src = (BASE + i18n() + "\n" + "\n".join(jconst(c) for c in CONSTS) + "\n" + "\n".join(js_fn(f) for f in FNS)
           + "\nconst R = {};\nLANG = 'en';\n" + SCEN + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"), encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class HarnessRuntimeJs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run()

    def test_missing_runtime_renders_nothing(self):
        self.assertEqual(self.R["none"], "")

    def test_r1_two_lines_current_to_target(self):
        h = self.R["behind"]
        self.assertIn("Runtime behind latest patch", h)
        self.assertIn("from sec-2026.json", h)
        self.assertEqual(h.count("class=hnrtr>"), 4)
        self.assertRegex(h, r"20\.1\.0</code> <span class=hntra>→</span> <code class=hnrc>20\.18\.1")
        self.assertIn("security fix", h)
        self.assertIn("end of life 2026-04-30", h)
        self.assertRegex(h, r"2 cycles behind</b> <span class=hntra>→</span> <code class=hnrc>24\.2\.0")
        self.assertIn("hnrun hnrt hnrtl-fail", h)
        self.assertIn("hnrun hnrt hnrtl-warn", h)

    def test_r2_stale_no_current_claim(self):
        h = self.R["stale"]
        self.assertIn("checked 12 days ago — rerun to know it is current", h)
        self.assertNotIn("Runtimes on latest patch", h)
        self.assertNotIn(">latest patch<", h)
        self.assertNotIn(">newest cycle<", h)
        self.assertIn("latest patch when checked", h)

    def test_fresh_ok_is_one_quiet_line(self):
        h = self.R["fresh"]
        self.assertIn("Runtimes on latest patch", h)
        self.assertNotIn("hnrtr", h)

    def test_r3_no_record_shows_cmd(self):
        h = self.R["rec"]
        self.assertIn("No check on record", h)
        self.assertIn("<code class=hnrtc>scripts/arch_checks.py --category security</code>", h)

    def test_r4_next_step_per_item_and_limit(self):
        h = self.R["behind"]
        self.assertEqual(h.count("class=hnrtn>"), 2)
        self.assertIn("Move to a supported cycle: <code class=hnrtc>brew install node</code>", h)
        self.assertNotIn("brew upgrade", h)
        self.assertNotIn("node@20", h)
        self.assertNotIn("restart the viewer", h)
        self.assertIn("System Python updates with macOS", h)
        self.assertIn("python.org publishes no security flag", h)

    def test_patch_ok_newer_cycle_has_no_step(self):
        h = self.R["newer"]
        self.assertIn("1 cycle behind", h)
        self.assertNotIn("hnrtn", h)
        self.assertNotIn("brew ", h)

    def test_eol_brew_moves_to_supported_cycle(self):
        h = self.R["eolpy"]
        self.assertIn("Move to a supported cycle: <code class=hnrtc>brew install python@3.15</code> then restart the sessions or tools that use it", h)
        self.assertNotIn("brew upgrade", h)
        self.assertNotIn("Upgrade with Homebrew", h)

    def test_system_python_line_unchanged(self):
        h = self.R["syspy"]
        self.assertIn("<span class=hnrtn>System Python updates with macOS — or switch to a Homebrew Python</span>", h)
        self.assertNotIn("Move to a supported cycle", h)
        self.assertNotIn("<code class=hnrtc>", h)

    def test_brew_command_follows_keg_path_and_restart_target(self):
        vk, plain, pyv, pyb, ok = self.R["cmds"]
        self.assertIn("<code class=hnrtc>brew upgrade node@20</code>", vk)
        self.assertIn("then restart the sessions or tools that use it", vk)
        self.assertNotIn("restart the viewer", vk)
        self.assertIn("<code class=hnrtc>brew upgrade node</code>", plain)
        self.assertIn("<code class=hnrtc>brew upgrade python@3.12</code>", pyv)
        self.assertIn("then restart the viewer", pyv)
        self.assertIn("<code class=hnrtc>brew upgrade python@3.13</code>", pyb)
        self.assertNotIn("restart the viewer", pyb)
        self.assertNotIn("hnrtn", ok)

    def test_unknown_keys_no_class_and_escaped(self):
        h = self.R["bad"]
        self.assertIn('class="hnrun hnrt">', h)
        self.assertIn('class="hnrtb">', h)
        self.assertNotIn("zz", h.replace("hnrtw", ""))
        self.assertNotIn("evil", h)
        self.assertNotIn("<b>1</b>", h)
        self.assertNotIn("<i>2</i>", h)
        self.assertIn("&lt;i&gt;2&lt;/i&gt;", h)
        self.assertIn("Update it with the tool that installed it", h)
        self.assertNotIn("rm -rf", h)
        p = self.R["proto"]
        self.assertIn('class="hnrun hnrt">', p)
        self.assertIn("latest unknown", p)
        self.assertIn("Update it with the tool that installed it", p)
        self.assertNotIn("function", p)

    def test_r3_not_all_clear_folds_to_one_line(self):
        h = self.R["closed"]
        self.assertTrue(h.startswith('<details class="hnmore hnrtw" data-hnmore=rt><summary>'))
        self.assertTrue(h.endswith("</details>"))
        summ = h[h.index("<summary>"):h.index("</summary>")]
        self.assertIn("Runtime behind latest patch", summ)
        self.assertIn('<b class="hnrtb hnrtl-fail">end of life</b>', summ)
        self.assertIn("2 runtimes", summ)
        self.assertIn("from sec-2026.json", summ)
        # nothing clickable in the summary: a click there toggles the fold
        self.assertNotIn("<code", summ)
        self.assertNotIn("<button", summ)
        self.assertNotIn("<a ", summ)
        self.assertIn('<b class="hnrtb hnrtl-warn">behind</b>', self.R["warnonly2"])
        self.assertIn("1 runtime ", self.R["warnonly2"])

    def test_r3_detail_unchanged(self):
        h = self.R["closed"]
        body = h[h.index("</summary>") + len("</summary>"):-len("</details>")]
        self.assertEqual(body.count("class=hnrtr>"), 4)
        self.assertIn("Move to a supported cycle: <code class=hnrtc>brew install node</code>", body)
        self.assertIn("python.org publishes no security flag", body)
        self.assertIn("System Python updates with macOS", body)

    def test_r3_stale_and_none_fold_without_clean_claim(self):
        st = self.R["stale"]
        summ = st[st.index("<summary>"):st.index("</summary>")]
        self.assertIn("checked 12 days ago", summ)
        self.assertIn("latest unknown", summ)
        self.assertNotIn("Runtimes on latest patch", st)
        rc = self.R["rec"]
        summ = rc[rc.index("<summary>"):rc.index("</summary>")]
        self.assertIn("No check on record", summ)
        self.assertNotIn("runtime</", summ)
        self.assertNotIn("<code", summ)

    def test_r3_info_only_summary(self):
        h = self.R["infoonly"]
        summ = h[h.index("<summary>"):h.index("</summary>")]
        self.assertNotIn("latest unknown", summ)
        self.assertIn('<b class="hnrtb hnrtl-info">newer cycle available</b>', summ)
        self.assertIn("1 runtime ", summ)

    def test_r4_open_survives_rerender(self):
        self.assertNotIn(" open>", self.R["closed"][:80])
        self.assertTrue(self.R["reopen"].startswith('<details class="hnmore hnrtw" data-hnmore=rt open><summary>'))
        self.assertEqual(self.R["reopen"].replace(" open>", ">", 1), self.R["closed"])


if __name__ == "__main__":
    unittest.main()
