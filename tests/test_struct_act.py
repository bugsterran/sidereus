"""Structure warm-up idle marker: only page loads and POST /api/act count as human input (traps/arch.md)."""
import http.client
import io
import os
import unittest
from unittest import mock

from tests._load import load, sidereus
from tests.test_routes_post import EVIL, HOST, OWN, post

cs = load()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
st = sidereus("structure")


def get(path):
    h = cs.Handler.__new__(cs.Handler)
    h.headers = http.client.parse_headers(io.BytesIO(("Host: %s\r\nSec-Fetch-Site: same-origin\r\n\r\n" % HOST).encode("latin-1")))
    h.rfile, h.wfile = io.BytesIO(b""), io.BytesIO()
    h.path, h.command, h.request_version = path, "GET", "HTTP/1.1"
    h.requestline = "GET %s HTTP/1.1" % path
    h.close_connection = False
    h.client_address = ("127.0.0.1", 0)
    h.do_GET()


def _stub(self, u):
    return self._send(200, "{}", "application/json")


class StructActTest(unittest.TestCase):
    def setUp(self):
        saved = st._struct_act[0]
        self.addCleanup(st._struct_act.__setitem__, 0, saved)
        st._struct_act[0] = 0.0
        p = mock.patch.object(st, "time", type("T", (), {"time": staticmethod(lambda: 5000.0)}))
        p.start()
        self.addCleanup(p.stop)
        # Stub every GET route so no live file is read
        p = mock.patch.dict(cs.Handler._GET_ROUTES, {k: _stub for k in cs.Handler._GET_ROUTES})
        p.start()
        self.addCleanup(p.stop)

    def test_timer_gets_do_not_mark(self):
        for path in ("/api/session/work", "/api/ext/work", "/api/agents/timeline", "/api/git/diff",
                     "/api/arch", "/api/state", "/api/agent/work"):
            get(path)
            self.assertEqual(st._struct_act[0], 0.0, path)

    def test_page_load_marks(self):
        get("/")
        self.assertEqual(st._struct_act[0], 5000.0)

    def test_post_act_marks(self):
        code, out, _h = post("/api/act", {}, origin=OWN)
        self.assertEqual((code, out), (200, {"ok": True}))
        self.assertEqual(st._struct_act[0], 5000.0)

    def test_post_act_needs_viewer_origin(self):
        for origin in (None, EVIL):
            code, _out, _h = post("/api/act", {}, origin=origin)
            self.assertEqual(code, 403)
        self.assertEqual(st._struct_act[0], 0.0)

    def test_other_posts_do_not_mark(self):
        post("/api/nope", {}, origin=OWN)
        self.assertEqual(st._struct_act[0], 0.0)

    def test_page_pings_act(self):
        with open(os.path.join(ROOT, "web", "js", "08-ui-kit.js"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("postJSON('/api/act')", src)
        self.assertIn("'pointerdown', 'keydown', 'wheel'", src)


if __name__ == "__main__":
    unittest.main()
