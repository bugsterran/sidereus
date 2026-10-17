"""Persisted 5-min OTel bySrc buckets (sidereus/otel.py `_otel_src*`).

The file path is swapped to a temp dir and module state is swapped per test — no live file, clock or network.
"""
import json
import os
import shutil
import tempfile
import unittest

from tests import _load

o = _load.sidereus("otel")

T0 = 1_800_000_000 // 3600 * 3600      # an on-the-hour epoch


class SrcPersistCase(unittest.TestCase):
    def setUp(self):
        self.saved = (o._otel_src, o._otel_src_meta, o.OTEL_SRC_FILE, o.OTEL_SRC_CAP)
        self.tmp = tempfile.mkdtemp()
        o.OTEL_SRC_FILE = os.path.join(self.tmp, "otel-bysrc.json")
        self._reset()

    def tearDown(self):
        (o._otel_src, o._otel_src_meta, o.OTEL_SRC_FILE, o.OTEL_SRC_CAP) = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _reset(self):
        # simulates a restart: empty memory, not yet loaded
        o._otel_src = {}
        o._otel_src_meta = {"loaded": False, "savedAt": 0.0, "dirty": False}

    def _add(self, ts, key, tok):
        with o._otel_lock:
            o._otel_src_add(ts, key, tok)

    def test_bucket_roll(self):
        self._add(T0 + 10, "m|repl_main_thread", 100)
        self._add(T0 + 299, "m|repl_main_thread", 50)
        self._add(T0 + 300, "m|repl_main_thread", 7)
        self.assertEqual(sorted(o._otel_src), [T0, T0 + 300])
        self.assertEqual(o._otel_src[T0]["m|repl_main_thread"], [2, 150])
        self.assertEqual(o._otel_src[T0 + 300]["m|repl_main_thread"], [1, 7])

    def test_cap_other_is_per_bucket(self):
        o.OTEL_SRC_CAP = 2
        for i in range(4):
            self._add(T0, "m%d|s" % i, 1)
        self._add(T0 + 300, "m3|s", 1)          # a fresh bucket has room again
        self.assertEqual(set(o._otel_src[T0]), {"m0|s", "m1|s", "other"})
        self.assertEqual(o._otel_src[T0]["other"], [2, 2])
        self.assertEqual(set(o._otel_src[T0 + 300]), {"m3|s"})

    def test_expiry_on_save(self):
        now = T0 + 9 * 86400
        self._add(T0, "m|a", 1)                  # 9 days old — dropped
        self._add(now - 3600, "m|a", 2)
        self.assertTrue(o._otel_src_save(now=now))
        self.assertEqual(list(o._otel_src), [int((now - 3600) // 300 * 300)])

    def test_save_throttled_and_only_when_dirty(self):
        self._add(T0, "m|a", 1)
        self.assertTrue(o._otel_src_save(now=T0 + 100))
        self._add(T0, "m|a", 1)
        self.assertFalse(o._otel_src_save(now=T0 + 130))    # < 60s since last write
        self.assertTrue(o._otel_src_save(now=T0 + 170))
        self.assertFalse(o._otel_src_save(now=T0 + 400))    # nothing changed

    def test_load_after_restart_merges(self):
        now = T0 + 3600
        self._add(T0, "m|a", 10)
        o._otel_src_save(now=now, force=True)
        with open(o.OTEL_SRC_FILE, encoding="utf-8") as f:
            self.assertIn(str(T0), json.load(f)["b"])
        self._reset()
        self._add(T0 + 5, "m|a", 1)              # ingested before the first load
        o._otel_src_load()                       # T0 is in the future, so the 8-day cut keeps it
        self.assertEqual(o._otel_src[T0]["m|a"], [2, 11])

    def test_load_corrupt_file_is_quiet(self):
        with open(o.OTEL_SRC_FILE, "w", encoding="utf-8") as f:
            f.write("{not json")
        o._otel_src_load()
        self.assertEqual(o._otel_src, {})
        self.assertTrue(o._otel_src_meta["loaded"])

    def test_window_sum(self):
        now = T0 + 5 * 3600
        self._add(now - 6 * 3600, "m|a", 1000)   # outside 5h
        self._add(now - 3600, "m|a", 10)
        self._add(now - 60, "m|b", 5)
        w = o._otel_src_win(5, now=now)
        self.assertEqual(w["rows"], {"m|a": [1, 10], "m|b": [1, 5]})
        self.assertEqual(w["total"], 15)
        self.assertEqual(w["since"], now - 6 * 3600)
        self.assertEqual(o._otel_src_win(8, now=now)["total"], 1015)

    def test_cmp_kinds_and_coverage(self):
        now = T0 + 6 * 3600 + 1800
        self._add(T0 + 60, "m|repl_main_thread", 100)       # before the full-hour window start (T0+1h)
        self._add(T0 + 3600 + 60, "m|repl_main_thread", 120)
        self._add(T0 + 3600 + 90, "m|agent:custom", 30)
        self._add(T0 + 3600 + 90, "m|agent_summary", 10)
        hours = {T0: {"m": [100, 0, 0, 0]}, T0 + 3600: {"m": [50, 20, 30, 0]}}
        c = o._otel_src_cmp(5, now=now, hours=hours)
        self.assertEqual(c["from"], T0 + 3600)
        self.assertTrue(c["covered"])
        self.assertEqual(c["otelTotal"], 160)
        self.assertEqual(c["transcriptTotal"], 100)
        self.assertEqual(c["byKind"], {"main": 120, "agent": 30, "side": 10, "nonMain": 40})
        self.assertEqual(c["ratio"], 1.6)
        # OTel history shorter than 8h ⇒ window starts at its first full hour and is flagged uncovered
        c2 = o._otel_src_cmp(8, now=now, hours=hours)
        self.assertEqual(c2["from"], T0)
        self.assertFalse(c2["covered"])
        self.assertEqual((c2["otelTotal"], c2["transcriptTotal"]), (260, 200))


if __name__ == "__main__":
    unittest.main()
