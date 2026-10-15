"""Quota history split by plan (quota._quota_log `plan`, burn_hist acct|plan, plan_shift cut, burn base/est/lim).
Fixtures only — module attributes patched; no live file, clock, thread or network."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from tests._load import sidereus, js_fn
from tests.test_saver_quota_js import i18n
from tests._node import node_e

q = sidereus("quota")
h = sidereus("burn_hist")
b = sidereus("burn")

W = 5 * 3600.0
NOW = 1_800_000_000.0
RESET = NOW + 3600
START = RESET - W


class _P(unittest.TestCase):
    def setUp(self):
        self._undo = []
        self.d = tempfile.mkdtemp()
        self.saved_hist, self.saved_cut, self.saved_lim = dict(h._hist), dict(h._plan_cut), dict(b._qb_lim)
        h._hist.update({"at": NOW - 60, "acct": {}, "busy": False, "loaded": True})
        h._plan_cut.clear()
        self.orig_save, self.orig_load = h._hist_save, h._hist_load
        self.patch(h, _plan_code=lambda: "pro", _hist_save=lambda: None, _hist_load=lambda: None,
                   _hist_start=lambda: None)

    def tearDown(self):
        for m, k, v in reversed(self._undo):
            setattr(m, k, v)
        h._hist.clear(); h._hist.update(self.saved_hist)
        h._plan_cut.clear(); h._plan_cut.update(self.saved_cut)
        b._qb_lim.clear(); b._qb_lim.update(self.saved_lim)
        shutil.rmtree(self.d, ignore_errors=True)

    def patch(self, m, **kw):
        for k, v in kw.items():
            self._undo.append((m, k, getattr(m, k)))
            setattr(m, k, v)


class Log(_P):
    def test_row_carries_plan_and_plan_change_logs(self):
        p = os.path.join(self.d, "quota-log.jsonl")
        acct = {"at": 0, "mt": 0, "id": "A", "seat": None, "tier": "default_claude_pro", "org": "claude_x"}
        self.patch(q, QUOTA_LOG=p, _cc_account=lambda: "A", _acct=acct, _qlog_last=[None])
        d = {"five_hour": {"pct": 10, "resets_at": "x"}, "seven_day": {"pct": 2}}
        q._quota_log(d, NOW, "t")
        q._quota_log(d, NOW, "t")                                 # unchanged: deduped
        acct["tier"] = "default_claude_max_5x"
        q._quota_log(d, NOW, "t")                                 # same % on a new plan: logged
        with open(p, encoding="utf-8") as f:
            rows = [json.loads(ln) for ln in f]
        self.assertEqual([r["plan"] for r in rows], ["default_claude_pro", "default_claude_max_5x"])
        acct["tier"] = None
        self.assertEqual(q._plan_code(), "claude_x")              # org when no tier


class Split(_P):
    def test_groups_by_acct_plan_untagged_stays_acct(self):
        rs = "1970-01-01T05:00:00Z"
        log = [{"t": 0, "h5": 10, "d7": 1, "reset5": rs, "acct": "a"},
               {"t": 600, "h5": 20, "d7": 4, "reset5": rs, "acct": "a"},
               {"t": 1200, "h5": 21, "d7": 5, "reset5": rs, "acct": "a", "plan": "pro"},
               {"t": 1800, "h5": 31, "d7": 8, "reset5": rs, "acct": "a", "plan": "pro"},
               {"t": 2400, "h5": 32, "d7": 9, "reset5": rs, "acct": "a", "plan": "max"},
               {"t": 3000, "h5": 52, "d7": 12, "reset5": rs, "acct": "a", "plan": "max"}]
        ev = [(300, 9e6), (1500, 1e6), (2700, 100e6)]
        out = h.hist_compute(log, ev, 10 * W)
        self.assertEqual(sorted(out), ["a", "a|max", "a|pro"])
        self.assertEqual((out["a"]["h5_per_pct"], out["a|pro"]["h5_per_pct"], out["a|max"]["h5_per_pct"]),
                         (900000, 100000, 5000000))
        self.assertEqual((out["a"]["wk_per_pct"], out["a|max"]["wk_per_pct"]), (3000000, 33333333))
        cut = h.hist_compute(log, ev, 10 * W, {"a": 2400})          # cut drops every older row of that account
        self.assertEqual(sorted(cut), ["a|max"])

    def test_est_prefers_acct_plan(self):
        h._hist["acct"] = {"a": {"h5_per_pct": 1, "h5_n": 1}, "a|pro": {"h5_per_pct": 7, "h5_n": 4}}
        self.assertEqual(h.burn_est({"ok": True, "cur": {"now_pct": 0.0}}, "a", now=NOW)["h5_per_pct"], 7)
        self.patch(h, _plan_code=lambda: "max")
        self.assertEqual(h.burn_est({"ok": True, "cur": {"now_pct": 0.0}}, "a", now=NOW)["h5_per_pct"], 1)


class Shift(unittest.TestCase):
    def test_ratio_and_floors(self):
        self.assertTrue(h.plan_shift(5e6, 5, 1e6, 3))          # 5x at 5%
        self.assertFalse(h.plan_shift(1.8e6, 20, 1e6, 3))      # model-mix range
        self.assertFalse(h.plan_shift(5e6, 3, 1e6, 3))         # 3%: integer rounding too coarse
        self.assertTrue(h.plan_shift(0.4e6, 20, 1e6, 3))       # downgrade
        self.assertFalse(h.plan_shift(5e6, 20, 1e6, 2))        # too little history
        self.assertFalse(h.plan_shift(5e6, 20, None, 0))


class PlanEst(unittest.TestCase):
    def body(self, pct, per=1_000_000, src="win", wk=None):
        return {"ok": True, "cur": {"now_pct": pct}, "head": {"per_pct": per, "src": src, "wk": wk}}

    def test_own_window_estimate_is_low_confidence(self):
        e = h.plan_est(self.body(18.0, wk={"lim": 3e9, "used": 1e9}))
        self.assertEqual((e["low"], e["h5_left"], e["wk_left"], e["wk_used"]), (True, 82_000_000, 2_000_000_000, 1_000_000_000))
        self.assertIsNone(h.plan_est(self.body(18.0, src="step"))["wk_left"])   # no 7d measurement: 5h only

    def test_none_below_floor_or_without_per_pct(self):
        self.assertIsNone(h.plan_est(self.body(1.0)))
        self.assertIsNone(h.plan_est(self.body(18.0, per=0)))
        self.assertIsNone(h.plan_est(self.body(18.0, src="anchor")))
        self.assertIsNone(h.plan_est({"ok": False}))


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PlanEstJs(unittest.TestCase):
    def test_left_renders_with_low_hint(self):
        src = ("var document = {getElementById: () => null};\n" + i18n() + "\n" + js_fn("burnEstTip") + "\n" + js_fn("burnEst") + """
const b = {est_why: 'plan', est: {low: true, h5_left: 82000000, wk_left: null, h5_n: 0, wk_n: 0}};
process.stdout.write(JSON.stringify([burnEst(b, '5h', 1e6, 18), burnEst(b, '7d', null, 5)]));""")
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        e5, e7 = json.loads(r.stdout)
        self.assertEqual(e5["left"], 82000000)
        self.assertIn("정확도 낮음", e5["tip"])
        self.assertIsNone(e7)


class Current(_P):
    def setUp(self):
        super().setUp()
        self.ev = []
        self.patch(b, _cc_account=lambda: "A", _qwk_pts=lambda: [], _tok_events=lambda t0: self.ev,
                   _qb_lim_set=lambda *a, **k: None, _qb_lim_load=lambda: None, _anchors=lambda: {},
                   quota_calibrating=lambda on: None, _qb_week=lambda now: None)
        b._qb_lim.update({"lim": 0.0, "at": 0.0, "loaded": True, "acct": None})
        self.patch(b, _qburn=dict(b._qburn, plan={}))
        h._hist["acct"] = {"A": {"h5_per_pct": 1_000_000, "h5_n": 5, "h5_src": "med"}}
        self.past = [(START - (k + 1) * W + W, [(START - (k + 1) * W + 600, 10.0), (START - (k + 1) * W + 7200, 40.0)])
                     for k in range(3)][::-1]

    def run_cur(self, rows):
        return b._qb_current(NOW, self.past + [(RESET, rows)], RESET, rows)

    def test_cut_drops_old_plan_bases_and_est(self):
        self.ev = [(START + 60, 50_000_000)]                    # 50M for 10% -> 5M/% vs 1M/% history
        out = self.run_cur([(START + 600, 2.0), (NOW - 300, 10.0)])
        self.assertEqual(h._plan_cut["A"]["t"], START)
        self.assertEqual((out["base"]["n"], out["base"]["why"]), (0, "plan"))
        self.patch(b, _qburn_pts=lambda: [(int(t), hh, R) for R, rw in self.past for t, hh in rw]
                   + [(int(START + 600), 2.0, RESET), (int(NOW - 300), 10.0, RESET)],
                   _qb_add_wk=lambda out: None)
        body = b._qb_body(NOW)[0]
        e = body["est"]                                         # this window's own 5M/% stands in, flagged low
        self.assertEqual((body["est_why"], e["low"], e["h5_per_pct"], e["h5_left"]), ("plan", True, 5_000_000, 450_000_000))
        h._hist["at"] = NOW + 1                                 # a pass after the cut: history is the new plan's
        self.assertNotIn("est_why", b._qb_body(NOW)[0])

    def test_empty_history_falls_back_to_own_window(self):
        out = {"ok": True, "cur": {"now_pct": 23.0}, "head": {"per_pct": 2_560_657, "src": "win"}, "est": None}
        h.est_fill(out, "A")                                    # no cut: history simply has nothing yet
        self.assertEqual((out["est_why"], out["est"]["low"], out["est"]["h5_left"]), ("hist", True, 197_170_589))
        h._plan_cut["A"] = {"t": START, "set": NOW - 3600}      # cut already folded into the table
        out["est"] = None; h.est_fill(out, "A")
        self.assertEqual(out["est_why"], "plan")
        kept = {"ok": True, "est": {"h5_left": 1}}; h.est_fill(kept, "A")
        self.assertEqual((kept["est"], "est_why" in kept), ({"h5_left": 1}, False))   # history est wins
        none = {"ok": True, "cur": {"now_pct": 1.0}, "head": {"per_pct": 5, "src": "win"}, "est": None}
        h.est_fill(none, "A")
        self.assertEqual((none["est"], "est_why" in none), (None, False))

    def test_same_plan_keeps_bases(self):
        self.ev = [(START + 60, 12_000_000)]                    # 1.2M/%: same plan
        out = self.run_cur([(START + 600, 2.0), (NOW - 300, 10.0)])
        self.assertNotIn("A", h._plan_cut)
        self.assertEqual(out["base"]["n"], 3)
        self.assertNotEqual(out["base"]["why"], "plan")

    def test_manual_reset_counts_from_the_drop(self):
        # tokens before the drop are the old reset's; per-% uses only the 50M after it over 10%, cut = window start
        self.ev = [(START + 60, 900_000_000), (START + 1900, 50_000_000)]
        self.run_cur([(START + 600, 30.0), (START + 1200, 40.0), (START + 1800, 2.0), (NOW - 300, 12.0)])
        self.assertEqual(h._plan_cut["A"]["t"], START)

    def test_cut_survives_plan_code_change_and_only_moves_forward(self):
        h._plan_cut["A"] = {"t": START, "set": NOW}
        self.patch(h, _plan_code=lambda: "max")
        self.assertEqual(h.plan_cut("A"), (START, True))
        h.plan_cut_set("A", START - W, NOW)
        self.assertEqual(h._plan_cut["A"]["t"], START)
        # legacy untagged windows before the cut stay out of the baseline even once rows carry the new code
        out = self.run_cur([(START + 600, 2.0), (NOW - 300, 10.0)])
        self.assertEqual((out["base"]["n"], out["base"]["why"]), (0, "plan"))
        log = [{"t": START - 600, "h5": 10, "d7": 1, "reset5": "x", "acct": "A"},
               {"t": START + 600, "h5": 10, "d7": 1, "reset5": "x", "acct": "A", "plan": "max"}]
        self.assertEqual(list(h.hist_compute(log, [], NOW, {"A": START})), ["A|max"])   # legacy "A" row cut

    def test_cut_round_trips_through_the_cache(self):
        self.patch(h, HIST_CACHE=os.path.join(self.d, "burn-hist-cache.json"), _hist_save=self.orig_save,
                   _hist_load=self.orig_load)
        h.plan_cut_set("A", START, NOW)
        h._plan_cut.clear()                                     # fresh process: nothing in memory
        h._hist.update({"at": 0.0, "acct": {}, "loaded": False})
        self.assertEqual(h.plan_cut("A"), (None, False))        # memory only until the body loads
        self.patch(b, _qburn_pts=lambda: [(int(t), hh, R) for R, rw in self.past for t, hh in rw]
                   + [(int(START + 600), 2.0, RESET), (int(NOW - 300), 10.0, RESET)], _qb_add_wk=lambda out: None)
        body = b._qb_body(NOW)[0]
        self.assertEqual((body["base"]["why"], body["est_why"]), ("plan", "plan"))
        self.assertEqual(h.plan_cut("A"), (START, True))

    def test_base_prefers_current_plan_windows(self):
        past = [(R, [(t, 5.0) for t in (R - W + 600, R - W + 1200)]) for R in (START - W, START, START + 0.5)]
        tags = {int(past[1][1][0][0]): "max", int(past[2][1][1][0]): "max", int(past[0][1][0][0]): "pro"}
        self.patch(h, _plan_code=lambda: "max")
        self.assertEqual(h.plan_past("A", past, tags), past[1:])           # untagged + other-plan dropped
        self.assertEqual(h.plan_past("A", past, {}), past)                  # no tagged rows: all kept
        self.patch(h, _plan_code=lambda: "team")
        self.assertEqual(h.plan_past("A", past, tags), past)                # nothing on this plan: all kept

    def test_held_lim_older_than_cut_is_stale(self):
        b._qb_lim.update({"lim": 5e8, "at": START - 600, "acct": "A"})
        self.assertFalse(b._qb_lim_stale(START, START))
        h._plan_cut["A"] = {"t": START, "set": NOW, "plan": "pro"}
        self.assertTrue(b._qb_lim_stale(START, START))
        b._qb_lim["at"] = START + 600
        self.assertFalse(b._qb_lim_stale(START, START))


if __name__ == "__main__":
    unittest.main()
