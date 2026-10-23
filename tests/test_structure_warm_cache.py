"""Idle warm-up writes structure results to the disk cache only; the memory cache holds screen-requested cells."""
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

S = sidereus("structure")


class _Stop(Exception):
    pass


class _Clock:
    """Stub for the module's `time`: fixed clock, sleep() stops the loop after `ticks` calls."""
    def __init__(self, ticks):
        self.left = ticks

    def time(self):
        return 1000000.0

    def sleep(self, _s):
        if self.left <= 0:
            raise _Stop()
        self.left -= 1


class WarmDiskOnly(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        S._struct_out_cache.clear()
        S._struct_warm_seen.clear()
        self.disk = {}
        self.builds = []

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        S._struct_out_cache.clear()
        S._struct_warm_seen.clear()

    def _patches(self, clock):
        cur = sidereus("structure_scan")._struct_build([("a.py", b"def f():\n    return 1\n")])

        def now(r, t=False):
            self.builds.append(t)
            return cur
        return [mock.patch.object(S, "_struct_src_root", lambda p: self.root),
                mock.patch.object(S, "_struct_git", lambda r: []),
                mock.patch.object(S, "_struct_backups", lambda r: []),
                mock.patch.object(S, "_struct_now", now),
                mock.patch.object(S, "_struct_disk_read", lambda k, key: self.disk.get((k, key))),
                mock.patch.object(S, "_struct_disk_write", lambda k, key, d: self.disk.__setitem__((k, key), d)),
                mock.patch.object(S, "_struct_warm_targets", lambda: [self.root]),
                mock.patch.object(S, "_struct_disk_prune", lambda: None),
                # R1: the warm loop spawns a child; run its body in-process here so nothing real is spawned.
                mock.patch.object(S, "_struct_warm_spawn", lambda r, t: S._structure_at(r, t, mem=False)),
                mock.patch.object(S, "STRUCT_WARM_BOOT_S", 0),
                mock.patch.object(S, "_struct_act", [0.0]),
                mock.patch.object(S, "time", clock)]

    def test_warm_fills_disk_not_memory_then_screen_is_disk_hit(self):
        ps = self._patches(_Clock(3))
        for p in ps:
            p.start()
        try:
            with self.assertRaises(_Stop):
                S._struct_warm_loop()
            self.assertEqual(len(self.builds), 3)          # tests 0 / 1 / 2 each warmed once
            self.assertEqual(len(self.disk), 3)
            self.assertEqual(S._struct_out_cache, {})      # warm-only cells stay out of memory
            out = S.structure(self.root)                   # screen request after warming
            self.assertTrue(out["ok"])
            self.assertTrue(out["warm"])
            self.assertEqual(len(self.builds), 3)          # disk hit, no rebuild
            self.assertEqual(len(S._struct_out_cache), 1)  # the requested cell is now in memory
        finally:
            for p in ps:
                p.stop()

    def test_warm_does_not_touch_screen_cell_recency(self):
        ps = self._patches(_Clock(1))
        for p in ps:
            p.start()
        try:
            S.structure(self.root)                         # screen fills the memory cell at t=1000000
            ck = next(iter(S._struct_out_cache))
            S._struct_out_cache[ck] = S._struct_out_cache[ck][:2] + (5.0,)
            with self.assertRaises(_Stop):
                S._struct_warm_loop()
            self.assertEqual(S._struct_out_cache[ck][2], 5.0)
            self.assertEqual(len(S._struct_out_cache), 1)
        finally:
            for p in ps:
                p.stop()

    def test_screen_disk_hits_stay_capped(self):
        n = S.STRUCT_CACHE_N
        with mock.patch.object(S, "_struct_disk_read", lambda k, key: {"ok": True, "snaps": []}):
            for i in range(n + 3):
                hit, _dk = S._struct_cache_get("/r%d" % i, ("/r%d" % i, 0, 1), ("k", i), float(i))
                self.assertTrue(hit["warm"])
        self.assertLessEqual(len(S._struct_out_cache), n)
        self.assertNotIn(("/r0", 0, 1), S._struct_out_cache)          # oldest evicted first
        self.assertIn(("/r%d" % (n + 2), 0, 1), S._struct_out_cache)


if __name__ == "__main__":
    unittest.main()
