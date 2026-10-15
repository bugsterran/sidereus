"""Plan metadata (`quota._cc_plan`) and the account-stamped 5h limit cache (`burn._qb_lim_*`).
No live files: ~/.claude.json and qb-lim-cache.json point at temp files; `_tok_events`/`_anchors` are patched."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

q = sidereus("quota")
b = sidereus("burn")


class _Patch(unittest.TestCase):
    def setUp(self):
        self._undo = []
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        for m, k, v in reversed(self._undo):
            setattr(m, k, v)
        shutil.rmtree(self.d, ignore_errors=True)

    def patch(self, m, **kw):
        for k, v in kw.items():
            self._undo.append((m, k, getattr(m, k)))
            setattr(m, k, v)


class Plan(_Patch):
    def test_reads_tier_codes_only(self):
        p = os.path.join(self.d, "claude.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"oauthAccount": {"accountUuid": "u1", "emailAddress": "x@y", "organizationName": "Org",
                                        "userRateLimitTier": "default_claude_max_5x", "seatTier": "team_tier_1",
                                        "organizationType": "claude_team"}}, f)
        self.patch(q, CLAUDE_CONF=p, _acct={"at": 0, "mt": 0, "id": None, "seat": None, "tier": None, "org": None})
        self.assertEqual(q._cc_plan(), {"tier": "default_claude_max_5x", "seat": "team_tier_1", "org": "claude_team"})

    def test_unknown_is_none(self):
        self.patch(q, _cc_account=lambda: None, _acct={"at": 0, "mt": 0, "id": None, "seat": None, "tier": None, "org": None})
        self.assertIsNone(q._cc_plan())


class LimStale(_Patch):
    NOW, START = 1_800_000_000.0, 1_800_000_000.0 - 3600

    def setUp(self):
        super().setUp()
        self.acct = "A"
        self.patch(b, QB_LIM_CACHE=os.path.join(self.d, "qb-lim-cache.json"), _cc_account=lambda: self.acct,
                   _qb_lim={"lim": 0.0, "at": 0.0, "loaded": True, "acct": None, "reset": 0.0, "seg": 0.0},
                   _tok_events=lambda t0: [], _anchors=lambda: {}, _qb_lim_load=lambda: None)

    def test_set_stamps_account_and_window(self):
        b._qb_lim_set(1.5e8, self.NOW, self.START + b.QBURN_WIN, self.START)
        with open(b.QB_LIM_CACHE, encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual((d["acct"], d["reset"], d["seg"]), ("A", self.START + b.QBURN_WIN, self.START))

    def test_recent_used_for_same_account(self):
        b._qb_lim_set(1.5e8, self.NOW - 600, self.START + b.QBURN_WIN, self.START)
        lim, src, _u = b._qb_limit(self.NOW, self.START, 20.0, [], (self.START, 0.0))
        self.assertEqual((lim, src), (1.5e8, "recent"))

    def test_account_switch_discards(self):
        b._qb_lim_set(1.5e8, self.NOW - 600, self.START + b.QBURN_WIN, self.START)
        self.acct = "B"
        lim, src, _u = b._qb_limit(self.NOW, self.START, 20.0, [], (self.START, 0.0))
        self.assertEqual((lim, src), (0.0, None))
        self.assertEqual(b._qb_lim["lim"], 0.0)

    def test_tokens_paired_with_the_logged_pct(self):
        # 20% logged 300 s ago; 40M more burned since. The denominator must not grow between polls.
        t_obs = self.NOW - 300
        ev = [(self.START + 60, 30_000_000), (t_obs - 10, 10_000_000), (self.NOW - 100, 40_000_000)]
        self.patch(b, _tok_events=lambda t0: ev, _qb_lim_set=lambda *a, **k: None)
        lim, src, _u = b._qb_limit(self.NOW, self.START, 20.0, [], (self.START, 0.0), t_obs)
        self.assertEqual((lim, src), (2e8, "win"))                         # 40M / 20%, not 80M / 20%
        self.patch(b, _qb_week=lambda now: None)
        head = b._qb_head(self.NOW, self.START, 20.0, 3600, 10.0, lim, src, after=40_000_000)
        self.assertEqual((head["tok"], head["used"]), (120_000_000, 80_000_000))   # live: 80% of 200M - 40M

    def test_step_start_is_first_log_of_current_pct(self):
        rows = [(100, 91.0), (200, 92.0), (300, 92.0), (400, 92.0)]
        self.assertEqual(b._qb_step_at(rows, 0), 200)       # not 400: a still % must not grow the denominator
        self.assertEqual(b._qb_step_at(rows, 250), 300)     # never before the segment start
        self.assertEqual(b._qb_step_at([(50, 5.0)], 0), 50)

    def test_unknown_account_uses_segment_cut(self):
        self.acct = None
        b._qb_lim_set(1.5e8, self.NOW - 1200, None, None)
        self.assertFalse(b._qb_lim_stale(self.START, self.START))          # plain window: same cap held
        self.assertTrue(b._qb_lim_stale(self.START, self.NOW - 900))       # stamped before a mid-window cut



if __name__ == "__main__":
    unittest.main()
