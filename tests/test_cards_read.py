"""mark_cards_read concurrency: overlapping read-modify-write must not lose keys (temp files only)."""
import os
import shutil
import tempfile
import threading
import unittest
from unittest import mock

from tests._load import sidereus

cards = sidereus("cards")


class MarkCardReadTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.p = [mock.patch.object(cards, "READ_IDS", os.path.join(self.d, "ids.txt")),
                  mock.patch.object(cards, "READ_MARK", os.path.join(self.d, "mark.txt"))]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        shutil.rmtree(self.d, ignore_errors=True)

    def test_concurrent_marks_keep_both(self):
        real = cards.cards_read_ids
        gate = threading.Barrier(2, timeout=0.3)

        def slow_read():
            out = real()
            try:
                gate.wait()          # without the lock both threads read the same snapshot here
            except threading.BrokenBarrierError:
                pass
            return out

        with mock.patch.object(cards, "cards_read_ids", slow_read):
            ts = [threading.Thread(target=cards.mark_cards_read, args=([k],))
                  for k in ("2026-09-24T10:00:00|done|a", "2026-09-24T10:00:01|done|b")]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
        self.assertEqual(sorted(cards.cards_read_ids()),
                         ["2026-09-24T10:00:00|done|a", "2026-09-24T10:00:01|done|b"])
        with open(cards.READ_IDS, "rb") as f:
            self.assertTrue(f.read().endswith(b"\n"))


if __name__ == "__main__":
    unittest.main()
