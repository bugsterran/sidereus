"""Idle structure warm-up runs each cell in a short-lived child process (issue #19). Nothing real is spawned."""
import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

S = sidereus("structure")
W = sidereus("structure_warm")


class _Stop(Exception):
    pass


class _Clock:
    def __init__(self, ticks):
        self.left = ticks

    def time(self):
        return 1000000.0

    def sleep(self, _s):
        if self.left <= 0:
            raise _Stop()
        self.left -= 1


class _BQ:
    """Fake boot_queue: records gate enter/exit so a failing child is shown to release the gate."""
    def __init__(self):
        self.log = []

    @contextlib.contextmanager
    def gate(self, name):
        self.log.append(("enter", name))
        try:
            yield
        finally:
            self.log.append(("exit", name))

    def done(self, name):
        self.log.append(("done", name))

    def others_done(self, name):
        return True


class _Base(unittest.TestCase):
    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp())
        with open(os.path.join(self.root, "a.py"), "w") as f:
            f.write("def f():\n    return 1\n")
        S._struct_out_cache.clear()
        S._struct_warm_seen.clear()
        self.disk = {}
        self.builds = []
        self.warns = []
        cur = sidereus("structure_scan")._struct_build([("a.py", b"def f():\n    return 1\n")])

        def now(r, t=False):
            self.builds.append(t)
            return cur
        self.ps = [mock.patch.object(S, "_struct_git", lambda r: []),
                   mock.patch.object(S, "_struct_backups", lambda r: []),
                   mock.patch.object(S, "_struct_now", now),
                   mock.patch.object(S, "_struct_disk_read", lambda k, key: self.disk.get((k, key))),
                   mock.patch.object(S, "_struct_disk_write", lambda k, key, d: self.disk.__setitem__((k, key), d)),
                   mock.patch.object(S, "warn_once", lambda *a, **k: self.warns.append(a[0]))]
        for p in self.ps:
            p.start()

    def tearDown(self):
        for p in self.ps:
            p.stop()
        shutil.rmtree(self.root, ignore_errors=True)
        S._struct_out_cache.clear()
        S._struct_warm_seen.clear()


class SpawnArgv(_Base):
    def test_r1_argv_devnull_timeout_and_bool(self):
        seen = []

        def run(argv, **kw):
            seen.append((argv, kw))
            return subprocess.CompletedProcess(argv, 0)
        with mock.patch.object(S.subprocess, "run", run):
            self.assertIs(S._struct_warm_spawn(self.root, 2), True)
        argv, kw = seen[0]
        self.assertEqual(argv, [sys.executable, "-m", "sidereus.structure_warm", self.root, "2"])
        for k in ("stdin", "stdout", "stderr"):
            self.assertEqual(kw[k], subprocess.DEVNULL)
        self.assertEqual(kw["timeout"], S.STRUCT_WARM_CHILD_TIMEOUT_S)   # R2: bounded child
        self.assertNotIn("shell", kw)
        self.assertTrue(os.path.isfile(os.path.join(kw["cwd"], "sidereus", "structure_warm.py")))
        self.assertEqual(self.warns, [])

    def test_r2_timeout_one_warning_false(self):
        def run(argv, **kw):
            raise subprocess.TimeoutExpired(argv, kw["timeout"])
        with mock.patch.object(S.subprocess, "run", run):
            self.assertIs(S._struct_warm_spawn(self.root, 0), False)
        self.assertEqual(self.warns, ["struct-warm-child"])


class ChildMain(_Base):
    def test_r1_main_writes_disk_not_memory(self):
        self.assertEqual(W.main([self.root, "0"]), 0)
        self.assertEqual([k for k, _key in self.disk], ["out"])
        self.assertEqual(S._struct_out_cache, {})          # the child never fills a memory cell
        with mock.patch.object(S, "_struct_src_root", lambda p: self.root):
            out = S.structure(self.root)                   # later screen request reads the child's disk entry
        self.assertTrue(out["warm"])
        self.assertEqual(len(self.builds), 1)

    def test_r2_bad_args_never_compute(self):
        called = []
        denied = next(iter(S._struct_denied_roots()))
        with mock.patch.object(S, "_structure_at", lambda *a, **k: called.append(a)):
            for argv in (["rel/path", "0"], [os.path.join(self.root, "missing"), "0"], [denied, "0"],
                         [self.root, "3"], [self.root], [self.root, "0", "x"], ["", "0"]):
                self.assertEqual(W.main(argv), 2, argv)
        self.assertEqual(called, [])

    def test_r2_main_does_not_touch_allow_list(self):
        def boom(*a, **k):
            raise AssertionError("allow-list must not run in the child")
        with mock.patch.object(S, "_struct_src_root", boom), mock.patch.object(S, "_allowed_cwds", boom):
            self.assertEqual(W.main([self.root, "0"]), 0)


class LoopSurvivesChild(_Base):
    def _loop(self, run):
        bq = _BQ()
        with mock.patch.object(S.subprocess, "run", run), \
                mock.patch.object(S, "boot_queue", bq), \
                mock.patch.object(S, "_struct_warm_targets", lambda: [self.root]), \
                mock.patch.object(S, "_struct_disk_prune", lambda: None), \
                mock.patch.object(S, "STRUCT_WARM_BOOT_S", 0), \
                mock.patch.object(S, "_struct_act", [0.0]), \
                mock.patch.object(S, "time", _Clock(3)):
            with self.assertRaises(_Stop):
                S._struct_warm_loop()
        return bq

    def _check(self, run):
        bq = self._loop(run)
        self.assertEqual(bq.log.count(("enter", "struct_warm")), 3)    # R3: every cell tried, loop kept going
        self.assertEqual(bq.log.count(("exit", "struct_warm")), 3)     # gate released after each failure
        self.assertEqual(len(S._struct_warm_seen), 3)                  # failed cells wait one CYCLE, no retry storm
        self.assertEqual(self.builds, [])                               # no in-process fallback in the warm loop
        self.assertEqual(set(self.warns), {"struct-warm-child"})
        with mock.patch.object(S, "_struct_src_root", lambda p: self.root):
            out = S.structure(self.root)                                # screen request computes in-process
        self.assertTrue(out["ok"])
        self.assertFalse(out["warm"])

    def test_r3_nonzero_exit(self):
        self._check(lambda argv, **kw: subprocess.CompletedProcess(argv, 1))

    def test_r3_timeout(self):
        def run(argv, **kw):
            raise subprocess.TimeoutExpired(argv, kw["timeout"])
        self._check(run)

    def test_r3_oserror(self):
        def run(argv, **kw):
            raise OSError("no exec")
        self._check(run)


if __name__ == "__main__":
    unittest.main()
