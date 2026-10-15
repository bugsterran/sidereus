"""git_rail caches on BoundedMemo: untracked line counts (stamp = size, mtime_ns) and session start epochs."""
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

gr = sidereus("git_rail")


class RailMemo(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d)
        self.reads = []
        real = gr._read_small
        gr._read_small = lambda p: (self.reads.append(p), real(p))[1]
        self.addCleanup(setattr, gr, "_read_small", real)
        gr._rail_lc.clear()
        gr._start_cache.clear()
        self.addCleanup(gr._rail_lc.clear)
        self.addCleanup(gr._start_cache.clear)

    def _w(self, name, body, mt=None):
        p = os.path.join(self.d, name)
        with open(p, "w") as fh:
            fh.write(body)
        if mt:
            os.utime(p, ns=(mt, mt))
        return p

    def test_untracked_count_hits_until_stamp_changes(self):
        self._w("a.txt", "1\n2\n", 10 ** 18)
        self.assertEqual(gr._untracked_rec(self.d, "a.txt")["add"], 2)
        self.assertEqual(gr._untracked_rec(self.d, "a.txt")["add"], 2)
        self.assertEqual(len(self.reads), 1)                        # second call served from the memo
        self._w("a.txt", "1\n2\n3", 10 ** 18 + 5)
        self.assertEqual(gr._untracked_rec(self.d, "a.txt")["add"], 3)
        self.assertEqual(len(self.reads), 2)                        # mtime/size changed -> re-read

    def test_untracked_binary_cached_and_cap(self):
        with open(os.path.join(self.d, "b.bin"), "wb") as fh:
            fh.write(b"x\0y")
        self.assertTrue(gr._untracked_rec(self.d, "b.bin")["bin"])
        self.assertTrue(gr._untracked_rec(self.d, "b.bin")["bin"])
        self.assertEqual(len(self.reads), 1)
        self.assertIsInstance(gr._rail_lc, gr.BoundedMemo)
        self.assertEqual(gr._rail_lc.cap, gr.RAIL_LC_MAX)
        self.assertEqual(gr._start_cache.cap, 256)

    def test_session_start_caches_zero_and_evicts_past_cap(self):
        paths = {}
        real = gr._sid_path
        gr._sid_path = lambda cwd, sid: paths.get(sid, "")
        self.addCleanup(setattr, gr, "_sid_path", real)
        paths["none"] = self._w("n.jsonl", '{"type":"x"}\n')
        self.assertEqual(gr._session_start(self.d, "none"), 0)
        self._w("n.jsonl", '{"timestamp":"2026-09-23T18:53:09Z"}\n')
        self.assertEqual(gr._session_start(self.d, "none"), 0)      # cached 0 is returned, file not re-read
        for i in range(300):
            paths["s%d" % i] = "/nonexistent/%d" % i
            gr._session_start(self.d, "s%d" % i)
        self.assertEqual(len(gr._start_cache), 256)
        self.assertNotIn(paths["none"], gr._start_cache)            # oldest evicted
        self.assertEqual(gr._session_start(self.d, "none"), 1790189589)


if __name__ == "__main__":
    unittest.main()
