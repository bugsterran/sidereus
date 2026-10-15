"""Widening a segment window reads only the new front range; results and compaction marks equal a cold read."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

tl = sidereus("timeline_scan")
tr = sidereus("transcript")

T0 = 1_790_000_000          # fixture epoch, never the clock


def _iso(t):
    import datetime
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _line(i, t):
    if i % 97 == 5:
        e = {"type": "system", "subtype": "compact_boundary", "timestamp": _iso(t),
             "compactMetadata": {"trigger": "auto", "preTokens": 1000 + i, "postTokens": 10, "durationMs": 5}}
    else:
        e = {"type": "assistant", "timestamp": _iso(t), "requestId": "r%d" % (i // 2),
             "message": {"id": "msg_%d" % (i // 2), "usage": {"input_tokens": 3, "output_tokens": i % 7}}}
    return json.dumps(e, separators=(",", ":"))


class _Counted:
    """File proxy counting the bytes `readline` returns."""
    def __init__(self, f, box):
        self.f, self.box = f, box

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.f.close()

    def seek(self, n):
        self.f.seek(n)

    def readline(self, n=-1):
        b = self.f.readline(n)
        self.box[0] += len(b)
        return b


class SegGrowTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.fp = os.path.join(self.d, "s.jsonl")
        n = 3000
        with open(self.fp, "w") as f:   # 3000 lines over 75 h, ~90 s apart
            f.write("\n".join(_line(i, T0 + i * 90) for i in range(n)) + "\n")
        self.end = T0 + (n - 1) * 90
        self.box = [0]
        real = open
        tr.open = lambda p, m="r", *a, **k: _Counted(real(p, m, *a, **k), self.box)
        self._clear()

    def tearDown(self):
        del tr.open
        self._clear()
        shutil.rmtree(self.d)

    def _clear(self):
        tl._SEG_RAW.clear(); tl._SEG_WIN.clear()

    def _pass(self, hours):
        cut = self.end - hours * 3600
        tk = []
        r = tl._sess_segments(self.fp, cut, nb=2000, lim=100000, tok_out=tk)
        return r, tk, tl._compacts(self.fp, cut)

    def test_grow_equals_cold(self):
        self._pass(12)
        b12 = self.box[0]
        self.box[0] = 0
        grown = self._pass(72)
        grow_bytes = self.box[0]
        self._clear(); self.box[0] = 0
        cold = self._pass(72)
        cold_bytes = self.box[0]
        self.assertEqual(grown, cold)
        self.assertTrue(grown[0][0] and grown[1] and grown[2])   # segments, tokens and compactions were read
        size = os.path.getsize(self.fp)
        # growth reads only the new front range: every byte about once overall (slack = one dropped line per step)
        self.assertLessEqual(b12 + grow_bytes, size + 10 * 300)
        self.assertLess(grow_bytes, cold_bytes)

    def test_warm_reads_nothing(self):
        self._pass(72)
        self.box[0] = 0
        self._pass(72)
        self.assertEqual(self.box[0], 0)

    def test_compacts_match_line_types(self):
        _r, _tk, comp = self._pass(80)
        want = [i for i in range(3000) if i % 97 == 5]
        self.assertEqual([c["pre"] for c in comp], [1000 + i for i in want][-20:])

    def test_head_extend_matches_cold(self):
        _l, st, en, _rs = tr._tail_incr(self.fp, 5000, None)
        front, fs = tr._head_extend(self.fp, 50000, st)
        cold, cst, cen, _ = tr._tail_incr(self.fp, 50000, None)
        self.assertEqual((front + _l, fs, en), (cold, cst, cen))


if __name__ == "__main__":
    unittest.main()
