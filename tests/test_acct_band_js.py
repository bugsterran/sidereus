"""Account band (web/js/40b acctCls/acctRowCls/acctTip): absent with <2 accounts,
same label -> same class whatever the list order, primary -> .acc0."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import i18n, jconst
from tests._node import node_e

FNS = ("acctList", "mainAcct", "mainAcctOk", "acctHash", "acctCls", "acctRowCls", "acctTip", "acctLabel", "acctChip", "acctShort")


def run(body):
    src = ("var document = {getElementById: () => null};\nconst NL = String.fromCharCode(10);\nlet QLAST = null, SESS = [], ACCTS = [];\n"
           + i18n() + "\n" + jconst("esc") + "\n" + "\n".join(js_fn(f) for f in FNS)
           + "\nconst R = {};\nLANG = 'en';\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"), encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class AcctBand(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
SESS = [{sid: 'a', state: 'think'}, {sid: 'b', state: 'idle', acct: 'work'}, {sid: 'c', state: 'done', acct: 'work'},
        {sid: 'd', state: 'idle', plat: 'codex'}];
R.one = [acctCls('work'), acctCls(''), acctRowCls({acct: 'work'}), acctTip({acct: 'work'}), acctChip({acct: 'work'}, 'c')];
ACCTS = undefined; R.undef = [acctCls('work')];
ACCTS = [{label: 'me', primary: true}, {label: 'work'}, {label: 'side'}, {label: 'z<b>'}];
R.a = ['work', 'side', 'z<b>', ''].map(acctCls);
R.tipP = acctTip({}); R.tipW = acctTip({acct: 'work', acctDir: '/x'}); R.ext = [acctRowCls({plat: 'codex'}), acctTip({plat: 'codex'})];
R.chip = [acctChip({}, 'c'), acctChip({acct: 'z<b>'}, 'c'), acctChip({plat: 'codex', acct: 'work'}, 'c'), acctLabel({plat: 'cc', acct: 'work'})];
ACCTS = [{label: 'default', primary: true}, {label: 'myaccount'}];
R.short1 = [acctChip({}, 'c'), acctChip({acct: 'myaccount'}, 'c')];
ACCTS = [{label: 'myaccount', primary: true}, {label: 'myacc2'}, {label: 'myacc'}];
R.short2 = [acctChip({}, 'c'), acctChip({acct: 'myacc2'}, 'c'), acctChip({acct: 'myacc'}, 'c')];
ACCTS = [{label: 'z<b>'}, {label: 'side'}, {label: 'work'}, {label: 'me', primary: true}];
R.b = ['work', 'side', 'z<b>', ''].map(acctCls); R.again = acctCls('work');
""")

    def test_absent_with_fewer_than_two(self):
        self.assertEqual(self.R["one"], ["", "", "", "", ""])
        self.assertEqual(self.R["undef"], [""])

    def test_stable_classes(self):
        a, b = self.R["a"], self.R["b"]
        self.assertEqual(a, b)
        self.assertEqual(self.R["again"], a[0])
        self.assertEqual(a[3], "acb acc0")
        self.assertEqual(len(set(a)), 4)
        for c in a[:3]:
            self.assertRegex(c, r"^acb acc[1-6]$")

    def test_tooltips(self):
        self.assertEqual(self.R["tipP"], "Claude account me")
        self.assertEqual(self.R["tipW"], "Claude account work — config dir /x")
        self.assertEqual(self.R["ext"], ["", ""])

    def test_label_chip(self):
        self.assertEqual(self.R["chip"], ['<span class="c" title="Claude account me">me</span>',
                                          '<span class="c" title="Claude account z&lt;b&gt;">z&lt;b&gt;</span>', "", "work"])

    def test_chip_shared_prefix(self):
        self.assertEqual(self.R["short1"], ['<span class="c" title="Claude account default">defa</span>',
                                            '<span class="c" title="Claude account myaccount">myac</span>'])
        a, b, c = self.R["short2"]
        self.assertIn(">myacco<", a); self.assertIn('title="Claude account myaccount"', a)
        self.assertIn(">myacc2<", b); self.assertIn(">myacc<", c)     # a label that prefixes another stays whole


class AcctChipCss(unittest.TestCase):
    def test_chip_tinted_and_main_hued(self):
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "css", "60-sessions.css")
        with open(p, encoding="utf-8") as f:
            css = f.read()
        base = next(l for l in css.splitlines() if l.startswith(":is(.sx > .sacb,.srec .srecac){"))
        self.assertIn("background:color-mix(in srgb,var(--acc)", base)
        shrink = int(base.split("flex:")[1].split()[1])
        self.assertLess(shrink, 9)          # a 9x shrink cut labels to a shared prefix
        # Main (.acc0) has its own hue, so its chip follows --acc like every account (no ink override).
        self.assertIn(".acc0{--acc:#3cc6c0}", css)
        self.assertNotIn(".acc0 :is(", css)
        hues = [l for l in css.splitlines() if l.startswith(".acc0{")][0]
        vals = [v.split("}")[0] for v in hues.split("--acc:")[1:]]
        self.assertEqual(len(vals), 7)
        self.assertEqual(len(set(vals)), 7)


if __name__ == "__main__":
    unittest.main()
