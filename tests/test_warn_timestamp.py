"""viewer.err lines carry a local-time prefix: warn_once lines and the request-error traceback header."""
import contextlib
import io
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from _load import load, sidereus  # noqa: E402

FROZEN = 1790000000.0          # fixed epoch; expected text is derived with the same local-time rules
STAMP = time.strftime("%Y-%m-%d %H:%M:%S ", time.localtime(FROZEN))


class WarnTimestamp(unittest.TestCase):
    def setUp(self):
        self.W = sidereus("warn")
        W = self.W
        self.saved = (list(W._WARN_LOG), set(W._warned), dict(W._SOFT), dict(W._wmute), W._clock)
        W._WARN_LOG[:] = []
        W._warned.clear()
        W._SOFT.clear()
        W._wmute.clear()
        W._clock = lambda: FROZEN

    def tearDown(self):
        W, s = self.W, self.saved
        W._WARN_LOG[:] = s[0]
        W._warned.clear(); W._warned.update(s[1])
        W._SOFT.clear(); W._SOFT.update(s[2])
        W._wmute.clear(); W._wmute.update(s[3])
        W._clock = s[4]

    def test_log_ts_format(self):
        self.assertEqual(self.W.log_ts(), STAMP)
        self.assertRegex(STAMP, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} $")

    def test_warn_lines_prefixed(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.W.warn_once("ts-en", "한국어", en="English")
            self.W.warn_once("ts-ko", "한국어만")
            self.W.warn_once("ts-soft", "느림", soft=True, en="slow")
        self.assertEqual(err.getvalue().splitlines(),
                         [STAMP + "⚠ English", STAMP + "⚠ 한국어만", STAMP + "⚠ slow"])

    def test_request_traceback_header_prefixed(self):
        cs = load()

        class H(cs.Handler):
            def __init__(self):
                self.client_address = ("127.0.0.1", 1)
                self.close_connection = False

        def boom(self):
            raise ValueError("probe")
        err = io.StringIO()
        orig = cs.BaseHTTPRequestHandler.handle_one_request
        cs.BaseHTTPRequestHandler.handle_one_request = boom
        try:
            with contextlib.redirect_stderr(err):
                h = H()
                h.handle_one_request()
        finally:
            cs.BaseHTTPRequestHandler.handle_one_request = orig
        lines = err.getvalue().splitlines()
        self.assertEqual(lines[0], STAMP + "Exception occurred during processing of request from ('127.0.0.1', 1)")
        self.assertEqual(lines[1], "Traceback (most recent call last):")
        self.assertEqual(lines[-1], "ValueError: probe")
        self.assertTrue(h.close_connection)


if __name__ == "__main__":
    unittest.main()
