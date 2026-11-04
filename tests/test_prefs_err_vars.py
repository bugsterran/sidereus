"""Settings › Preferences errors reach the page as a bare template + vars (so TE() matches the ko key), never filled English.

⚠Paths point at the CcAccts temp-dir fixture — no live config or settings file is touched.
"""
import json
import os
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._node import node_e
from tests.test_prefs import ORIGIN, get
from tests.test_routes_post import post
from tests import test_cc_settings_accts as A

BAD = "config file unreadable ({e}) — fix it by hand"
CCBAD = "settings.json is not valid JSON ({e}) — fix it by hand"
LAYOUT = "settings.json layout can't be edited safely (duplicate {key}?) — change it by hand"


class ErrVars(unittest.TestCase):
    setUp, _put, _b = A.CcAccts.setUp, A.CcAccts._put, A.CcAccts._b

    def _broken_config(self):
        with open(self.cp, "w", encoding="utf-8") as f:
            f.write("{bad")

    def test_get_broken_config_is_template(self):
        self._put(self.sp)
        self._broken_config()
        code, out = get("/api/prefs")[:2]
        self.assertEqual(code, 200)
        self.assertTrue(out["ok"])
        self.assertEqual((out["err"], out["vars"]), (BAD, {"e": "JSONDecodeError"}))

    def test_post_broken_config_is_flat_template(self):
        self._put(self.sp)
        self._broken_config()
        code, out, _ = post("/api/prefs/set", {"key": "port", "value": 8800}, origin=ORIGIN)
        self.assertEqual((code, out), (400, {"ok": False, "err": BAD, "vars": {"e": "JSONDecodeError"}}))

    def test_extra_account_row_and_cc_err_are_templates(self):
        self._put(self.sp, "{bad")
        self._put(self.xp, "{bad")
        out = get("/api/prefs")[1]
        self.assertEqual((json.loads(json.dumps(out["cc_err"])), out["cc_vars"]), (CCBAD, {"e": "JSONDecodeError"}))
        row = out["cc_accts"][0]
        self.assertEqual((row["err"], row["vars"]), (CCBAD, {"e": "JSONDecodeError"}))

    def test_skipped_row_is_template(self):
        self._put(self.sp)
        self._put(self.xp, "{bad")
        code, out, _ = post("/api/prefs/set", {"key": "cc_compact_window", "value": 300000}, origin=ORIGIN)
        self.assertEqual(code, 200, out)
        row = out["files"][1]
        self.assertEqual((row["status"], row["err"], row["vars"]), ("skipped", CCBAD, {"e": "JSONDecodeError"}))


class LayoutErr(unittest.TestCase):
    def test_duplicate_key_is_template(self):
        raw = b'{"autoCompactWindow": 1, "autoCompactWindow": 2}\n'
        _n, _c, err = A.CC._plan_raw(raw, json.loads(raw), "autoCompactWindow", 300000)
        self.assertEqual((err[0], A.CC._efull(err[1])), (400, {"err": LAYOUT, "vars": {"key": "autoCompactWindow"}}))


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TeFills(unittest.TestCase):
    def test_layout_ko_fills(self):
        body = "console.log(JSON.stringify(TE({err: %s, vars: {key: 'k'}})));" % json.dumps(LAYOUT)
        r = subprocess.run(node_e(i18n_prelude("'ko'", ("T", "TE")) + body), capture_output=True, text=True,
                           timeout=20, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), "settings.json 구조를 안전하게 고칠 수 없습니다(k 중복?) — 직접 고치세요")

    def test_ko_and_en_fill(self):
        body = ("console.log(JSON.stringify(TE({err: %s, vars: {e: 'JSONDecodeError'}})));" % json.dumps(BAD))
        for lang, want in (("'en'", "config file unreadable (JSONDecodeError) — fix it by hand"),
                           ("'ko'", "설정 파일을 읽을 수 없습니다(JSONDecodeError) — 직접 고치세요")):
            r = subprocess.run(node_e(i18n_prelude(lang, ("T", "TE")) + body), capture_output=True, text=True,
                               timeout=20, encoding="utf-8")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout), want)


if __name__ == "__main__":
    unittest.main()
