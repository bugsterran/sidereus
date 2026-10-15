"""Guard refusals (bad Host, cross-origin POST) must finish promptly on keep-alive connections.

⚠Before 2026-09-25 they sent no Content-Length and left the body unread, so an HTTP/1.1 client
waited for more bytes until it gave up (curl >120s).
"""
import socket
import threading
import time
import unittest
from http.server import ThreadingHTTPServer

from tests._load import load

cs = load()
PORT = cs.PORT


def _exchange(port, raw, timeout=3.0):
    """Send raw bytes, read until the server closes; return (response bytes, seconds)."""
    s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    t0 = time.time()
    s.sendall(raw)
    buf = b""
    try:
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    except socket.timeout:
        pass
    finally:
        s.close()
    return buf, time.time() - t0


class GuardCloseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), cs.Handler)
        cls.port = cls.srv.server_address[1]
        # ⚠poll_interval: shutdown() waits up to one poll (default 0.5s) in tearDownClass.
        cls.th = threading.Thread(target=cls.srv.serve_forever, kwargs={"poll_interval": 0.05},
                                  daemon=True)
        cls.th.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def _check(self, raw, status, text):
        buf, dt = _exchange(self.port, raw)
        self.assertLess(dt, 1.0, "connection hung")
        head, _, body = buf.partition(b"\r\n\r\n")
        self.assertTrue(head.startswith(b"HTTP/1.1 " + status), head[:40])
        self.assertIn(b"Content-Length: %d" % len(text), head)
        self.assertEqual(body, text)

    def test_cross_origin_post(self):
        raw = (b"POST /api/dm HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nOrigin: http://evil.example\r\n"
               b"Content-Type: application/json\r\nContent-Length: 2\r\n\r\n{}" % PORT)
        self._check(raw, b"403", b"cross-origin POST refused\n")

    def test_bad_host_get(self):
        raw = b"GET /api/state HTTP/1.1\r\nHost: evil.example\r\n\r\n"
        self._check(raw, b"403", b"host refused\n")

    def test_bad_host_post(self):
        raw = (b"POST /api/dm HTTP/1.1\r\nHost: evil.example\r\n"
               b"Content-Length: 2\r\n\r\n{}")
        self._check(raw, b"403", b"host refused\n")

    def test_unknown_post_path(self):
        raw = (b"POST /api/no-such-route HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n"
               b"Content-Length: 2\r\n\r\n{}" % PORT)
        self._check(raw, b"404", b'{"error": "not found"}')


if __name__ == "__main__":
    unittest.main()
