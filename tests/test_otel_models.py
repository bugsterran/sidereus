"""R1/R2 «Models»: sidereus/otel.py `_otel_src_models` folds bysrc buckets per model with a main/agent/side split.

`_otel_src` is swapped per test; no file, clock or network is used (`now` is passed in).
"""
import json
import time
import unittest

from tests import _load

o = _load.sidereus("otel")


def _ts(d, h, m=0):
    return int(time.mktime(time.strptime("%s %02d:%02d" % (d, h, m), "%Y-%m-%d %H:%M")))


B = _ts("2026-10-12", 14)
START = _ts("2026-10-12", 0)
NOW = _ts("2026-10-14", 20)


class ModelsCase(unittest.TestCase):
    def setUp(self):
        self.saved = o._otel_src
        o._otel_src = {}

    def tearDown(self):
        o._otel_src = self.saved

    def test_r1_fold_by_model_sorted_by_tokens(self):
        o._otel_src = {B: {"claude-opus-5-5|repl_main_thread": [2, 100], "claude-haiku-4-5|agent:x": [5, 300]},
                       B + 300: {"claude-opus-5-5|agent:y": [1, 50], "claude-opus-5-5|compact": [1, 10]}}
        r = o._otel_src_models(START, NOW)
        self.assertEqual([x["model"] for x in r["rows"]], ["claude-haiku-4-5", "claude-opus-5-5"])
        op = r["rows"][1]
        self.assertEqual((op["count"], op["tokens"]), (4, 160))
        self.assertEqual(r["n"], 9)
        self.assertEqual(r["from"], START)

    def test_r2_kind_split(self):
        o._otel_src = {B: {"m|repl_main_thread": [2, 100], "m|agent:a": [1, 20], "m|agent:b": [1, 30], "m|prompt_suggestion": [3, 7]}}
        k = o._otel_src_models(START, NOW)["rows"][0]["kinds"]
        self.assertEqual(k, {"main": [2, 100], "agent": [2, 50], "side": [3, 7]})

    def test_r1_pre_start_and_future_excluded(self):
        old = _ts("2026-10-08", 10)
        o._otel_src = {old: {"m|repl_main_thread": [5, 50]}, B: {"m|repl_main_thread": [1, 1]},
                       NOW + 600: {"m|repl_main_thread": [9, 9]}}
        r = o._otel_src_models(START, NOW)
        self.assertEqual(r["n"], 1)
        self.assertEqual(r["since"], old)

    def test_other_overflow_is_one_row(self):
        o._otel_src = {B: {"other": [3, 30]}, B + 300: {"other": [1, 5]}}
        r = o._otel_src_models(START, NOW)
        self.assertEqual(len(r["rows"]), 1)
        self.assertEqual(r["rows"][0]["model"], "other")
        self.assertEqual((r["rows"][0]["count"], r["rows"][0]["tokens"]), (4, 35))

    def test_r3_empty(self):
        r = o._otel_src_models(START, NOW)
        self.assertEqual(r["n"], 0)
        self.assertEqual(r["rows"], [])
        self.assertIsNone(r["since"])

    def test_metadata_only_no_query_source_strings(self):
        o._otel_src = {B: {"claude-opus|agent:secret-agent": [1, 2], "claude-opus|repl_main_thread": [1, 2],
                           "claude-opus|sidequest": [1, 2]}}
        s = json.dumps(o._otel_src_models(START, NOW))
        for w in ("secret", "agent:", "repl_main_thread", "sidequest", "|"):
            self.assertNotIn(w, s)


if __name__ == "__main__":
    unittest.main()
