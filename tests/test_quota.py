"""Deterministic unit tests for the quota/burn math (sidereus/burn.py, sidereus/quota.py).

Every IO path (quota log tail, transcripts, quota API cache, qb-lim-cache file, clock) is
monkeypatched, so no live data file is read or written and no thread starts.
"""
import types
import unittest

from tests import _load

b = _load.sidereus("burn")
bw = _load.sidereus("burn_week")
q = _load.sidereus("quota")

NOW = 1_800_000_000.0
H = 3600.0
D = 86400.0


class _Patch(object):
    """Set module attributes for one test and restore them afterwards (on every given module that has the name)."""

    def __init__(self, *mods):
        self.mods, self.saved = mods, {}

    def set(self, **kw):
        for k, v in kw.items():
            mods = [m for m in self.mods if hasattr(m, k)]
            assert mods, k
            for m in mods:
                if (m, k) not in self.saved:
                    self.saved[(m, k)] = getattr(m, k)
                setattr(m, k, v)

    def undo(self):
        for (m, k), v in self.saved.items():
            setattr(m, k, v)
        self.saved = {}


class _BurnFixture(unittest.TestCase):
    """Runs `quota_burn()` against a synthetic 5h cycle (fixture only — no tests, so subclasses do not rerun any)."""

    def setUp(self):
        self.p = _Patch(b, bw)      # burn imports `_qwk_pts`/`_tok_events`/... by name: patch both bindings
        self.lim_sets = []
        self.saved_cache = dict(b._qburn)
        self.saved_lim = dict(b._qb_lim)
        b._qburn["out"], b._qburn["at"] = None, 0
        b._qb_lim.update({"lim": 0.0, "at": 0.0, "loaded": True})
        self.p.set(
            time=types.SimpleNamespace(time=lambda: NOW),
            _qb_lim_set=lambda lim, at, *_a: self.lim_sets.append((lim, at)),   # never write qb-lim-cache.json
            _qb_lim_load=lambda: None,
            _cc_account=lambda: None,     # never read the live ~/.claude.json (`_qb_lim_stale`)
            _anchors=lambda: {},
            usage=lambda: {},
            quota=lambda: {},
            _tok_events=lambda since: [],
            _qwk_rate=lambda now, wp: (0, 0.0, None, None),
            _qwk_pts=lambda: [],          # never read the live quota log (5h switch lookup)
            quota_calibrating=lambda on: None,   # never touch quota's poll interval
            burn_est=lambda out, acct: None,     # never the live history pass (sidereus/burn_hist.py)
        )

    def tearDown(self):
        self.p.undo()
        b._qburn.clear(); b._qburn.update(self.saved_cache)
        b._qb_lim.clear(); b._qb_lim.update(self.saved_lim)

    def run_burn(self, rows, reset=NOW + H, tokens=None, wk=None, qwk=None):
        """rows: [(t, pct)] of the current cycle; tokens: total local tokens since the cycle start."""
        self.p.set(_qburn_pts=lambda: [(int(t), float(h), float(reset)) for t, h in rows])
        if tokens is not None:
            # before the first log: the tokens that moved the % precede its first sighting (burn._qb_step_at)
            t_ev = (rows[0][0] - 1) if rows else NOW - 100
            self.p.set(_tok_events=lambda since: [(t_ev, tokens)])
        if wk is not None:
            self.p.set(quota=lambda: {"seven_day": wk})
        if qwk is not None:
            self.p.set(_qwk_rate=lambda now, wp: qwk)
        b._qburn["out"] = None
        return b.quota_burn()

    # rows on a straight line: 60 %/h, last point exactly at NOW

class BurnCase(_BurnFixture):
    """Scenarios on a synthetic 5h cycle."""

    LINE_FAST = [(NOW - 2400, 20.0), (NOW - 1200, 40.0), (NOW, 60.0)]
    LINE_SLOW = [(NOW - 2400, 50.0), (NOW - 1200, 55.0), (NOW, 60.0)]

    def test_no_data_returns_not_ok(self):
        out = self.run_burn([])
        self.assertFalse(out["ok"])
        self.assertEqual(out["why"], "no-data")

    def test_used_local_is_measured_sum(self):
        # ★2026-10-02: the page shows `cur.used_local` (local event sum), never `head.used` (% x per_pct estimate)
        out = self.run_burn(self.LINE_FAST, tokens=6_200_000)
        self.assertEqual(out["cur"]["used_local"], 6_200_000)
        self.assertIsNone(out["cur"]["wk_used_local"])     # 7d shown only for a measured `cyc` sum

    def test_used_local_from_window_start_unless_switch(self):
        # an h5 drop moves seg[0] but is no switch -> still the whole window; an in-window switch -> since seg[0]
        drop = [(NOW - 2400, 40.0), (NOW - 1200, 0.0), (NOW, 20.0)]
        self.p.set(_tok_events=lambda since: [(NOW - 2000, 5_000_000), (NOW - 600, 3_000_000)])
        b._qburn["out"] = None
        self.p.set(_qburn_pts=lambda: [(int(t), h, float(NOW + H)) for t, h in drop])
        self.assertEqual(b.quota_burn()["cur"]["used_local"], 8_000_000)
        self.p.set(_acct_seg=lambda pts: (None, NOW - 1300))
        b._qburn["out"] = None
        self.assertEqual(b.quota_burn()["cur"]["used_local"], 3_000_000)

    def test_cycle_past_reset_is_stale_not_extrapolated(self):
        out = self.run_burn(self.LINE_FAST, reset=NOW - 10)
        self.assertEqual((out["ok"], out["why"]), (False, "stale"))
        self.assertNotIn("proj", out)

    def test_projection_hits_100_before_reset_gives_eta(self):
        out = self.run_burn(self.LINE_FAST)
        self.assertAlmostEqual(out["cur"]["rate_pph"], 60.0, places=2)
        self.assertEqual(out["proj"]["raw"], 120.0)
        self.assertEqual(out["proj"]["pct"], 100.0)          # clamped for the gauge
        self.assertEqual(out["proj"]["over_in"], 2400)       # (100-60)/60 h
        self.assertEqual(out["proj"]["over_at"], int(NOW + 2400))

    def test_eta_after_reset_is_not_emitted(self):
        out = self.run_burn(self.LINE_SLOW)
        self.assertAlmostEqual(out["proj"]["raw"], 75.0, places=1)
        self.assertIsNone(out["proj"]["over_at"])
        self.assertIsNone(out["proj"]["over_in"])

    def test_already_at_100_gives_zero_not_negative_eta(self):
        rows = [(NOW - 2000, 90.0), (NOW - 600, 100.0)]
        out = self.run_burn(rows)
        self.assertEqual(out["proj"]["over_in"], 0)
        self.assertEqual(out["proj"]["over_at"], int(NOW - 600))

    def test_flat_usage_has_zero_rate_and_no_eta(self):
        out = self.run_burn([(NOW - 2400, 30.0), (NOW - 1200, 30.0), (NOW, 30.0)], tokens=30_000_000)
        self.assertEqual(out["cur"]["rate_pph"], 0.0)
        self.assertEqual(out["proj"]["raw"], 30.0)
        self.assertIsNone(out["proj"]["over_in"])
        self.assertEqual(out["head"]["tph"], 0)

    def test_idle_tail_is_counted_in_slope(self):
        # Climbed fast long ago, idle for the last 40 min: slope must not keep the old climb.
        rows = [(NOW - 2600, 10.0), (NOW - 2500, 40.0)]
        out = self.run_burn(rows)
        self.assertLess(out["cur"]["rate_pph"], 60.0)
        self.assertIsNone(out["proj"]["over_in"])

    def test_single_observation_emits_no_forecast(self):
        out = self.run_burn([(NOW - 30, 2.0)])
        self.assertIsNone(out["proj"]["pct"])
        self.assertIsNone(out["proj"]["raw"])

    def test_head_back_computes_used_left_per_pct(self):
        out = self.run_burn(self.LINE_FAST, tokens=60_000_000)
        h = out["head"]
        self.assertEqual(h["src"], "win")
        self.assertEqual(h["lim"], 100_000_000)              # 60M / 60%
        self.assertEqual(h["per_pct"], 1_000_000)
        self.assertEqual(h["used"], 60_000_000)
        self.assertEqual(h["tok"], 40_000_000)
        self.assertEqual(h["used"] + h["tok"], h["lim"])
        self.assertEqual(h["tph"], 60_000_000)
        self.assertEqual(h["room"], 2.0)                     # 40% left / (60 min * 100/300)
        self.assertEqual(len(self.lim_sets), 1)              # success is remembered (patched, no file)

    def test_low_pct_skips_back_computation(self):
        rows = [(NOW - 2400, 3.0), (NOW - 1200, 4.0), (NOW, 5.0)]
        out = self.run_burn(rows, tokens=5_000_000)
        # no win, no recent: the early own step (±1/span), never stored as `recent`
        self.assertEqual((out["head"]["src"], out["head"]["lim"], out["head"]["unc"]), ("step", 100_000_000, 0.2))
        self.assertEqual(self.lim_sets, [])

    def test_early_window_back_computes_once_pct_floor_met(self):
        reset = NOW + b.QBURN_WIN - 600                      # only 10 min into the window: no time wait any more
        rows = [(NOW - 500, 10.0), (NOW - 200, 15.0), (NOW, 20.0)]
        out = self.run_burn(rows, reset=reset, tokens=20_000_000)
        self.assertEqual((out["head"]["src"], out["head"]["lim"]), ("win", 100_000_000))
        self.assertEqual(out["cur"]["elapsed"], 600)

    def test_zero_local_tokens_falls_back_to_recent_then_anchor(self):
        b._qb_lim.update({"lim": 200_000_000.0, "at": NOW - 60})
        out = self.run_burn(self.LINE_FAST, tokens=0)
        self.assertEqual((out["head"]["src"], out["head"]["lim"]), ("recent", 200_000_000))
        b._qb_lim.update({"lim": 200_000_000.0, "at": NOW - b.QB_LIM_TTL - 1})   # expired
        self.p.set(_anchors=lambda: {"blockLimitTokens": 500_000_000})
        out = self.run_burn(self.LINE_FAST, tokens=0)
        self.assertEqual((out["head"]["src"], out["head"]["lim"]), ("anchor", 500_000_000))

    def test_eff_headroom_is_5h_when_week_has_more_room(self):
        wk = {"pct": 50.0, "leftSec": 3 * D}
        out = self.run_burn(self.LINE_FAST, tokens=60_000_000, wk=wk,
                            qwk=(100_000_000, 2_000_000.0, "step", None))
        h = out["head"]
        self.assertEqual(h["wk"]["lim"], 200_000_000)
        self.assertEqual((h["eff"], h["cap"]), (40_000_000, "5h"))
        self.assertEqual(out["wk"], {"now_pct": 50.0, "left": int(3 * D)})

    def test_eff_headroom_is_7d_when_week_is_tighter(self):
        wk = {"pct": 70.0, "leftSec": D}
        out = self.run_burn(self.LINE_FAST, tokens=60_000_000, wk=wk,
                            qwk=(70_000_000, 1_000_000.0, "step", None))
        self.assertEqual((out["head"]["eff"], out["head"]["cap"]), (30_000_000, "7d"))

    def test_eff_headroom_never_negative_when_week_over_100(self):
        wk = {"pct": 105.0, "leftSec": D}
        out = self.run_burn(self.LINE_FAST, tokens=60_000_000, wk=wk,
                            qwk=(105_000_000, 1_000_000.0, "step", None))
        self.assertEqual((out["head"]["eff"], out["head"]["cap"]), (0, "7d"))

    def test_week_cyc_rounding_band_guards_small_pct(self):
        wk = {"pct": 0.4, "leftSec": 6 * D}
        out = self.run_burn(self.LINE_FAST, tokens=60_000_000, wk=wk,
                            qwk=(4_000_000, 10_000_000.0, "cyc", NOW - H))
        w = out["head"]["wk"]
        self.assertIsNone(w["hi"])                           # pct - 0.5 <= 0 must not divide
        self.assertEqual(w["lo"], int(4_000_000 / 0.9 * 100))

    def test_week_after_early_reset_below_1pct_has_no_calendar_fallback(self):
        self.p.set(usage=lambda: {"week": {"tokens": 900_000_000}})
        wk = {"pct": 0.0, "leftSec": 6 * D}
        out = self.run_burn(self.LINE_FAST, tokens=60_000_000, wk=wk,
                            qwk=(0, 0.0, None, NOW - H))
        self.assertIsNone(out["head"]["wk"])

    def test_week_calendar_fallback_when_no_reset_seen(self):
        self.p.set(usage=lambda: {"week": {"tokens": 90_000_000}})
        wk = {"pct": 30.0, "leftSec": 2 * D}
        out = self.run_burn(self.LINE_FAST, tokens=60_000_000, wk=wk)
        w = out["head"]["wk"]
        self.assertEqual((w["src"], w["lim"], w["used"]), ("week", 300_000_000, 90_000_000))

    def test_week_unc_covers_one_pct_of_headroom(self):
        # 98% with 2 x 29M left minus 25M spent since: ±1% x per (29M / 33M) beats the 1/span term
        wk = {"pct": 98.0, "leftSec": D}
        bw._qwk["span"] = 10.0
        out = self.run_burn(self.LINE_FAST, tokens=60_000_000, wk=wk,
                            qwk=(98 * 29_000_000 + 25_000_000, 29_000_000.0, "step", None))
        w = out["head"]["wk"]
        self.assertEqual(w["lim"] - w["used"], 33_000_000)
        self.assertEqual(w["unc"], round(29 / 33, 3))

    def test_week_used_never_exceeds_lim(self):
        wk = {"pct": 99.0, "leftSec": D}
        out = self.run_burn(self.LINE_FAST, tokens=60_000_000, wk=wk,
                            qwk=(99_000_000 + 5_000_000, 1_000_000.0, "step", None))
        w = out["head"]["wk"]
        self.assertEqual((w["used"], w["lim"]), (100_000_000, 100_000_000))
        self.assertEqual((out["head"]["eff"], out["head"]["cap"]), (0, "7d"))

    def test_week_with_none_fields_is_ignored(self):
        wk = {"pct": None, "leftSec": None}
        out = self.run_burn(self.LINE_FAST, tokens=60_000_000, wk=wk)
        self.assertIsNone(out["head"]["wk"])
        self.assertNotIn("wk", out)
        self.assertEqual(out["head"]["cap"], "5h")


class QwkRateCase(unittest.TestCase):
    """7d rate from quota-log d7 points: early reset (`cyc`) vs step span (`step`)."""

    def setUp(self):
        self.p = _Patch(bw)

    def tearDown(self):
        self.p.undo()

    def rate(self, pts, events, wp):
        self.p.set(_qwk_pts=lambda: list(pts), _tok_events=lambda since: list(events))
        return bw._qwk_rate(NOW, wp)

    def test_d7_drop_is_detected_as_reset_and_back_computed(self):
        st = NOW - D
        pts = [(NOW - 5 * D, 80.0), (NOW - 3 * D, 87.0), (st, 0.0), (NOW - D / 2, 3.0)]
        ev = [(NOW - 2 * D, 999_000_000), (st + 10, 30_000_000)]      # pre-reset tokens must not count
        self.assertEqual(self.rate(pts, ev, 3.0), (30_000_000, 10_000_000.0, "cyc", st))

    def test_reset_below_1pct_returns_start_without_rate(self):
        st = NOW - H
        pts = [(NOW - 2 * D, 60.0), (st, 0.0)]
        self.assertEqual(self.rate(pts, [(st + 1, 5_000_000)], 0.0), (0, 0.0, None, st))

    def test_reset_with_zero_tokens_returns_no_rate(self):
        st = NOW - H
        pts = [(NOW - 2 * D, 60.0), (st, 0.0), (NOW - 60, 2.0)]
        self.assertEqual(self.rate(pts, [], 2.0), (0, 0.0, None, st))

    def test_long_history_uses_latest_span_of_target_not_whole_history(self):
        # 20 <- 12 is only 8%p, 20 <- 8 reaches the 10%p target; 20 <- 5 (whole history) is not used
        pts = [(NOW - 5 * D, 5.0), (NOW - 4 * D, 8.0), (NOW - 3 * D, 12.0),
               (NOW - 2 * D, 12.0), (NOW - D, 20.0)]
        ev = [(NOW - 4.5 * D, 999_000_000), (NOW - 3.5 * D, 60_000_000),   # before t0 excluded
              (NOW - D / 2, 1_000_000_000)]                                # after t1 excluded
        self.assertEqual(self.rate(pts, ev, 22.0), (110_000_000, 5_000_000.0, "step", None))
        self.assertEqual(bw._qwk["span"], 12.0)

    def test_segment_below_target_uses_widest_span(self):
        # ★2026-09-27 live: new account 12, 13, 14, 15, 16 — no 10%p span, so 12 -> 16 (±25%), not the latest 14 -> 16
        pts = [(NOW - 5 * H, 12.0), (NOW - 4 * H, 13.0), (NOW - 3 * H, 14.0), (NOW - 2 * H, 15.0), (NOW - H, 16.0)]
        ev = [(NOW - 4.5 * H, 20_000_000), (NOW - 2.5 * H, 20_000_000)]
        self.assertEqual(self.rate(pts, ev, 16.0), (160_000_000, 10_000_000.0, "step", None))
        self.assertEqual(bw._qwk["span"], 4.0)

    def test_step_span_too_small_returns_nothing(self):
        pts = [(NOW - 3 * D, 10.0), (NOW - D, 11.0)]
        self.assertEqual(self.rate(pts, [(NOW - 2 * D, 1)], 11.0), (0, 0.0, None, None))

    def test_one_point_flap_is_neither_reset_nor_step(self):
        pts = [(NOW - 3 * D, 66.0), (NOW - 2 * D, 67.0), (NOW - 1.5 * D, 66.0), (NOW - D, 67.0)]
        self.assertEqual(self.rate(pts, [(NOW - 1.2 * D, 5_000_000)], 67.0), (0, 0.0, None, None))

    def test_two_point_step_is_measured(self):
        # ★2026-09-27 12 -> 15 must yield a number (unc 1/3 shown by `_qb_week`)
        pts = [(NOW - D, 12.0), (NOW - H, 15.0)]
        self.assertEqual(self.rate(pts, [(NOW - D / 2, 30_000_000)], 15.0),
                         (150_000_000, 10_000_000.0, "step", None))
        self.assertEqual(bw._qwk["span"], 3.0)

    def test_points_older_than_7_days_are_ignored(self):
        pts = [(NOW - 8 * D, 90.0), (NOW - 2 * D, 10.0), (NOW - D, 11.0)]
        # the 90 -> 10 "drop" is outside the window, so no reset is seen
        self.assertEqual(self.rate(pts, [], 11.0), (0, 0.0, None, None))

    def test_empty_log_returns_nothing(self):
        self.assertEqual(self.rate([], [], 50.0), (0, 0.0, None, None))

    # ★2026-09-27 account switch: the old account's reset/steps and tokens must not reach the new account's 7d rate.
    def test_account_switch_drops_old_reset_and_blocks_calendar_fallback(self):
        self.p.set(_cc_account=lambda: "new")
        sw = NOW - 2 * H
        pts = [(NOW - 3 * D, 100.0, "old"), (NOW - D, 0.0, "old"), (NOW - 3 * H, 4.0, "old"),
               (sw, 12.0, "new"), (NOW - H, 14.0, "new")]
        ev = [(NOW - D / 2, 78_000_000), (sw + 10, 9_000_000)]
        # old account's reset at NOW - D would give "cyc" 87M / 14; the new segment's 12 -> 14 step gives 9M / 2
        self.assertEqual(self.rate(pts, ev, 14.0), (63_000_000, 4_500_000.0, "step", None))
        pts[-1] = (NOW - H, 13.0, "new")                     # 1%p only: unknown, and `sw` blocks the calendar week
        self.assertEqual(self.rate(pts, ev, 13.0), (0, 0.0, None, sw))

    def test_account_switch_step_uses_new_account_rows_only(self):
        self.p.set(_cc_account=lambda: "new")
        sw = NOW - 2 * D
        pts = [(NOW - 3 * D, 50.0, "old"), (sw, 10.0, "new"), (NOW - D, 16.0, "new")]
        ev = [(NOW - 2.5 * D, 999_000_000), (sw + 10, 30_000_000)]
        self.assertEqual(self.rate(pts, ev, 16.0), (80_000_000, 5_000_000.0, "step", None))

    # ★2026-10-01 a foreign stint must not erase the current account's history.
    def test_foreign_stint_in_the_middle_keeps_history_and_never_spans_it(self):
        self.p.set(_cc_account=lambda: "a")
        pts = [(NOW - 3 * D + k * H, float(4 + k), "a") for k in range(93)]          # 4 -> 96, ends NOW-3D+92H
        t96 = NOW - 3 * D + 92 * H
        pts += [(t96 + 0.5 * H, 96.0, "b"), (t96 + 1.5 * H, 97.0, "b"),           # other account
                (t96 + 2 * H, 96.0, "a"), (t96 + 2.5 * H, 98.0, "a")]
        ev = [(NOW - 3 * D + (k + 0.5) * H, 29_000_000) for k in range(92)]         # 29M per own step
        ev += [(t96 + H, 500_000_000), (t96 + 2.2 * H, 10_000_000)]                 # b's burst, a's 96 -> 98
        u, per, src, _st = self.rate(pts, ev, 98.0)
        self.assertEqual((src, per), ("step", 29_000_000.0))                       # 86 -> 96 in run 1
        self.assertEqual(bw._qwk["span"], 10.0)
        self.assertEqual(u, 98 * 29_000_000)

    def test_left_decreases_as_tokens_accrue_within_one_pct(self):
        pts = [(NOW - 2 * D, 10.0), (NOW - D, 20.0), (NOW - H, 20.0)]
        ev = [(NOW - 1.5 * D, 100_000_000)]
        u0, per, _s, _t = self.rate(pts, ev, 20.0)
        u1, per1, _s, _t = self.rate(pts, ev + [(NOW - 60, 7_000_000)], 20.0)
        self.assertEqual((per, per1), (10_000_000.0, 10_000_000.0))               # per-% fixed within a step
        self.assertEqual(u1 - u0, 7_000_000)                                      # so lim - used falls 1:1

    def test_last_row_foreign_adds_no_since(self):
        self.p.set(_cc_account=lambda: "a")
        pts = [(NOW - 2 * D, 10.0, "a"), (NOW - D, 20.0, "a"), (NOW - H, 20.0, "b")]
        ev = [(NOW - 1.5 * D, 100_000_000), (NOW - 0.5 * H, 50_000_000)]      # the 50M is b's stint
        self.assertEqual(self.rate(pts, ev, 20.0), (200_000_000, 10_000_000.0, "step", None))

    def test_reset_with_foreign_rows_after_it_is_not_a_plain_sum(self):
        self.p.set(_cc_account=lambda: "a")
        st = NOW - 2 * D
        pts = [(NOW - 3 * D, 90.0, "a"), (st, 0.0, "a"), (NOW - 1.5 * D, 12.0, "a"),
               (NOW - D, 12.0, "b"), (NOW - H, 12.0, "a")]
        ev = [(st + 10, 120_000_000), (NOW - D + 10, 900_000_000)]
        self.assertEqual(self.rate(pts, ev, 12.0)[2], "step")                     # 0 -> 12 inside run 1 only
        self.assertEqual(self.rate(pts, ev, 12.0)[1], 10_000_000.0)

    def test_untagged_rows_are_not_a_mismatch(self):
        self.p.set(_cc_account=lambda: "new")
        st = NOW - D
        pts = [(NOW - 3 * D, 87.0, None), (st, 0.0, None), (NOW - H, 3.0, "new")]
        self.assertEqual(self.rate(pts, [(st + 10, 30_000_000)], 3.0), (30_000_000, 10_000_000.0, "cyc", st))


class AcctSwitch5hCase(_BurnFixture):
    """★2026-09-27: a switch inside the 5h window counts only the new account's tokens and % gained since."""

    def test_mid_window_switch_back_computes_from_first_new_row(self):
        sw = NOW - H
        self.p.set(_cc_account=lambda: "new",
                   _qwk_pts=lambda: [(NOW - 2 * H, 5.0, "old"), (sw, 5.0, "new")],
                   _tok_events=lambda since: [(NOW - 3 * H, 500_000_000), (sw + 60, 20_000_000)])
        rows = [(NOW - 3 * H, 40.0), (sw, 50.0), (NOW, 60.0)]
        out = self.run_burn(rows)
        self.assertEqual(out["head"]["src"], "win")
        self.assertEqual(out["head"]["lim"], 200_000_000)     # 20M / (60 - 50)%
        self.assertEqual(out["head"]["unc"], 0.1)            # rounding of a 10%p difference: 1/10

    def test_baseline_drops_cycles_logged_before_the_switch(self):
        sw = NOW - 11 * H
        # three past cycles (ending NOW-14h, -9h, -4h; the first two start before the switch) + the current one
        past = [(r - 4 * H + k * H, 10.0 * (k + 1), r) for r in (NOW - 14 * H, NOW - 9 * H, NOW - 4 * H)
                for k in range(4)]
        cur = [(NOW - 2 * H, 10.0, NOW + 3 * H), (NOW, 20.0, NOW + 3 * H)]
        self.p.set(_qburn_pts=lambda: past + cur)
        b._qburn["out"] = None
        self.assertEqual(b.quota_burn()["base"]["n"], 3)     # untagged log: every past cycle counts
        self.p.set(_cc_account=lambda: "new", _qwk_pts=lambda: [(sw - H, 1.0, "old"), (sw, 1.0, "new")])
        b._qburn["out"] = None
        self.assertEqual(b.quota_burn()["base"]["n"], 1)     # only the cycle whose rows all follow the switch


class ManualReset5hCase(_BurnFixture):
    """★2026-09-27: a one-time manual 5h reset (h5 40 -> 0) mid-window, with or without a new `reset5`."""

    def test_reset_with_new_reset5_is_a_new_cycle(self):
        old_r, new_r = NOW + 2 * H, NOW + 5 * H - 60
        self.p.set(_qburn_pts=lambda: [(NOW - 2 * H, 30.0, old_r), (NOW - H, 40.0, old_r),
                                       (NOW - 30 * 60, 0.0, new_r), (NOW, 10.0, new_r)])
        self.assertEqual(len(b._qburn_cycles(b._qburn_pts())), 2)
        b._qburn["out"] = None
        out = b.quota_burn()
        self.assertEqual(out["cur"]["reset"], int(new_r))
        self.assertEqual(out["base"]["n"], 1)                # the pre-reset cycle is a normal past cycle

    def test_drop_inside_one_cycle_segments_forecast_and_limit(self):
        self.p.set(_tok_events=lambda since: [(NOW - 2.5 * H, 500_000_000), (NOW - 600, 20_000_000)])
        rows = [(NOW - 2 * H, 40.0), (NOW - 50 * 60, 45.0), (NOW - 30 * 60, 0.0), (NOW, 10.0)]
        out = self.run_burn(rows)
        self.assertEqual(out["cur"]["rate_pph"], 20.0)       # slope from the drop only (0 -> 10 in 30 min)
        self.assertEqual(out["head"]["lim"], 200_000_000)     # post-drop 20M / 10%, not 520M / 10%
        self.assertEqual(out["head"]["unc"], 0.1)

    def test_one_point_dip_is_jitter_not_a_reset(self):
        self.assertEqual(b._qb_drop([(1, 66.0), (2, 67.0), (3, 66.0), (4, 67.0)]), 0)
        self.assertEqual(b._qb_drop([(1, 40.0), (2, 0.0), (3, 5.0)]), 1)

    def test_past_cycle_with_a_drop_is_not_a_baseline(self):
        past = [(r - 4 * H + k * H, 10.0 * (k + 1), r) for r in (NOW - 14 * H, NOW - 9 * H, NOW - 4 * H)
                for k in range(4)]
        past[5] = (past[5][0], 0.0, past[5][2])            # middle cycle: 10, 0, 30, 40
        cur = [(NOW - 2 * H, 10.0, NOW + 3 * H), (NOW, 20.0, NOW + 3 * H)]
        self.p.set(_qburn_pts=lambda: past + cur)
        b._qburn["out"] = None
        self.assertEqual(b.quota_burn()["base"]["n"], 2)


class HeadroomStepCase(_BurnFixture):
    """Replays the live 2026-09-29 polls: 16% -> 18% -> 20%, ~1.3M tokens/min, one quota log per 300 s."""

    def test_headroom_is_flat_within_a_step_and_moves_only_on_a_new_step(self):
        start = NOW - 4 * H
        l16, l18, l20 = NOW - 625, NOW, NOW + 300
        # 55.17M by the 16% log, 55.66M by the 18% log, then 1.3M/min until the 20% log (64.4M)
        ev = [(start + 60, 55_171_406), (l18 - 5, 490_626)] + [(l18 + 15 * i, 325_000) for i in range(1, 21)]
        rows = [(start + 600, 2.0), (l16, 16.0), (l18, 18.0), (l20, 20.0)]
        self.p.set(_tok_events=lambda since: ev)
        seen = []
        for now in [l18 + 15 * i for i in range(20)] + [l20 + 15 * i for i in range(4)]:
            self.p.set(time=types.SimpleNamespace(time=lambda now=now: now),
                       _qburn_pts=lambda now=now: [(int(t), h, start + 5 * H) for t, h in rows if t <= now])
            b._qburn["out"] = None
            hd = b.quota_burn()["head"]
            seen.append((b._qburn["out"]["cur"]["now_pct"], hd["tok"], hd["since"]))
        s18 = [x for x in seen if x[0] == 18.0]
        self.assertEqual(len({x[1] for x in s18}), 1)           # was 253.1M -> 248.8M within one step (sawtooth)
        self.assertAlmostEqual(s18[0][1], 0.82 * 55_662_032 / 0.18, delta=2)
        self.assertEqual(s18[-1][2], 19 * 325_000)              # the not-yet-counted spend is still reported
        s20 = [x for x in seen if x[0] == 20.0]
        self.assertEqual(len({x[1] for x in s20}), 1)
        self.assertNotEqual(s20[0][1], s18[0][1])              # a new step is a real input


class HelperCase(unittest.TestCase):
    """Small pure helpers the burn chart relies on."""

    def test_cycles_split_on_reset_with_tolerance(self):
        pts = [(1, 1.0, 1000.0), (2, 2.0, 1000.0 + b.QBURN_TOL), (3, 0.0, 1000.0 + 18000)]
        cyc = b._qburn_cycles(pts)
        self.assertEqual(len(cyc), 2)
        self.assertEqual(cyc[0][1], [(1, 1.0), (2, 2.0)])

    def test_slope_zero_for_one_point_or_no_time_spread(self):
        self.assertEqual(b._qb_slope([(0, 5.0)]), 0.0)
        self.assertEqual(b._qb_slope([(10, 5.0), (10, 9.0)]), 0.0)
        self.assertAlmostEqual(b._qb_slope([(0, 0.0), (3600, 12.0)]), 12.0)

    def test_interp_out_of_range_is_none_and_duplicate_x_safe(self):
        s = [(0, 0.0), (100, 10.0), (100, 20.0)]
        self.assertIsNone(b._qb_interp(s, -1))
        self.assertIsNone(b._qb_interp(s, 101))
        self.assertEqual(b._qb_interp(s, 50), 5.0)
        self.assertIsNone(b._qb_interp([], 0))

    def test_quantile_interpolates_small_samples(self):
        self.assertEqual(b._qb_q([7.0], 0.5), 7.0)
        self.assertEqual(b._qb_q([0.0, 10.0], 0.25), 2.5)

    def test_epoch_parses_z_and_rejects_garbage(self):
        self.assertEqual(b._qb_epoch("1970-01-01T00:01:00Z"), 60.0)
        self.assertIsNone(b._qb_epoch("not a date"))


class QuotaPollCase(unittest.TestCase):
    """Poll interval and 429 backoff in sidereus/quota.py."""

    def setUp(self):
        self.p = _Patch(q)
        self.p.set(_calib={"until": 0.0})             # burn tests may have left calibration on
        self.saved = dict(q._quota)
        self.saved_ra = list(q._quota_retry_after)

    def tearDown(self):
        self.p.undo()
        q._quota.clear(); q._quota.update(self.saved)
        q._quota_retry_after[:] = self.saved_ra

    def interval(self, data, seat=""):
        self.p.set(_cc_seat=lambda: seat)
        q._quota["data"] = data
        return q._quota_interval()

    def test_interval_steps_by_5h_pct(self):
        self.assertEqual(self.interval({"five_hour": {"pct": 11}}), q.QUOTA_SLOW_S)
        self.assertEqual(self.interval({"five_hour": {"pct": 75}}), 120)
        self.assertEqual(self.interval({"five_hour": {"pct": 95}}), 60)
        self.assertEqual(self.interval({"five_hour": {"pct": None}}), q.QUOTA_SLOW_S)
        self.assertEqual(self.interval(None), q.QUOTA_SLOW_S)

    def test_interval_credit_seat_polls_every_minute(self):
        d = {"five_hour": {"pct": 0}, "extra": {"pct": 26.4}}
        self.assertEqual(self.interval(d, seat="enterprise_usage_based"), 60)

    def test_backoff_grows_to_cap_and_honours_retry_after(self):
        q._quota_retry_after[0] = 0
        self.assertEqual([q._wait_hint(n) for n in (1, 2, 3, 4, 5, 9)],
                         [30, 60, 120, 240, q.QUOTA_MAX_BACKOFF, q.QUOTA_MAX_BACKOFF])
        q._quota_retry_after[0] = 1000
        self.assertEqual(q._wait_hint(1), 1000)


class ProbeSwitchCase(unittest.TestCase):
    """The paid header probe is opt-in; the OMC cache is written only into an existing plugin dir."""

    def setUp(self):
        import os
        self.os = os
        self.p = _Patch(q)
        self.env = os.environ.pop(q.QUOTA_PROBE_ENV, None)
        self.calls = []
        self.p.set(_oauth_token=lambda: self.calls.append("tok") or None)

    def tearDown(self):
        self.p.undo()
        self.os.environ.pop(q.QUOTA_PROBE_ENV, None)
        if self.env is not None:
            self.os.environ[q.QUOTA_PROBE_ENV] = self.env

    def test_probe_off_by_default(self):
        self.p.set(CFG={})
        self.assertFalse(q._quota_probe_on())
        self.assertIsNone(q._quota_probe_hdr())
        self.assertEqual(self.calls, [])          # never even reads the token

    def test_probe_config_and_env(self):
        self.p.set(CFG={"quota_probe": True})
        self.assertTrue(q._quota_probe_on())
        self.os.environ[q.QUOTA_PROBE_ENV] = "0"
        self.assertFalse(q._quota_probe_on())
        self.p.set(CFG={})
        self.os.environ[q.QUOTA_PROBE_ENV] = "1"
        self.assertTrue(q._quota_probe_on())

    def test_omc_dir_never_created(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            missing = self.os.path.join(t, "oh-my-claudecode")
            self.p.set(OMC_CACHE=self.os.path.join(missing, ".usage-cache.json"))
            q._omc_cache_write({"five_hour": {"pct": 10}, "at": 1})
            self.assertFalse(self.os.path.exists(missing))
            self.os.mkdir(missing)
            q._omc_cache_write({"five_hour": {"pct": 10}, "at": 1})
            self.assertTrue(self.os.path.exists(q.OMC_CACHE))


if __name__ == "__main__":
    unittest.main()
