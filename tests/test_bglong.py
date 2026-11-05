"""Long-running background shells: `bgtasks.bg_long` reads launch times only (no stat, no output). No live files."""
import unittest
from unittest import mock

from tests._clock import NOW
from tests._load import sidereus

bt = sidereus("bgtasks")

FP = "/nonexistent/test-bglong/sess.jsonl"


class TestBgLong(unittest.TestCase):
    def setUp(self):
        self._boot = bt.boot_time
        bt.boot_time = lambda: NOW - 86400
        self.addCleanup(setattr, bt, "boot_time", self._boot)
        self.addCleanup(bt._bg_open.pop, FP, None)

    def put(self, rows):
        bt._bg_open[FP] = dict(rows)

    def test_31m_is_long_with_absolute_at(self):
        t = NOW - 31 * 60
        self.put({"a": ("bg", "npm run dev", t, "/p/a.output"), "b": ("bg", "x", NOW - 60)})
        r = bt.bg_long(FP, NOW)
        self.assertEqual(r, {"n": 2, "long": 1, "max": 31 * 60, "at": int(t), "last": int(t)})
        self.assertEqual(bt.bg_long(FP, NOW + 41)["at"], int(t))   # absolute: not drifting with now

    def test_29m_is_none(self):
        self.put({"a": ("bg", "x", NOW - 29 * 60)})
        self.assertIsNone(bt.bg_long(FP, NOW))

    def test_launch_before_boot_skipped(self):
        self.put({"a": ("bg", "x", NOW - 2 * 86400)})
        self.assertIsNone(bt.bg_long(FP, NOW))

    def test_non_bg_rows_ignored(self):
        self.put({"a": ("task", "watch", NOW - 3 * 3600), "b": ("sub", "agent", NOW - 3 * 3600)})
        self.assertIsNone(bt.bg_long(FP, NOW))

    def test_no_stat(self):
        self.put({"a": ("bg", "x", NOW - 40 * 60, "/p/a.output")})
        with mock.patch.object(bt.os, "stat", side_effect=AssertionError("stat")) as st:
            self.assertEqual(bt.bg_long(FP, NOW)["long"], 1)
        st.assert_not_called()

    def test_unknown_session_none(self):
        self.assertIsNone(bt.bg_long("/nonexistent/other.jsonl", NOW))

    def test_owned_by_bgtasks(self):
        att = sidereus("attention")
        self.assertEqual(bt.BG_LONG_S, 1800)
        self.assertIs(att.BG_LONG_S, bt.BG_LONG_S)


if __name__ == "__main__":
    unittest.main()
