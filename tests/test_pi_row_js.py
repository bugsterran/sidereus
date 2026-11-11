"""pi logo and rollout row: aiLogo('pi') is an original glyph with no visible text; a pi rollout row shows the
«Hooks not connected» chip whose tooltip points to Settings › Diagnostics › Connect, not docs/HOOKS.md. Node, no live files."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import ROOT, js_fn
from tests._node import node_e


def _ailg():
    """The `const AILG = {...};` statement verbatim from web/js (looked up by content, not file)."""
    d = os.path.join(ROOT, "web", "js")
    for f in sorted(os.listdir(d)):
        with open(os.path.join(d, f), encoding="utf-8") as fh:
            m = re.search(r"^const AILG = \{.*?^\};", fh.read(), re.S | re.M)
        if m:
            return m.group(0)
    raise LookupError("no AILG")


PRE = """
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const T = s => s;
const TV = o => o.msg.replace(/\\{(\\w+)\\}/g, (_, k) => o.vars[k]);
function platName(k){ return AILG[k] ? AILG[k][0] : String(k); }
function sessBranchHtml(){ return ''; } function acctChip(){ return ''; }
function sessGitChip(){ return ''; } function sessUsage(){ return ''; }
function sessActs(){ return ''; } function sessWorkBadges(){ return ''; }
"""


def run(body):
    src = _ailg() + "\n" + PRE + js_fn("aiLogo") + "\n" + js_fn("sessIdRow") + "\n" + body
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PiRowJs(unittest.TestCase):
    def test_r5_logo_svg_without_text(self):
        h = run("console.log(JSON.stringify(aiLogo('pi')));")
        self.assertIn('class="ailg ailg-pi"', h)
        self.assertIn("<svg", h)
        self.assertNotIn("<text", h)
        inner = re.sub(r"<[^>]*>", "", h)              # only the title attribute may carry the name
        self.assertEqual(inner.strip(), "")

    def test_pi_rollout_row_has_connect_chip(self):
        pi, cx = run("const r = o => sessIdRow(Object.assign({project: 'p', rollout: true, state: 'unknown'}, o));"
                     "console.log(JSON.stringify([r({plat: 'pi'}), r({plat: 'cx'})]));")
        self.assertIn("ailg-pi", pi)
        self.assertIn(">Hooks not connected</span>", pi)
        self.assertIn("Settings › Diagnostics › Connect", pi)
        self.assertNotIn("docs/HOOKS.md", pi)
        self.assertIn("docs/HOOKS.md", cx)              # other CLIs keep the manual hook docs

    def test_r2_r3_old_extension_chip_tooltips(self):
        rl, cn = run("const r = o => sessIdRow(Object.assign({project: 'p', plat: 'pi', state: 'idle'}, o));"
                     "console.log(JSON.stringify([r({extOld: 'reload'}), r({extOld: 'connect'})]));")
        for h in (rl, cn):
            self.assertIn('class="sz snohk"', h)
            self.assertIn(">Old extension</span>", h)
            self.assertNotIn("Hooks not connected", h)
        self.assertIn("run /reload in pi", rl)
        self.assertNotIn("pi Connect", rl)
        self.assertIn("Settings › Diagnostics › pi Connect, then /reload", cn)

    def test_r4_no_chip_same_rev_and_unconnected_unchanged(self):
        same, miss, bad, roll = run(
            "const r = o => sessIdRow(Object.assign({project: 'p', plat: 'pi', state: 'idle'}, o));"
            "console.log(JSON.stringify([r({extOld: ''}), r({}), r({extOld: '<x>'}), r({rollout: true, state: 'unknown'})]));")
        for h in (same, miss, bad):
            self.assertNotIn("Old extension", h)
            self.assertNotIn("snohk", h)
        self.assertIn(">Hooks not connected</span>", roll)
        self.assertNotIn("Old extension", roll)


if __name__ == "__main__":
    unittest.main()
