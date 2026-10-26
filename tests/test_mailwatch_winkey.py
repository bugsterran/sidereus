"""Mailbox watch keys that differ only in Windows case/separator: one row and no false change on the client
(90d-mailwatch.js mwKey/mwProjList/mwDiff), deterministic watch_on and collapsed save on the server (prefs.py).

Windows is simulated: the server swaps prefs.os for ntpath rules (as test_win_compat), the client keys off the drive-letter form.
⚠Config path is a temp file — never the live config.local.json.
"""
import json
import os
import posixpath
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tests._load import js_fn, sidereus
from tests._node import node_e
from tests.test_prefs import _ENV_CLEAR
from tests.test_win_compat import _NtOs

P = sidereus("prefs")


class _PosixOs:
    """`os` with POSIX path rules whatever the host is; everything else is the real os."""
    sep, altsep, name, path = "/", None, "posix", posixpath

    def __getattr__(self, name):
        return getattr(os, name)


class ServerWinKeys(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-mwk-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, "config.local.json")
        for p in (mock.patch.object(P, "CONFIG_PATH", self.path), mock.patch.dict(os.environ, _ENV_CLEAR),
                  mock.patch.object(P, "warn_once", lambda *a, **k: None), mock.patch.object(P, "os", _NtOs())):
            p.start()
            self.addCleanup(p.stop)

    def test_watch_on_ignores_key_order(self):
        a = {"mode": "on", "projects": {"C:\\work\\app": "off", "c:/work/app": "on"}}
        b = {"mode": "on", "projects": {"c:/work/app": "on", "C:\\work\\app": "off"}}
        for cwd in ("C:\\work\\app", "c:/work/app", "C:\\work\\app\\src"):
            self.assertEqual(P.watch_on(cwd, a), P.watch_on(cwd, b), cwd)
        self.assertFalse(P.watch_on("C:\\work\\app", a))    # exact spelling wins
        self.assertTrue(P.watch_on("c:/work/app", b))
        self.assertFalse(P.watch_on("C:\\WORK\\app\\src", a))   # no exact match: first in sorted order ("C:..." < "c:...")

    def test_save_collapses_equal_keys(self):
        v = {"mode": "on", "projects": {"C:\\work\\app": "off", "D:\\x": "on", "c:/work/app": "on"}}
        code, out = P.prefs_set({"key": "mailbox_watch", "value": v})
        self.assertEqual(code, 200, out)
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["mailbox_watch"]["projects"], {"D:\\x": "on", "c:/work/app": "on"})

    def test_posix_keys_unchanged(self):
        with mock.patch.object(P, "os", _PosixOs()):     # ⚠not the real os: on a Windows runner that is nt and collapses /A and /a
            v = {"mode": "on", "projects": {"/A": "off", "/a": "on"}}
            self.assertEqual(P._watch_collapse(v), v)
            self.assertFalse(P.watch_on("/A", v))


JS = r"""
const T = (s) => s, mwOO = m => m;
const R = {};
R.k = [mwKey('C:\\work\\app'), mwKey('c:/work/app/'), mwKey('c:\\'), mwKey('\\\\Srv\\Share'), mwKey('/Users/A')];
let MW_PROJS = [{path: 'c:/work/app'}, {path: '/Users/A'}, {path: '/users/a'}];
const strProjList = () => [{p: 'C:/WORK/APP'}];
R.list = mwProjList({projects: {'C:\\work\\app': 'off'}});
const sv = {mode: 'on', projects: {'C:\\work\\app': 'off'}};
R.same = mwDiff(sv, {mode: 'on', projects: {'c:/work/app': 'off'}});
R.chg = mwDiff(sv, {mode: 'on', projects: {'c:/work/app': 'on'}});
process.stdout.write(JSON.stringify(R));
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ClientWinKeys(unittest.TestCase):
    def test_merge_and_diff(self):
        src = "\n".join(js_fn(n) for n in ("mwKey", "mwNorm", "mwProjList", "mwDiff")) + "\n" + JS
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        R = json.loads(r.stdout)
        self.assertEqual(R["k"], ["c:\\work\\app", "c:\\work\\app", "c:\\", "\\\\srv\\share", "/Users/A"])
        self.assertEqual(R["list"], ["/Users/A", "/users/a", "C:\\work\\app"])   # one Windows row, saved spelling; POSIX case kept
        self.assertEqual(R["same"], [])
        self.assertEqual(R["chg"], ["c:/work/app off → on"])


if __name__ == "__main__":
    unittest.main()
