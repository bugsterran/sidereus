"""Page UI prefs store (sidereus/ui_prefs.py + GET /api/ui-prefs.js, POST /api/ui-prefs[/reset]).

⚠ui_prefs.PATH / BAK_DIR point at a temp dir in every test — the live ui-prefs.json is never read or written.
"""
import http.client
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import load, sidereus
from tests.test_routes_post import post, HOST, PORT

cs = load()
U = sidereus("ui_prefs")
B = sidereus("bus")
ORIGIN = "http://127.0.0.1:%d" % PORT


def get_js(extra="Sec-Fetch-Site: same-origin\r\n", path="/api/ui-prefs.js"):
    h = cs.Handler.__new__(cs.Handler)
    h.headers = http.client.parse_headers(io.BytesIO(("Host: %s\r\n%s\r\n" % (HOST, extra)).encode("latin-1")))
    h.rfile, h.wfile = io.BytesIO(b""), io.BytesIO()
    h.path, h.command, h.request_version = path, "GET", "HTTP/1.1"
    h.requestline = "GET %s HTTP/1.1" % path
    h.close_connection = False
    h.client_address = ("127.0.0.1", 0)
    h.do_GET()
    head, _, payload = h.wfile.getvalue().partition(b"\r\n\r\n")
    return head.decode("latin-1"), payload.decode("utf-8")


class UiPrefs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-uiprefs-")
        self.path = os.path.join(self.tmp, "ui-prefs.json")
        self.bak = os.path.join(self.tmp, "bak")
        for p in (mock.patch.object(U, "PATH", self.path), mock.patch.object(U, "BAK_DIR", self.bak),
                  mock.patch.object(U, "_MEM", {}), mock.patch.object(U, "_strftime", lambda f: "20260101-000000"),
                  mock.patch.object(U, "_REV", 1000)):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _file(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def test_get_null_without_file_then_literal(self):
        head, body = get_js()
        self.assertIn("200", head.split("\r\n", 1)[0])
        self.assertIn("Content-Type: application/javascript", head)
        self.assertIn("Cache-Control: no-store", head)
        self.assertEqual(body, "window.__UIP=null;window.__UIPREV=1000;")
        code, out, _ = post("/api/ui-prefs", {"set": {"mbRoom": "a</script>", "dfW": 300}}, origin=ORIGIN)
        self.assertEqual((code, out), (200, {"ok": True, "rev": 1001, "prev": 1000}))
        _, body = get_js()
        tail = ";window.__UIPREV=1001;"
        self.assertTrue(body.startswith("window.__UIP=") and body.endswith(tail))
        self.assertNotIn("</", body)
        self.assertEqual(json.loads(body[len("window.__UIP="):-len(tail)]), {"mbRoom": "a</script>", "dfW": 300})

    def test_get_requires_same_origin(self):
        post("/api/ui-prefs", {"set": {"mbRoom": "secret-path"}}, origin=ORIGIN)
        for extra in ("", "Sec-Fetch-Site: cross-site\r\n", "Sec-Fetch-Site: same-site\r\n"):
            head, body = get_js(extra)
            self.assertIn("403", head.split("\r\n", 1)[0], extra)
            self.assertNotIn("__UIP", body)
            self.assertNotIn("secret-path", body)

    def test_merge_and_delete(self):
        post("/api/ui-prefs", {"set": {"mbA": 1, "sidereus.x": [1, 2]}}, origin=ORIGIN)
        code, _, _ = post("/api/ui-prefs", {"set": {"mbB": "b"}, "del": ["mbA"]}, origin=ORIGIN)
        self.assertEqual(code, 200)
        self.assertEqual(self._file(), {"sidereus.x": [1, 2], "mbB": "b"})

    def test_bad_keys_skipped_rest_applied(self):
        long = "mb" + "x" * 200
        code, out, _ = post("/api/ui-prefs", {"set": {"evil": 1, "dfWx": 1, long: 1, "mbOk": 2,
                                                      "mbBig": "x" * (U.VALUE_MAX + 1)}, "del": ["nope"]}, origin=ORIGIN)
        self.assertEqual(code, 200)
        self.assertEqual(sorted(out["skipped"]), sorted(["evil", "dfWx", long[:U.KEY_MAX], "mbBig", "nope"]))
        self.assertEqual(self._file(), {"mbOk": 2})

    def test_corrupt_file_backed_up_before_write(self):
        with open(self.path, "wb") as f:
            f.write(b"{not json")
        warned = []
        with mock.patch.object(U, "warn_once", lambda k, *a, **kw: warned.append(k)):   # expected warning, keep stderr clean
            code, _, _ = post("/api/ui-prefs", {"set": {"mbA": 1}}, origin=ORIGIN)
        self.assertEqual(code, 200)
        self.assertEqual(warned, ["ui-prefs-read"])
        with open(os.path.join(self.bak, "20260101-000000", "ui-prefs.json"), "rb") as f:
            self.assertEqual(f.read(), b"{not json")
        self.assertEqual(self._file(), {"mbA": 1})

    def test_caps_400(self):
        for body in ({"set": []}, {"del": "mbA"}, [1]):
            code, _, _ = post("/api/ui-prefs", body, origin=ORIGIN)
            self.assertEqual(code, 400, body)
        with mock.patch.object(U, "FILE_MAX", 50):
            code, _, _ = post("/api/ui-prefs", {"set": {"mbA": "x" * 60}}, origin=ORIGIN)
            self.assertEqual(code, 400)
        self.assertFalse(os.path.exists(self.path))

    def test_no_origin_403(self):
        for path in ("/api/ui-prefs", "/api/ui-prefs/reset"):
            code, _, _ = post(path, {"set": {"mbA": 1}})
            self.assertEqual(code, 403)
        self.assertFalse(os.path.exists(self.path))

    def test_path_none_writes_nothing(self):
        with mock.patch.object(U, "PATH", None):
            code, _, _ = post("/api/ui-prefs", {"set": {"mbA": 1}}, origin=ORIGIN)
            self.assertEqual(code, 200)
            self.assertEqual(U.load(), {"mbA": 1})
            self.assertEqual(post("/api/ui-prefs/reset", {}, origin=ORIGIN)[0], 200)
        self.assertEqual(os.listdir(self.tmp), [])

    def test_permission_error_once_retries(self):
        real, calls = os.replace, []

        def flaky(a, b):
            calls.append(1)
            if len(calls) == 1:
                raise PermissionError("locked")
            return real(a, b)
        with mock.patch.object(B, "_ATOMIC_WAIT", 0), mock.patch.object(B.os, "replace", flaky):
            code, _, _ = post("/api/ui-prefs", {"set": {"agPH": 1}}, origin=ORIGIN)
        self.assertEqual((code, len(calls)), (200, 2))
        self.assertEqual(self._file(), {"agPH": 1})

    def test_reset_moves_to_backup(self):
        post("/api/ui-prefs", {"set": {"mbA": 1}}, origin=ORIGIN)
        code, out, _ = post("/api/ui-prefs/reset", {}, origin=ORIGIN)
        self.assertEqual(code, 200)
        moved = os.path.join(self.bak, "20260101-000000", "ui-prefs.json")
        with open(moved, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"mbA": 1})
        self.assertEqual(self._file(), {"_v": 1})
        post("/api/ui-prefs/reset", {}, origin=ORIGIN)     # same second: a -2 folder, nothing overwritten
        self.assertTrue(os.path.exists(os.path.join(self.bak, "20260101-000000-2", "ui-prefs.json")))


    def test_patch_merges_per_entry(self):
        post("/api/ui-prefs", {"set": {"mbCol": json.dumps({"a": 1, "b": 2})}}, origin=ORIGIN)
        code, out, _ = post("/api/ui-prefs", {"patch": {"mbCol": {"c": 3}}}, origin=ORIGIN)   # another tab adds c
        self.assertEqual(code, 200)
        self.assertNotIn("skipped", out)
        stored = self._file()["mbCol"]
        self.assertIsInstance(stored, str)
        self.assertNotIn(" ", stored)                      # compact JSON string
        self.assertEqual(json.loads(stored), {"a": 1, "b": 2, "c": 3})

    def test_patch_null_deletes_one_entry(self):
        post("/api/ui-prefs", {"set": {"mbCol": json.dumps({"a": 1, "b": 2})}}, origin=ORIGIN)
        post("/api/ui-prefs", {"patch": {"mbCol": {"a": None}}}, origin=ORIGIN)
        self.assertEqual(json.loads(self._file()["mbCol"]), {"b": 2})

    def test_patch_bad_stored_string_starts_empty(self):
        for bad in ("not json", json.dumps([1, 2]), 7):
            post("/api/ui-prefs", {"set": {"mbCol": bad}}, origin=ORIGIN)
            post("/api/ui-prefs", {"patch": {"mbCol": {"x": 1}}}, origin=ORIGIN)
            self.assertEqual(json.loads(self._file()["mbCol"]), {"x": 1}, bad)

    def test_patch_key_checks(self):
        code, out, _ = post("/api/ui-prefs", {"patch": {"evil": {"a": 1}, "mbBig": {"a": "x" * (U.VALUE_MAX + 1)},
                                                          "mbNot": [1], "mbOk": {"a": 1}}}, origin=ORIGIN)
        self.assertEqual(code, 200)
        self.assertEqual(sorted(out["skipped"]), ["evil", "mbBig", "mbNot"])
        self.assertEqual(self._file(), {"mbOk": '{"a":1}'})
        self.assertEqual(post("/api/ui-prefs", {"patch": [1]}, origin=ORIGIN)[0], 400)

    def test_rev_increments_on_update_and_reset(self):
        self.assertEqual(U.rev(), 1000)
        _, out, _ = post("/api/ui-prefs", {"set": {"mbA": 1}}, origin=ORIGIN)
        self.assertEqual((out["rev"], out["prev"]), (1001, 1000))
        _, out, _ = post("/api/ui-prefs/reset", {}, origin=ORIGIN)
        self.assertEqual((out["rev"], out["prev"]), (1002, 1001))
        self.assertEqual(U.rev(), 1002)

    def test_rev_increments_memory_only(self):
        with mock.patch.object(U, "PATH", None):
            self.assertEqual(U.update({"patch": {"mbA": {"k": 1}}})[1]["rev"], 1001)
            self.assertEqual(U.reset()[1], {"ok": True, "rev": 1002, "prev": 1001})
            self.assertEqual(U._MEM, {"mbA": '{"k":1}'})
        self.assertFalse(os.path.exists(self.path))

    def test_get_json_snapshot(self):
        post("/api/ui-prefs", {"set": {"mbRoom": "r"}}, origin=ORIGIN)
        head, body = get_js(path="/api/ui-prefs")
        self.assertIn("200", head.split("\r\n", 1)[0])
        self.assertEqual(json.loads(body), {"rev": 1001, "prefs": {"mbRoom": "r"}})

    def test_get_json_requires_same_origin(self):
        post("/api/ui-prefs", {"set": {"mbRoom": "secret-path"}}, origin=ORIGIN)
        for extra in ("", "Sec-Fetch-Site: cross-site\r\n", "Sec-Fetch-Site: same-site\r\n"):
            head, body = get_js(extra, path="/api/ui-prefs")
            self.assertIn("403", head.split("\r\n", 1)[0], extra)
            self.assertNotIn("secret-path", body)


class StateUiRev(unittest.TestCase):
    def setUp(self):
        from tests.test_state_guard import _READERS
        st = sidereus("state")
        saved = {k: getattr(st, k) for k in list(_READERS) + ["warn_once", "state_off", "ui_prefs_rev"]}
        self.addCleanup(lambda: [setattr(st, k, v) for k, v in saved.items()])
        for k, v in _READERS.items():
            setattr(st, k, v)
        st.warn_once = lambda *a, **k: None
        st.state_off = lambda: set()
        st.ui_prefs_rev = lambda: 4242
        self.st = st

    def test_state_has_int_rev_only(self):
        s = self.st.state()
        self.assertEqual(s["uiRev"], 4242)
        self.assertIsInstance(s["uiRev"], int)
        for k in ("prefs", "uiPrefs", "__UIP"):
            self.assertNotIn(k, s)


if __name__ == "__main__":
    unittest.main()
