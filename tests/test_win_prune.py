"""Window-learning memory: `_win_prune` drops gone/old transcripts from _win_seen/_win_scanned, keeps recent ones."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

L = sidereus("live_win")
NOW = 1_790_000_000


class WinPrune(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d)

    def mk(self, name, age_days):
        p = os.path.join(self.d, name)
        open(p, "w").close()
        t = NOW - age_days * 86400
        os.utime(p, (t, t))
        return p

    def test_prune(self):
        fresh, old = self.mk("fresh.jsonl", 1), self.mk("old.jsonl", L.CLAUDE_SCAN_DAYS + 1)
        gone = os.path.join(self.d, "gone.jsonl")
        seen = {fresh: 1_000_000, old: 1_000_000, gone: 200_000}
        scanned = {fresh: 1.0, old: 2.0, gone: 3.0}
        ev = {"m": {1_000_000: {fresh, old, gone}}}
        with mock.patch.object(L, "_win_seen", seen), mock.patch.object(L, "_win_scanned", scanned), \
                mock.patch.object(L, "_win_ev", ev):
            self.assertEqual(L._win_prune(NOW), 2)
            self.assertEqual(seen, {fresh: 1_000_000})
            self.assertEqual(scanned, {fresh: 1.0})
            self.assertEqual(len(ev["m"][1_000_000]), 3)        # model votes untouched
            self.assertEqual(L._ctx_window("m", 10, fresh), (1_000_000, "obs"))
            self.assertEqual(L._win_prune(NOW), 0)


if __name__ == "__main__":
    unittest.main()
