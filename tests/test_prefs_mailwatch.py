"""Config `mailbox_watch` (sidereus/prefs.py): validator, effective default (on), prefs_get/prefs_set round trip.

⚠Config path is a temp file — never the live config.local.json.
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus
from tests.test_prefs import _ENV_CLEAR

P = sidereus("prefs")


class MailWatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-mw-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, "config.local.json")
        for p in (mock.patch.object(P, "CONFIG_PATH", self.path), mock.patch.dict(os.environ, _ENV_CLEAR),
                  mock.patch.object(P, "warn_once", lambda *a, **k: None)):
            p.start()
            self.addCleanup(p.stop)

    def test_validator_accepts(self):
        v = {"mode": "off", "projects": {"/a/b": "on", "/c": "off"}}
        self.assertEqual(P._v_watch(v), v)
        self.assertEqual(P._v_watch({}), {"mode": "on", "projects": {}})

    def test_validator_rejects(self):
        bad = [[], "on", {"mode": "auto"}, {"mode": "on", "extra": 1}, {"projects": {"rel/path": "on"}},
               {"projects": {"/a": "auto"}}, {"projects": {"/a\x00b": "on"}}, {"projects": {"/" + "x" * 1024: "on"}},
               {"projects": {"/p%d" % i: "on" for i in range(201)}}, {"projects": ["/a"]}]
        for v in bad:
            with self.assertRaises(ValueError, msg=repr(v)[:80]):
                P._v_watch(v)
        P._v_watch({"projects": {"/" + "x" * 1023: "on"}})   # exactly 1024 chars is allowed
        P._v_watch({"projects": {"/p%d" % i: "on" for i in range(200)}})

    def test_effective_default_on(self):
        self.assertEqual(P.effective("mailbox_watch", {}), {"mode": "on", "projects": {}})
        self.assertEqual(P.effective("mailbox_watch", {"mailbox_watch": {"mode": "bogus"}}), {"mode": "on", "projects": {}})
        self.assertTrue(P.watch_on("/any", P.effective("mailbox_watch", {})))
        v = {"mode": "off", "projects": {"/on": "on"}}
        self.assertFalse(P.watch_on("/other", v))
        self.assertTrue(P.watch_on("/on", v))
        self.assertFalse(P.watch_on("/x", {"mode": "on", "projects": {"/x": "off"}}))
        self.assertTrue(P.watch_on("/x", {"mode": "bogus"}))   # invalid value = on

    def test_subfolder_inherits(self):
        v = {"mode": "on", "projects": {"/p": "off"}}
        self.assertFalse(P.watch_on("/p/sub/dir", v))
        self.assertTrue(P.watch_on("/pp", v))   # sibling with a shared prefix is not under /p

    def test_longer_key_wins(self):
        v = {"mode": "off", "projects": {"/p": "off", "/p/api": "on"}}
        self.assertTrue(P.watch_on("/p/api/src", v))
        self.assertFalse(P.watch_on("/p/web", v))

    def test_own_pane_and_round_trip(self):
        self.assertIn("mailbox_watch", P.PREFS_OWN_PANE)
        out = P.prefs_get()
        self.assertNotIn("mailbox_watch", out["keys"])
        self.assertEqual(out["mailbox_watch"], {"mode": "on", "projects": {}})
        v = {"mode": "off", "projects": {"/w": "on"}}
        self.assertEqual(P.prefs_set({"key": "mailbox_watch", "value": v})[0], 200)
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["mailbox_watch"], v)
        self.assertEqual(P.prefs_get()["mailbox_watch"], v)
        self.assertEqual(P.prefs_set({"key": "mailbox_watch", "value": {"mode": "x"}})[0], 400)
        self.assertEqual(P.prefs_set({"key": "mailbox_watch", "reset": True})[0], 200)
        self.assertEqual(P.prefs_get()["mailbox_watch"], {"mode": "on", "projects": {}})


class MailboxConfigLoad(unittest.TestCase):
    def test_load_keeps_key_without_warning(self):
        import mailbox_config as mc
        tmp = tempfile.mkdtemp(prefix="sidereus-mwcfg-")
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "config.local.json")
        v = {"mode": "off", "projects": {"/w": "on"}}
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"mailbox_watch": v}, f)
        warned = []
        with mock.patch.object(mc, "config_path", lambda: path), mock.patch.object(mc, "_cache", None), \
                mock.patch.object(mc, "_warn_once", lambda key, msg, *a, **k: warned.append(key)):
            got = mc.load(reload=True)
        self.assertEqual(got.get("mailbox_watch"), v)
        self.assertEqual(warned, [])

    def test_merge_keeps_all_prefs_owned_keys(self):
        import mailbox_config as mc
        over = {"features": {"retro": False}, "pipeline_apply": {"mode": "ask", "projects": {}}}
        with mock.patch.object(mc, "_warn_once", lambda *a, **k: self.fail("warned")):
            out = mc._merge({"port": 1}, over)
        self.assertEqual({k: out[k] for k in over}, over)

    def test_prefs_own_matches_prefs_pane(self):
        import mailbox_config as mc
        self.assertEqual(set(mc._PREFS_OWN), P.PREFS_OWN_PANE)

    def test_merge_keeps_claude_roots(self):
        import mailbox_config as mc
        roots = [{"dir": "/x/.claude-alt", "label": "Alt"}]
        with mock.patch.object(mc, "_warn_once", lambda *a, **k: self.fail("warned")):
            out = mc._merge({"port": 1}, {"claude_roots": roots})
        self.assertEqual(out["claude_roots"], roots)

    def test_server_import_sees_saved_feature_toggle(self):
        # Fresh interpreter = the server's import order (sidereus.config CFG -> prefs.effective -> features._TOGGLES).
        import subprocess
        import sys
        from tests._load import ROOT
        tmp = tempfile.mkdtemp(prefix="sidereus-mwfeat-")
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "config.local.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"features": {"retro": False}, "pipeline_apply": {"mode": "off", "projects": {}}}, f)
        env = dict(os.environ, MAILBOX_DIR=tmp, MAILBOX_CONFIG=path)
        code = ("import json; from sidereus import prefs, features; "
                "print(json.dumps([prefs.effective('features'), features._TOGGLES, prefs.effective('pipeline_apply')['mode']]))")
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60, encoding="utf-8")
        self.assertEqual(out.returncode, 0, out.stderr[-500:])
        eff, tog, mode = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertEqual((eff, tog, mode), ({"retro": False}, {"retro": False}, "off"))


if __name__ == "__main__":
    unittest.main()
