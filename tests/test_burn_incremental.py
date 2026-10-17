"""Consumption-report scan is incremental: appended bytes only, same result as a fresh full scan.

No live files: temp dirs only; the clock is a fixed `now` passed in and file mtimes are set to it.
"""
import json
import os
import shutil
import tempfile
import time
import unittest

from tests import _load

bs = _load.sidereus("burn_scan")
NOW = time.mktime((2026, 10, 13, 12, 0, 0, 0, 0, -1))


def _line(t, mid, rid, tok):
    return json.dumps({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)), "requestId": rid,
                       "message": {"id": mid, "usage": {"input_tokens": tok, "output_tokens": 1}}}) + "\n"


class BurnIncremental(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        names = ("CLAUDE_PROJECTS", "_slug_name", "_compact_win")
        self.saved = {k: getattr(bs, k) for k in names}
        self.burn = dict(bs._burn)
        bs.CLAUDE_PROJECTS, bs._slug_name = self.d, (lambda s: s)
        bs._compact_win = lambda now=None: {"value": 1_000_000, "since": 0, "prev": None, "approx": True}
        bs._burn_files.clear()

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(bs, k, v)
        bs.__dict__.pop("open", None)
        bs._burn.clear()
        bs._burn.update(self.burn)
        bs._burn_files.clear()
        shutil.rmtree(self.d, ignore_errors=True)

    def _fp(self, proj, name):
        p = os.path.join(self.d, proj)
        os.makedirs(p, exist_ok=True)
        return os.path.join(p, name)

    def _append(self, fp, text, now=NOW):
        with open(fp, "a", encoding="utf-8") as f:
            f.write(text)
        os.utime(fp, (now, now))

    def _result(self, now=NOW):
        bs._burn_fetch(now)
        b = bs._burn
        return b["rows"], b["subs"], [(x["proj"], x["id"]) for x in b["sess"]], b["tot"]

    def _fresh(self, now=NOW):
        saved = dict(bs._burn_files)
        bs._burn_files.clear()
        try:
            return self._result(now)
        finally:
            bs._burn_files.clear()
            bs._burn_files.update(saved)

    def _count_reads(self):
        got = []
        real_open = open

        class F(object):
            def __init__(self, f):
                self.f = f

            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.f.close()

            def __getattr__(self, n):
                return getattr(self.f, n)

            def read(self, *a):
                b = self.f.read(*a)
                got.append(len(b))
                return b

        bs.open = lambda *a, **k: F(real_open(*a, **k))
        return got

    def test_incremental_equals_full_over_three_passes(self):
        a, b = self._fp("pa", "s1.jsonl"), self._fp("pb", "s2.jsonl")
        self._append(a, _line(NOW - 600, "m1", "r1", 10) + _line(NOW - 600, "m1", "r1", 10))
        self._append(b, _line(NOW - 300, "m2", "r2", 20) + _line(NOW - 5 * 3600, "m0", "r0", 999))
        r1 = self._result()
        self.assertEqual(r1, self._fresh())
        self._append(a, _line(NOW - 60, "m3", "r3", 5) + '{"bad": "usage"\n')
        self._append(b, _line(NOW - 60, "m1", "r1", 10))     # same response in another file: counted once
        r2 = self._result()
        self.assertEqual(r2, self._fresh())
        self._append(b, _line(NOW - 30, "m4", "r4", 7) + json.dumps({"timestamp": "x", "usage": 1}) + "\n")
        r3 = self._result()
        self.assertEqual(r3, self._fresh())
        self.assertEqual(r3[3], 10 + 20 + 5 + 7)
        self.assertEqual(sum(r["req"] for r in r3[0]), 4)

    def test_only_appended_bytes_are_read(self):
        a = self._fp("pa", "s1.jsonl")
        first = _line(NOW - 60, "m1", "r1", 10) * 3
        self._append(a, first)
        self._result()
        got = self._count_reads()
        self._result()
        self.assertEqual(got, [])              # no change: file not even opened
        more = _line(NOW - 30, "m2", "r2", 20)
        self._append(a, more)
        self._result()
        self.assertEqual(sum(got), len(more))

    def test_replaced_inode_resets(self):
        a = self._fp("pa", "s1.jsonl")
        self._append(a, _line(NOW - 60, "m1", "r1", 10) + _line(NOW - 60, "m2", "r2", 20))
        self.assertEqual(self._result()[3], 30)
        tmp = a + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(_line(NOW - 60, "m9", "r9", 3) + _line(NOW - 60, "m8", "r8", 40) + _line(NOW - 60, "m7", "r7", 1))
        os.utime(tmp, (NOW, NOW))
        os.replace(tmp, a)                     # new inode, larger size
        self.assertEqual(self._result()[3], 44)
        self.assertEqual(self._result(), self._fresh())

    def test_lines_before_cut_excluded_as_window_moves(self):
        a = self._fp("pa", "s1.jsonl")
        self._append(a, _line(NOW - 3500, "m1", "r1", 10) + _line(NOW - 60, "m2", "r2", 20)
                     + _line(NOW - 4000, "m0", "r0", 999))
        self.assertEqual(self._result()[3], 30)
        later = NOW + 200                      # m1 now falls before the cut
        os.utime(a, (later, later))
        self.assertEqual(self._result(later)[3], 20)
        self.assertEqual(self._result(later), self._fresh(later))

    def test_file_leaving_window_dropped(self):
        a, b = self._fp("pa", "s1.jsonl"), self._fp("pb", "s2.jsonl")
        self._append(a, _line(NOW - 60, "m1", "r1", 10))
        self._append(b, _line(NOW - 60, "m2", "r2", 20))
        self._result()
        os.utime(b, (NOW - 7200, NOW - 7200))
        self.assertEqual(self._result()[3], 10)
        self.assertEqual(sorted(bs._burn_files), [a])

    def test_cross_file_duplicate_counted_once(self):
        a, b = self._fp("pa", "s1.jsonl"), self._fp("pb", "s2.jsonl")
        self._append(a, _line(NOW - 60, "m1", "r1", 10))
        self._append(b, _line(NOW - 60, "m1", "r1", 10) + _line(NOW - 60, "m2", "r2", 5))
        rows = self._result()[0]
        self.assertEqual(sum(r["req"] for r in rows), 2)
        self.assertEqual(self._result(), self._fresh())


if __name__ == "__main__":
    unittest.main()
