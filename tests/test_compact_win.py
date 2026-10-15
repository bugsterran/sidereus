"""Compaction-window labels: `since` moves only when `autoCompactWindow` changes, not on unrelated edits."""
import json
import os
import tempfile
import unittest

from tests._load import sidereus

bu = sidereus("burn_scan")  # _compact_win and its paths live there (burn_usage split 2026-09-25)


class CompactWinTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.stg = os.path.join(self.d, "settings.json")
        self.state = os.path.join(self.d, "compact-win.json")
        self._orig = (bu.CLAUDE_SETTINGS, bu.COMPACT_STATE)
        bu.CLAUDE_SETTINGS, bu.COMPACT_STATE = self.stg, self.state

    def tearDown(self):
        bu.CLAUDE_SETTINGS, bu.COMPACT_STATE = self._orig

    def write(self, d, mtime):
        with open(self.stg, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.utime(self.stg, (mtime, mtime))

    def test_seed_from_mtime(self):
        self.write({"autoCompactWindow": 450000}, 1000)
        cw = bu._compact_win(now=5000)
        self.assertEqual((cw["value"], cw["since"], cw["prev"], cw["approx"]), (450000, 1000, None, True))

    def test_unrelated_edit_keeps_since(self):
        self.write({"autoCompactWindow": 450000}, 1000)
        bu._compact_win(now=5000)
        self.write({"autoCompactWindow": 450000, "hooks": {"Stop": []}}, 9000)
        self.assertEqual(bu._compact_win(now=9500)["since"], 1000)

    def test_value_change_moves_since(self):
        self.write({"autoCompactWindow": 200000}, 1000)
        bu._compact_win(now=5000)
        self.write({"autoCompactWindow": 450000}, 9000)
        cw = bu._compact_win(now=9500)
        self.assertEqual((cw["value"], cw["since"], cw["prev"], cw["approx"]), (450000, 9500, 200000, False))

    def test_default_and_unreadable(self):
        self.write({"env": {}}, 1000)
        self.assertEqual(bu._compact_win(now=5000)["value"], 1_000_000)
        with open(self.stg, "w") as f:
            f.write("{half")
        self.assertEqual(bu._compact_win(now=6000)["value"], 1_000_000)   # half-written file: keep state

    def test_session_labels(self):
        cw = {"value": 450000, "since": 1000, "prev": 200000}
        self.assertEqual(bu._sess_win(1500, cw), 450000)
        self.assertEqual(bu._sess_win(500, cw), 200000)
        self.assertIsNone(bu._sess_win(500, dict(cw, prev=None)))


if __name__ == "__main__":
    unittest.main()
