"""Viewer git calls never write the watched repo (GIT_OPTIONAL_LOCKS=0), and structure tar/plain errors are not cached.
Real git only in a temp repo; subprocess/disk cache faked elsewhere."""
import os
import shutil
import subprocess
import tempfile
import time
import unittest

from tests._load import sidereus

gi = sidereus("gitinfo")
ss = sidereus("structure_snap")


class GitEnv(unittest.TestCase):
    def test_git_env_sets_flag(self):
        self.assertEqual(gi.git_env()["GIT_OPTIONAL_LOCKS"], "0")

    def test_git_run_passes_env(self):
        seen = {}
        saved = gi.subprocess.run

        def fake(cmd, **kw):
            seen.update(kw)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        gi.subprocess.run = fake
        try:
            gi._git_run("/nonexistent", ["status"], 1)
        finally:
            gi.subprocess.run = saved
        self.assertEqual(seen["env"]["GIT_OPTIONAL_LOCKS"], "0")


@unittest.skipUnless(shutil.which("git"), "git not installed")
class StatusLeavesIndexAlone(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        d = self.td.name
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@t")
        for c in (["init", "-q"], ["add", "a.txt"], ["commit", "-qm", "x"]):
            if c[0] == "add":
                with open(os.path.join(d, "a.txt"), "w", encoding="utf-8") as f:
                    f.write("a\n")
            subprocess.run(["git", "-C", d] + c, check=True, env=env, capture_output=True)
        self.idx = os.path.join(d, ".git", "index")
        old = time.time() - 100
        os.utime(self.idx, (old, old))
        os.utime(os.path.join(d, "a.txt"), (old + 50, old + 50))   # stat-dirty, content unchanged
        gi._git_cache.pop(d, None)

    def tearDown(self):
        gi._git_cache.pop(self.td.name, None)
        self.td.cleanup()

    def test_git_state_does_not_touch_index(self):
        before = os.stat(self.idx).st_mtime_ns
        gi._git_state(self.td.name, ttl=0)
        self.assertEqual(os.stat(self.idx).st_mtime_ns, before)
        self.assertFalse(os.path.exists(self.idx + ".lock"))


class StructErrorsNotCached(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self._saved = (ss._struct_disk_read, ss._struct_disk_write, ss._struct_build, dict(ss._struct_blob_cache))
        ss._struct_disk_read = lambda *a, **k: None
        ss._struct_disk_write = lambda *a, **k: None

    def tearDown(self):
        ss._struct_disk_read, ss._struct_disk_write, ss._struct_build = self._saved[:3]
        ss._struct_blob_cache.clear(); ss._struct_blob_cache.update(self._saved[3])
        self.td.cleanup()

    def _keys(self, kind, path):
        return [k for k in ss._struct_blob_cache if k[0] == kind and k[1] == path]

    def test_bad_tar_not_cached(self):
        p = os.path.join(self.td.name, "b.tar.gz")
        with open(p, "wb") as f:
            f.write(b"not a gzip")
        self.assertIsNone(ss._struct_tar(p))
        self.assertEqual(self._keys("tar", p), [])

    def test_plain_error_not_cached_but_size_cap_is(self):
        p = os.path.join(self.td.name, "x.py")
        with open(p, "w", encoding="utf-8") as f:
            f.write("x = 1\n")

        def boom(*a, **k):
            raise RuntimeError("parse")
        ss._struct_build = boom
        self.assertIsNone(ss._struct_plain(p, "x.py"))
        self.assertEqual(self._keys("bak", p), [])
        saved_max = ss.STRUCT_MAX_BYTES
        ss.STRUCT_MAX_BYTES = 1
        try:
            self.assertIsNone(ss._struct_plain(p, "x.py"))
        finally:
            ss.STRUCT_MAX_BYTES = saved_max
        self.assertEqual(len(self._keys("bak", p)), 1)


if __name__ == "__main__":
    unittest.main()
