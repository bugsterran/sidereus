"""Security review 2026-09-25: /api/say body length, /api/state query parsing, cross-site API GETs."""
import threading
import unittest
from http.server import ThreadingHTTPServer

from tests._fs import assert_mode
from tests._load import load, sidereus
from tests.test_guard_close import _exchange

cs = load()
PORT = cs.PORT
RG = sidereus("routes_get")


class RequestHardeningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._state_body = RG._state_body
        cls.calls = []

        def fake(since, nc):
            cls.calls.append((since, nc))
            return b"{}", None
        RG._state_body = fake     # ⚠no live state build in tests
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), cs.Handler)
        cls.port = cls.srv.server_address[1]
        # ⚠poll_interval: shutdown() waits up to one poll (default 0.5s) in tearDownClass.
        threading.Thread(target=cls.srv.serve_forever, kwargs={"poll_interval": 0.05},
                         daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        RG._state_body = cls._state_body

    def _status(self, raw):
        buf, dt = _exchange(self.port, raw)
        self.assertLess(dt, 1.0, "connection hung")
        return buf.split(b"\r\n", 1)[0]

    def _get(self, path, extra=b""):
        return self._status(b"GET %s HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nConnection: close\r\n%s\r\n"
                            % (path, PORT, extra))

    def _say(self, length):
        # No body bytes follow: a server that tries to read would hang until the timeout.
        return self._status(b"POST /api/say HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n"
                            b"Content-Type: application/json\r\nContent-Length: %s\r\n\r\n" % (PORT, length))

    def test_say_negative_length(self):
        self.assertIn(self._say(b"-1").split()[1], (b"400", b"413"))

    def test_say_huge_length(self):
        self.assertIn(self._say(b"999999999").split()[1], (b"400", b"413"))

    def test_say_garbage_length(self):
        self.assertEqual(self._say(b"abc").split()[1], b"400")

    def test_state_bad_since(self):
        self.calls.clear()
        self.assertEqual(self._get(b"/api/state?since=x&cards=y").split()[1], b"200")
        self.assertEqual(self.calls, [(0, 50)])

    def test_state_cross_site(self):
        self.assertEqual(self._get(b"/api/state", b"Sec-Fetch-Site: cross-site\r\n").split()[1], b"403")

    def test_state_same_origin(self):
        self.assertEqual(self._get(b"/api/state", b"Sec-Fetch-Site: same-origin\r\n").split()[1], b"200")

    def test_state_none(self):
        self.assertEqual(self._get(b"/api/state", b"Sec-Fetch-Site: none\r\n").split()[1], b"200")

    def test_same_site_refused(self):
        # Another 127.0.0.1 port is same-site: its page must not trigger side-effect GETs.
        for p in (b"/api/state", b"/api/wkuse?force=1"):
            self.assertEqual(self._get(p, b"Sec-Fetch-Site: same-site\r\n").split()[1], b"403")

    def test_handler_timeout(self):
        self.assertEqual(cs.Handler.timeout, 30)

    def test_atomic_write_private(self):
        import os
        import tempfile
        bus = sidereus("bus")
        d = tempfile.mkdtemp(prefix="sidereus-test-")
        for i, kw in enumerate(({}, {"tmp": os.path.join(d, "t.tmp")})):
            p = os.path.join(d, "f%d.json" % i)
            bus._atomic_write(p, b"{}", **kw)
            assert_mode(self, p, 0o600)
        p = os.path.join(d, "a.jsonl")
        with bus._open_append(p) as f:
            f.write("x\n")
        assert_mode(self, p, 0o600)

    def test_state_no_header(self):
        self.assertEqual(self._get(b"/api/state").split()[1], b"200")

    def test_page_cross_site(self):
        self.assertEqual(self._get(b"/", b"Sec-Fetch-Site: cross-site\r\n").split()[1], b"200")


if __name__ == "__main__":
    unittest.main()
