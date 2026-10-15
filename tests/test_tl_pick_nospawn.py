"""Burn path (`_tok_events` -> `_tl_pick`) never calls sessions() — snapshot or nothing (2026-09-29).

All sources monkeypatched: sessions, snapshots, projects dir, segment scan — no live files or clock.
"""
import unittest

from tests._load import sidereus

tl = sidereus("timeline")


class TlPickNoSpawn(unittest.TestCase):
    def setUp(self):
        self.saved = []
        self.set("CLAUDE_PROJECTS", "/nonexistent-sidereus-test")
        self.set("_TOKEV", {})

    def set(self, name, val):
        self.saved.append((name, getattr(tl, name)))
        setattr(tl, name, val)

    def tearDown(self):
        for name, val in reversed(self.saved):
            setattr(tl, name, val)

    def test_snapshot_present(self):
        seen = []
        self.set("sessions_cached", lambda **k: seen.append(k) or ([{"cwd": "/x/p", "project": "p"}], True))
        self.assertEqual(tl._tok_events(1000.0), [])
        self.assertEqual(seen, [{"wait": 0.5, "max_age": tl.TL_SNAP_S}])

    def test_snapshot_missing(self):
        self.set("sessions_cached", lambda **k: ([], False))
        self.assertEqual(tl._tok_events(2000.0), [])
        self.assertEqual(tl._tl_pick(2000.0), [])
        self.assertEqual(tl._tl_snap_rows(), ([], False))


if __name__ == "__main__":
    unittest.main()
