"""compact_hist_append errors and per-account failed rows carry {err, vars}; the UI fills the slots after translating.

⚠prefs.CONFIG_PATH / cc_settings paths point at a temp dir (CcAccts fixture) — no live file is touched.
"""
import json
import os
import subprocess
import unittest
from unittest import mock

from tests._load import js_fn
from tests._node import node_e
from tests._i18n_js import i18n_prelude
from tests import test_cc_settings_accts as A

CC, P = A.CC, A.P


class HistErr(unittest.TestCase):
    # reuse the CcAccts temp-dir fixture without re-running its tests
    setUp, _put, _b, _save = A.CcAccts.setUp, A.CcAccts._put, A.CcAccts._b, A.CcAccts._save

    def test_write_oserror_is_keyed(self):
        def boom(_d):
            raise PermissionError("denied")
        with mock.patch.object(P, "_write", boom):
            self.assertEqual(P.compact_hist_append("2026-09-29", 300000),
                             {"err": "config write failed ({e})", "vars": {"e": "PermissionError"}})

    def test_invalid_history_carries_why(self):
        with open(self.cp, "w", encoding="utf-8") as f:
            json.dump({"compact_history": "nope"}, f)
        r = P.compact_hist_append("2026-09-29", 300000)
        self.assertEqual(r["err"], "compact_history invalid ({why}) — not updated")
        self.assertTrue(r["vars"]["why"])

    def test_unreadable_and_non_object(self):
        with open(self.cp, "w", encoding="utf-8") as f:
            f.write("{bad")
        self.assertEqual(P.compact_hist_append("2026-09-29", 1),
                         {"err": "config file unreadable ({e}) — fix it by hand", "vars": {"e": "JSONDecodeError"}})
        self.assertEqual(P._read_file()[1], "config file unreadable (JSONDecodeError) — fix it by hand")
        with open(self.cp, "w", encoding="utf-8") as f:
            f.write("[]")
        self.assertEqual(P.compact_hist_append("2026-09-29", 1),
                         {"err": "config file top level is not an object — fix it by hand"})

    def test_failed_row_keeps_vars(self):
        self._put(self.sp)
        self._put(self.xp)
        real = CC._write_raw

        def fake(p, raw, new_raw, label=None, into=None):
            if p == self.xp:
                return 500, {"ok": False, "err": "write failed ({e})", "vars": {"e": "PermissionError"}}
            return real(p, raw, new_raw, label, into)
        with mock.patch.object(CC, "_write_raw", fake):
            code, out, _ = self._save([{"path": self.xp, "window": 200000}])
        self.assertEqual(code, 200, out)
        row = out["files"][1]
        self.assertEqual((row["status"], row["err"], row["vars"]), ("failed", "write failed ({e})", {"e": "PermissionError"}))


def _run(body):
    pre = i18n_prelude("'ko'", ("T", "TV", "TE"))
    r = subprocess.run(node_e(pre + body), capture_output=True, text=True, timeout=20, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


class HistErrJs(unittest.TestCase):
    def test_ko_fills_vars(self):
        src = ("const MP_SRV_ERR = [[/^write failed/, 'Could not write the file']];\n" + js_fn("mpSrvErr") + "\n"
               "const f = {status: 'failed', err: 'write failed ({e})', vars: {e: 'PermissionError'}};\n"
               "console.log(JSON.stringify({hist: TE({err: 'config write failed ({e})', vars: {e: 'PermissionError'}}),"
               " row: TE(f), why: TE({err: 'compact_history invalid ({why}) — not updated', vars: {why: 'bad row'}}),"
               " srv: mpSrvErr({ok: false, err: 'config file unreadable ({e}) — fix it by hand', vars: {e: 'OSError'}}),"
               " tbl: mpSrvErr({ok: false, err: 'write failed ({e})', vars: {e: 'OSError'}}), str: mpSrvErr('weird')}));\n")
        R = _run(src)
        self.assertEqual(R["hist"], "설정 파일 쓰기 실패(PermissionError)")
        self.assertEqual(R["row"], "쓰기 실패(PermissionError)")
        self.assertNotIn("{e}", R["row"])
        self.assertIn("bad row", R["why"])
        self.assertTrue(R["srv"].endswith("설정 파일을 읽을 수 없습니다(OSError) — 직접 고치세요"), R["srv"])
        self.assertNotIn("{e}", R["tbl"])
        self.assertTrue(R["str"].endswith(": weird"), R["str"])


if __name__ == "__main__":
    unittest.main()
