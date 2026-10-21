"""Demo /api/pipelines serves a second, empty project (the billing session cwd) so the empty-project start row is reachable."""
import unittest

from tests._load import sidereus


class _U:
    def __init__(self, q=""):
        self.query = q


class DemoPipelinesEmpty(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo = sidereus("demo")
        a = 1_790_000_000
        cls.w = cls.demo.World(anchor=a, page_build="abc123def456", now=a)
        cls.web = cls.w.by["web"]["cwd"]
        cls.bill = cls.w.by["bill"]["cwd"]

    def get(self, q):
        return self.demo.respond(self.w, "/api/pipelines", _U(q))

    def test_projects_list(self):
        code, b = self.get("")
        self.assertEqual(code, 200)
        self.assertEqual(b["projects"], [{"path": self.web, "n": 1}, {"path": self.bill, "n": 0}])

    def test_empty_project(self):
        code, b = self.get("proj=" + self.bill)
        self.assertEqual(code, 200)
        self.assertEqual((b["pipelines"], b["std"], b["suggest"]), ([], [], []))
        self.assertEqual(b["proj"], self.bill)
        self.assertIn("apply", b)

    def test_main_project_unchanged(self):
        code, b = self.get("proj=" + self.web)
        self.assertEqual(code, 200)
        self.assertEqual(len(b["pipelines"]), 1)

    def test_unknown_still_400(self):
        for p in ("/tmp/x", self.bill + "/sub", self.w.by["inv"]["cwd"]):
            self.assertEqual(self.get("proj=" + p)[0], 400, p)

    def test_eval_unknown_for_empty(self):
        self.assertEqual(self.demo.respond(self.w, "/api/pipelines/eval", _U("proj=" + self.bill))[0], 400)


if __name__ == "__main__":
    unittest.main()
