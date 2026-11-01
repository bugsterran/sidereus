"""«To-do» (sidereus/todo.py + GET /api/todo, POST /api/todo/add · /set, /api/state `todo`).
⚠Tmp repos only: `_allowed_cwds`, `_now`, `TRASH_DIR`, `LEDGER_DIR` are patched on the todo module."""
import glob
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import load, sidereus
from tests.test_prefs import get
from tests.test_routes_post import post, EVIL
from tests.test_prefs import ORIGIN
from tests.test_state_guard import _READERS

cs = load()
TD = sidereus("todo")
F = sidereus("features")
ST = sidereus("state")


class Todo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-todo-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.repo, ".git"))
        os.makedirs(os.path.join(self.repo, ".claude"))
        self.cwd = os.path.join(self.repo, "sub")
        os.makedirs(self.cwd)
        self.t = 1767225600.0   # 2026-01-01T00:00:00Z
        self.trash = os.path.join(self.tmp, "trash")
        for k, v in (("_allowed_cwds", lambda: {self.cwd: {"cwd": self.cwd}}), ("_now", lambda: self.t),
                     ("TRASH_DIR", self.trash), ("LEDGER_DIR", os.path.join(self.tmp, "ledger")), ("_MEMO", {})):
            p = mock.patch.object(TD, k, v)
            p.start()
            self.addCleanup(p.stop)
        self.p = os.path.join(self.repo, ".claude", "todo.md")

    def w(self, raw):
        with open(self.p, "wb") as f:
            f.write(raw)
        os.utime(self.p, (self.t, self.t))   # ledger times come from the file mtime

    def r(self):
        with open(self.p, "rb") as f:
            return f.read()

    def test_parse_three_states(self):
        it = TD.parse(b"# notes\n- [ ] a\n  - [~] b\r\n- [x] c\n- [X] d\n- [?] e\n-[ ] f\n")
        self.assertEqual([(x["i"], x["s"], x["t"]) for x in it], [(1, " ", "a"), (2, "~", "b"), (3, "x", "c"), (4, "x", "d")])
        self.assertEqual(TD._counts(it), {"o": 1, "w": 1, "d": 2})

    def test_r5_missing_big_symlink_no_data(self):
        self.assertEqual(TD._read(self.repo), (None, None))   # missing
        self.w(b"- [ ] a\n" * (TD.TODO_MAX // 8 + 1))
        self.assertEqual(TD._read(self.repo), (None, None))   # over 64 KB
        os.remove(self.p)
        real = os.path.join(self.tmp, "real.md")
        with open(real, "wb") as f:
            f.write(b"- [ ] a\n")
        os.symlink(real, self.p)
        self.assertEqual(TD._read(self.repo), (None, None))   # symlinked file
        self.assertEqual(TD.state_counts([{"cwd": self.cwd}]), {})

    def test_r5_symlinked_parent_no_data_and_refused(self):
        os.rmdir(os.path.join(self.repo, ".claude"))
        other = os.path.join(self.tmp, "other")
        os.makedirs(other)
        with open(os.path.join(other, "todo.md"), "wb") as f:
            f.write(b"- [ ] a\n")
        os.symlink(other, os.path.join(self.repo, ".claude"))
        self.assertEqual(TD._read(self.repo), (None, None))
        code, _ = TD.add({"cwd": self.cwd, "text": "x"})
        self.assertEqual(code, 400)
        with open(os.path.join(other, "todo.md"), "rb") as f:
            self.assertEqual(f.read(), b"- [ ] a\n")

    def test_r3_add_keeps_crlf_and_other_lines(self):
        old = b"# head \r\n- [x] done\r\nfree text"
        self.w(old)
        code, out = TD.add({"cwd": self.cwd, "text": "  new item "})
        self.assertEqual(code, 200)
        self.assertEqual(self.r(), old + b"\r\n- [ ] new item\r\n")
        self.assertEqual(out["items"][-1]["t"], "new item")

    def test_r3_add_rejects_bad_text(self):
        for t in ("", "a\nb", "x" * 201, "tab\there", 5, None):
            self.assertEqual(TD.add({"cwd": self.cwd, "text": t})[0], 400, repr(t))

    def test_r3_add_creates_file(self):
        shutil.rmtree(os.path.join(self.repo, ".claude"))
        self.assertEqual(TD.add({"cwd": self.cwd, "text": "first"})[0], 200)
        self.assertEqual(self.r(), b"- [ ] first\n")
        self.assertEqual(glob.glob(os.path.join(self.trash, "*")), [])   # nothing to back up

    def test_r3_set_changes_bracket_only_and_stale_409(self):
        old = b"intro\n- [ ] a\n- [~] b\n"
        self.w(old)
        it = TD.parse(old)
        code, _ = TD.set_state({"cwd": self.cwd, "i": 1, "h": it[0]["h"], "s": "x"})
        self.assertEqual(code, 200)
        self.assertEqual(self.r(), b"intro\n- [x] a\n- [~] b\n")
        code, _ = TD.set_state({"cwd": self.cwd, "i": 1, "h": it[0]["h"], "s": " "})   # h of the old line
        self.assertEqual(code, 409)
        self.assertEqual(TD.set_state({"cwd": self.cwd, "i": 0, "h": TD._h(b"intro"), "s": "x"})[0], 409)   # not an item
        self.assertEqual(TD.set_state({"cwd": self.cwd, "i": 2, "h": it[1]["h"], "s": "~"})[0], 400)

    def test_r3_backup_before_write(self):
        self.w(b"- [ ] a\n")
        self.assertEqual(TD.add({"cwd": self.cwd, "text": "b"})[0], 200)
        baks = glob.glob(os.path.join(self.trash, "*", "todo-*.md"))
        self.assertEqual(len(baks), 1)
        with open(baks[0], "rb") as f:
            self.assertEqual(f.read(), b"- [ ] a\n")

    def test_r3_unknown_cwd_refused(self):
        self.w(b"- [ ] a\n")
        for cwd in (self.tmp, "/etc", None, "rel"):
            self.assertEqual(TD.add({"cwd": cwd, "text": "x"})[0], 403)
            self.assertEqual(TD.todo_get(cwd)[0], 403)
        self.assertEqual(self.r(), b"- [ ] a\n")

    def test_r3_origin_required(self):
        self.w(b"- [ ] a\n")
        for origin in (None, EVIL):
            code, _out, _ = post("/api/todo/add", {"cwd": self.cwd, "text": "x"}, origin=origin)
            self.assertEqual(code, 403)
        self.assertEqual(self.r(), b"- [ ] a\n")
        code, out, _ = post("/api/todo/add", {"cwd": self.cwd, "text": "x"}, origin=ORIGIN)
        self.assertEqual((code, out["ok"]), (200, True))
        code, out = get("/api/todo?cwd=" + self.cwd)
        self.assertEqual([x["t"] for x in out["items"]], ["a", "x"])

    def test_r4_ledger_add_start_done_incl_direct_edits(self):
        self.w(b"- [ ] a\n")
        TD.state_counts([{"cwd": self.cwd}])
        self.t += 3600
        self.w(b"- [~] a\n- [ ] bb\n")    # a session edits the file directly
        TD.state_counts([{"cwd": self.cwd}])
        self.t += 86400
        self.w(b"- [x] a\n- [ ] bb\n")
        self.assertEqual(TD.state_counts([{"cwd": self.cwd}]), {self.cwd: {"o": 1, "w": 0, "d": 1}})
        led = TD._ledger_load(self.repo)
        t0 = 1767225600.0
        self.assertEqual(led["a#0"], {"t": "a", "add": t0, "start": t0 + 3600, "done": t0 + 3600 + 86400})
        self.assertEqual(led["bb#0"], {"t": "bb", "add": t0 + 3600})

    def test_r4_repeated_text_keeps_separate_entries(self):
        t0 = self.t
        self.w(b"- [x] X\n")
        TD.todo_get(self.cwd)
        self.t += 86400
        self.w(b"- [ ] X\n- [x] X\n")   # done-first: the earlier Done stays on its day
        for _ in range(3):
            TD.todo_get(self.cwd)
            self.t += 60
        led = TD._ledger_load(self.repo)
        self.assertEqual(led["x#0"], {"t": "X", "add": t0})   # first line reopened: its done dropped
        self.assertEqual(led["x#1"], {"t": "X", "add": t0 + 86400, "done": t0 + 86400})
        self.w(b"- [x] X\n- [x] X\n")
        TD.todo_get(self.cwd)
        led = TD._ledger_load(self.repo)
        self.assertEqual(led["x#1"]["done"], t0 + 86400)   # never re-stamped

    def test_r4_unpolled_edits_use_file_mtime(self):
        t0 = self.t
        self.w(b"- [~] a\n- [x] b\n")   # written while no viewer polled
        self.t = t0 + 5 * 86400         # first poll days later
        TD.state_counts([{"cwd": self.cwd}])
        led = TD._ledger_load(self.repo)
        self.assertEqual(led["a#0"], {"t": "a", "add": t0, "start": t0})
        self.assertEqual(led["b#0"], {"t": "b", "add": t0, "done": t0})   # never seen [~]: no start

    def test_r4_days_newest_first(self):
        self.w(b"- [ ] a\n")
        TD.todo_get(self.cwd)
        self.t += 2 * 86400
        self.w(b"- [x] a\n")
        code, out = TD.todo_get(self.cwd)
        self.assertEqual(code, 200)
        days = out["days"]
        self.assertEqual([d["day"] for d in days], sorted([d["day"] for d in days], reverse=True))
        self.assertEqual(days[0]["done"], ["a"])
        self.assertEqual(days[-1]["added"], ["a"])

    def test_r1_state_key_omitted_when_feature_off(self):
        saved = {k: getattr(ST, k) for k in _READERS}
        self.addCleanup(lambda: [setattr(ST, k, v) for k, v in saved.items()])
        for k, v in _READERS.items():
            setattr(ST, k, v)
        real = F._load(F.FEATURES_DIR)
        with mock.patch.object(F, "_MANIFESTS", {"todo": real["todo"]}):
            with mock.patch.object(F, "_TOGGLES", {}):
                self.assertIn("todo", ST.state())
            with mock.patch.object(F, "_TOGGLES", {"todo": False}):
                self.assertNotIn("todo", ST.state())
                self.assertEqual(F.route_feature("/api/todo/add"), "todo")


if __name__ == "__main__":
    unittest.main()
