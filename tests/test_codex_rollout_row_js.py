"""Codex row read from its rollout file (server `rollout: true`, no hooks): 40b sessIdRow shows a «Hooks not
connected» chip, the logo tooltip does not claim hook events, 20 sessLabel shows only the last activity.
Pure functions under node with stubs; no live files."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

PRE = """
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const T = s => s;
const TV = o => o.msg.replace(/\\{(\\w+)\\}/g, (_, k) => o.vars[k]);
const LBL = { tool: 'Running a tool', think: 'Thinking', ask: 'Awaiting answer', wait: 'Awaiting input', unknown: 'Unknown' };
function stateLbl(k){ return LBL[k] || ''; } function srvEn(s){ return s; } function U(n, u){ return n + u; }
function waitOnLabel(){ return ''; }
function platName(k){ return k === 'cx' ? 'Codex' : String(k); }
function aiLogo(p, extra){ return '<i class=ailg title="' + esc(p + (extra || '')) + '"></i>'; }
function sessBranchHtml(){ return ''; } function acctChip(){ return ''; }
function sessGitChip(){ return ''; } function sessUsage(){ return '<i class=sc>9%</i>'; }
function sessActs(){ return '<i class=srz>R</i>'; }
"""
FNS = "\n".join(js_fn(n) for n in ("sessIdRow", "sessLabel", "sessPlChip", "sessWorkBadges")) + "\n"


def run(body):
    r = subprocess.run(node_e(PRE + FNS + body), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class CodexRolloutRow(unittest.TestCase):
    def test_chip_and_logo_tooltip(self):
        ro, hk = run("const r = {plat: 'cx', project: 'p', rollout: true, state: 'unknown'};"
                     "console.log(JSON.stringify([sessIdRow(r), sessIdRow({plat: 'cx', project: 'p', state: 'wait'})]));")
        self.assertIn(">Hooks not connected</span>", ro)
        self.assertIn("State read from Codex's record file", ro)
        self.assertIn("docs/HOOKS.md", ro)
        self.assertNotIn("events its CLI hooks send", ro)                   # logo must not claim hook events
        self.assertIn("record file (hooks not connected)", ro)
        self.assertNotIn("Hooks not connected", hk)                        # hooked Codex row: no chip
        self.assertIn("events its CLI hooks send", hk)

    def test_r1_group_order(self):
        h = run("console.log(JSON.stringify(sessIdRow({plat: 'cx', project: 'p', state: 'wait', err: 1})));")
        pos = [h.index('class="sxg ' + c + '"') for c in ("sxid", "sxus", "sxwk", "sxac")]
        self.assertEqual(pos, sorted(pos))
        self.assertLess(h.index("class=sxl"), pos[0])                     # lead cell before every group

    def test_label_is_last_activity_only(self):
        a, b, c, d = run("const L = o => sessLabel(Object.assign({plat: 'cx', rollout: true, state: 'unknown'}, o));"
                         "console.log(JSON.stringify([L({ageSec: 600}), L({state: 'wait', ageSec: 59}),"
                         " L({blocked: 'Bash waiting for approval', ageSec: 120}), L({})]));")
        self.assertEqual(a, "Last activity 10m ago")
        self.assertEqual(b, "Last activity 0m ago")
        self.assertEqual(c, "Last activity 2m ago")
        self.assertEqual(d, "Unknown")
        for s in (a, b, c, d):
            for bad in ("Awaiting", "Blocked", "approval"):
                self.assertNotIn(bad, s)


if __name__ == "__main__":
    unittest.main()
