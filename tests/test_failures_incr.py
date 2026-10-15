"""Incremental read of sidereus/failures_scan._fail_read: no line lost or double-counted across reads."""
import json
import os
import tempfile
import time
import unittest
from datetime import datetime

from tests._load import sidereus

S = sidereus("failures_scan")


def _line(i):
    body = ("<task-notification><tool-use-id>toolu_%d</tool-use-id><status>failed</status>"
            "<summary>boom %d</summary></task-notification>" % (i, i))
    return json.dumps({"type": "user", "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                       "cwd": "/w/repo", "message": {"role": "user", "content": body}}) + "\n"


class IncrementalReadTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.fp = os.path.join(self.d.name, "s.jsonl")
        self._ev, self._off = S._FAIL_EV, S._FAIL_OFF
        S._FAIL_EV, S._FAIL_OFF = {}, {}

    def tearDown(self):
        S._FAIL_EV, S._FAIL_OFF = self._ev, self._off
        self.d.cleanup()

    def _append(self, s):
        with open(self.fp, "a") as f:
            f.write(s)

    def test_appends_counted(self):
        n = 0
        for add, want in ((1, 1), (1, 2), (2, 4)):
            for _ in range(add):
                n += 1
                self._append(_line(n))
            self.assertEqual(len(S._fail_read(self.fp)), want)

    def test_line_split_across_reads_counted_once(self):
        self._append(_line(1))
        ln = _line(2)
        self._append(ln[:40])
        self.assertEqual(len(S._fail_read(self.fp)), 1)
        self._append(ln[40:])
        self.assertEqual(len(S._fail_read(self.fp)), 2)
        self.assertEqual(len(S._fail_read(self.fp)), 2)

    def test_mid_line_offset_drops_partial(self):
        self._append(_line(1) + _line(2))
        S._FAIL_OFF[self.fp] = 10          # mid-line: the first (partial) line must be skipped
        self.assertEqual(len(S._fail_read(self.fp)), 1)

    def test_prune_drops_missing_files(self):
        S._FAIL_EV["/nope/x.jsonl"] = [{}]
        S._FAIL_OFF["/nope/x.jsonl"] = 5
        self._append(_line(1))
        S._fail_read(self.fp)
        saved = S._FAIL_PRUNED[0]
        try:
            S._FAIL_PRUNED[0] = 0.0
            S._fail_prune(time.time())
        finally:
            S._FAIL_PRUNED[0] = saved
        self.assertNotIn("/nope/x.jsonl", S._FAIL_EV)
        self.assertNotIn("/nope/x.jsonl", S._FAIL_OFF)
        self.assertIn(self.fp, S._FAIL_EV)


if __name__ == "__main__":
    unittest.main()
