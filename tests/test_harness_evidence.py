"""Harness «결과» evidence reader (sidereus/harness_evidence.py) and its attachment in harness_plat. EV_FILE points at a temp file."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import load, sidereus

load()
EV = sidereus("harness_evidence")
HP = sidereus("harness_plat")
H = sidereus("harness")


def _rec(repo, ts, **kw):
    d = {"v": 1, "kind": "check", "ts": ts, "mode": "fast", "repo": repo, "head": "abc1234", "dirty": False, "rc": 0,
         "steps": [{"name": "tests", "rc": 0, "n": 10, "failed": 0, "secs": 1.5}]}
    d.update(kw)
    return json.dumps(d)


class EvidenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-ev-"))
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        self.other = os.path.join(self.tmp, "other")
        self.f = os.path.join(self.tmp, "evidence.jsonl")
        self._old = (EV.EV_FILE, EV.EV_READ_MAX)
        EV.EV_FILE = self.f

    def tearDown(self):
        EV.EV_FILE, EV.EV_READ_MAX = self._old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, lines):
        with open(self.f, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def test_missing_file(self):
        self.assertEqual(EV.recent(self.repo), [])

    def test_repo_filter_newest_first_limit(self):
        self._write([_rec(self.repo, 1), _rec(self.other, 2), _rec(self.repo, 3), _rec(self.repo, 4)])
        rows = EV.recent(self.repo)
        self.assertEqual([r["ts"] for r in rows], [4, 3, 1])
        self.assertEqual(rows[0]["kind"], "check")
        self.assertEqual([r["ts"] for r in EV.recent(self.repo, limit=2)], [4, 3])
        self.assertEqual([r["ts"] for r in EV.recent(os.path.join(self.repo, "."))], [4, 3, 1])   # realpath

    def test_junk_and_whitelist(self):
        bad_steps = [{"name": "Tests!", "rc": 0}, {"name": "x" * 21}, "nope", {"name": "leak", "rc": "1", "n": True, "secret": "s"}]
        self._write(["{not json", "", "\xff", json.dumps([1]), _rec(self.repo, 1, v=2), _rec(self.repo, 2, kind="other"),
                     _rec(self.repo, 5, steps=bad_steps, body="SENTINEL", head="<b>", mode="x y",
                          screen=[{"w": 900, "lang": "ko", "ok": 1, "diff": 0.5, "path": "/x"}, "junk"])])
        rows = EV.recent(self.repo)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(set(r), {"kind", "ts", "mode", "head", "dirty", "rc", "steps", "screen"})
        self.assertEqual(r["steps"], [{"name": "leak", "rc": 0, "n": 0, "failed": 0, "secs": 0.0}])
        self.assertEqual((r["head"], r["mode"]), ("", ""))
        self.assertEqual(r["screen"], [{"w": 900, "lang": "ko", "ok": False, "diff": 0.5}])
        self.assertNotIn("SENTINEL", json.dumps(rows))

    def test_subdir_matches_git_root(self):
        os.makedirs(os.path.join(self.repo, ".git"))
        sub = os.path.join(self.repo, "web", "app")
        os.makedirs(sub)
        self._write([_rec(self.repo, 1, mode="hook-test"), _rec(sub, 2), _rec(self.other, 3), _rec(self.tmp, 4)])
        self.assertEqual([r["ts"] for r in EV.recent(sub)], [2, 1])
        self.assertEqual([r["ts"] for r in EV.recent(self.repo)], [1])

    def test_real_ts_round_trips(self):
        self._write([_rec(self.repo, 1791332536), _rec(self.repo, 1791332537.25), _rec(self.repo, 5e9), _rec(self.repo, -3)])
        self.assertEqual([r["ts"] for r in EV.recent(self.repo)], [0.0, 0.0, 1791332537.25, 1791332536])

    def test_tail_only(self):
        EV.EV_READ_MAX = 4096
        self._write([_rec(self.repo, i, mode="x" * 20) for i in range(200)])
        self.assertGreater(os.path.getsize(self.f), 4096 * 4)
        rows = EV.recent(self.repo, limit=200)
        self.assertTrue(0 < len(rows) < 40)
        self.assertEqual(rows[0]["ts"], 199)
        self.assertGreater(rows[-1]["ts"], 150)

    def test_scan_all_rows_and_floor(self):
        self._write([_rec(self.repo, 1000 + i) for i in range(300)] + [_rec(self.other, 2000)])
        rows, floor = EV.scan(self.repo)
        self.assertEqual((len(rows), rows[0]["ts"], rows[-1]["ts"], floor), (300, 1299, 1000, 0.0))   # past 120, whole file read
        self.assertEqual([r["ts"] for r in EV.recent(self.repo, 5)], [1299, 1298, 1297, 1296, 1295])
        self.assertEqual(EV.scan(""), ([], 0.0))
        EV.EV_READ_MAX = 4096
        self._write(["{junk"] + [_rec(self.other if i % 2 else self.repo, 1000 + i) for i in range(300)])
        rows, floor = EV.scan(self.repo)
        self.assertGreater(floor, 1000)   # oldest line in the read, any repo
        self.assertLessEqual(floor, rows[-1]["ts"])
        self.assertEqual(rows[0]["ts"], 1298)

    def test_scan_cap(self):
        old = EV.EV_SCAN_MAX
        EV.EV_SCAN_MAX = 10
        try:
            self._write([_rec(self.repo, 1000 + i) for i in range(50)])
            rows, floor = EV.scan(self.repo)
        finally:
            EV.EV_SCAN_MAX = old
        self.assertEqual((len(rows), floor), (10, 1040))


class PlatAttachTest(unittest.TestCase):
    def setUp(self):
        self._old = (H.harness, HP._proj_ok, HP.harness_evidence.recent, HP.harness_evidence.commits, HP.harness_evidence.scan)
        HP.harness_evidence.commits = lambda proj: []   # no live git
        H.harness = lambda proj, days: (200, {"ok": True, "proj": proj, "days": 30, "events": [], "rules": [], "agents": [],
                                              "counts": {}, "mcps": [], "skills": [], "scanning": False})
        HP._proj_ok = lambda proj: True
        HP.harness_evidence.recent = lambda proj, limit=30: [{"kind": "check", "ts": 1, "proj": proj}]
        HP.harness_evidence.scan = lambda proj: ([{"kind": "check", "ts": 1, "proj": proj}], 0.0)

    def tearDown(self):
        H.harness, HP._proj_ok, HP.harness_evidence.recent, HP.harness_evidence.commits, HP.harness_evidence.scan = self._old

    def test_cc_and_cx(self):
        code, body = HP.harness_plat("cc", "/p", 30)
        self.assertEqual(code, 200)
        self.assertEqual(body["evidence"], [{"kind": "check", "ts": 1, "proj": "/p"}])
        cx = HP.HP_MODS.get("cx")
        if cx is None:
            self.skipTest("no cx platform module")
        old = (cx.harness_items, HP.ctxsrc._git_root)
        cx.harness_items = lambda proj, top: []
        HP.ctxsrc._git_root = lambda p: ""
        try:
            code, body = HP.harness_plat("cx", "/p", 30)
        finally:
            cx.harness_items, HP.ctxsrc._git_root = old
        self.assertEqual(code, 200)
        self.assertEqual(body["evidence"][0]["proj"], "/p")

    def test_evidence_only_route(self):
        code, body = HP.harness_evidence_only("/p")
        self.assertEqual((code, body["evidence"][0]["proj"]), (200, "/p"))
        HP._proj_ok = lambda proj: False
        self.assertEqual(HP.harness_evidence_only("/x")[0], 400)

    def test_error_has_no_evidence(self):
        H.harness = lambda proj, days: (400, {"ok": False, "msg": "unknown project"})
        code, body = HP.harness_plat("cc", "/p", 30)
        self.assertEqual(code, 400)
        self.assertNotIn("evidence", body)



class CommitsTest(unittest.TestCase):
    """commits(): hash + commit time only, per-repo TTL cache; _git_log/_now/_git_root patched (no live git)."""
    def setUp(self):
        self._old = (EV._git_log, EV._now, EV.gitinfo._git_root)
        self.t, self.calls, self.out = 1000.0, [], "abcdef1\t1700000000\n"
        EV._git_log = lambda repo: self.calls.append(repo) or self.out
        EV._now = lambda: self.t
        EV.gitinfo._git_root = lambda p: "/r"
        EV._CM_CACHE.clear()

    def tearDown(self):
        EV._git_log, EV._now, EV.gitinfo._git_root = self._old
        EV._CM_CACHE.clear()

    def test_parse_and_malformed(self):
        self.out = ("abcdef1\t1700000000\n0123456789ab\t1700000100\tSUBJECT leak\nZZZZZZZ\t1\nabc\t5\n"
                    "abcdef2\tsoon\nabcdef3\n\nabcdef4\t-5\n")
        self.assertEqual(EV.commits("/r/sub"), [{"h": "abcdef1", "ct": 1700000000}, {"h": "0123456789ab", "ct": 1700000100}])
        self.assertEqual(self.calls, [os.path.realpath("/r")])

    def test_git_failure_empty(self):
        self.out = None
        self.assertEqual(EV.commits("/r"), [])
        self.assertEqual(EV.commits(""), [])
        self.assertEqual(EV.commits(None), [])

    def test_ttl_cache_refetch(self):
        self.assertEqual(len(EV.commits("/r")), 1)
        self.t += EV.EV_CM_TTL - 1
        self.out = "abcdef1\t1\nabcdef2\t2\n"
        self.assertEqual(len(EV.commits("/r")), 1)
        self.assertEqual(len(self.calls), 1)
        self.t += 2
        self.assertEqual(len(EV.commits("/r")), 2)
        self.assertEqual(len(self.calls), 2)

    def test_git_log_argv(self):
        seen = []
        old = EV.gitinfo._git_run
        EV._git_log = self._old[0]

        class R:
            returncode, stdout = 0, "abcdef1\t9\n"
        EV.gitinfo._git_run = lambda cwd, args, timeout, wait=None: seen.append((cwd, args, wait)) or R()
        try:
            self.assertEqual(EV.commits("/r"), [{"h": "abcdef1", "ct": 9}])
        finally:
            EV.gitinfo._git_run = old
        self.assertEqual(seen[0][1], ["log", "-n", "30", "--format=%h%x09%ct"])
        self.assertEqual(seen[0][2], 0.5)


if __name__ == "__main__":
    unittest.main()
