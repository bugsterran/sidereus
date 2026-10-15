"""Per-day / per-session OTel cache split (sidereus/otel_cache.py) and its feed from otel api_request (R2, R3, R4).

File path and module state are swapped per test; timestamps are fixed — no live file, clock or network.
"""
import json
import os
import shutil
import tempfile
import time
import unittest

from tests import _load

c = _load.sidereus("otel_cache")
o = _load.sidereus("otel")


def _ts(d, h=12):
    return time.mktime(time.strptime("%s %02d" % (d, h), "%Y-%m-%d %H"))


class CacheStoreCase(unittest.TestCase):
    def setUp(self):
        self.saved = (c._oc, c._oc_meta, c.OC_FILE, c.OC_SESS_CAP, c.OC_MIN_TOK)
        self.tmp = tempfile.mkdtemp()
        c.OC_FILE = os.path.join(self.tmp, "otel-cache.json")
        self._reset()

    def tearDown(self):
        (c._oc, c._oc_meta, c.OC_FILE, c.OC_SESS_CAP, c.OC_MIN_TOK) = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _reset(self):
        c._oc = {}
        c._oc_meta = {"loaded": False, "savedAt": 0.0, "dirty": False}

    def test_r2_split_per_day_and_session(self):
        c._oc_add(_ts("2026-10-01", 1), "s1", 100, 10)
        c._oc_add(_ts("2026-10-01", 23), "s1", 50, 5)
        c._oc_add(_ts("2026-10-01", 9), "s2", "7", None)
        c._oc_add(_ts("2026-10-02", 0), "s1", 1, 2)
        d1 = c._oc["2026-10-01"]
        self.assertEqual(d1["t"], [157, 15])
        self.assertEqual(d1["s"], {"s1": [150, 15], "s2": [7, 0]})
        self.assertEqual(c._oc["2026-10-02"]["t"], [1, 2])

    def test_r2_zero_event_not_stored(self):
        c._oc_add(_ts("2026-10-01"), "s1", 0, None)
        self.assertEqual(c._oc, {})

    def test_r2_session_cap_merges_into_other(self):
        c.OC_SESS_CAP = 2
        for s in ("a", "b", "x", "y"):
            c._oc_add(_ts("2026-10-01"), s, 1, 1)
        self.assertEqual(set(c._oc["2026-10-01"]["s"]), {"a", "b", "기타"})

    def test_r2_save_load_round_trip_is_additive(self):
        c._oc_add(_ts("2026-10-01"), "s1", 100, 10)
        self.assertTrue(c._oc_save(now=_ts("2026-10-01", 13)))
        with open(c.OC_FILE, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["d"]["2026-10-01"], {"t": [100, 10], "s": {"s1": [100, 10]}})
        self._reset()
        c._oc_add(_ts("2026-10-01"), "s1", 1, 1)   # ingested after restart, before the load
        c._oc_load()
        c._oc_load()                                # second load does not double-count
        self.assertEqual(c._oc["2026-10-01"]["s"]["s1"], [101, 11])

    def test_r2_save_throttled_and_only_when_dirty(self):
        now = _ts("2026-10-01", 13)
        c._oc_add(_ts("2026-10-01"), "s1", 1, 1)
        self.assertTrue(c._oc_save(now=now))
        c._oc_add(_ts("2026-10-01"), "s1", 1, 1)
        self.assertFalse(c._oc_save(now=now + 10))
        self.assertTrue(c._oc_save(now=now + 61))
        self.assertFalse(c._oc_save(now=now + 200))

    def test_r2_prune_older_than_31_days(self):
        c._oc_add(_ts("2026-08-20"), "s1", 1, 1)
        c._oc_add(_ts("2026-09-20"), "s1", 1, 1)
        self.assertTrue(c._oc_save(now=_ts("2026-10-05")))
        self.assertEqual(list(c._oc), ["2026-09-20"])

    def test_r3_view_days_and_top_sessions_by_create_share(self):
        c.OC_MIN_TOK = 100
        c._oc_add(_ts("2026-09-01"), "old", 0, 999)       # before since — excluded
        c._oc_add(_ts("2026-10-01"), "s1", 90, 10)        # 10%
        c._oc_add(_ts("2026-10-02"), "s2", 50, 50)        # 50%
        c._oc_add(_ts("2026-10-02"), "tiny", 1, 9)        # under OC_MIN_TOK
        v = c._oc_view("2026-10-01")
        self.assertEqual(v["days"], [{"d": "2026-10-01", "read": 90, "create": 10, "pct": 10},
                                     {"d": "2026-10-02", "read": 51, "create": 59, "pct": 54}])
        self.assertEqual([s["sid"] for s in v["sessions"]], ["s2", "s1"])
        self.assertEqual(v["sessions"][0], {"sid": "s2", "read": 50, "create": 50, "pct": 50})

    def test_r4_empty_store(self):
        self.assertEqual(c._oc_view("2026-10-01"), {"days": [], "sessions": []})


def _rec(rid, cr, cc):
    at = {"event.name": "api_request", "session.id": "s1", "request_id": rid, "model": "m",
          "input_tokens": 1, "cache_read_tokens": cr, "cache_creation_tokens": cc, "output_tokens": 1000}
    return {"attributes": [{"key": k, "value": ({"intValue": v} if isinstance(v, int) else {"stringValue": v})}
                           for k, v in at.items()]}


class IngestFeedCase(unittest.TestCase):
    def setUp(self):
        self.saved = (o._otel, o._otel_stat, o._otel_req, o._otel_sample, o._usage_add, o._otel_src_add, o._oc_add)
        o._otel, o._otel_req, o._otel_sample = {}, o.BoundedMemo(4000), {}
        o._otel_stat = {"posts": 0, "recs": 0, "kept": 0, "dropName": 0, "dropSeq": 0, "dropSid": 0,
                        "acct": 0, "dupReq": 0, "reSeq": 0, "names": {}, "lastPost": 0, "lastKept": 0}
        self.usage, self.src, self.oc = [], [], []
        o._usage_add = lambda ts, tok, cost, sid="": self.usage.append(tok)
        o._otel_src_add = lambda ts, key, tok: self.src.append(tok)
        o._oc_add = lambda ts, sid, r, cc: self.oc.append((sid, r, cc))

    def tearDown(self):
        (o._otel, o._otel_stat, o._otel_req, o._otel_sample, o._usage_add, o._otel_src_add, o._oc_add) = self.saved

    def test_r2_token_sum_unchanged_and_split_fed(self):
        o._otel_ingest({"resourceLogs": [{"scopeLogs": [{"logRecords": [_rec("r1", 10, 100), _rec("r1", 10, 100)]}]}]})
        self.assertEqual(self.usage, [1111])       # input + read + creation + output, duplicate dropped
        self.assertEqual(self.src, [1111])
        self.assertEqual(self.oc, [("s1", 10, 100)])


if __name__ == "__main__":
    unittest.main()
