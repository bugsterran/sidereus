"""Account switch: nothing crosses it (no other account's per-%, no anchor, no `cyc` over a foreign stint), the own
first % step gives the per-% (`step`), and usage polling is fast only while calibrating. All IO is patched."""
import types
import unittest

from tests._load import sidereus

b = sidereus("burn")
bw = sidereus("burn_week")
B = (b, bw)          # burn imports `_qwk_pts`/`_tok_events`/`_cc_account` by name: patch both bindings
q = sidereus("quota")

NOW = 1_800_000_000.0
START = NOW - 3600


class _P(unittest.TestCase):
    def setUp(self):
        self._undo = []

    def tearDown(self):
        for m, k, v in reversed(self._undo):
            setattr(m, k, v)

    def patch(self, m, **kw):
        ms = m if isinstance(m, tuple) else (m,)
        for k, v in kw.items():
            hit = [x for x in ms if hasattr(x, k)]
            assert hit, k
            for x in hit:
                self._undo.append((x, k, getattr(x, k)))
                setattr(x, k, v)


class FiveHour(_P):
    T_SW = START + 600                      # switch to B inside this 5h window

    def setUp(self):
        super().setUp()
        log = [(START - 900, 30.0, "A"), (START + 300, 5.0, "A"), (self.T_SW, 14.0, "B")]
        self.patch(B, _cc_account=lambda: "B", _qb_lim_load=lambda: None, _qb_lim_set=lambda *a, **k: None,
                   _qb_lim={"lim": 5.19e8, "at": NOW - 600, "loaded": True, "acct": "A", "reset": 0.0, "seg": 0.0},
                   _anchors=lambda: {"blockLimitTokens": 519164200}, _qwk_pts=lambda: list(log))

    def ev(self, t_obs):
        # 7M own tokens between the two logs; the earlier 50M event is the old account's (before the switch)
        return [(self.T_SW - 30, 50_000_000), (self.T_SW + 60, 3_000_000), (t_obs - 5, 4_000_000)]

    def test_first_step_gives_own_per(self):
        t_obs = NOW - 120
        self.patch(B, _tok_events=lambda t0: self.ev(t_obs))
        lim, src, unc = b._qb_limit(NOW, START, 20.0, [], (self.T_SW, 14.0), t_obs)     # 14 -> 20: below the 8%p gate
        self.assertEqual(src, "step")
        self.assertAlmostEqual(lim, 7_000_000 / 0.06)
        self.assertAlmostEqual(unc[0], 1 / 6.0)

    def test_14_to_28_uses_own_tokens_only(self):
        t_obs = NOW - 120
        self.patch(B, _tok_events=lambda t0: self.ev(t_obs))
        lim, src, _u = b._qb_limit(NOW, START, 28.0, [], (self.T_SW, 14.0), t_obs)
        self.assertEqual(src, "win")
        self.assertAlmostEqual(lim, 7_000_000 / 0.14)              # 50M/% Pro-sized, not A's 519M cap

    def test_no_own_step_is_measuring(self):
        self.patch(B, _tok_events=lambda t0: [(self.T_SW + 60, 3_000_000)])
        lim, src, _u = b._qb_limit(NOW, START, 14.0, [], (self.T_SW, 14.0), self.T_SW)
        self.assertEqual((lim, src), (0.0, None))                  # no A cap, no anchor -> UI «측정 중»
        self.assertEqual(b._qb_lim["lim"], 0.0)


class Weekly(_P):
    def setUp(self):
        super().setUp()
        self.patch(B, _cc_account=lambda: "B")

    def test_cyc_not_across_foreign_stint(self):
        # B ended its old stint at 30, A logged, B came back at 22 -> 24: the reset was not seen by B.
        pts = [(NOW - 3 * 86400, 30.0, "B"), (NOW - 2 * 86400, 100.0, "A"),
               (NOW - 3000, 22.0, "B"), (NOW - 1500, 24.0, "B")]
        ev = [(NOW - 2900, 4_000_000), (NOW - 2000, 5_080_000)]
        self.patch(B, _qwk_pts=lambda: list(pts), _tok_events=lambda t0: [e for e in ev if e[0] >= t0])
        used, per, src, _st = bw._qwk_rate(NOW, 24.0)
        self.assertEqual(src, "step")                              # was cyc: 9.08M / 22% -> lim 41.3M
        self.assertAlmostEqual(per, 9_080_000 / 2.0)

    def test_cyc_kept_for_own_reset(self):
        pts = [(NOW - 5000, 90.0, "B"), (NOW - 4000, 1.0, "B"), (NOW - 1000, 4.0, "B")]
        ev = [(NOW - 3000, 8_000_000)]
        self.patch(B, _qwk_pts=lambda: list(pts), _tok_events=lambda t0: [e for e in ev if e[0] >= t0])
        _u, per, src, st = bw._qwk_rate(NOW, 4.0)
        self.assertEqual((src, st), ("cyc", NOW - 4000))
        self.assertAlmostEqual(per, 2_000_000)


class Polling(_P):
    def setUp(self):
        super().setUp()
        self.t = [NOW]
        self.patch(q, time=types.SimpleNamespace(time=lambda: self.t[0]), _calib={"until": 0.0},
                   _quota={"data": {"five_hour": {"pct": 20}}, "at": 0, "err": None, "next": 0})

    def test_fast_only_while_calibrating(self):
        self.assertEqual(q._quota_interval(), q.QUOTA_SLOW_S)
        q.quota_calibrating(True)
        self.assertEqual(q._quota_interval(), 60)
        self.t[0] += q.QUOTA_CALIB_TTL + 1                         # not renewed: lapses
        self.assertEqual(q._quota_interval(), q.QUOTA_SLOW_S)
        q.quota_calibrating(True)
        q.quota_calibrating(False)
        self.assertEqual(q._quota_interval(), q.QUOTA_SLOW_S)

    def test_burn_sets_flag_from_source(self):
        seen = []
        self.patch(B, quota_calibrating=seen.append, _qb_head=lambda *a, **k: None, _qwk_pts=lambda: [],
                   _tok_events=lambda t0: [], _acct_seg=lambda pts: ([], START - 10))   # a switch happened
        for src, span_pct, want in (("step", 3.0, True), ("step", 6.0, False), ("win", 10.0, False),
                                    (None, 0.0, True), ("anchor", 0.0, True)):
            self.patch(B, _qb_limit=lambda *a, _s=src: (1e8 if _s else 0.0, _s, (None, 0)))
            r = [(START + 600, 0.0), (START + 1200, span_pct)]
            b._qb_current(NOW, [(START + b.QBURN_WIN, r)], START + b.QBURN_WIN, r)
            self.assertEqual(seen[-1], want, src)

    def test_no_switch_not_calibrating(self):
        # fresh window / idle h5=0 has no per-% either, but without a switch there is nothing to calibrate
        seen = []
        self.patch(B, quota_calibrating=seen.append, _qb_head=lambda *a, **k: None, _qwk_pts=lambda: [],
                   _tok_events=lambda t0: [], _qb_limit=lambda *a: (1e8, "anchor", (None, 0)))
        r = [(START + 600, 0.0), (START + 1200, 0.0)]
        b._qb_current(NOW, [(START + b.QBURN_WIN, r)], START + b.QBURN_WIN, r)
        self.assertEqual(seen, [False])


class StaleLabel(_P):
    def test_row_equal_to_next_foreign_row_is_foreign(self):
        # ★quota-log `h5 15 d7 96 acct 5817baff`: the switch row carried the old label with the new account's value
        self.patch(B, _cc_account=lambda: "B")
        pts = [(NOW - 300, 21.0, "B"), (NOW - 200, 96.0, "B"), (NOW - 100, 96.0, "A")]
        runs, sw = bw._acct_runs(pts)
        self.assertEqual(runs, [[pts[0]]])
        self.assertEqual(sw, NOW - 100)


if __name__ == "__main__":
    unittest.main()
