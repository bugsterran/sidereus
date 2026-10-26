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


class _FakeThread:
    """threading.Thread stand-in: start() records the name, runs nothing."""
    def __init__(self, runs):
        self.runs = runs

    def __call__(self, target=None, name=None, daemon=None):
        runs = self.runs
        return type("T", (), {"start": lambda _s: runs.append(name)})()


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

    def test_save_replaces_cache(self):
        old = F._TOGGLES
        code, out = F.save({"key": "features", "value": {"retro": False}})
        self.assertEqual((code, out["restart"], out["features"]), (200, False, {"hist": True, "retro": False}))
        self.assertIsNot(F._TOGGLES, old)              # swapped whole, never mutated
        self.assertEqual(old, {})
        code, out = F.save({"key": "features", "reset": True})
        self.assertEqual((code, F._TOGGLES, out["features"]), (200, {}, {"hist": True, "retro": True}))

    def test_save_write_failure_restores(self):
        old = F._TOGGLES
        with mock.patch.object(P, "prefs_set", lambda req: (500, {"ok": False, "err": "write failed"})):
            code, out = F.save({"key": "features", "value": {"retro": False}})
        self.assertEqual((code, out["ok"]), (500, False))
        self.assertIs(F._TOGGLES, old)
        self.assertEqual(F.save({"key": "features", "value": {"nope": False}})[0], 400)
        self.assertIs(F._TOGGLES, old)

    def test_on_off_on_live(self):
        saved = {k: getattr(ST, k) for k in _READERS}
        self.addCleanup(lambda: [setattr(ST, k, v) for k, v in saved.items()])
        for k, v in _READERS.items():
            setattr(ST, k, v)
        stub = lambda h, u: h._send(200, "{}", "application/json; charset=utf-8")   # noqa: E731  (no live retro read)
        p = mock.patch.dict(cs.Handler._GET_ROUTES, {"/api/retro": stub})
        p.start()
        self.addCleanup(p.stop)
        for want, live in (({}, True), ({"retro": False}, False), ({"hist": False}, False), ({}, True)):
            self.assertEqual(F.save({"key": "features", "value": want})[0], 200)
            self.assertEqual(get("/api/retro"), (200, {}) if live else (404, {"error": "feature off"}), want)
            self.assertEqual("fail1h" in ST.state(), live, want)
            self.assertEqual(F.snapshot()["retro"], live, want)    # hist off forces retro off

    def test_thread_registry(self):
        runs = []
        for p in (mock.patch.object(F, "_STARTED", set()), mock.patch.object(F, "_THREAD_SPEC", ()),
                  mock.patch.object(F.threading, "Thread", _FakeThread(runs))):
            p.start()
            self.addCleanup(p.stop)
        once = []
        F.register_threads((("tl_warm", lambda: None, "loop"), ("win_loop", lambda: once.append(1), "once")))
        self._off(retro=False)
        F.start_threads()
        self.assertEqual((runs, once), ([], [1]))          # claimed loop not started while off; core once runs
        for want in ({}, {"retro": False}, {}):
            self.assertEqual(F.save({"key": "features", "value": want})[0], 200)
        self.assertEqual((runs, once), (["tl_warm"], [1]))  # started once on toggle-on; on→off→on adds none

    def test_load_skips_bad_manifest(self):
        with open(os.path.join(self.tmp, "a.json"), "w", encoding="utf-8") as f:
            json.dump(_m("ok"), f)
        with open(os.path.join(self.tmp, "b.json"), "w", encoding="utf-8") as f:
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
