"""Uncertainty of the back-computed quota denominator (`qb_unc`, `_qb_unc_ests`) — pure functions, no live data."""
import unittest

from tests._load import sidereus

bu = sidereus("burn")


class QbUnc(unittest.TestCase):
    NOISY = [3.0, 3.3, 2.8, 3.2, 2.9, 3.1, 3.0, 3.2]

    def test_few_samples_large_many_small(self):
        few, n_few = bu.qb_unc(self.NOISY[:3], 60.0)
        many, n_many = bu.qb_unc(self.NOISY, 60.0)
        self.assertEqual((n_few, n_many), (3, 8))
        self.assertGreater(few, many)
        self.assertGreater(few, 0.3)
        self.assertLess(many, 0.2)

    def test_single_sample_is_unmeasurable(self):
        self.assertEqual(bu.qb_unc([3.0], 60.0), (1.0, 1))

    def test_rounding_floor_at_low_pct(self):
        u, _ = bu.qb_unc([3.0] * 8, 4.0)             # identical samples: spread 0, rounding 0.5/4
        self.assertAlmostEqual(u, 0.125)
        u, _ = bu.qb_unc([3.0] * 8, 50.0)
        self.assertAlmostEqual(u, 0.01)

    def test_rounding_only_and_missing_pct(self):
        self.assertEqual(bu.qb_unc(None, 10.0), (0.05, 0))
        self.assertEqual(bu.qb_unc([3.0, 3.1], 0), (None, 0))
        self.assertEqual(bu.qb_unc([3.0, 3.1], None), (None, 0))

    def test_only_recent_samples_count(self):
        # a wild early sample falls out of the last QB_UNC_N window
        u, n = bu.qb_unc([0.5] + [3.0] * bu.QB_UNC_N, 60.0)
        self.assertEqual(n, bu.QB_UNC_N)
        self.assertAlmostEqual(u, 0.5 / 60.0)

    def test_ests_from_change_points(self):
        rows = [(100, 2.0), (200, 4.0), (300, 4.0), (400, 5.0), (500, 10.0)]
        ev = [(50, 10), (150, 10), (250, 10), (350, 10), (450, 10)]
        # 2% skipped (< QB_UNC_MIN_PCT), repeated 4% skipped, events before start ignored
        self.assertEqual(bu._qb_unc_ests(rows, 100, ev), [10 / 4.0, 30 / 5.0, 40 / 10.0])


if __name__ == "__main__":
    unittest.main()
