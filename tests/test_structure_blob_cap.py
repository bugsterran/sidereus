"""Every in-memory structure blob write is capped — disk hits included (issue #17 footprint growth)."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

SC = sidereus("structure_scan")
SN = sidereus("structure_snap")
_DEC = SN._struct_dec_build
_FAKE = (3, [{"file": "a.py", "name": "f", "lang": "py", "line": 1, "lines": 3, "h": "x"}],
         False, 1, 0, {"vendor": 0, "vendorLines": 0, "test": 0, "testLines": 0}, {"t.py"})


class BlobCacheCap(unittest.TestCase):
    def setUp(self):
        self._saved = dict(SC._struct_blob_cache)
        SC._struct_blob_cache.clear()
        self.tmp = tempfile.mkdtemp()
        self.n = SC.STRUCT_BCACHE_N + 15
        self.paths = []
        for i in range(self.n):
            p = os.path.join(self.tmp, "f%d.bak" % i)
            with open(p, "w", encoding="utf-8") as f:
                f.write("x")
            self.paths.append(p)
        # disk copy always hits: no git, no tar, no parse
        self.p = [mock.patch.object(SN, "_struct_disk_read", lambda *a: b"blob"),
                  mock.patch.object(SN, "_struct_dec_build", lambda raw: _FAKE if raw == b"blob" else _DEC(raw))]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)
        SC._struct_blob_cache.clear()
        SC._struct_blob_cache.update(self._saved)

    def test_git_disk_hits_capped(self):
        for i in range(self.n):
            self.assertIsNotNone(SN._struct_git_tree("/nonexistent-root", "%040x" % i))
        self.assertLessEqual(len(SC._struct_blob_cache), SC.STRUCT_BCACHE_N)

    def test_bak_disk_hits_capped(self):
        for p in self.paths:
            self.assertIsNotNone(SN._struct_plain(p, "a.py"))
        self.assertLessEqual(len(SC._struct_blob_cache), SC.STRUCT_BCACHE_N)

    def test_tar_disk_hits_capped(self):
        for p in self.paths:
            self.assertIsNotNone(SN._struct_tar(p))
        self.assertLessEqual(len(SC._struct_blob_cache), SC.STRUCT_BCACHE_N)

    def test_memory_holds_bytes_and_hit_equals_build(self):
        sha = "%040x" % 1
        first = SN._struct_git_tree("/nonexistent-root", sha)
        self.assertEqual(first, _FAKE)
        vals = list(SC._struct_blob_cache.values())
        self.assertEqual(len(vals), 1)
        self.assertIsInstance(vals[0], bytes)
        with mock.patch.object(SN, "_struct_disk_read", lambda *a: self.fail("memory hit expected")):
            self.assertEqual(SN._struct_git_tree("/nonexistent-root", sha), _FAKE)

    def test_size_cap_none_stays_cached(self):
        SN._struct_mem_put(("bak", "p"), None)
        self.assertIsNone(SN._struct_mem_get(("bak", "p")))
        self.assertIs(SN._struct_mem_get(("bak", "q")), SN._MISS)

    def test_put_evicts_oldest_keeps_newest(self):
        for i in range(self.n):
            SC._struct_blob_put(("k", i), i)
        self.assertEqual(len(SC._struct_blob_cache), SC.STRUCT_BCACHE_N)
        self.assertIn(("k", self.n - 1), SC._struct_blob_cache)
        self.assertNotIn(("k", 0), SC._struct_blob_cache)


if __name__ == "__main__":
    unittest.main()
