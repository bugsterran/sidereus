"""7d measured used tokens (`cur.wk_used_local` / `wk.used_local`) must not depend on the 5h cycle state.

A 5h window without a denominator (h5 0%, `head` None) or a just-ended 5h cycle («stale», no `cur`) used to drop
the measured 7d sum, so the status bar flipped to the per-1% estimate. Fixture-only: no live file, clock or network.
"""
import unittest

from tests.test_quota import NOW, H, _BurnFixture, b

WK = {"pct": 18.0, "leftSec": 28_567}
CYC = (490_000_000, 26_000_000.0, "cyc", NOW - 11 * H)     # used, per-%, src, observed reset


class WkUsedIndependentOf5h(_BurnFixture):

    IDLE = [(NOW - 600, 0.0), (NOW, 0.0)]     # fresh 5h window: no denominator -> head None

    def test_no_5h_head_keeps_measured_7d(self):
        out = self.run_burn(self.IDLE, wk=WK, qwk=CYC)
        self.assertTrue(out["ok"])
        self.assertIsNone(out["head"])
        self.assertEqual(out["cur"]["wk_used_local"], 490_000_000)
        self.assertEqual(out["wk"]["used_local"], 490_000_000)

    def test_stale_5h_body_still_carries_7d(self):
        out = self.run_burn(self.IDLE, reset=NOW - 10, wk=WK, qwk=CYC)
        self.assertEqual(out.get("why"), "stale")
        self.assertNotIn("cur", out)
        self.assertEqual(out["wk"]["used_local"], 490_000_000)

    def test_estimate_source_is_not_shown_as_measured(self):
        out = self.run_burn(self.IDLE, wk=WK, qwk=(468_000_000, 26_000_000.0, "step", None))
        self.assertIsNone(out["cur"]["wk_used_local"])
        self.assertNotIn("used_local", out["wk"])

    def test_wk_used_helper(self):
        self.assertEqual(b._qb_wk_used({"used": 5, "src": "cyc"}), 5)
        self.assertIsNone(b._qb_wk_used({"used": 5, "src": "week"}))
        self.assertIsNone(b._qb_wk_used(None))


if __name__ == "__main__":
    unittest.main()
