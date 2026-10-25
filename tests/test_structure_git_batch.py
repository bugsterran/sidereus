"""`_struct_git_tree` cat-file deadlock guard + failed stages are neither cached nor persisted. No live git."""
import os
import shutil
import subprocess
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

from tests._load import sidereus

SN = sidereus("structure_snap")
S = sidereus("structure")
GI = sidereus("gitinfo")


class _BlockingPipe(object):
    """stdin that blocks past a pipe-size threshold, like a real pipe whose reader stopped reading."""
    def __init__(self, dead, limit=65536):
        self.dead, self.limit = dead, limit

    def write(self, b):
        if len(b) > self.limit:
            self.dead.wait()
            raise BrokenPipeError()

    def close(self):
        pass


class _StuckOut(object):
    """stdout of a git blocked on its own full stdout: nothing arrives until the process is killed."""
    def __init__(self, dead):
        self.dead = dead

    def readline(self):
        self.dead.wait()
        return b""

    def read(self, n=-1):
        return b""

    def close(self):
        pass


class _FakePopen(object):
    def __init__(self, *a, **k):
        self.dead = threading.Event()
        self.stdin = _BlockingPipe(self.dead)
        self.stdout = _StuckOut(self.dead)

    def kill(self):
        self.dead.set()

    def wait(self, timeout=None):
        if not self.dead.wait(timeout):
            raise subprocess.TimeoutExpired("fake", timeout)
        return -9


def _fake_sub(ls_out):
    run = lambda *a, **k: types.SimpleNamespace(stdout=ls_out, returncode=0)
    return types.SimpleNamespace(run=run, Popen=_FakePopen, PIPE=subprocess.PIPE,
                                 DEVNULL=subprocess.DEVNULL, TimeoutExpired=subprocess.TimeoutExpired)


class GitTreeDeadline(unittest.TestCase):
    def setUp(self):
        SN._struct_blob_cache.clear()

    def test_stuck_cat_file_returns_and_releases_slot(self):
        # 3000 blobs -> ~123KB of shas on stdin, past the fake 64KB pipe
        ls = b"".join(b"100644 blob %040x\tf%d.py\0" % (i, i) for i in range(3000))
        writes = []
        with mock.patch.object(SN, "subprocess", _fake_sub(ls)), \
                mock.patch.object(SN, "STRUCT_GIT_TIMEOUT", 0.1), \
                mock.patch.object(SN, "_struct_disk_read", lambda *a: None), \
                mock.patch.object(SN, "_struct_disk_write", lambda *a: writes.append(a)):
            t0 = time.time()
            got = SN._struct_git_tree("/nonexistent-root", "a" * 40)
            dt = time.time() - t0
        self.assertIsNone(got)
        self.assertLess(dt, 5.0)                       # did-not-hang bound, not a benchmark: a loaded runner adds seconds
        self.assertTrue(GI.git_slot_free(0))
        self.assertEqual(SN._struct_blob_cache, {})     # failure not cached in memory
        self.assertEqual(writes, [])                     # nor on disk


class FailedStageNotPersisted(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        with open(os.path.join(self.root, "a.py"), "w", encoding="utf-8") as f:
            f.write("def f():\n    return 1\n")
        S._struct_out_cache.clear()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        S._struct_out_cache.clear()

    def _run(self, tree):
        writes = []
        cur = sidereus("structure_scan")._struct_build([("a.py", b"def f():\n    return 1\n")])
        with mock.patch.object(S, "_struct_src_root", lambda p: self.root), \
                mock.patch.object(S, "_struct_git", lambda r: [(1, "b" * 40)]), \
                mock.patch.object(S, "_struct_git_tree", tree), \
                mock.patch.object(S, "_struct_now", lambda r, t=False: cur), \
                mock.patch.object(S, "_struct_disk_read", lambda *a: None), \
                mock.patch.object(S, "_struct_disk_write", lambda *a: writes.append(a[0])):
            out = S.structure(self.root)
        return out, writes

    def test_failed_git_stage_not_written(self):
        out, writes = self._run(lambda r, s, t=False: None)
        self.assertTrue(out["ok"])
        self.assertTrue(out.get("incomplete"))
        self.assertNotIn("out", writes)
        self.assertEqual(S._struct_out_cache, {})

    def test_ok_stage_written(self):
        cur = sidereus("structure_scan")._struct_build([("a.py", b"def f():\n    return 1\n")])
        out, writes = self._run(lambda r, s, t=False: cur)
        self.assertNotIn("incomplete", out)
        self.assertIn("out", writes)


if __name__ == "__main__":
    unittest.main()
