"""X-Build-Time: every Handler._send response carries the page assembly time + PAGE_BUILD."""
import io
import re
import unittest
from tests._load import load, sidereus

cs = load()
pg = sidereus("page")


class BuildTimeHeader(unittest.TestCase):
    def test_value_format(self):
        self.assertTrue(pg.BUILD_TIME.endswith(" " + pg.PAGE_BUILD))
        self.assertRegex(pg.BUILD_TIME, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ [0-9a-f]{12}$")
        self.assertEqual(cs.BUILD_TIME, pg.BUILD_TIME)

    def test_header_sent(self):
        h = cs.Handler.__new__(cs.Handler)
        sent = []
        h.headers = {}
        h.wfile = io.BytesIO()
        h.send_response = lambda code: sent.append(("code", code))
        h.send_header = lambda k, v: sent.append((k, v))
        h.end_headers = lambda: None
        h._send(200, "{}", "application/json")
        self.assertIn(("X-Build-Time", pg.BUILD_TIME), sent)
        self.assertTrue(re.match(r"\d{4}-", dict(sent)["X-Build-Time"]))


if __name__ == "__main__":
    unittest.main()
