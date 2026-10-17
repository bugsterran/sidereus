"""Today-by-hour scan is incremental: appended bytes only, same totals as a fresh full scan.

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


class TodayIncremental(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.saved = {k: getattr(bs, k) for k in ("CLAUDE_PROJECTS", "_slug_name")}
        self.today = dict(bs._today)
        bs.CLAUDE_PROJECTS, bs._slug_name = self.d, (lambda s: s)
        bs._today_files.clear()
        bs._today_day[0] = 0

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(bs, k, v)
        bs.__dict__.pop("open", None)
        bs._today.clear()
        bs._today.update(self.today)
        bs._today_files.clear()
        bs._today_day[0] = 0
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
        bs._today_fetch(now)
        return [(r["name"], r["tok"], r["series"]) for r in bs._today["by"]], bs._today["h0"], bs._today["h1"]

    def _fresh(self, now=NOW):
        saved = dict(bs._today_files)
        bs._today_files.clear()
        try:
            return self._result(now)
        finally:
            bs._today_files.clear()
            bs._today_files.update(saved)

    def test_incremental_equals_full_over_three_passes(self):
        a, b = self._fp("pa", "s1.jsonl"), self._fp("pb", "s2.jsonl")
        self._append(a, _line(NOW - 7200, "m1", "r1", 10) + _line(NOW - 7200, "m1", "r1", 10))
        self._append(b, _line(NOW - 3600, "m2", "r2", 20) + _line(NOW - 50 * 3600, "m0", "r0", 999))
        r1 = self._result()
        self.assertEqual(r1, self._fresh())
        self._append(a, _line(NOW - 60, "m3", "r3", 5) + '{"bad": "usage"\n')
        self._append(b, _line(NOW - 60, "m1", "r1", 10))     # same response in another file: counted once
        r2 = self._result()
        self.assertEqual(r2, self._fresh())
        self._append(b, _line(NOW - 30, "m4", "r4", 7) + json.dumps({"timestamp": "x", "usage": 1}) + "\n")
        r3 = self._result()
        self.assertEqual(r3, self._fresh())
        self.assertEqual(sum(t for _n, t, _s in r3[0]), 11 + 21 + 6 + 8)

    def test_truncated_or_replaced_file_resets(self):
        a = self._fp("pa", "s1.jsonl")
        self._append(a, _line(NOW - 60, "m1", "r1", 10) + _line(NOW - 60, "m2", "r2", 20))
        self.assertEqual(self._result()[0][0][1], 32)
        with open(a, "w", encoding="utf-8") as f:
            f.write(_line(NOW - 60, "m9", "r9", 3))
        os.utime(a, (NOW, NOW))
        self.assertEqual(self._result()[0][0][1], 4)
        tmp = a + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(_line(NOW - 60, "m9", "r9", 3) + _line(NOW - 60, "m8", "r8", 40) + _line(NOW - 60, "m7", "r7", 1))
        os.utime(tmp, (NOW, NOW))
        os.replace(tmp, a)                     # new inode, larger size
        self.assertEqual(self._result()[0][0][1], 4 + 41 + 2)
        self.assertEqual(self._result(), self._fresh())

    def test_partial_trailing_line_counted_once(self):
        a = self._fp("pa", "s1.jsonl")
        whole = _line(NOW - 60, "m2", "r2", 20)
        self._append(a, _line(NOW - 60, "m1", "r1", 10) + whole[:25])
        self.assertEqual(self._result()[0][0][1], 11)
        self._append(a, whole[25:-1])          # complete JSON but no newline yet
        self.assertEqual(self._result()[0][0][1], 11)
        self._append(a, "\n")
        self.assertEqual(self._result()[0][0][1], 32)
        self.assertEqual(self._result()[0][0][1], 32)

    def test_no_change_reads_nothing(self):
        a = self._fp("pa", "s1.jsonl")
        self._append(a, _line(NOW - 60, "m1", "r1", 10))
        first = self._result()
        opened = []
        real_open = open

        def counting_open(*a, **k):
            opened.append(a[0])
            return real_open(*a, **k)
        bs.open = counting_open
        self.assertEqual(self._result(), first)
        self.assertEqual(opened, [])

    def test_day_rollover_and_dropped_files(self):
        a, b = self._fp("pa", "s1.jsonl"), self._fp("pb", "s2.jsonl")
        self._append(a, _line(NOW - 60, "m1", "r1", 10))
        self._append(b, _line(NOW - 60, "m2", "r2", 20))
        self._result()
        os.remove(b)
        self.assertEqual([n for n, _t, _s in self._result()[0]], ["pa"])
        self.assertEqual(sorted(bs._today_files), [a])
        nxt = NOW + 86400
        self._append(a, _line(nxt - 60, "m3", "r3", 5), now=nxt)
        self.assertEqual(self._result(nxt)[0][0][1], 6)     # yesterday's lines no longer count


if __name__ == "__main__":
    unittest.main()
