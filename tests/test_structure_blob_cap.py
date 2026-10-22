"""Every in-memory structure blob write is capped — disk hits included (issue #17 footprint growth)."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

SC = sidereus("structure_scan")
SN = sidereus("structure_snap")


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
                  mock.patch.object(SN, "_struct_dec_build", lambda raw: {"files": 1})]
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

    def test_put_evicts_oldest_keeps_newest(self):
        for i in range(self.n):
            SC._struct_blob_put(("k", i), i)
        self.assertEqual(len(SC._struct_blob_cache), SC.STRUCT_BCACHE_N)
        self.assertIn(("k", self.n - 1), SC._struct_blob_cache)
        self.assertNotIn(("k", 0), SC._struct_blob_cache)


if __name__ == "__main__":
    unittest.main()
