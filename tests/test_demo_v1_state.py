"""Demo GET /api/v1/* refuses plainly instead of a 200 stub that does not match the v1 schema."""
import unittest

from tests._load import sidereus


class _U:
    def __init__(self, q=""):
        self.query = q


class DemoV1State(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo = sidereus("demo")
        a = 1_790_000_000
        cls.w = cls.demo.World(anchor=a, page_build="abc123def456", now=a)

    def test_v1_state_is_refused(self):
        code, body = self.demo.respond(self.w, "/api/v1/state", _U())
        self.assertEqual(code, 404)
        self.assertEqual(body, {"error": "not available in demo mode"})

    def test_other_unknown_paths_keep_the_stub(self):
        self.assertEqual(self.demo.respond(self.w, "/api/unknown-x", _U()), (200, {"ok": True}))


if __name__ == "__main__":
    unittest.main()
