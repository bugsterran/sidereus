"""Cold `/api/quota/burn`: fast log-only body marked `warm: False`, never cached; full body after warm-up.

Everything is monkeypatched (clock, quota log points, token events, live-sample flag) — no live files or clock.
"""
import unittest

from tests._load import sidereus

bu = sidereus("burn")
bw = sidereus("burn_week")
NOW = 1_790_000_000.0


class _Clock:
    def __init__(self, t):
        self.t = t

    def time(self):
        return self.t

    def sleep(self, s):
        self.t += s


class QburnWarm(unittest.TestCase):
    def setUp(self):
        self.saved = []
        reset = NOW + 3600
        s0 = reset - bu.QBURN_WIN
        self.pts = [(int(s0 + 600 * i), float(i), reset) for i in range(24)]   # 4h in, 23%
        self.tok_calls = []
        self.clock = _Clock(NOW)

        def tok(since):
            self.tok_calls.append(since)
            return [(since + 60 * i, 1_000_000) for i in range(100)]
        for name, val in (("time", self.clock), ("_qburn_pts", lambda: list(self.pts)),
                          ("_tok_events", tok),
                          ("_qb_lim_set", lambda lim, at, *_a: None), ("_qb_lim_load", lambda: None),
                          ("_qb_lim", {"lim": 0.0, "at": 0.0, "loaded": True}),
                          ("_qburn", {"pos": None, "pts": [], "at": 0, "out": None}),
                          ("_qb_warm", {"on": True, "done": False, "cold": False, "t0": int(NOW)}),   # log predates start
                          ("_anchors", lambda: {}), ("usage", lambda: {}), ("quota", lambda: {}),
                          ("_qwk_pts", lambda: []),
                          ("burn_est", lambda out, acct: None)):   # never the live history pass (sidereus/burn_hist.py)
            # burn imports the 7d names by name: patch every binding (burn_week owns `usage`)
            for m in [x for x in (bu, bw) if hasattr(x, name)]:
                self.saved.append((m, name, getattr(m, name)))
                setattr(m, name, val)

    def tearDown(self):
        for m, name, val in reversed(self.saved):
            setattr(m, name, val)

    def test_cold_is_light_marked_and_uncached(self):
        out = bu.quota_burn()
        self.assertTrue(out["ok"])
        self.assertIs(out["warm"], False)
        self.assertIsNone(out["head"])
        self.assertEqual(self.tok_calls, [])                    # the slow token scan is skipped
        self.assertEqual(out["cur"]["now_pct"], 23.0)
        self.assertIsNone(bu._qburn["out"])                     # partial body is never cached as final
        # waited at most QBURN_COLD_WAIT for a live sample that never came
        self.assertLessEqual(self.clock.t - NOW, bu.QBURN_COLD_WAIT + 0.1)

    def _live_row(self):
        self.pts.append((int(NOW), 25.0, self.pts[-1][2]))   # the startup sample, written by this process

    def test_live_sample_skips_wait(self):
        self._live_row()
        bu.quota_burn()
        self.assertEqual(self.clock.t, NOW)

    def test_fast_and_full_agree_on_rate(self):
        self._live_row()
        fast = bu.quota_burn()
        bu._qb_warm.update(on=False)
        full = bu.quota_burn()
        self.assertIs(fast["warm"], False)
        self.assertNotIn("warm", full)
        self.assertEqual(fast["cur"]["rate_pph"], full["cur"]["rate_pph"])
        self.assertEqual(fast["proj"]["over_at"], full["proj"]["over_at"])
        self.assertEqual(fast["cur"]["now_pct"], 25.0)

    def test_warm_waits_for_the_row_not_a_flag(self):
        # a sample flagged but not yet in the log must not be computed and cached as the warm body
        calls = []
        orig = bu._qburn_pts

        def pts():
            calls.append(1)
            if len(calls) == 3:
                self._live_row()          # the append lands on the third read
            return orig()
        bu._qburn_pts = pts
        bu._qburn_warm()
        self.assertEqual(bu._qburn["out"]["cur"]["now_pct"], 25.0)

    def test_warm_thread_body_is_full_and_cached(self):
        self._live_row()
        bu._qburn_warm()                                        # run inline
        self.assertTrue(bu._qb_warm["done"])
        out = bu.quota_burn()
        self.assertNotIn("warm", out)
        self.assertIsNotNone(out["head"])
        self.assertIs(out, bu._qburn["out"])

    def test_warm_waits_for_live_sample_then_gives_up(self):
        bu._qburn_warm()
        self.assertGreaterEqual(self.clock.t - NOW, bu.QBURN_WARM_MAX)
        self.assertFalse(bu._qb_warm["done"])
        self.assertIsNone(bu._qburn["out"])                     # the pre-sample body is not cached as final
        out = bu.quota_burn()                                   # full body, still marked, still uncached
        self.assertIs(out["warm"], False)
        self.assertIsNotNone(out["head"])
        self.assertIsNone(bu._qburn["out"])
        self._live_row()
        out = bu.quota_burn()                                   # first request that sees a live row ends warm-up
        self.assertNotIn("warm", out)
        self.assertTrue(bu._qb_warm["done"])
        self.assertIs(out, bu._qburn["out"])

    def test_rate_ignores_repeated_row_and_is_continuous(self):
        # live 09-24: a same-% startup row plus the 1 s edge gate gave 11.27 at +1 s and 11.94 at +3 s
        cyc = bu._qburn_cycles(self.pts)
        rows = sorted(cyc[-1][1])
        last_t, last_p = rows[-1]
        dup = rows + [(last_t + 100, last_p)]
        now0 = last_t + 100                    # no row crosses the 45 min window edge within +3 s
        a = [round(bu._qb_forecast(now0 + d, rows, last_p, 3000)[0], 2) for d in (0, 1, 3)]
        b = [round(bu._qb_forecast(now0 + d, dup, last_p, 3000)[0], 2) for d in (0, 1, 3)]
        self.assertEqual(a, b)
        self.assertLess(abs(a[2] - a[0]), 0.05)

    def test_not_started_keeps_old_path(self):
        bu._qb_warm.update(on=False)
        out = bu.quota_burn()
        self.assertNotIn("warm", out)
        self.assertIsNotNone(out["head"])


if __name__ == "__main__":
    unittest.main()
