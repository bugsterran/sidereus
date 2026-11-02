"""Demo «To-do» (state `todo` + GET /api/todo) and quota fields keep the live shapes (todo.py · usage.quota_who · burn)."""
import unittest
from urllib.parse import urlparse

from tests._load import sidereus

demo = sidereus("demo")
todo = sidereus("todo")

A = 1_790_000_000


def _get(w, path, q=""):
    return demo.respond(w, path, urlparse(path + ("?" + q if q else "")))


class DemoTodo(unittest.TestCase):
    def setUp(self):
        self.w = demo.World(anchor=A, page_build="b", now=A)

    def test_state_has_todo_counts(self):
        t = self.w.state(0, 50)["todo"]
        self.assertTrue(t)
        for cwd, c in t.items():
            self.assertEqual(set(c), {"o", "w", "d"})
            self.assertTrue(any(s["cwd"] == cwd for s in self.w.sess))
        web = self.w.by["web"]["cwd"]
        self.assertEqual(t[web], {"o": 1, "w": 1, "d": 1})
        self.assertNotIn(self.w.by["docs"]["cwd"], t)   # repo without items: no chip

    def test_get_shape_matches_live(self):
        cwd = self.w.by["bill"]["cwd"]
        code, out = _get(self.w, "/api/todo", "cwd=" + cwd)
        self.assertEqual(code, 200)
        self.assertEqual(set(out), {"ok", "repo", "items", "days", "max"})
        self.assertEqual(out["max"], todo.TEXT_MAX)
        for it in out["items"]:
            self.assertEqual(set(it), {"i", "s", "t", "h", "sid"})
            self.assertIn(it["s"], (" ", "~", "x"))
            self.assertLessEqual(len(it["t"]), todo.TEXT_MAX)
        owners = [it["sid"] for it in out["items"] if it["s"] == "~"]
        self.assertEqual(owners, [self.w.by["bill"]["sid"]])
        for d in out["days"]:
            self.assertEqual(set(d), {"day", "added", "started", "done"})

    def test_get_off_screen_and_empty(self):
        self.assertEqual(_get(self.w, "/api/todo", "cwd=/elsewhere")[0], 403)
        code, out = _get(self.w, "/api/todo", "cwd=" + self.w.by["docs"]["cwd"])
        self.assertEqual((code, out["items"], out["days"]), (200, [], []))


class DemoQuota(unittest.TestCase):
    def setUp(self):
        self.w = demo.World(anchor=A, page_build="b", now=A)

    def test_quota_who_fields(self):
        live = {"start", "exact", "acct", "total", "rows", "others", "othersTok", "partial", "since"}
        ex = self.w.state(0, 50)["quotaWho"]
        self.assertEqual(set(ex), live)
        self.assertTrue(ex["exact"])
        est = self.w.quota_who(est=True)
        self.assertEqual(set(est), live)
        self.assertFalse(est["exact"])
        self.assertEqual(est["start"], A - 5 * 3600)

    def test_burn_used_fields(self):
        b = _get(self.w, "/api/quota/burn")[1]
        self.assertGreater(b["cur"]["used_acct"], 0)
        self.assertGreater(b["wk"]["used_acct"], 0)
        self.assertGreater(b["wk"]["used_local"], 0)


if __name__ == "__main__":
    unittest.main()
