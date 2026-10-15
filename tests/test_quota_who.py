"""Unit tests for 5h attribution (sidereus/usage.py `_usage_add` buckets + `quota_who`).

`_usage` and `_sid_proj` are swapped for fresh dicts per test; `now` is passed in, so no
live file, clock or network is used.
"""
import unittest
from datetime import datetime, timezone

from tests import _load

u = _load.sidereus("usage")

NOW = 1_800_000_000.0
H = 3600.0


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


class QuotaWhoCase(unittest.TestCase):
    def setUp(self):
        self.saved = (u._usage, u._sid_proj)
        # "seed running" state: quota_who never kicks the real transcript scan thread
        u._usage = {"live": [], "spark": [], "liveby": [], "bycSeed": {"done": False}}
        u._sid_proj = {"aaaa1111-x": "alpha", "bbbb2222-y": "beta", "cccc3333-z": "alpha"}

    def tearDown(self):
        u._usage, u._sid_proj = self.saved

    def q(self, reset_in):
        return {"five_hour": {"pct": 10, "resets_at": _iso(NOW + reset_in)}}

    def test_groups_by_project_within_cycle(self):
        # cycle = [NOW-3h, NOW+2h); the event 4h ago belongs to the previous cycle
        u._usage_add(NOW - 4 * H, 999, 0, "aaaa1111-x")
        u._usage_add(NOW - 2 * H, 300, 0, "aaaa1111-x")
        u._usage_add(NOW - 1 * H, 100, 0, "cccc3333-z")
        u._usage_add(NOW - 60, 600, 0, "bbbb2222-y")
        w = u.quota_who(self.q(2 * H), now=NOW)
        self.assertTrue(w["exact"])
        self.assertEqual(w["total"], 1000)
        self.assertEqual([(r["name"], r["tok"], r["n"]) for r in w["rows"]],
                         [("beta", 600, 1), ("alpha", 400, 2)])
        self.assertEqual(w["rows"][0]["share"], 60.0)
        self.assertEqual(w["rows"][1]["sids"][0], {"sid": "aaaa1111", "tok": 300})
        self.assertFalse(w["partial"])     # first event predates the cycle start

    def test_partial_and_unknown_sid(self):
        u._usage_add(NOW - 600, 50, 0, "dddd4444-q")
        w = u.quota_who(self.q(2 * H), now=NOW)
        self.assertTrue(w["partial"])
        self.assertEqual(w["rows"][0]["name"], "dddd4444")

    def test_no_reset_falls_back_to_last_5h(self):
        u._usage_add(NOW - 6 * H, 70, 0, "aaaa1111-x")
        u._usage_add(NOW - 1 * H, 30, 0, "aaaa1111-x")
        w = u.quota_who({}, now=NOW)
        self.assertFalse(w["exact"])
        self.assertEqual(w["total"], 30)

    def test_old_buckets_pruned(self):
        u._usage_add(NOW - 8 * H, 1, 0, "aaaa1111-x")
        u._usage_add(NOW, 1, 0, "aaaa1111-x")
        self.assertEqual(len(u._usage["byc"]), 1)

    def test_empty(self):
        w = u.quota_who(self.q(H), now=NOW)
        self.assertEqual((w["total"], w["rows"], w["partial"]), (0, [], True))



class SeedCase(unittest.TestCase):
    def setUp(self):
        self.saved = (u._usage, u._sid_proj, u._who_scan)
        u._usage = {"live": [], "spark": [], "liveby": []}
        u._sid_proj = {"aaaa1111-x": "alpha", "bbbb2222-y": "beta"}
        self.start = NOW - 3 * H

    def tearDown(self):
        u._usage, u._sid_proj, u._who_scan = self.saved

    def q(self):
        return {"five_hour": {"resets_at": _iso(self.start + 5 * H)}}

    def test_seed_before_live_only(self):
        # live OTel began at NOW-600; transcript copies at/after that must not be added again
        u._usage_add(NOW - 600, 500, 0, "bbbb2222-y")
        u._who_scan = lambda start: ([(start - 10, 9, "aaaa1111-x"), (NOW - 2 * H, 300, "aaaa1111-x"),
                                      (NOW - 600, 500, "bbbb2222-y")], start)
        u._who_seed(self.start, now=NOW)
        w = u.quota_who(self.q(), now=NOW)
        self.assertEqual(w["total"], 800)
        self.assertEqual([(r["name"], r["tok"]) for r in w["rows"]], [("beta", 500), ("alpha", 300)])
        self.assertFalse(w["partial"])

    def test_seed_truncated_stays_partial(self):
        u._who_scan = lambda start: ([(NOW - H, 10, "aaaa1111-x")], NOW - 2 * H)
        u._who_seed(self.start, now=NOW)
        w = u.quota_who(self.q(), now=NOW)
        self.assertTrue(w["partial"])
        self.assertEqual(w["since"], int(NOW - 2 * H))

    def test_seed_failure_is_quiet(self):
        def boom(start):
            raise RuntimeError("x")
        u._who_scan = boom
        u._who_seed(self.start, now=NOW)
        self.assertTrue(u._usage["bycSeed"]["done"])
        self.assertTrue(u.quota_who(self.q(), now=NOW)["partial"])

    def test_new_cycle_reseeds_once(self):
        # boot seed for cycle 1, then resets_at moves to cycle 2: seed must re-run once, since = new start
        class SyncThread:
            def __init__(self, target, args=(), **kw):
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)
        saved_thr, u.threading = u.threading, type("T", (), {"Thread": SyncThread})
        self.addCleanup(setattr, u, "threading", saved_thr)
        clock = [NOW - 4 * H]
        saved_time, u.time = u.time, type("C", (), {"time": staticmethod(lambda: clock[0])})
        self.addCleanup(setattr, u, "time", saved_time)
        calls = []
        s1, s2 = NOW - 8 * H, NOW - 3 * H
        ev = [(s1 + 60, 7, "aaaa1111-x"), (s2 + 60, 40, "aaaa1111-x"), (NOW - 60, 2, "bbbb2222-y")]

        def scan(start):
            calls.append(start)
            return [e for e in ev if e[0] >= start], start
        u._who_scan = scan
        u.quota_who({"five_hour": {"resets_at": _iso(s1 + 5 * H)}}, now=clock[0])
        clock[0] = NOW
        q2 = {"five_hour": {"resets_at": _iso(s2 + 5 * H)}}
        u.quota_who(q2, now=NOW)
        u.quota_who(q2, now=NOW)
        w = u.quota_who({"five_hour": {"resets_at": _iso(s2 + 5 * H + 1)}}, now=NOW)   # jitter: no rescan
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1], s2)
        self.assertEqual(w["since"], int(s2))
        self.assertFalse(w["partial"])
        self.assertEqual(w["total"], 42)     # s2 events once each; cycle-1 event excluded
        self.assertEqual(sum(sum(r.values()) for r in u._usage["byc"].values()), 49)   # nothing added twice


if __name__ == "__main__":
    unittest.main()
