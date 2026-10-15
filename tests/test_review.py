"""«리뷰» queue (sidereus/review.py): signatures reopen items, marks persist, request validation, prune, row filter.
No live data: git (`review._git_run`), edit ownership (`file_owner.index`), visible rows (`work._allowed_cwds`,
`review.sessions_snapshot`) and the store path (`review.RV_FILE`) are all faked; the repo is a temp dir."""
import http.client
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tests._load import load, sidereus

cs = load()
rv = sidereus("review")
fo = sidereus("file_owner")
wk = sidereus("work")
stm = sidereus("state")
SID = "0123abcd-0000-4000-8000-00000000beef"
NOW = 1_800_000_000.0


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-rv-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.root, ".git"))
        for f in ("a.py", "b.py"):
            with open(os.path.join(self.root, f), "w") as fh:
                fh.write("x\n")
        self.diff = {"a.py": ("M", 3, 1), "b.py": ("A", 10, 0)}
        self.head = "c0ffee"
        self.calls = []
        self.row = {"sid": SID, "cwd": self.root, "state": "wait", "branch": "main", "ageSec": 300,
                    "sub": [], "bgs": [], "wf": [], "repos": [self.root], "plat": "cc"}
        self.patch(rv, "RV_FILE", os.path.join(self.tmp, "review-state.json"))
        self.patch(rv, "_git_run", self._git)
        self.patch(rv, "sessions_snapshot", lambda n=60: None)
        self.patch(fo, "index", lambda now=None: {
            os.path.join(self.root, f): {(SID, "main"): {"ts": NOW - 60, "n": 1, "agent": "", "desc": "",
                                                         "cwd": self.root}} for f in ("a.py", "b.py")})
        self.patch(wk, "_allowed_cwds", lambda ttl=5: {self.root: self.row})
        rv._RV_CACHE.clear()
        rv._RV_MEM.update(key=None, items={})

    def patch(self, obj, name, val):
        p = mock.patch.object(obj, name, val)
        p.start()
        self.addCleanup(p.stop)

    def _git(self, cwd, args, timeout, wait=None):
        self.calls.append(args[0])
        if args[0] == "rev-parse":
            return subprocess.CompletedProcess(args, 0, self.head + "\n", "")
        want = [a[len(":(literal)"):] for a in args if a.startswith(":(literal)")]
        raw = "".join(":100644 100644 0 0 %s\0%s\0" % (self.diff[p][0], p) for p in want if p in self.diff)
        num = "".join("%d\t%d\t%s\0" % (self.diff[p][1], self.diff[p][2], p) for p in want if p in self.diff)
        return subprocess.CompletedProcess(args, 0, raw + num, "")

    def fresh(self):
        """Drop the git cache and the parsed store so the next call recomputes / rereads from disk."""
        rv._RV_CACHE.clear()
        rv._RV_MEM.update(key=None, items={})

    def rows(self, now=NOW):
        return rv.review([self.row], now)


class Queue(_Base):
    def test_lists_finished_session_files(self):
        out = self.rows()
        self.assertEqual(out["n"], 1)
        r = out["rows"][0]
        self.assertEqual({k: r[k] for k in ("sid", "root", "nf", "add", "del", "done", "since")},
                         {"sid": SID, "root": self.root, "nf": 2, "add": 13, "del": 1, "done": False,
                          "since": int(NOW - 300)})
        code, f = rv.review_files(self.root, SID, NOW)
        self.assertEqual(code, 200)
        self.assertEqual([(x["path"], x["st"], x["add"], x["del"], x["rv"]) for x in f["files"]],
                         [("a.py", "M", 3, 1, False), ("b.py", "A", 10, 0, False)])

    def test_committed_file_leaves_the_list(self):
        del self.diff["a.py"]
        self.assertEqual(self.rows()["rows"][0]["nf"], 1)

    def test_running_asking_blocked_excluded(self):
        for extra in ({"state": "think"}, {"state": "tool"}, {"state": "ask"}, {"state": "abort"},
                      {"blocked": "권한 대기"}, {"sub": [{"aid": "x"}]}, {"bgs": [{"id": 1}]},
                      {"wf": [{"run": True}]}):
            self.row = dict(self.row, **extra)
            self.assertEqual(self.rows(), {"n": 0, "rows": []}, extra)
            self.row.update(state="wait", blocked="", sub=[], bgs=[], wf=[])
        self.row["state"] = "done"
        self.assertEqual(self.rows()["n"], 1)

    def test_no_slot_reuses_last_value(self):
        self.rows()
        def busy(*a, **k):
            raise subprocess.TimeoutExpired("git (slot wait)", 0)
        self.patch(rv, "_git_run", busy)
        self.assertEqual(self.rows(NOW + 60)["rows"][0]["nf"], 2)


class Marks(_Base):
    def mark(self, **kw):
        req = dict({"cwd": self.root, "sid": SID, "on": True}, **kw)
        return rv.review_mark(req, NOW)

    def test_session_mark_persists_and_sig_change_reopens(self):
        self.assertEqual(self.mark(all=True), (200, {"ok": True, "done": True, "n": 2}))
        self.fresh()
        out = self.rows()
        self.assertEqual((out["n"], out["rows"][0]["done"]), (0, True))
        self.diff["a.py"] = ("M", 4, 1)          # the session (or anyone) edited it again
        self.fresh()
        out = self.rows()
        self.assertEqual((out["n"], out["rows"][0]["done"]), (1, False))
        f = rv.review_files(self.root, SID, NOW)[1]
        self.assertEqual([x["rv"] for x in f["files"]], [False, True])

    def test_head_change_reopens(self):
        self.mark(all=True)
        self.head = "beef01"
        self.fresh()
        self.assertEqual(self.rows()["n"], 1)

    def test_file_marks_persist_and_complete(self):
        self.assertEqual(self.mark(path="a.py")[1]["done"], False)
        self.fresh()
        f = rv.review_files(self.root, SID, NOW)[1]
        self.assertEqual(([x["rv"] for x in f["files"]], f["done"]), ([True, False], False))
        self.assertEqual(self.mark(path="b.py")[1], {"ok": True, "done": True, "n": 2})
        self.fresh()
        self.assertEqual(self.rows()["n"], 0)
        self.assertEqual(self.mark(path="a.py", on=False)[1]["done"], False)
        self.fresh()
        self.assertEqual(self.rows()["n"], 1)
        with open(rv.RV_FILE, encoding="utf-8") as fh:
            d = json.load(fh)
        self.assertEqual(d["v"], 1)
        self.assertEqual(list(d["items"][self.root + "\t" + SID]["files"]), ["b.py"])

    def test_client_sig_ignored(self):
        self.mark(all=True, sig="deadbeef")
        with open(rv.RV_FILE, encoding="utf-8") as fh:
            it = json.load(fh)["items"][self.root + "\t" + SID]
        self.assertEqual(it["sig"], rv.review_files(self.root, SID, NOW)[1]["sig"])
        self.assertNotEqual(it["sig"], "deadbeef")

    def test_bad_input_400(self):
        bad = [{"sid": "../etc"}, {"sid": "ffffffff-dead-4000-8000-000000000000"}, {"cwd": "/etc"},
               {"cwd": 5}, {"path": "c.py"}, {"path": "../x"}, {"on": "yes"}, {"path": 3}, {"all": True, "path": "a.py"}]
        for kw in bad:
            req = dict({"cwd": self.root, "sid": SID, "on": True, "path": "a.py"}, **kw)
            self.assertEqual(rv.review_mark(req, NOW)[0], 400, kw)
        self.assertEqual(rv.review_mark([1], NOW)[0], 400)
        self.assertEqual(rv.review_files("/etc", SID, NOW)[0], 400)
        self.assertEqual(rv.review_files(self.root, "zz", NOW)[0], 400)
        self.assertFalse(os.path.exists(rv.RV_FILE))

    def test_prune_7_days_and_cap(self):
        items = {"r\t%d" % i: {"at": NOW - i, "sig": "", "files": {}} for i in range(400)}
        items["old\tx"] = {"at": NOW - 8 * 86400, "sig": "", "files": {}}
        kept = rv._save(items, NOW)
        self.assertEqual(len(kept), rv.RV_MAX_ITEMS)
        self.assertNotIn("old\tx", kept)
        self.assertIn("r\t0", kept)
        self.assertNotIn("r\t399", kept)


def _post(path, body):
    hdr = "Host: 127.0.0.1:%d\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n" % (cs.PORT, len(body))
    h = cs.Handler.__new__(cs.Handler)
    h.headers = http.client.parse_headers(io.BytesIO(hdr.encode("latin-1")))
    h.rfile, h.wfile = io.BytesIO(body), io.BytesIO()
    h.path, h.command, h.request_version = path, "POST", "HTTP/1.1"
    h.requestline = "POST %s HTTP/1.1" % path
    h.close_connection, h.client_address = False, ("127.0.0.1", 0)
    h.do_POST()
    return int(h.wfile.getvalue().split(b"\r\n", 1)[0].split()[1])


class Route(_Base):
    def test_oversize_and_garbage_400(self):
        big = json.dumps({"cwd": self.root, "sid": SID, "on": True, "path": "a.py", "pad": "x" * 5000}).encode()
        self.assertEqual(_post("/api/review/mark", big), 400)
        self.assertEqual(_post("/api/review/mark", b"{nope"), 400)
        self.assertFalse(os.path.exists(rv.RV_FILE))

    def test_ok(self):
        body = json.dumps({"cwd": self.root, "sid": SID, "all": True, "on": True}).encode()
        self.assertEqual(_post("/api/review/mark", body), 200)
        self.assertTrue(os.path.exists(rv.RV_FILE))


class StatePiece(unittest.TestCase):
    def test_review_exception_is_none(self):
        from tests.test_state_guard import _READERS
        saved = {k: getattr(stm, k) for k in list(_READERS) + ["warn_once", "review"]}
        self.addCleanup(lambda: [setattr(stm, k, v) for k, v in saved.items()])
        for k, v in _READERS.items():
            setattr(stm, k, v)
        stm.warn_once = lambda *a, **k: None

        def boom(*a, **k):
            raise ValueError("boom")
        stm.review = boom
        self.assertIsNone(stm.state()["review"])
        stm.review = lambda rows: {"n": 0, "rows": []}
        self.assertEqual(stm.state()["review"], {"n": 0, "rows": []})


if __name__ == "__main__":
    unittest.main()
