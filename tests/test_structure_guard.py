"""structure() allow list + bounded walks (security review 2026-09-25)."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

S = sidereus("structure")
SN = sidereus("structure_snap")
SC = sidereus("structure_scan")


class _Tree(unittest.TestCase):
    N = 10

    def setUp(self):
        self.d = os.path.realpath(tempfile.mkdtemp())
        for i in range(self.N):
            os.makedirs(os.path.join(self.d, "d%02d" % i))
            with open(os.path.join(self.d, "d%02d" % i, "m.py"), "w", encoding="utf-8") as f:
                f.write("def f%d():\n    return %d\n" % (i, i))
        S._struct_out_cache.clear()
        w = mock.patch.object(S, "sessions_snapshot_wait", lambda: None)   # no in-flight poll unless a test says so
        w.start()
        self.addCleanup(w.stop)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)
        S._struct_out_cache.clear()

    def _walk_counter(self):
        real = os.walk
        calls = {"n": 0, "dirs": 0}

        def walk(*a, **k):
            calls["n"] += 1
            for t in real(*a, **k):
                calls["dirs"] += 1
                yield t
        return calls, walk


class AllowList(_Tree):
    def test_outside_refused_without_scan(self):
        calls, walk = self._walk_counter()
        git = mock.Mock(return_value=[])
        with mock.patch.object(S, "_struct_src_root", lambda p: ""), \
                mock.patch.object(S, "_struct_git", git), \
                mock.patch("os.walk", walk):
            out = S.structure("/")
        self.assertFalse(out["ok"])
        self.assertEqual(out["msg"], "Only projects shown on screen can be opened.")
        self.assertEqual(calls["n"], 0)
        git.assert_not_called()

    def test_real_allow_list_rejects_root(self):
        with mock.patch.object(S, "_struct_warm_targets", lambda: [self.d]), \
                mock.patch.object(S, "sessions_snapshot", lambda: None):
            self.assertEqual(S._struct_src_root("/"), "")
            self.assertEqual(S._struct_src_root(self.d), self.d)

    def test_same_cwd_rows_allow_both_repos(self):
        # ⚠_allowed_cwds() keeps one row per cwd; the UI offers every row's repos, so both must pass.
        a, b = os.path.join(self.d, "d01"), os.path.join(self.d, "d02")
        rows = [{"cwd": self.d, "repos": [a]}, {"cwd": self.d, "repos": [b]}]
        with mock.patch.object(S, "_allowed_cwds", lambda: {self.d: rows[1]}), \
                mock.patch.object(S, "sessions_snapshot", lambda: rows):
            self.assertEqual(S._struct_src_root(a), a)
            self.assertEqual(S._struct_src_root(b), b)
            self.assertEqual(S._struct_src_root(os.path.join(self.d, "d03")), "")
            self.assertNotIn(a, S._struct_warm_targets())      # warming is not widened

    def test_no_snapshot_falls_back_to_warm_targets(self):
        with mock.patch.object(S, "_struct_warm_targets", lambda: [self.d]), \
                mock.patch.object(S, "sessions_snapshot", lambda: None):
            self.assertEqual(S._struct_src_root(self.d), self.d)

    def _old_allowed(self):
        # Pre-2026-09-28 implementation, kept verbatim as the reference set.
        cands = list(S._struct_warm_targets())
        for r in S.sessions_snapshot() or ():
            cands.append(r.get("cwd"))
            cands.extend(r.get("repos") or [])
        return set(os.path.realpath(p) for p in cands if p) - S._struct_denied_roots()

    def test_snapshot_path_matches_old_decisions_without_sessions(self):
        d = self.d
        code, cwd, repo, sib = (os.path.join(d, x) for x in ("d00", "d01", "d02", "d03"))
        outside = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, True)
        os.symlink(outside, os.path.join(cwd, "esc"))
        os.symlink(repo, os.path.join(d, "via"))
        rows = [{"cwd": cwd, "repos": [repo]}, {"cwd": cwd, "repos": [cwd]}]
        dedup = {cwd: rows[1]}
        boom = mock.Mock(side_effect=AssertionError("sessions() path must not run"))
        probes = [code, cwd, repo, cwd + "/", sib, d, os.path.dirname(d), "/", os.path.join(cwd, "esc"),
                  os.path.join(d, "via"), os.path.join(d, "nope"), os.path.join(cwd, "..", "d03")]
        with mock.patch.object(S, "CODE_DIR", code), \
                mock.patch.object(S, "sessions_snapshot", lambda: rows):
            with mock.patch.object(S, "_allowed_cwds", lambda: dedup):
                old = [os.path.realpath(p) in self._old_allowed() for p in probes]
            with mock.patch.object(S, "_allowed_cwds", boom):
                new = [bool(S._struct_src_root(p)) for p in probes]
        boom.assert_not_called()
        self.assertEqual(new, old)
        self.assertEqual(new[:5], [True, True, True, True, False])
        self.assertEqual(new[5:10], [False, False, False, False, True])

    def test_snapshot_failure_keeps_old_union(self):
        def bad():
            raise RuntimeError("x")
        with mock.patch.object(S, "_struct_warm_targets", lambda: [self.d]), \
                mock.patch.object(S, "sessions_snapshot", bad):
            self.assertEqual(S._struct_src_root(self.d), self.d)

    def test_waited_snapshot_same_decisions_as_present(self):
        # A snapshot obtained by joining an in-flight poll must allow exactly what a present one allows.
        rows = [{"cwd": self.d, "repos": [os.path.join(self.d, "d01")]}]
        boom = mock.Mock(side_effect=AssertionError("cold sessions() path must not run"))
        with mock.patch.object(S, "CODE_DIR", os.path.join(self.d, "d00")), \
                mock.patch.object(S, "_allowed_cwds", boom), \
                mock.patch.object(S, "_struct_warm_targets", boom):
            with mock.patch.object(S, "sessions_snapshot", lambda: rows):
                present = S._struct_allowed_roots()
            with mock.patch.object(S, "sessions_snapshot", lambda: None), \
                    mock.patch.object(S, "sessions_snapshot_wait", lambda: rows):
                waited = S._struct_allowed_roots()
        self.assertEqual(waited, present)
        self.assertEqual(present, {self.d, os.path.join(self.d, "d00"), os.path.join(self.d, "d01")})

    def test_only_page_loads_mark(self):
        # API GETs are timers/MCP too; human input arrives via POST /api/act (tests/test_struct_act.py).
        self.assertFalse([p for p in S.STRUCT_PAGE_PATHS if p.startswith("/api/")])

    def test_allowed_path_works(self):
        with mock.patch.object(S, "_struct_src_root", lambda p: self.d if p == self.d else ""), \
                mock.patch.object(S, "_struct_git", lambda r: []), \
                mock.patch.object(S, "_struct_backups", lambda r: []), \
                mock.patch.object(S, "_struct_disk_read", lambda *a: None), \
                mock.patch.object(S, "_struct_disk_write", lambda *a: None), \
                mock.patch.object(SN, "_struct_fcache_load", lambda *a: None), \
                mock.patch.object(SN, "_struct_fcache_save", lambda *a: None):
            out = S.structure(self.d)
        self.assertTrue(out["ok"])
        self.assertEqual(out["path"], self.d)
        self.assertEqual(len(out["snaps"]), 1)


class WalkCap(_Tree):
    def test_now_stops_outer_walk(self):
        calls, walk = self._walk_counter()
        with mock.patch.object(SN, "STRUCT_MAX_FILES", 1), \
                mock.patch.object(SC, "STRUCT_MAX_FILES", 1), \
                mock.patch.object(SN, "_struct_fcache_load", lambda *a: None), \
                mock.patch.object(SN, "_struct_fcache_save", lambda *a: None), \
                mock.patch("os.walk", walk):
            got = SN._struct_now(self.d)
        # cap*2 = 2 -> stops once 3 files are held; root + 3 subdirs, not all 11 dirs
        self.assertLess(calls["dirs"], self.N + 1)
        self.assertEqual(calls["dirs"], 4)
        self.assertTrue(got[2])            # truncated flag still set by _struct_build

    def test_key_stops_outer_walk(self):
        calls, walk = self._walk_counter()
        with mock.patch.object(S, "STRUCT_MAX_FILES", 1), mock.patch("os.walk", walk):
            S._struct_key(self.d, [], [], False, 10)
        self.assertEqual(calls["dirs"], 4)


SS = sidereus("sessions")


class _Clock:
    def __init__(self):
        self.t = 1000.0

    def time(self):
        return self.t


class _CV:
    """Stands in for _SNAP_CV: each wait() runs `on_wait` (the in-flight call finishing) and advances the clock."""
    def __init__(self, clock, on_wait):
        self.clock, self.on_wait, self.n = clock, on_wait, 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def wait(self, left):
        self.n += 1
        self.clock.t += min(left, 1.0)
        self.on_wait()


class SnapshotWait(unittest.TestCase):
    def _run(self, snap, on_wait, timeout=8.0):
        clock = _Clock()
        cv = _CV(clock, lambda: on_wait(snap, clock))
        with mock.patch.object(SS, "time", clock), mock.patch.object(SS, "_SNAP", snap), \
                mock.patch.object(SS, "_SNAP_CV", cv):
            return SS.sessions_snapshot_wait(timeout), cv.n

    def test_nothing_in_flight_returns_none_without_waiting(self):
        got, n = self._run({"at": 0, "rows": [], "busy": 0}, lambda s, c: None)
        self.assertIsNone(got)
        self.assertEqual(n, 0)

    def test_joins_in_flight_call(self):
        rows = [{"cwd": "/x"}]

        def finish(s, c):
            s.update(at=c.t, rows=rows, busy=0)
        got, n = self._run({"at": 0, "rows": [], "busy": 1}, finish)
        self.assertIs(got, rows)
        self.assertEqual(n, 1)

    def test_times_out(self):
        got, n = self._run({"at": 0, "rows": [], "busy": 1}, lambda s, c: None, timeout=3.0)
        self.assertIsNone(got)
        self.assertEqual(n, 3)

    def test_default_call_counts_in_flight_and_leaves_zero(self):
        seen = []
        snap = {"at": 0, "rows": [], "busy": 0}

        def body(a, c):
            seen.append(snap["busy"])
            raise RuntimeError("x")
        with mock.patch.object(SS, "_SNAP", snap), mock.patch.object(SS, "_sessions", body):
            with self.assertRaises(RuntimeError):
                SS.sessions()
            with self.assertRaises(RuntimeError):
                SS.sessions(1, 5)          # non-default call is not counted
        self.assertEqual(seen, [1, 0])
        self.assertEqual(snap["busy"], 0)


if __name__ == "__main__":
    unittest.main()
