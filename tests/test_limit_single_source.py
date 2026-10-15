"""5h limit has one source (burn back-solve): usage() and the burn scan never divide by the 519M anchor.

★2026-09-27 cross-tab audit. No live files: module attributes are patched, the clock is fixed.
"""
import unittest

from tests import _load

u = _load.sidereus("usage")
bs = _load.sidereus("burn_scan")


class UsageNo5hDenominator(unittest.TestCase):
    def setUp(self):
        self.saved = {k: getattr(u, k) for k in ("_anchors", "_usage")}
        u._anchors = lambda: {"blockLimitTokens": 519_164_200}
        u._usage = {"blocks": {"totalTokens": 40_000_000, "costUSD": 1.0,
                               "startTime": None, "endTime": None},
                    "week": None, "blockMax": 617_242_503, "weekMax": 0,
                    "at": 1_800_000_000.0, "live": []}

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(u, k, v)

    def test_block_has_tokens_but_no_anchor_pct(self):
        b = u.usage()["block"]
        self.assertEqual(b["tokens"], 40_000_000)
        for k in ("max", "pct", "src"):
            self.assertNotIn(k, b)


class BurnScanNoLimit(unittest.TestCase):
    def test_source_has_no_anchor_limit(self):
        import inspect
        src = inspect.getsource(bs._burn_fetch)
        self.assertNotIn("blockLimitTokens", src)
        self.assertFalse(hasattr(bs, "_anchors"))


class CalibrateNeverWritesAnchor(unittest.TestCase):
    # ⚠usage-anchor.json is hand-maintained; a revived _quota_calibrate would overwrite blockLimitTokens.
    def test_fresh_quota_writes_nothing(self):
        ql = _load.sidereus("quota_loop")
        names = ("quota", "usage", "_anchors", "_atomic_write")
        saved = {k: getattr(ql, k) for k in names}
        writes = []
        try:
            ql.quota = lambda: {"age": 0, "five_hour": {"pct": 50}, "seven_day": {"pct": 50}}
            ql.usage = lambda: {"block": {"tokens": 350_000_000}, "week": {"tokens": 400_000_000}}
            ql._anchors = lambda: {"blockLimitTokens": 519_164_200}
            ql._atomic_write = lambda *a, **k: writes.append(a)
            ql._quota_calibrate()
        finally:
            for k, v in saved.items():
                setattr(ql, k, v)
        self.assertEqual(writes, [])


if __name__ == "__main__":
    unittest.main()
