"""Per-account tokens per 1% from history (sidereus/burn_hist.py). Fixtures only — no live file, clock, thread or network."""
import unittest

from tests import _load

h = _load.sidereus("burn_hist")

W = 5 * 3600.0
R1, R2, R3, R4 = 100 * W, 101 * W, 102 * W, 103 * W   # closed window ends (resets)
NOW = R4 - 600                                          # R4's window is still open


def full_window(reset, tok_per_pct, top=100.0):
    """Rows for one window rising to `top`, and events spending `tok_per_pct` per 1% up to the first >= 99 row."""
    start = reset - W
    rows = [(start + 600 * i, min(top, 25.0 * i), reset) for i in range(1, 6)]   # 25, 50, 75, 100, 100
    end = next(t for t, p, _r in rows if p >= 99)
    ev = [(start + 60, tok_per_pct * top / 2), (end - 60, tok_per_pct * top / 2)]
    return rows, ev


class PerPct5h(unittest.TestCase):
    def test_median_of_full_windows_excludes_open_one(self):
        rows, ev = [], []
        for r, k in ((R1, 1e6), (R2, 2e6), (R3, 4e6), (R4, 100e6)):   # R4 is open: must not count
            a, b = full_window(r, k)
            rows += a
            ev += b
        per, n, src = h.h5_per_pct(rows, h.tok_counter(sorted(ev)), NOW)
        self.assertEqual((per, n, src), (2e6, 3, "med"))

    def test_pooled_fallback_under_three_windows(self):
        rows = [(R1 - W + 600, 10.0, R1), (R1 - W + 1200, 30.0, R1), (R1 - W + 9000, 50.0, R1)]   # 2nd gap > 30 min
        ev = [(R1 - W + 900, 4e6), (R1 - W + 5000, 99e6)]
        per, n, src = h.h5_per_pct(rows, h.tok_counter(ev), NOW)
        self.assertEqual((per, n, src), (2e5, 1, "pool"))   # 4M / 20 pts; the long gap is skipped

    def test_unknown_without_rises(self):
        self.assertEqual(h.h5_per_pct([], h.tok_counter([]), NOW), (None, 0, None))


class PerPct7d(unittest.TestCase):
    def test_pooled_same_account_rises_only(self):
        rows = [(0, 10.0, "A"), (600, 12.0, "A"), (1200, 12.0, "B"), (1800, 13.0, "A"), (2400, 14.0, "A"),
                (6000, 20.0, "A"), (6600, 19.0, "A"), (7200, 20.0, "A")]
        ev = [(300, 6e6), (900, 50e6), (2100, 3e6), (4000, 70e6), (6900, 3e6)]
        per, n = h.wk_per_pct(rows, "A", h.tok_counter(ev))
        # counted: 0->600 (6M, +2), 1800->2400 (3M, +1), 6600->7200 (3M, +1); B rows, the 3600 s gap and the drop are not
        self.assertEqual((per, n), (3e6, 4))

    def test_too_few_points(self):
        self.assertEqual(h.wk_per_pct([(0, 1.0, "A"), (60, 2.0, "A")], "A", h.tok_counter([(30, 5)])), (None, 1))


class Compute(unittest.TestCase):
    def test_per_account_table(self):
        log = [{"t": 0, "h5": 10, "d7": 1, "reset5": "1970-01-01T05:00:00Z", "acct": "A"},
               {"t": 600, "h5": 20, "d7": 4, "reset5": "1970-01-01T05:00:00Z", "acct": "A"}]
        out = h.hist_compute(log, [(300, 9e6)], 10 * W)
        self.assertEqual(out["A"], {"h5_per_pct": 900000, "h5_n": 1, "h5_src": "pool", "wk_per_pct": 3000000, "wk_n": 3})
        tagged = h.hist_compute([dict(r, plan="pro") for r in log], [(300, 9e6)], 10 * W)
        self.assertEqual(list(tagged), ["A|pro"])               # plan-tagged rows group under acct|plan


class Est(unittest.TestCase):
    def setUp(self):
        self.saved = dict(h._hist)
        self.starts = []
        self.orig = (h._hist_load, h._hist_start, h._plan_code)
        h._hist_load, h._hist_start = (lambda: None), (lambda: self.starts.append(1))
        h._plan_code = lambda: None                          # never read the live ~/.claude.json
        h._hist.update({"at": 0.0, "acct": {}, "busy": False, "loaded": False})

    def tearDown(self):
        h._hist_load, h._hist_start, h._plan_code = self.orig
        h._hist.clear()
        h._hist.update(self.saved)

    def test_cold_is_null_and_kicks_one_pass(self):
        out = {"ok": True, "cur": {"now_pct": 40.0}, "wk": {"now_pct": 20.0}}
        self.assertIsNone(h.burn_est(out, "A-uuid", now=NOW))
        self.assertIsNone(h.burn_est(out, "A-uuid", now=NOW))
        self.assertEqual(self.starts, [1])                   # busy: no second pass
        self.assertIsNone(h.burn_est(out, None, now=NOW))    # unknown account: nothing

    def test_left_and_used_from_history(self):
        h._hist.update({"at": NOW, "loaded": True, "acct": {"A-uuid": {
            "h5_per_pct": 600000, "h5_n": 6, "h5_src": "med", "wk_per_pct": 3000000, "wk_n": 160}}})
        e = h.burn_est({"ok": True, "cur": {"now_pct": 40.0}, "wk": {"now_pct": 20.0}}, "A-uuid", now=NOW + 60)
        self.assertEqual((e["acct"], e["h5_left"], e["wk_left"], e["wk_used"]), ("A-uuid"[:8], 36000000, 240000000, 60000000))
        self.assertEqual(self.starts, [])                    # fresh table: no pass
        e = h.burn_est({"ok": False, "why": "stale"}, "A-uuid", now=NOW + 60)
        self.assertEqual((e["h5_left"], e["wk_left"]), (None, None))


class MissingQuotaLog(unittest.TestCase):
    def test_missing_log_is_empty_not_error(self):
        import os
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(h, "QUOTA_LOG", os.path.join(d, "quota-log.jsonl")):
            self.assertEqual(h._log_rows(), [])


if __name__ == "__main__":
    unittest.main()
