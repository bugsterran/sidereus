"""Worktree work-unit signals: session -> worktree token aggregation and card order. Synthetic data only."""
import threading
import time
import unittest

from tests._load import sidereus

g = sidereus("git_wt")
git = sidereus("git")   # owner of _branch_cache

MAIN = "/repo/app"
WT = "/repo/app/.claude/worktrees/fix-x"
PATHS = [MAIN, WT]
START, MID = 10_000, 3_000


class WtTokens(unittest.TestCase):
    def rows(self):
        return [{"sid": "s-main", "cwd": MAIN + "/web", "wt": {"root": MAIN}},
                {"sid": "s-wt", "cwd": WT + "/sidereus", "wt": {"root": "/private" + WT}},   # /private realpath form
                {"sid": "s-out", "cwd": "/elsewhere"}]

    def test_longest_prefix_and_subagents_to_parent(self):
        sid_root = g._sid_roots(self.rows())
        # s-wt twice in one bucket window: its own turn + its subagent (already folded under the parent sid)
        cyc = {START: {"s-main": 100, "s-wt": 40, "s-out": 60}, START + 300: {"s-wt": 10}}
        day = {MID: {"s-wt": 5}, MID - 300: {"s-wt": 999}, START: {"s-main": 100, "s-wt": 50}}
        out, total = g.wt_tokens(PATHS, sid_root, cyc, day, START, MID)
        self.assertEqual(out[WT], {"cyc": 50, "day": 55})       # nested worktree wins over the main checkout
        self.assertEqual(out[MAIN], {"cyc": 100, "day": 100})
        self.assertEqual(total, 210)                            # unmatched sessions still count in the 5h total

    def test_old_bucket_outside_cycle_ignored(self):
        out, total = g.wt_tokens(PATHS, {"a": MAIN}, {START - 600: {"a": 7}}, {}, START, MID)
        self.assertEqual((out[MAIN]["cyc"], total), (0, 0))

    def test_remembered_sid_survives(self):
        m = g._sid_roots([], {"old": WT})
        self.assertEqual(g._wt_pick(m["old"], {g._wt_key(p) for p in PATHS}), WT)


NOW = 1_000_000


def _wt_order(cards):
    """Server card order (git_wt.wt_order). cards = [(path, score, live, act)] in input order.
    score -> one attention row with a non-list-only signal; live -> one live session whose age never beats `act`."""
    wts = [{"path": "/r/" + c[0]} for c in cards]
    sig = {"/r/" + p: {"chg": act} for p, _sc, _lv, act in cards}
    sess, attn = [], []
    for p, sc, lv, _act in cards:
        sid = "s-" + p
        sess.append({"sid": sid, "cwd": "/r/" + p, "state": "tool" if lv else "done", "ageSec": NOW})
        if sc:
            attn.append({"sid": sid, "score": sc, "sigs": [{"k": "done"}, {"k": "ask"}]})
    return [x[3:] for x in g.wt_order(wts, sig, sess, attn, now=NOW)]


class WtSort(unittest.TestCase):
    def test_attention_then_live_then_recent(self):
        cards = [("quiet-old", 0, False, 100), ("live", 0, True, 50), ("hot", 90, False, 10),
                 ("hotter", 100, False, 5), ("quiet-new", 0, False, 200)]
        self.assertEqual(_wt_order(cards), ["hotter", "hot", "live", "quiet-new", "quiet-old"])

    def test_full_tie_keeps_input_order(self):
        self.assertEqual(_wt_order([("b", 0, True, 7), ("a", 0, True, 7), ("c", 0, False, 7)]), ["b", "a", "c"])

    def test_list_only_attention_and_nested_worktree(self):
        wts = [{"path": MAIN, "main": True}, {"path": WT}]
        sess = [{"sid": "m", "cwd": MAIN, "state": "done"},
                {"sid": "w", "cwd": WT + "/sidereus", "wt": {"root": "/private" + WT}, "state": "done"}]
        # list-only kinds never rank; a real signal on the nested worktree's session lifts that card, not the main one
        self.assertEqual(g.wt_order(wts, {}, sess, [{"sid": "w", "score": 50, "sigs": [{"k": "gone"}]}], now=NOW), [MAIN, WT])
        self.assertEqual(g.wt_order(wts, {}, sess, [{"sid": "w", "score": 50, "sigs": [{"k": "fail"}]}], now=NOW), [WT, MAIN])

    def test_live_activity_beats_old_change(self):
        wts = [{"path": MAIN}, {"path": WT}]
        sess = [{"sid": "a", "cwd": MAIN, "state": "tool", "ageSec": 10}, {"sid": "b", "cwd": WT, "state": "tool", "ageSec": 5}]
        self.assertEqual(g.wt_order(wts, {MAIN: {"chg": NOW}}, sess, [], now=NOW), [MAIN, WT])
        self.assertEqual(g.wt_order(wts, {}, sess, [], now=NOW), [WT, MAIN])

    def test_poll_orders_from_branch_cache(self):
        saved = dict(git._branch_cache)
        try:
            git._branch_cache.clear()
            wts = [{"path": MAIN}, {"path": WT}]
            git._branch_cache[("/repo/app", 80)] = (1, {"worktrees": wts, "wtSig": {MAIN: {"chg": 9}, WT: {"chg": 1}}})
            git._branch_cache[("/repo/app", 30)] = (2, {"worktrees": wts, "wtSig": {MAIN: {"chg": 1}, WT: {"chg": 9}}})
            git._branch_cache[("/repo/one", 80)] = (1, {"worktrees": [{"path": "/repo/one"}], "wtSig": {}})
            self.assertEqual(g.wt_orders([], {"rows": []}, now=NOW), {"/repo/app": [WT, MAIN]})   # newest entry per cwd
        finally:
            git._branch_cache.clear()
            git._branch_cache.update(saved)


class WtRowsSource(unittest.TestCase):
    """wt_signals takes sid roots from the poll's sessions snapshot; stale -> background refresh, never in-thread."""
    ROWS = [{"sid": "s-main", "cwd": MAIN, "wt": {"root": MAIN}}, {"sid": "s-wt", "cwd": WT}]
    WTS = [{"path": MAIN, "main": True, "branch": "master", "head": "a1"},
           {"path": WT, "branch": "fix-x", "head": "b2"}]          # paths do not exist -> no git calls

    def setUp(self):
        s = sidereus("sessions")
        q = sidereus("quota")
        self.saved = [(g, k, getattr(g, k)) for k in ("quota_who", "_wt_fold")]
        self.saved += [(q, "quota", q.quota), (s, "sessions", s.sessions)]
        self.snap0 = dict(s._SNAP)
        self.calls = []
        g.quota_who = lambda qq, now: {"start": START}
        g._wt_fold = lambda now=None: (MID, {MID: {"s-wt": 5}}, MID)
        q.quota = lambda: {}

        def fake_sessions():            # the refresh: records which thread ran it, then fills the snapshot
            self.calls.append(threading.current_thread().name)
            s._SNAP.update({"at": time.time(), "rows": self.ROWS})
            return self.ROWS
        s.sessions = fake_sessions
        self.thr = list(g._WT_THR)
        g._WT_THR[:] = [object()]                                  # never start the fold thread in tests
        with g._usage_lock:
            self.byc = g._usage.get("byc")
            g._usage["byc"] = {START: {"s-main": 30, "s-wt": 10}}

    def tearDown(self):
        for mod, k, v in self.saved:
            setattr(mod, k, v)
        sidereus("sessions")._SNAP.update(self.snap0)
        g._WT_THR[:] = self.thr
        with g._usage_lock:
            g._usage["byc"] = self.byc
        g._WT_SID.clear()

    def sig(self, **kw):
        g._WT_SID.clear()
        return g.wt_signals(self.WTS, [], [], now=START + 100, **kw)

    def test_fresh_snapshot_served_without_sessions_call(self):
        sidereus("sessions")._SNAP.update({"at": time.time() - 30, "rows": self.ROWS})
        out = self.sig()
        self.assertEqual(self.calls, [])
        self.assertEqual(out, self.sig(rows=self.ROWS))            # same dict as the explicit-rows path
        self.assertEqual(out["wtSig"][WT]["cyc"], 10)

    def test_no_or_stale_snapshot_refreshes_in_background(self):
        s = sidereus("sessions")
        for at in (0, time.time() - g.WT_SNAP_S - 5):
            s._SNAP.update({"at": at, "rows": []})
            self.calls.clear()
            out = self.sig()
            self.assertEqual(self.calls, ["sessions_refresh"])     # never the request thread
            self.assertEqual(out, self.sig(rows=self.ROWS))

    def test_snapshot_helper_age(self):
        s = sidereus("sessions")
        s._SNAP.update({"at": time.time() - 10, "rows": ["r"]})
        self.assertEqual(s.sessions_snapshot(60), ["r"])
        self.assertIsNone(s.sessions_snapshot(5))


if __name__ == "__main__":
    unittest.main()
