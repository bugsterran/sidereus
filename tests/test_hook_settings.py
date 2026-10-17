"""Gemini settings.json lost our hooks (interactive CLI or /auth rewrite): soft warning names the gaps."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

ext = sidereus("ext")
gm = sidereus("plat_gemini")
warn = sidereus("warn")

NOW = 1790000000.0


def _full():
    cmd = {"type": "command", "command": "/usr/bin/python3 /x/ext-hooks/ext_hook.py --platform gemini"}
    return {"hooksConfig": {"enabled": True},
            "hooks": {ev: [{"hooks": [dict(cmd)]}] for ev in gm.HOOK_EVENTS}}


class HookSettings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.gdir = os.path.join(self.tmp, ".gemini")
        os.makedirs(self.gdir)
        self.saved = (gm.root, gm.used_since, dict(ext._ext), warn.warn_once, ext.warn_once)
        gm.root = lambda: self.gdir
        gm.used_since = lambda since: True
        ext._hook_chk.clear()
        self.warned = []
        ext.warn_once = lambda key, msg, soft=False, en=None, vars=None: self.warned.append((key, msg, soft, vars))

    def tearDown(self):
        gm.root, gm.used_since, store, warn.warn_once, ext.warn_once = self.saved
        ext._ext.clear()
        ext._ext.update(store)
        ext._hook_chk.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, cfg):
        with open(os.path.join(self.gdir, "settings.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)

    def test_complete_settings_no_warning(self):
        self._write(_full())
        self.assertEqual(ext.ext_hook_check(NOW), {})
        self.assertEqual(self.warned, [])

    def test_missing_after_agent_warns_and_names_it(self):
        cfg = _full()
        del cfg["hooks"]["AfterAgent"]
        self._write(cfg)
        self.assertEqual(ext.ext_hook_check(NOW), {"gemini": ["AfterAgent"]})
        key, msg, soft, vars = self.warned[-1]
        self.assertEqual(key, "hooks:gemini")
        self.assertFalse(soft)                       # certain config problem: straight to the strip
        ext.ext_hook_check(NOW + 10)                 # throttled: no re-send between evaluations
        self.assertEqual(len(self.warned), 1)
        self.assertIn("AfterAgent", vars["miss"])
        self.assertNotRegex(msg, "[가-힣]")          # English template; Korean lives in I18N.ko

    def test_hooks_disabled_warns(self):
        cfg = _full()
        cfg["hooksConfig"]["enabled"] = False
        self._write(cfg)
        self.assertEqual(ext.ext_hook_check(NOW), {"gemini": ["hooksConfig.enabled"]})
        self.assertTrue(self.warned)

    def test_no_gemini_dir_no_warning(self):
        shutil.rmtree(self.gdir)
        self.assertEqual(ext.ext_hook_check(NOW), {})
        self.assertEqual(self.warned, [])

    def test_unused_gemini_no_warning(self):
        self._write({})
        gm.used_since = lambda since: False
        ext._ext.clear()
        self.assertEqual(ext.ext_hook_check(NOW), {})

    def test_throttled_then_rechecked(self):
        self._write(_full())
        ext.ext_hook_check(NOW)
        cfg = _full()
        del cfg["hooks"]["SessionEnd"]
        self._write(cfg)
        sp = os.path.join(self.gdir, "settings.json")
        mt = os.stat(sp).st_mtime + 5
        os.utime(sp, (mt, mt))            # ⚠coarse Windows mtime: two quick writes can share one stamp
        self.assertEqual(ext.ext_hook_check(NOW + 10), {})                        # within HOOK_CHECK_S
        self.assertEqual(ext.ext_hook_check(NOW + ext.HOOK_CHECK_S), {"gemini": ["SessionEnd"]})
        self.assertEqual(len(self.warned), 1)


if __name__ == "__main__":
    unittest.main()
