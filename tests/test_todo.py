"""«To-do» (sidereus/todo.py + GET /api/todo, POST /api/todo/add · /set · /agent, /api/state `todo`).
⚠Tmp repos only: `_allowed_cwds`, `_now`, `LEDGER_DIR`, `_MEMO`, `_NOIMPORT` are patched on the todo module."""
import json
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
        self.cwd = os.path.join(self.repo, "sub")
        os.makedirs(self.cwd)
        self.t = 1767225600.0   # 2026-01-01T00:00:00Z
        self.led = os.path.join(self.tmp, "ledger")
        for k, v in (("_allowed_cwds", lambda: {self.cwd: {"cwd": self.cwd}}), ("_now", lambda: self.t),
                     ("LEDGER_DIR", self.led), ("_MEMO", {}), ("_NOIMPORT", set())):
            p = mock.patch.object(TD, k, v)
            p.start()
            self.addCleanup(p.stop)
        self.p = os.path.join(self.repo, ".claude", "todo.md")

    def w(self, raw):
        os.makedirs(os.path.dirname(self.p), exist_ok=True)
        with open(self.p, "wb") as f:
            f.write(raw)
        os.utime(self.p, (self.t, self.t))   # import falls back to the file mtime

    def r(self):
        with open(self.p, "rb") as f:
            return f.read()

    def store(self):
        with open(TD._ledger_path(self.repo), encoding="utf-8") as f:
            return json.load(f)

    def ag(self, **kw):
        kw.setdefault("cwd", self.cwd)
        kw.setdefault("sid", "s1")
        return TD.agent(kw)

    def test_parse_three_states(self):
        it = TD.parse(b"# notes\n- [ ] a\n  - [~] b\r\n- [x] c\n- [X] d\n- [?] e\n-[ ] f\n")
        self.assertEqual([(x["i"], x["s"], x["t"]) for x in it], [(1, " ", "a"), (2, "~", "b"), (3, "x", "c"), (4, "x", "d")])
        self.assertEqual(TD._counts(it), {"o": 1, "w": 1, "d": 2})

    def test_r1_r2_writes_never_create_repo_claude(self):
        self.assertEqual(TD.add({"cwd": self.cwd, "text": "person"})[0], 200)
        code, out = self.ag(action="add", text="agent item")
        self.assertEqual((code, [x["t"] for x in out["items"]]), (200, ["person", "agent item"]))
        it = TD.todo_get(self.cwd)[1]["items"]
        self.assertEqual(TD.set_state({"cwd": self.cwd, "i": it[0]["i"], "h": it[0]["h"], "s": "x"})[0], 200)
        self.assertFalse(os.path.lexists(os.path.join(self.repo, ".claude")))
        self.assertEqual(sorted(os.listdir(self.repo)), [".git", "sub"])
        st = self.store()
        self.assertEqual((st["v"], st["repo"], st["seq"]), (2, self.repo, 2))
        self.assertEqual([(x["s"], x["sid"]) for x in st["items"]], [("x", ""), (" ", "s1")])

    def test_r3_import_copies_items_and_v1_times(self):
        t0 = self.t
        old = b"# head\n- [ ] a\n- [~] b\n- [x] c\n"
        self.w(old)
        os.makedirs(self.led)
        with open(TD._ledger_path(self.repo), "w", encoding="utf-8") as f:
            json.dump({"v": 1, "items": {"a#0": {"t": "a", "add": t0 - 500}, "c#0": {"t": "c", "add": t0 - 900, "done": t0 - 100},
                                         "gone#0": {"t": "gone", "add": t0 - 999, "done": t0 - 50},
                                         "dropped#0": {"t": "dropped", "add": t0 - 999}}}, f)
        self.t += 3600
        code, out = TD.todo_get(self.cwd)
        self.assertEqual(code, 200)
        self.assertEqual([(x["s"], x["t"]) for x in out["items"]], [(" ", "a"), ("~", "b"), ("x", "c"), ("x", "gone")])
        st = self.store()
        self.assertEqual(st["imported"], t0 + 3600)
        by = {x["t"]: x for x in st["items"]}
        self.assertEqual(by["a"]["add"], t0 - 500)
        self.assertEqual((by["b"]["add"], by["b"]["start"]), (t0, t0))   # no v1 key: file mtime
        self.assertEqual(by["c"]["done"], t0 - 100)
        self.assertEqual(by["gone"]["done"], t0 - 50)                   # done-only v1 entry kept for «By day»
        self.assertEqual(self.r(), old)
        self.assertEqual(os.stat(self.p).st_mtime, t0)                  # todo.md read-only

    def test_r3_edit_after_import_changes_nothing(self):
        self.w(b"- [ ] a\n")
        self.assertEqual(TD.state_counts([{"cwd": self.cwd}]), {self.cwd: {"o": 1, "w": 0, "d": 0}})
        before = self.store()
        self.t += 60
        self.w(b"- [x] a\n- [ ] b\n- [ ] c\n")
        TD._MEMO.clear()
        self.assertEqual(TD.state_counts([{"cwd": self.cwd}]), {self.cwd: {"o": 1, "w": 0, "d": 0}})
        self.assertEqual([x["t"] for x in TD.todo_get(self.cwd)[1]["items"]], ["a"])
        self.assertEqual(self.store(), before)
        self.assertEqual(self.r(), b"- [x] a\n- [ ] b\n- [ ] c\n")

    def test_r3_nothing_to_import_writes_no_file(self):
        self.assertEqual(TD.state_counts([{"cwd": self.cwd}]), {})
        self.assertEqual(TD.todo_get(self.cwd)[1]["items"], [])
        self.assertFalse(os.path.exists(self.led))
        self.w(b"- [ ] late\n")   # in-process memo: not re-read
        self.assertEqual(TD.state_counts([{"cwd": self.cwd}]), {})

    def test_r3_symlinked_todo_not_imported(self):
        other = os.path.join(self.tmp, "other")
        os.makedirs(other)
        with open(os.path.join(other, "todo.md"), "wb") as f:
            f.write(b"- [ ] a\n")
        os.symlink(other, os.path.join(self.repo, ".claude"))
        self.assertEqual(TD.todo_get(self.cwd)[1]["items"], [])

    def test_symlinked_repo_root_no_count_and_404(self):
        self.w(b"- [ ] a\n")
        lnk = os.path.join(self.tmp, "lnk")
        os.symlink(self.repo, lnk)
        with mock.patch.object(TD, "_allowed_cwds", lambda: {lnk: {"cwd": lnk}}):
            self.assertEqual(TD.todo_get(lnk)[0], 404)
            self.assertEqual(TD.state_counts([{"cwd": lnk}]), {})   # same verdict as GET: no badge, no import
        self.assertFalse(os.path.exists(self.led))

    def test_get_items_carry_starting_sid(self):
        self.ag(action="add", text="a")
        self.ag(action="add", text="b")
        self.ag(action="start", id=2, sid="s9")
        self.assertEqual([x["sid"] for x in TD.todo_get(self.cwd)[1]["items"]], ["s1", "s9"])

    def test_r2_set_toggles_and_stale_409(self):
        self.ag(action="add", text="a")
        it = TD.todo_get(self.cwd)[1]["items"][0]
        code, out = TD.set_state({"cwd": self.cwd, "i": it["i"], "h": it["h"], "s": "x"})
        self.assertEqual((code, out["items"][0]["s"]), (200, "x"))
        self.assertEqual(TD.set_state({"cwd": self.cwd, "i": it["i"], "h": it["h"], "s": " "})[0], 409)   # h of the old state
        self.assertEqual(TD.set_state({"cwd": self.cwd, "i": 99, "h": it["h"], "s": " "})[0], 409)
        self.assertEqual(TD.set_state({"cwd": self.cwd, "i": it["i"], "h": it["h"], "s": "~"})[0], 400)
        self.assertEqual(self.store()["items"][0]["done"], self.t)

    def test_r2_add_rejects_bad_text(self):
        for t in ("", "a\nb", "x" * 201, "tab\there", 5, None):
            self.assertEqual(TD.add({"cwd": self.cwd, "text": t})[0], 400, repr(t))

    def test_r2_unknown_cwd_refused(self):
        for cwd in (self.tmp, "/etc", None, "rel"):
            self.assertEqual(TD.add({"cwd": cwd, "text": "x"})[0], 403)
            self.assertEqual(TD.todo_get(cwd)[0], 403)

    def test_r2_viewer_origin_required(self):
        for origin in (None, EVIL):
            code, _out, _ = post("/api/todo/add", {"cwd": self.cwd, "text": "x"}, origin=origin)
            self.assertEqual(code, 403)
        code, out, _ = post("/api/todo/add", {"cwd": self.cwd, "text": "x"}, origin=ORIGIN)
        self.assertEqual((code, out["ok"]), (200, True))
        code, out = get("/api/todo?cwd=" + self.cwd)
        self.assertEqual([x["t"] for x in out["items"]], ["x"])

    def test_r1_agent_route_any_origin_403(self):
        body = {"cwd": self.cwd, "sid": "s1", "action": "add", "text": "x"}
        for origin in (ORIGIN, EVIL):
            self.assertEqual(post("/api/todo/agent", body, origin=origin)[0], 403)
        self.assertFalse(os.path.exists(self.led))
        code, out, _ = post("/api/todo/agent", body)
        self.assertEqual((code, out["repo"], [x["t"] for x in out["items"]]), (200, self.repo, ["x"]))

    def test_r1_agent_any_git_root(self):
        other = os.path.join(self.tmp, "r2")
        os.makedirs(os.path.join(other, ".git"))
        self.assertEqual(TD.agent({"cwd": other, "sid": "s", "action": "add", "text": "x"})[0], 200)   # not on screen

    def test_r1_start_demotes_same_sid_only(self):
        for t in ("a", "b", "c"):
            self.ag(action="add", text=t)
        self.ag(action="start", id=1)
        self.ag(action="start", id=3, sid="s2")
        code, out = self.ag(action="start", text="b")
        self.assertEqual(code, 200)
        self.assertEqual([(x["t"], x["s"]) for x in out["items"]], [("a", " "), ("b", "~"), ("c", "~")])
        self.assertEqual(self.ag(action="done", text="b")[1]["items"][1]["s"], "x")
        self.assertEqual(self.ag(action="open", text="b")[1]["items"][1]["s"], " ")
        self.assertEqual(self.ag(action="done", id=42)[0], 404)
        for a in ("start", "done", "open"):
            self.assertEqual(self.ag(action=a)[0], 400, a)   # neither text nor id
        self.assertEqual(self.ag(action="done", text="nope")[0], 404)
        self.assertEqual(TD.state_counts([{"cwd": self.cwd}]), {self.cwd: {"o": 2, "w": 1, "d": 0}})

    def test_r1_open_by_text_reopens_started_or_done(self):
        self.ag(action="add", text="X")
        self.ag(action="start", text="X")
        code, out = self.ag(action="open", text="x")
        self.assertEqual((code, out["items"][0]["s"]), (200, " "))
        self.ag(action="done", text="X")
        code, out = self.ag(action="open", text="X")
        self.assertEqual((code, out["items"][0]["s"]), (200, " "))
        self.assertEqual(self.ag(action="open", text="X")[0], 404)   # already open

    def test_r1_agent_bad_input_400(self):
        for kw in ({"action": "add", "text": "x" * 201}, {"action": "add", "text": "a\x07b"}, {"action": "add", "text": "a\nb"},
                   {"action": "add"}, {"action": "zap"}, {"action": "list", "sid": "bad sid"}, {"action": "list", "sid": 5}):
            self.assertEqual(self.ag(**kw)[0], 400, repr(kw))
        self.assertEqual(self.ag(action="add", text="x" * 200)[0], 200)
        self.assertEqual(self.ag(action="list")[0], 200)

    def test_r1_agent_home_or_root_404(self):
        home = os.path.join(self.tmp, "home")
        os.makedirs(os.path.join(home, ".git"))
        with mock.patch.object(TD, "_real_home", lambda: home):
            self.assertEqual(TD.agent({"cwd": home, "sid": "s", "action": "add", "text": "x"})[0], 404)
        with mock.patch.object(TD, "_git_root", lambda d: "/"):
            self.assertEqual(TD.agent({"cwd": "/", "sid": "s", "action": "add", "text": "x"})[0], 404)
        for cwd in ("rel", None, self.tmp):
            self.assertEqual(TD.agent({"cwd": cwd, "sid": "s", "action": "list"})[0], 404)
        self.assertFalse(os.path.exists(self.led))

    def test_r2_days_and_prune(self):
        self.ag(action="add", text="a")
        self.t += 2 * 86400
        self.ag(action="done", text="a")
        days = TD.todo_get(self.cwd)[1]["days"]
        self.assertEqual([d["day"] for d in days], sorted([d["day"] for d in days], reverse=True))
        self.assertEqual((days[0]["done"], days[-1]["added"]), (["a"], ["a"]))
        self.t += TD.LEDGER_DONE_S + 1
        self.ag(action="add", text="b")
        self.assertEqual([x["t"] for x in self.store()["items"]], ["b"])

    def test_bad_store_value_skipped(self):
        os.makedirs(self.led)
        with open(TD._ledger_path(self.repo), "w", encoding="utf-8") as f:
            f.write('{"v": 2, "seq": 3, "items": [{"id": 1, "s": " ", "t": "a", "add": "x"}, {"id": 2, "s": "?", "t": "b"},'
                    ' {"id": true, "s": " ", "t": "c"}, {"id": 3, "s": "x", "t": "d", "done": "nope"}]}')
        self.assertEqual(TD.state_counts([{"cwd": self.cwd}]), {self.cwd: {"o": 1, "w": 0, "d": 1}})
        self.assertEqual(TD.todo_get(self.cwd)[1]["days"], [])
        self.assertEqual(self.ag(action="add", text="e")[1]["items"][-1]["id"], 4)

    def test_get_states_text_max(self):
        self.assertEqual(TD.todo_get(self.cwd)[1]["max"], TD.TEXT_MAX)

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
                self.assertEqual(F.route_feature("/api/todo/agent"), "todo")

    def test_off_feature_skips_piece_entirely(self):
        saved = {k: getattr(ST, k) for k in _READERS}
        self.addCleanup(lambda: [setattr(ST, k, v) for k, v in saved.items()])
        for k, v in _READERS.items():
            setattr(ST, k, v)
        calls = []
        real = F._load(F.FEATURES_DIR)
        with mock.patch.object(ST, "todo_counts", lambda rows: calls.append(1) or {}), \
                mock.patch.object(F, "_MANIFESTS", {"todo": real["todo"]}), mock.patch.object(F, "_TOGGLES", {"todo": False}):
            ST.state()
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
