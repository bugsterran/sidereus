"""NaN/inf/far-future timestamps: hook ts and stored `at` fall back or are dropped, so rows still age out."""
import json
import math
import unittest
from unittest import mock

from tests._load import sidereus

st = sidereus("ext_store")
PQ = sidereus("pl_reqs")
PR = sidereus("pl_runs")
AP = sidereus("arch_prov")

SID = "c0ffee00-1111-2222-3333-444455556666"
NOW = 1_000_000.0


class ExtTs(unittest.TestCase):
    def setUp(self):
        clock = mock.Mock()
        clock.time = lambda: NOW
        saved = (dict(st._ext), dict(st._runs), dict(st._tok), dict(st._hooktok), dict(st._ext_ended))
        for p in (mock.patch.object(st, "time", clock),
                  mock.patch.object(st, "_ext_save_locked", lambda: None),
                  mock.patch.object(st, "_runs_save_locked", lambda: None),
                  mock.patch.object(st, "_hooktok_save_locked", lambda: None)):
            p.start()
            self.addCleanup(p.stop)

        def restore():
            for d, v in zip((st._ext, st._runs, st._tok, st._hooktok, st._ext_ended), saved):
                d.clear(); d.update(v)
        self.addCleanup(restore)
        for d in (st._ext, st._runs, st._tok, st._hooktok, st._ext_ended):
            d.clear()

    def test_bad_ts_becomes_receive_time_and_ages_out(self):
        for bad in (float("nan"), float("inf"), "nan", "-inf", NOW + 10 ** 9, json.loads("NaN")):
            st._ext.clear()
            ok, _ = st.ext_ingest({"platform": "gemini", "session_id": SID, "event": "UserPromptSubmit", "ts": bad})
            self.assertTrue(ok, bad)
            v = st._ext[("gemini", SID)]
            self.assertEqual(v["lastSeen"], NOW, bad)
            self.assertTrue(st._ext_aged_out(v, NOW + st.EXT_TTL_S + 1), bad)

    def test_stored_nan_still_ages_out(self):
        self.assertTrue(st._ext_aged_out({"lastSeen": float("nan")}, NOW))
        self.assertTrue(st._ext_aged_out({"ended": float("nan")}, NOW))
        st._runs["r1"] = {"plat": "gemini", "parent": SID, "end": float("nan")}
        st._runs_prune_locked(NOW)
        self.assertNotIn("r1", st._runs)

    def test_valid_ts_kept(self):
        st.ext_ingest({"platform": "gemini", "session_id": SID, "event": "UserPromptSubmit", "ts": NOW - 5})
        self.assertEqual(st._ext[("gemini", SID)]["lastSeen"], NOW - 5)


class NumNonFinite(unittest.TestCase):
    def test_num_rejects_nonfinite(self):
        for mod in (PQ, PR, AP):
            for bad in (float("nan"), float("inf"), -math.inf):
                self.assertEqual(mod._num(bad), 0.0, mod.__name__)
            self.assertEqual(mod._num(5), 5.0)

    def test_nan_at_record_pruned(self):
        r = {"id": "m1", "repo": "/tmp/repo", "pipeline": "arch-map", "sid": "0a1b2c3d-0000",  # nosec B108
             "to": "alice", "mid": "m1", "at": float("nan")}
        self.assertIsNone(PQ._clean(r, NOW))
        r["at"] = NOW
        self.assertIsNotNone(PQ._clean(r, NOW))


if __name__ == "__main__":
    unittest.main()


class StoredNonFinite(unittest.TestCase):
    """Corrupt store values (not the hook input path): +inf lastSeen ages out, a far-future run t1 is not kept open."""

    def test_stored_inf_last_seen_ages_out(self):
        self.assertTrue(st._ext_aged_out({"lastSeen": float("inf")}, NOW))

    def test_far_future_run_dropped(self):
        rows = PR.pl_runs_of(SID, NOW, _raw={"quick-fix": {"t0": NOW - 60, "t1": NOW + 10 ** 9}})
        self.assertEqual(rows, [])
        rows = PR.pl_runs_of(SID, NOW, _raw={"quick-fix": {"t0": NOW - 60, "t1": NOW - 30}})
        self.assertEqual(len(rows), 1)
