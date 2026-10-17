"""Work popup account chip: session_work carries acct/acctDir for primary and non-primary with 2+ accounts, none with 1;
the 35b header renders it escaped; acctTip names the primary's config dir."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from tests._load import sidereus, js_fn
from tests.test_saver_quota_js import i18n, jconst
from tests._node import node_e

st = sidereus("steps")
wk = sidereus("work")
cr = wk.claude_roots


class WorkAcct(unittest.TestCase):
    def setUp(self):
        fd, self.fp = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        with open(self.fp, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "timestamp": "2026-10-05T00:00:00.000Z",
                                "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Read",
                                                         "input": {"file_path": "/x/a.py"}}]}}) + "\n")
        self._saved = (wk._allowed_cwds, wk._sid_path, st._git_root, cr.accounts, cr.acct_of, cr.SCAN_HOME)
        wk._allowed_cwds = lambda ttl=5: {"/x": {"project": "x"}}
        wk._sid_path = lambda cwd, sid: self.fp
        st._git_root = lambda d: None
        cr.SCAN_HOME = "/h"
        self.accs = [{"dir": "/h/.claude", "label": "me", "primary": True},
                     {"dir": "/h/.claude-work", "label": "work", "primary": False}]
        self.rec = ("", "")
        cr.accounts = lambda: [dict(a) for a in self.accs]
        cr.acct_of = lambda sid, fp: self.rec

    def tearDown(self):
        wk._allowed_cwds, wk._sid_path, st._git_root, cr.accounts, cr.acct_of, cr.SCAN_HOME = self._saved
        os.unlink(self.fp)

    def test_primary(self):
        d = wk.session_work("/x", sid="abcdef12-0000")
        self.assertEqual((d["acct"], d["acctDir"], d["acctPrimary"]), ("me", "~/.claude", True))

    def test_non_primary(self):
        self.rec = ("work", "/h/.claude-work")
        d = wk.session_work("/x", sid="abcdef12-0000")
        self.assertEqual((d["acct"], d["acctDir"], d["acctPrimary"]), ("work", "~/.claude-work", False))

    def test_single_account(self):
        self.accs = self.accs[:1]
        d = wk.session_work("/x", sid="abcdef12-0000")
        self.assertTrue(d["ok"])
        for k in ("acct", "acctDir", "acctPrimary"):
            self.assertNotIn(k, d)


class ScanClosesFile(WorkAcct):
    """_open_or_tail(tail=0) returns a bare file (agent_work, SESS_TAIL=0): _work_scan must close it."""

    def test_scan_closes(self):
        f = st._open_or_tail(self.fp)
        st._work_scan(f, "/x")
        self.assertTrue(f.closed)

    def test_no_resource_warning(self):
        import gc
        import warnings
        saved = wk.SESS_TAIL
        wk.SESS_TAIL = 0
        try:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                self.assertTrue(wk.session_work("/x", sid="abcdef12-0000")["ok"])
                gc.collect()
        finally:
            wk.SESS_TAIL = saved
        self.assertFalse([x for x in w if issubclass(x.category, ResourceWarning)])


FNS = ("acctList", "mainAcct", "mainAcctOk", "acctHash", "acctCls", "acctTip", "wkAcct")


def run(body):
    src = ("var document = {getElementById: () => null};\nconst UIS = {getItem: () => ''};\nlet ACCTS = [];\n" + i18n() + "\n" + jconst("esc") + "\n"
           + "\n".join(js_fn(f) for f in FNS) + "\nconst R = {};\nLANG = 'en';\n" + body
           + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"), encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class WorkAcctJs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
R.none = [wkAcct({ok: true}), wkAcct(null), acctTip({})];
ACCTS = [{label: 'me', primary: true, dir: '/h/.claude'}, {label: 'w<b>', dir: '/h/.claude-w'}];
R.prim = wkAcct({ok: true, acct: 'me', acctDir: '~/.claude', acctPrimary: true});
R.oth = wkAcct({ok: true, acct: 'w<b>', acctDir: '~/.claude-w'});
R.tip = acctTip({});
LANG = 'ko'; R.ko = wkAcct({ok: true, acct: 'me', acctDir: '~/.claude', acctPrimary: true});
""")

    def test_absent(self):
        self.assertEqual(self.R["none"], ["", "", ""])

    def test_header_chip(self):
        self.assertIn("acb acc0", self.R["prim"])
        self.assertIn("Account: me · ~/.claude", self.R["prim"])
        self.assertRegex(self.R["oth"], r"acb acc[1-6]")
        self.assertIn("w&lt;b&gt;", self.R["oth"])
        self.assertNotIn("<b>", self.R["oth"])
        self.assertIn("계정: me", self.R["ko"])

    def test_primary_tip_dir(self):
        self.assertEqual(self.R["tip"], "Claude account me — config dir /h/.claude")


if __name__ == "__main__":
    unittest.main()
