"""Server error templates (sidereus/hook_connect.py, sidereus/cc_settings.py) carry {e} in vars, have I18N.ko entries,
and the page shows them through TE() (40c to-do, 90f hook connect, 47i hook remove)."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tests._i18n_js import i18n_prelude
from tests._load import load, sidereus
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load()
HC = sidereus("hook_connect")
CS = sidereus("cc_settings")

KEYS = ["unreadable ({e})", "not valid JSON — fix it by hand", "top level is not an object — fix it by hand",
        "`hooks` is not an object — fix it by hand", "settings.json not found", "settings.json unreadable ({e})",
        "settings.json is not valid JSON ({e}) — fix it by hand", "settings.json top level is not an object — fix it by hand"]


def _node(body):
    r = subprocess.run(node_e(i18n_prelude("'ko'", ("T", "TE")) + body), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


class PyTemplates(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)

    def _put(self, text):
        p = os.path.join(self.d, "f.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def test_hook_connect_unreadable_is_template(self):
        _r, _d, err = HC._read(self.d)     # a folder: open() raises an OSError subclass
        self.assertEqual(err, "unreadable ({e})")
        self.assertEqual(set(HC._ev(err)), {"e"})

    def test_hook_connect_reply_and_row_carry_vars(self):
        err = HC._Err("unreadable ({e})", e="PermissionError")
        with mock.patch.object(HC, "_plan", return_value={"raw": None, "err": (400, err)}):
            code, out = HC.connect({"plat": "cursor", "dry": True})
        self.assertEqual((code, out), (400, {"ok": False, "err": "unreadable ({e})", "vars": {"e": "PermissionError"}}))
        self.assertEqual(json.loads(json.dumps(out))["err"], "unreadable ({e})")
        with mock.patch.object(HC, "_plan", return_value={"raw": None, "err": (400, "unknown plat x")}):
            self.assertNotIn("vars", HC.connect({"plat": "cursor", "dry": True})[1])

    def test_cc_settings_templates(self):
        _r, _d, err = CS._read_at(self._put("{bad"))
        self.assertEqual(err, "settings.json is not valid JSON ({e}) — fix it by hand")
        self.assertEqual(CS._ev(err), {"e": "JSONDecodeError"})
        self.assertEqual(CS._efull(err), {"err": err, "vars": {"e": "JSONDecodeError"}})
        self.assertEqual(CS._etext(err), "settings.json is not valid JSON (JSONDecodeError) — fix it by hand")
        _r, _d, err = CS._read_at(self.d)
        self.assertEqual(err, "settings.json unreadable ({e})")
        self.assertEqual(CS._efull("symlink"), {"err": "symlink"})
        self.assertEqual(CS._etext("symlink"), "symlink")

    def test_cc_reply_vars_and_rows_filled(self):
        p = self._put("[1]")
        with mock.patch.object(CS, "settings_path", return_value=p):
            code, out = CS.otel_port_set(4318)
        self.assertEqual((code, out), (400, {"ok": False, "err": "settings.json top level is not an object — fix it by hand"}))
        row = CS._acct_row({"label": "x", "path": self._put("{bad")})
        self.assertEqual((row["err"], row["vars"]), ("settings.json is not valid JSON ({e}) — fix it by hand", {"e": "JSONDecodeError"}))


class KoEntries(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_every_template_has_ko_and_te_fills(self):
        o = _node("console.log(JSON.stringify([%s.map(k => TE({err: k, vars: {e: 'OSError'}})),"
                  " TE({why: 'unreadable ({e})', vars: {e: 'PermissionError'}})]));" % json.dumps(KEYS))
        for k, v in zip(KEYS, o[0]):
            self.assertNotEqual(k.replace("{e}", "OSError"), v, k)
            self.assertNotIn("{e}", v)
        self.assertEqual(o[1], "읽을 수 없습니다(PermissionError)")


HNRM = r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
const c = {T, TE, esc: s => String(s), document: {addEventListener: () => {}}};
vm.createContext(c);
vm.runInContext(fs.readFileSync(path.join(%s, 'web', 'js', '47i-harness-hookrm.js'), 'utf8'), c);
console.log(JSON.stringify([c.hnRmErr({status: 400, body: {err: 'write failed ({e})', vars: {e: 'OSError'}}}),
  c.hnRmErr({status: 500, body: {err: 'odd line'}}), c.hnRmErr(new Error('net down'))]));
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class HookRemoveErr(unittest.TestCase):
    def test_reason_through_te(self):
        o = _node(HNRM % json.dumps(ROOT))
        self.assertTrue(o[0].endswith(": 쓰기 실패(OSError)"), o[0])
        self.assertTrue(o[1].endswith(": odd line"), o[1])     # unknown key: verbatim
        self.assertTrue(o[2].endswith(": net down"), o[2])


if __name__ == "__main__":
    unittest.main()
