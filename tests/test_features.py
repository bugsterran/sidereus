"""Feature registry (sidereus/features.py): route / thread / state gates and toggle resolution.

⚠Manifests and toggles are patched on the features module — never the live config or features/ files.
"""
import json
import re
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import load, sidereus, ROOT
from tests.test_prefs import get
from tests.test_routes_post import post
from tests.test_state_guard import _READERS

cs = load()
F = sidereus("features")
P = sidereus("prefs")
ST = sidereus("state")


def _m(fid, deps=(), routes=(), threads=(), state_keys=()):
    return {"id": fid, "title": fid, "default_on_public": False, "deps": list(deps), "modules": [],
            "routes": list(routes), "threads": list(threads), "state_keys": list(state_keys), "web": [], "settings": []}


class Features(unittest.TestCase):
    def setUp(self):
        man = {"retro": _m("retro", deps=["hist"], routes=["/api/retro"], threads=["tl_warm"], state_keys=["fail1h"]),
               "hist": _m("hist", routes=["/api/prefs*"])}
        self.tmp = tempfile.mkdtemp(prefix="sidereus-feat-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        for p in (mock.patch.object(F, "_MANIFESTS", man), mock.patch.object(F, "_TOGGLES", {}),
                  mock.patch.object(P, "CONFIG_PATH", os.path.join(self.tmp, "config.local.json"))):
            p.start()
            self.addCleanup(p.stop)

    def _off(self, **t):
        p = mock.patch.object(F, "_TOGGLES", t)
        p.start()
        self.addCleanup(p.stop)

    def test_missing_key_all_on(self):
        self.assertEqual(F.snapshot(), {"hist": True, "retro": True})
        self.assertTrue(F.thread_on("tl_warm"))
        self.assertEqual(F.state_off(), set())
        self.assertTrue(F.on("sessions"))              # no manifest = core = on

    def test_dep_off_forces_dependents_off(self):
        self._off(hist=False)
        self.assertEqual(F.snapshot(), {"hist": False, "retro": False})
        self._off(retro=False)
        self.assertEqual(F.snapshot(), {"hist": True, "retro": False})

    def test_route_feature(self):
        self.assertEqual(F.route_feature("/api/retro"), "retro")
        self.assertEqual(F.route_feature("/api/prefs/set"), "hist")   # prefix claim
        self.assertIsNone(F.route_feature("/api/state"))

    def test_get_off_404(self):
        self._off(retro=False)
        self.assertEqual(get("/api/retro"), (404, {"error": "feature off"}))

    def test_post_off_404(self):
        self._off(hist=False)
        code, out, h = post("/api/prefs/set", {"key": "viewer_me", "value": "x"})
        self.assertEqual((code, out), (404, {"error": "feature off"}))
        self.assertTrue(h.close_connection)
        self.assertFalse(os.path.exists(P.CONFIG_PATH))     # the route never ran

    def test_thread_off(self):
        self._off(retro=False)
        self.assertFalse(F.thread_on("tl_warm"))
        self.assertTrue(F.thread_on("win_loop"))

    def test_state_key_absent(self):
        saved = {k: getattr(ST, k) for k in _READERS}
        self.addCleanup(lambda: [setattr(ST, k, v) for k, v in saved.items()])
        for k, v in _READERS.items():
            setattr(ST, k, v)
        s = ST.state()
        self.assertIn("fail1h", s)
        self.assertEqual(s["features"], {"hist": True, "retro": True})
        self._off(retro=False)
        s = ST.state()
        self.assertNotIn("fail1h", s)
        self.assertEqual(s["features"], {"hist": True, "retro": False})

    def test_load_skips_bad_manifest(self):
        with open(os.path.join(self.tmp, "a.json"), "w") as f:
            json.dump(_m("ok"), f)
        with open(os.path.join(self.tmp, "b.json"), "w") as f:
            f.write("{broken")
        with mock.patch.object(F, "warn_once", lambda *a, **k: None):
            self.assertEqual(sorted(F._load(self.tmp)), ["ok"])

    def test_prefs_validator(self):
        self.assertEqual(P._v_features({"retro": False}), {"retro": False})
        for bad in ([], {"retro": 1}, {"../x": True}):
            with self.assertRaises(ValueError):
                P._v_features(bad)

    def test_example_config_ships_public_defaults(self):
        with open(os.path.join(ROOT, "config.example.json"), encoding="utf-8") as f:
            ex = json.load(f)["features"]
        real = F._load(F.FEATURES_DIR)
        self.assertEqual(ex, {fid: m["default_on_public"] for fid, m in real.items()})

    def test_doc_routes_in_manifest(self):
        # Every route FEATURES.md lists for a manifest feature must be claimed by it, or turning it off leaves that route live.
        real = F._load(F.FEATURES_DIR)
        with open(os.path.join(ROOT, "docs", "dev", "FEATURES.md"), encoding="utf-8") as f:
            rows = [ln.split("|") for ln in f if ln.startswith("| ")]
        seen = 0
        for cells in rows:
            fid = cells[1].strip()
            if fid not in real:
                continue
            for r in re.findall(r"/api/[\w/\-]+\*?", cells[2]):
                seen += 1
                with mock.patch.object(F, "_MANIFESTS", {fid: real[fid]}):
                    self.assertEqual(F.route_feature(r), fid, "%s listed under %s but not in features/%s.json" % (r, fid, fid))
        self.assertGreater(seen, 5)


if __name__ == "__main__":
    unittest.main()
