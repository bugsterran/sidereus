"""Settings «기능» (sidereus/features.py listing/check_toggles + /api/prefs) and its web toggle logic (90c-features.js).

⚠Manifests, config path and settings.json are patched to temp values — never the live files.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tests._load import load, sidereus, js_fn
from tests.test_prefs import get, ORIGIN, _ENV_CLEAR
from tests.test_routes_post import post, EVIL
from tests.test_features import _m
from tests._node import node_e

cs = load()
F = sidereus("features")
P = sidereus("prefs")
CC = sidereus("cc_settings")


class FeaturePrefs(unittest.TestCase):
    def setUp(self):
        man = {"retro": _m("retro", deps=["hist", "failures"]), "hist": _m("hist")}
        man["retro"]["title"] = "돌아보기"
        self.tmp = tempfile.mkdtemp(prefix="sidereus-fprefs-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, "config.local.json")
        for p in (mock.patch.object(F, "_MANIFESTS", man), mock.patch.object(F, "_TOGGLES", {}),
                  mock.patch.object(P, "CONFIG_PATH", self.path), mock.patch.dict(os.environ, _ENV_CLEAR),
                  mock.patch.object(CC, "SETTINGS_PATH", os.path.join(self.tmp, "settings.json")),
                  mock.patch.object(CC, "TRASH_DIR", os.path.join(self.tmp, "trash")),
                  mock.patch.object(P, "warn_once", lambda *a, **k: None)):
            p.start()
            self.addCleanup(p.stop)

    def _file(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def test_listing_payload(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"features": {"hist": False}}, f)
        rows = F.listing()
        self.assertEqual([r["id"] for r in rows], ["hist", "retro"])
        self.assertEqual(sorted(rows[0]), ["default_on_public", "deps", "id", "on", "set", "title"])   # ⚠allow-list, metadata only
        self.assertEqual((rows[0]["on"], rows[0]["set"]), (True, False))     # running = import-time; saved = file now
        self.assertEqual((rows[1]["title"], rows[1]["deps"], rows[1]["set"]), ("돌아보기", ["hist", "failures"], True))

    def test_get_prefs_has_features(self):
        code, out = get("/api/prefs")
        self.assertEqual(code, 200)
        self.assertEqual([r["id"] for r in out["features"]], ["hist", "retro"])
        self.assertNotIn("features", out["keys"])

    def test_check_toggles(self):
        F.check_toggles({"retro": False, "hist": True})
        for bad in ({"nope": False}, {"retro": 0}, [], None, {"failures": False}):   # failures has no manifest = core
            with self.assertRaises(ValueError):
                F.check_toggles(bad)

    def test_post_known_ids_saved(self):
        code, out, _h = post("/api/prefs/set", {"key": "features", "value": {"retro": False}}, origin=ORIGIN)
        self.assertEqual((code, out["ok"], out["restart"]), (200, True, True))
        self.assertEqual(self._file()["features"], {"retro": False})
        code, out, _h = post("/api/prefs/set", {"key": "features", "reset": True}, origin=ORIGIN)
        self.assertEqual(code, 200)
        self.assertNotIn("features", self._file())

    def test_post_rejects(self):
        for val in ({"nope": False}, {"retro": "off"}, ["retro"]):
            code, out, _h = post("/api/prefs/set", {"key": "features", "value": val}, origin=ORIGIN)
            self.assertEqual((code, out["ok"]), (400, False), val)
        code, _out, _h = post("/api/prefs/set", {"key": "features", "value": {"retro": False}}, origin=EVIL)
        self.assertEqual(code, 403)
        code, _out, _h = post("/api/prefs/set", {"key": "features", "value": {"retro": False}})
        self.assertEqual(code, 403)
        self.assertFalse(os.path.exists(self.path))


JS = r"""
const R = {}, deps = {retro: ['hist', 'failures'], hist: [], a: ['b'], b: ['a']};
R.on = mpfEff({retro: true, hist: true}, deps, 'retro');
R.depOff = mpfEff({retro: true, hist: false}, deps, 'retro');
R.core = mpfEff({retro: true}, deps, 'failures');
R.cycle = mpfEff({a: true, b: true}, deps, 'a');
MPSRV = {features: [{id: 'hist', set: true}, {id: 'retro', set: false}]};
R.want0 = mpfWant(mpfRows());
mpfAct('retro:1'); mpfAct('nope:0');
R.want1 = mpfWant(mpfRows());
mpfAct('undo');
R.want2 = mpfWant(mpfRows());
process.stdout.write(JSON.stringify(R));
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class FeaturePaneJs(unittest.TestCase):
    def test_toggle_logic(self):
        src = "let MPSRV = null, MPF_PEND = null, MPF_NOTE = null;\n" + "\n".join(
            js_fn(f) for f in ("mpfRows", "mpfWant", "mpfEff", "mpfAct")) + "\n" + JS
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        R = json.loads(r.stdout)
        self.assertEqual((R["on"], R["depOff"], R["core"], R["cycle"]), (True, False, True, True))
        self.assertEqual(R["want0"], {"hist": True, "retro": False})
        self.assertEqual(R["want1"], {"hist": True, "retro": True})      # unknown id ignored
        self.assertEqual(R["want2"], R["want0"])


if __name__ == "__main__":
    unittest.main()
