"""`_sess_segments` stops widening once a file was read whole, and its caches survive a full window pass."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

tl = sidereus("timeline_scan")      # segment scan/caches live here since the 2026-09-24 split


def _line(i, typ="assistant"):
    ts = "2026-09-24T%02d:%02d:%02d.000Z" % (10 + i // 3600, (i // 60) % 60, i % 60)
    return json.dumps({"type": typ, "timestamp": ts, "requestId": "r%d" % i,
                       "message": {"id": "msg_%d" % i, "usage": {"input_tokens": 3, "output_tokens": 2}}},
                      separators=(",", ":"))      # transcripts are compact; the scanner matches `"timestamp":"`


class SegWholeTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self._scan, self._whole = tl._seg_scan, tl._seg_whole
        self.n = 0

        def count(*a):
            self.n += 1
            return self._scan(*a)
        tl._seg_scan = count
        for c in (tl._SEG_RAW, tl._SEG_WIN):
            c.clear()

    def tearDown(self):
        tl._seg_scan, tl._seg_whole = self._scan, self._whole
        for c in (tl._SEG_RAW, tl._SEG_WIN):
            c.clear()
        shutil.rmtree(self.d)

    def write(self, name, n):
        fp = os.path.join(self.d, name)
        with open(fp, "w") as f:
            f.write("\n".join(_line(i * 7) for i in range(n)) + "\n")
        return fp

    def run_both(self, fp, nb, lim):
        """(result with the guard, scans) vs (result with the guard off, scans) from cold caches."""
        cut = 0                                   # before every line — the window never "reaches" cut
        out = []
        for guard in (True, False):
            tl._SEG_RAW.clear(); tl._SEG_WIN.clear(); self.n = 0
            tl._seg_whole = self._whole if guard else (lambda *a: False)
            tk = []
            r = tl._sess_segments(fp, cut, nb, lim, tok_out=tk)
            out.append(((r, tk), self.n))
        return out

    def test_small_file_one_scan_same_result(self):
        fp = self.write("a.jsonl", 50)
        (g, ng), (u, nu) = self.run_both(fp, 3_000_000, 6000)
        self.assertEqual(g, u)
        self.assertTrue(g[0][0] and g[1])         # segments and tokens were actually read
        self.assertEqual(ng, 1)
        self.assertGreater(nu, 1)

    def test_file_larger_than_window_still_grows(self):
        fp = self.write("b.jsonl", 200)
        (g, ng), (u, _nu) = self.run_both(fp, 500, 6000)
        self.assertEqual(g, u)
        self.assertGreater(ng, 1)

    def test_trimmed_scan_still_grows(self):
        fp = self.write("c.jsonl", 100)           # whole file fits, but 100 lines > lim=10 trims
        (g, ng), (u, _nu) = self.run_both(fp, 3_000_000, 10)
        self.assertEqual(g, u)
        self.assertGreater(ng, 1)

    def test_cache_survives_pass_over_many_files(self):
        fps = [self.write("f%03d.jsonl" % i, 3) for i in range(320)]      # > the old 300 cap
        for fp in fps:
            tl._sess_segments(fp, 0)
        self.n = 0
        for fp in fps:
            tl._sess_segments(fp, 0)
        self.assertEqual(self.n, len(fps))        # one scan each ...
        self.assertEqual(len(tl._SEG_RAW), len(fps))   # ... all served from the raw cache


if __name__ == "__main__":
    unittest.main()
