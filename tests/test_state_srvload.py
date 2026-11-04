"""/api/state under machine load: no subprocess on the request thread, a young sessions snapshot is served without
waiting, and `srvLoad` {load1, snapAge, slow}. No live files, clock or network: git helpers, sessions() and every
state() reader are replaced on their owning modules; blocked background threads are released and joined."""
import threading
import time
import unittest
from unittest import mock

from tests import _clock
from tests._load import sidereus

S = sidereus("sessions")
st = sidereus("state")
rv = sidereus("review")
PQ = sidereus("pl_reqs")
HSC = sidereus("harness_selfcheck")
SHA = "a" * 40


class _TickingTime(object):
    """`time` stand-in starting at _clock.NOW; advances with the monotonic clock so wait loops still end."""

    def __init__(self):
        self._t0 = time.monotonic()

    def time(self):
        return _clock.NOW + (time.monotonic() - self._t0)

    def __getattr__(self, name):
        return getattr(time, name)


class _Gate(unittest.TestCase):
    def setUp(self):
        self.gate = threading.Event()
        self.addCleanup(self._release)

    def _release(self):
        self.gate.set()
        for t in threading.enumerate():
            if t.name in ("bg-refresh", "sessions_refresh"):
                t.join(5)

    def fast(self, fn, *a):
        t0 = time.monotonic()
        out = fn(*a)
        self.assertLess(time.monotonic() - t0, 0.5)
        return out


class NoSubprocessOnRequest(_Gate):
    def test_review_poll_serves_cache_while_git_blocks(self):
        ck = ("/r", ("a.py",))
        old = {"at": 0.0, "head": "c0", "files": {"a.py": ("M", 1, 0)}}
        with mock.patch.object(rv, "_RV_CACHE", sidereus("memo").BoundedMemo(8)), \
                mock.patch.object(rv, "_root_stat", lambda *a: self.gate.wait(5)):
            self.assertIsNone(self.fast(rv._root_stat_bg, "/r", ["a.py"], 100.0))   # cold: unknown, not blocked
            rv._RV_CACHE.put(ck, old)
            self.assertIs(self.fast(rv._root_stat_bg, "/r", ["a.py"], 100.0), old)  # stale: last answer served

    def test_fix_commit_does_not_wait_for_git_log(self):
        def slow(repo, at):
            self.gate.wait(5)
            return "b2b2b2b\t%d\n" % (at + 5)
        with mock.patch.object(PQ, "_git_log", slow), mock.patch.object(PQ, "_FIX_CACHE", {}):
            self.assertEqual(self.fast(PQ._fix_commit, "/r", 1000, 2000.0), "")
            self.assertEqual(self.fast(PQ._fix_commit, "/r", 1000, 2000.0), "")    # one lookup in flight, no second
            self._release()
            self.assertEqual(PQ._fix_commit("/r", 1000, 2000.0), "b2b2b2b")

    def test_selfcheck_head_does_not_wait_for_git(self):
        g = mock.Mock(returncode=0, stdout=SHA + "\n")
        with mock.patch.dict(HSC._HSC_MEMO, clear=True), mock.patch.object(HSC, "_now", lambda: 100.0), \
                mock.patch.object(HSC.gitinfo, "_git_run", lambda *a, **k: self.gate.wait(5) and g):
            self.assertEqual(self.fast(HSC._head, "/r"), "")
            self._release()
            self.assertEqual(HSC._head("/r"), SHA)


class YoungSnapshot(_Gate):
    ROWS = [{"sid": "s1"}]

    def setUp(self):
        super().setUp()
        self.snap0, self.sess0, self.time0 = dict(S._SNAP), S.sessions, S.time
        S.time = _TickingTime()
        S.sessions = lambda: self.gate.wait(5) and []
        self.addCleanup(self._restore)

    def _restore(self):
        self._release()
        S.sessions, S.time = self.sess0, self.time0
        S._SNAP.update(self.snap0)

    def test_young_snapshot_served_without_wait(self):
        S._SNAP.update({"at": S.time.time() - 3, "rows": self.ROWS})
        got = self.fast(S.sessions_cached, 2, st.STATE_FRESH_S, st.STATE_COLD_S, st.STATE_SERVE_S)
        self.assertEqual(got, (self.ROWS, False))

    def test_old_snapshot_still_waits(self):
        S._SNAP.update({"at": S.time.time() - 300, "rows": self.ROWS})
        t0 = time.monotonic()
        self.assertEqual(S.sessions_cached(0.2, 1.0, None, st.STATE_SERVE_S), (self.ROWS, False))
        self.assertGreaterEqual(time.monotonic() - t0, 0.15)

    def test_snapshot_age_unknown_before_first(self):
        S._SNAP.update({"at": 0, "rows": []})
        self.assertIsNone(S.snapshot_age())


class SrvLoad(unittest.TestCase):
    def setUp(self):
        self.t = [0.0]
        tick = self.t

        def cost(sec, val):
            def f(*a, **k):
                tick[0] += sec
                return val
            return f
        readers = {
            "_tick": lambda: tick[0], "_loadavg": lambda: (1.25, 1.0, 1.0), "snapshot_age": lambda: 2.36,
            "quota": cost(0.0, None), "sessions_cached": cost(0.0, ([], True)), "cards": lambda n=50: [],
            "usage": cost(0.125, None), "selfcheck": lambda s: None, "health": lambda: None,
            "cards_read": lambda: "", "cards_read_ids": lambda: [], "presence": lambda: {},
            "ack_map": lambda cut=None: {}, "messages": lambda since=0: [], "messages_first": lambda: [],
            "cursors": lambda: {}, "_load": lambda name, d: d, "_ack_cut": lambda: 0,
            "attention": cost(0.5, {"rows": []}), "wt_orders": cost(0.375, {}), "quota_who": cost(0.3125, None),
            "review": lambda rows: None, "_saver_state": lambda pct, left=None: None, "_saver_view": lambda: None,
            "_saver_switch": lambda: None, "ext_usage_today": lambda: {}, "state_off": lambda: set(),
        }
        p = mock.patch("os.cpu_count", lambda: 12)   # no live machine facts
        p.start()
        self.addCleanup(p.stop)
        for k, v in readers.items():
            p = mock.patch.object(st, k, v)
            p.start()
            self.addCleanup(p.stop)

    def test_shape_and_slowest_first(self):
        s = st.state()["srvLoad"]
        self.assertEqual(s, {"load1": 1.25, "ncpu": 12, "snapAge": 2.4,
                             "slow": [["attention", 500], ["wtOrder", 375], ["quotaWho", 312]], "top": None})

    def test_unknown_is_none_and_cap(self):
        with mock.patch.object(st, "_loadavg", None), mock.patch.object(st, "snapshot_age", lambda: None), \
                mock.patch.object(st, "SLOW_PIECE_MS", 0):
            s = st.state()["srvLoad"]
        self.assertEqual((s["load1"], s["snapAge"]), (None, None))
        with mock.patch("os.cpu_count", lambda: None):
            self.assertIsNone(st.state()["srvLoad"]["ncpu"])
        self.assertEqual(len(s["slow"]), st.SLOW_MAX)
        self.assertEqual([x[1] for x in s["slow"]], sorted((x[1] for x in s["slow"]), reverse=True))

    def test_loadavg_error_is_none(self):
        def bad():
            raise OSError("no load")
        with mock.patch.object(st, "_loadavg", bad):
            self.assertIsNone(st.state()["srvLoad"]["load1"])


if __name__ == "__main__":
    unittest.main()
