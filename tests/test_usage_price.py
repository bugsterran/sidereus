"""Model price lookup: provider/date wrappers resolve to the bare id, unknown ids stay unpriced."""
import unittest

from tests._load import sidereus, load

load()
U = sidereus("usage_index")


class UsagePrice(unittest.TestCase):
    def test_wrappers_resolve(self):
        for m in ("claude-haiku-4-5-20251001", "us.anthropic.claude-haiku-4-5-20251001-v1:0",
                  "anthropic.claude-haiku-4-5-v1:0", "claude-haiku-4-5@20251001", "claude-haiku-4-5[1m]",
                  "claude-haiku-4-5-latest"):
            self.assertEqual(U._price(m), (1.0, 5.0), m)

    def test_family_point_release_not_guessed(self):
        self.assertEqual(U._price("claude-opus-5-5")[:2], (4.0, 20.0))   # not opus-5's $5/$25
        self.assertEqual(U._price("claude-opus-5[1m]"), (5.0, 25.0))
        self.assertIsNone(U._price("claude-opus-5-9"))

    def test_older_ids_and_dated_forms(self):
        cases = {"claude-opus-4-20250514": (15.0, 75.0), "claude-opus-4-1-20250805": (15.0, 75.0),
                 "claude-opus-4-5-20251101": (5.0, 25.0), "claude-opus-4-6": (5.0, 25.0),
                 "claude-sonnet-4-5-20250929": (3.0, 15.0), "claude-sonnet-4-20250514": (3.0, 15.0),
                 "claude-3-5-haiku-20241022": (0.80, 4.0), "claude-3-5-haiku-latest": (0.80, 4.0)}
        for m, want in cases.items():
            self.assertEqual(U._price(m)[:2], want, m)
        self.assertAlmostEqual(U._cost4("claude-opus-4-20250514", [0, 0, 0, 1_000_000]), 1.5)
        self.assertAlmostEqual(U._cost4("claude-3-5-haiku-20241022", [0, 0, 0, 1_000_000]), 0.08)

    def test_cache_read_override(self):
        t = [0, 0, 0, 1_000_000]
        self.assertAlmostEqual(U._cost4("claude-opus-5-5", t), 0.20)
        self.assertAlmostEqual(U._cost4("claude-fable-5-1", t), 0.25)
        self.assertAlmostEqual(U._cost4("claude-fable-5", t), 1.0)
        self.assertAlmostEqual(U._cost4("claude-opus-5", [1_000_000, 1_000_000, 1_000_000, 0]), 5 + 25 + 6.25)

    def test_haiku_5_5_and_sonnet_5_5(self):
        # a bare key is the <=100k tier; `|long` keys carry the >100k rate (USAGE_TIER)
        self.assertAlmostEqual(U._cost4("claude-haiku-5-5", [1_000_000, 1_000_000, 1_000_000, 1_000_000]),
                               0.10 + 0.50 + 0.125 + 0.01)
        self.assertAlmostEqual(U._cost4("claude-haiku-5-5[1m]", [0, 0, 0, 1_000_000]), 0.01)
        self.assertAlmostEqual(U._cost4("claude-sonnet-5-5", [0, 0, 0, 1_000_000]), 0.10)
        orig = U.warn_once
        U.warn_once = lambda *a, **kw: None
        try:
            self.assertIsNone(U._price("claude-haiku-5"))
        finally:
            U.warn_once = orig

    def test_tier_threshold_is_strict(self):
        k = U._tier_key
        self.assertEqual(k("claude-haiku-5-5", [100_000, 5, 0, 0]), "claude-haiku-5-5")
        self.assertEqual(k("claude-haiku-5-5", [1, 9, 50_000, 50_000]), "claude-haiku-5-5|long")  # prompt 100_001
        self.assertEqual(k("claude-haiku-5-5[1m]", [0, 0, 0, 100_001]), "claude-haiku-5-5[1m]|long")
        self.assertEqual(k("claude-haiku-5-5-20261001", [100_001, 0, 0, 0]), "claude-haiku-5-5-20261001|long")
        for m in ("claude-opus-5-5", "claude-haiku-4-5", "claude-sonnet-5-5[1m]"):
            self.assertEqual(k(m, [900_000, 0, 0, 0]), m)

    def test_long_and_short_rates(self):
        t = [1_000_000, 1_000_000, 1_000_000, 1_000_000]
        self.assertAlmostEqual(U._cost4("claude-haiku-5-5|long", t), 0.50 + 2.50 + 0.625 + 0.05)
        self.assertAlmostEqual(U._cost4("claude-haiku-5-5[1m]|long", t), 0.50 + 2.50 + 0.625 + 0.05)
        self.assertAlmostEqual(U._cost4("claude-haiku-5-5", t), 0.10 + 0.50 + 0.125 + 0.01)

    def test_one_hour_cache_write_is_double_input(self):
        cc = [0, 0, 1_000_000, 0]
        self.assertAlmostEqual(U._cost4("claude-opus-5-5|1h", cc), 8.0)
        self.assertAlmostEqual(U._cost4("claude-opus-5-5", cc), 5.0)
        self.assertAlmostEqual(U._cost4("claude-haiku-5-5|long|1h", cc), 1.0)
        self.assertEqual(U._key_split("claude-haiku-5-5|long|1h"), ("claude-haiku-5-5", True, True))
        self.assertEqual(U._model_disp("claude-opus-5-5[1m]|1h"), "claude-opus-5-5[1m]")

    def test_request_rows_split_one_hour(self):
        u = {"input_tokens": 10, "output_tokens": 20, "cache_creation_input_tokens": 300,
             "cache_read_input_tokens": 4, "cache_creation": {"ephemeral_1h_input_tokens": 100}}
        self.assertEqual(U._req_rows("claude-opus-5-5", u),
                         [("claude-opus-5-5", [10, 20, 200, 4]), ("claude-opus-5-5|1h", [0, 0, 100, 0])])
        tok, usd = U._req_cost("claude-opus-5-5", u)
        self.assertEqual(tok, 334)
        self.assertAlmostEqual(usd, (10 * 4 + 20 * 20 + 200 * 5 + 4 * 0.2 + 100 * 8) / 1e6)
        u.pop("cache_creation")
        self.assertEqual(U._req_rows("claude-opus-5-5", u), [("claude-opus-5-5", [10, 20, 300, 4])])
        # total missing: rebuilt from the split, and the rebuilt prompt picks the long tier
        u2 = {"input_tokens": 1, "cache_creation": {"ephemeral_5m_input_tokens": 40_000,
                                                    "ephemeral_1h_input_tokens": 60_000}}
        self.assertEqual(U._req_rows("claude-haiku-5-5", u2),
                         [("claude-haiku-5-5|long", [1, 0, 40_000, 0]), ("claude-haiku-5-5|long|1h", [0, 0, 60_000, 0])])

    def test_unknown_warns(self):
        seen = []
        orig = U.warn_once
        U.warn_once = lambda k, *a, **kw: seen.append(k)
        try:
            self.assertIsNone(U._price("gpt-x"))
            self.assertIsNone(U._price("<synthetic>"))
            self.assertIsNone(U._price("gpt-y|long|1h"))
        finally:
            U.warn_once = orig
        self.assertEqual(seen, ["price:gpt-x", "price:gpt-y"])


if __name__ == "__main__":
    unittest.main()
