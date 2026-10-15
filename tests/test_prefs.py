"""«내 방식» server prefs (sidereus/prefs.py + GET /api/prefs, POST /api/prefs/set).

⚠prefs.CONFIG_PATH points at a temp dir in every test — the live config.local.json is never read or written.
"""
import http.client
import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from unittest import mock

from tests._load import load, sidereus
from tests.test_routes_post import post, HOST, PORT, EVIL

cs = load()
P = sidereus("prefs")
CC = sidereus("cc_settings")
ORIGIN = "http://127.0.0.1:%d" % PORT
_ENV_CLEAR = {"MAILBOX_VIEWER_ME": "", "MAILBOX_VIEWER_ROOM": "", "SIDEREUS_PORT": ""}


def get(path):
    h = cs.Handler.__new__(cs.Handler)
    h.headers = http.client.parse_headers(io.BytesIO(("Host: %s\r\n\r\n" % HOST).encode("latin-1")))
    h.rfile, h.wfile = io.BytesIO(b""), io.BytesIO()
    h.path, h.command, h.request_version = path, "GET", "HTTP/1.1"
    h.requestline = "GET %s HTTP/1.1" % path
    h.close_connection = False
    h.client_address = ("127.0.0.1", 0)
    h.do_GET()
    head, _, payload = h.wfile.getvalue().partition(b"\r\n\r\n")
    return int(head.split(b"\r\n", 1)[0].split()[1]), json.loads(payload.decode("utf-8"))


class Prefs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-prefs-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, "config.local.json")
        # ⚠cc_settings paths too: GET /api/prefs also reads settings.json
        for p in (mock.patch.object(P, "CONFIG_PATH", self.path), mock.patch.dict(os.environ, _ENV_CLEAR),
                  mock.patch.object(CC, "SETTINGS_PATH", os.path.join(self.tmp, "settings.json")),
                  mock.patch.object(CC, "TRASH_DIR", os.path.join(self.tmp, "trash")),
                  mock.patch.object(P, "warn_once", lambda *a, **k: None)):
            p.start()
            self.addCleanup(p.stop)

    def _file(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def test_port_pref(self):
        self.assertEqual(get("/api/prefs")[1]["keys"]["port"], {"value": 8799, "default": 8799, "src": "default", "restart": True})
        for bad in (80, 70000, "9000", True, 1023):
            code, out, _ = post("/api/prefs/set", {"key": "port", "value": bad}, origin=ORIGIN)
            self.assertEqual(code, 400, bad)
        self.assertFalse(os.path.exists(self.path))
        code, out, _ = post("/api/prefs/set", {"key": "port", "value": 9123}, origin=ORIGIN)
        self.assertEqual((code, out["value"]), (200, 9123))
        self.assertEqual(self._file()["port"], 9123)
        self.assertEqual(post("/api/prefs/set", {"key": "port", "value": 9200}, origin=EVIL)[0], 403)
        self.assertEqual(self._file()["port"], 9123)
        with mock.patch.dict(os.environ, {"SIDEREUS_PORT": "9300"}):
            self.assertEqual(get("/api/prefs")[1]["keys"]["port"]["src"], "env")
            self.assertEqual(post("/api/prefs/set", {"key": "port", "value": 9200}, origin=ORIGIN)[0], 400)

    def test_defaults_when_no_file(self):
        code, out = get("/api/prefs")
        self.assertEqual(code, 200)
        self.assertEqual(out["path"], self.path)
        k = out["keys"]
        self.assertEqual(sorted(k), ["cc_auto_compact", "cc_compact_window", "compact_history", "default_room", "port", "saver_hook_dir", "viewer_me"])
        self.assertEqual(k["port"], {"value": 8799, "default": 8799, "src": "default", "restart": True})
        self.assertEqual(k["saver_hook_dir"]["value"], "~/.claude/hooks")
        self.assertEqual(k["compact_history"]["value"], [])
        self.assertFalse(os.path.exists(self.path))

    def test_set_keeps_unknown_keys_and_backs_up(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"_comment": "x", "self": {"ids": ["a"]}, "zzz": 1}, f)
        code, out, _ = post("/api/prefs/set", {"key": "port", "value": 9300}, origin=ORIGIN)
        self.assertEqual((code, out), (200, {"ok": True, "value": 9300, "restart": True}))
        d = self._file()
        self.assertEqual(d, {"_comment": "x", "self": {"ids": ["a"]}, "zzz": 1, "port": 9300})
        with open(self.path + ".bak", encoding="utf-8") as f:
            self.assertNotIn("port", json.load(f))
        self.assertEqual(get("/api/prefs")[1]["keys"]["port"]["src"], "file")
        code, out, _ = post("/api/prefs/set", {"key": "port", "reset": True}, origin=ORIGIN)
        self.assertEqual(out["value"], 8799)
        self.assertNotIn("port", self._file())
        self.assertEqual([n for n in os.listdir(self.tmp) if ".tmp" in n], [])

    def test_bom_config_reads(self):
        with open(self.path, "wb") as f:
            f.write(b"\xef\xbb\xbf" + json.dumps({"port": 9500}).encode("utf-8"))
        self.assertEqual(get("/api/prefs")[1]["keys"]["port"]["value"], 9500)
        import mailbox_config as mc
        saved = (mc._cache, mc.FILE_OK)
        self.addCleanup(lambda: (setattr(mc, "_cache", saved[0]), setattr(mc, "FILE_OK", saved[1])))
        with mock.patch.dict(os.environ, {"MAILBOX_CONFIG": self.path}), mock.patch.object(mc, "_warn_once", lambda *a, **k: None):
            mc.load(reload=True)
        self.assertTrue(mc.FILE_OK)

    def test_origin_required(self):
        for origin in (None, EVIL):
            code, out, _ = post("/api/prefs/set", {"key": "viewer_me", "value": "나"}, origin=origin)
            self.assertEqual(code, 403, origin)
        self.assertFalse(os.path.exists(self.path))

    def test_rejects(self):
        bad = [{"key": "nope", "value": 1}, {"key": "port"}, {"key": "port", "value": "8800"},
               {"key": "port", "value": True}, {"key": "port", "value": 80}, {"key": "saver_hook_dir", "value": "rel/dir"},
               {"key": "saver_hook_dir", "value": "~/a/../b"}, {"key": "viewer_me", "value": "a/b"},
               {"key": "default_room", "value": ""},
               {"key": "compact_history", "value": [["2026-09-10", 1000], ["2026-09-03", 2000]]},
               {"key": "compact_history", "value": [["2026-13-01", 1000]]},
               {"key": "compact_history", "value": [["2026-09-01", 5]]}, []]
        for body in bad:
            code, out, _ = post("/api/prefs/set", body, origin=ORIGIN)
            self.assertEqual(code, 400, body)
            self.assertFalse(out["ok"])
        self.assertFalse(os.path.exists(self.path))

    def test_broken_file_not_overwritten(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{broken")
        code, out, _ = post("/api/prefs/set", {"key": "viewer_me", "value": "나"}, origin=ORIGIN)
        self.assertEqual(code, 400)
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "{broken")

    def test_env_key_read_only(self):
        with mock.patch.dict(os.environ, {"MAILBOX_VIEWER_ME": "envme"}):
            k = get("/api/prefs")[1]["keys"]["viewer_me"]
            self.assertEqual((k["value"], k["src"]), ("envme", "env"))
            code, _, _ = post("/api/prefs/set", {"key": "viewer_me", "value": "나"}, origin=ORIGIN)
            self.assertEqual(code, 400)

    def test_compact_history_roundtrip(self):
        rows = [["2026-09-01", None], ["2026-09-05", 250000]]
        code, out, _ = post("/api/prefs/set", {"key": "compact_history", "value": rows}, origin=ORIGIN)
        self.assertEqual((code, out["value"]), (200, rows))
        self.assertEqual(P.compact_hist({"compact_history": rows}),
                         ((0, None), (datetime(2026, 9, 1).timestamp(), None), (datetime(2026, 9, 5).timestamp(), 250000)))

    def test_effective_defaults_match_old_constants(self):
        self.assertEqual(P.compact_hist({}), ((0, None),))
        self.assertEqual(P.compact_hist({"compact_history": []}), P.compact_hist({}))
        self.assertEqual(P.effective("port", {}), 8799)
        self.assertEqual(P.effective("port", {"port": 10}), 8799)
        self.assertEqual(P.effective("saver_hook_dir", {"saver_hook_dir": "rel"}), "~/.claude/hooks")

    def test_mailbox_config_merge_accepts_new_keys(self):
        import mailbox_config as mc
        m = mc._merge(mc.DEFAULTS, {"port": 9400, "compact_history": [["2026-09-01", 1000]],
                                    "saver_hook_dir": "/x"})
        self.assertEqual((m["port"], m["compact_history"], m["saver_hook_dir"]),
                         (9400, [["2026-09-01", 1000]], "/x"))
        with mock.patch.object(mc, "_warn_once", lambda *a: None):
            m = mc._merge(mc.DEFAULTS, {"port": "9400", "compact_history": ["x"]})
        self.assertEqual((m["port"], m["compact_history"]), (8799, []))


if __name__ == "__main__":
    unittest.main()
