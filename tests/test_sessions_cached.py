"""Request/hook paths never run sessions() in their own thread — `sessions_cached` snapshot + background refresh (2026-09-29).
No live files: sessions() and the snapshot are replaced on sidereus.sessions; the refresh thread is joined."""
import threading
import time
import unittest

from tests import _clock
from tests._load import sidereus

S = sidereus("sessions")


class _TickingTime(object):
    """`time` stand-in: wall clock starts at _clock.NOW and advances with the monotonic clock.
    ⚠A fully frozen time() would stall sessions_snapshot_wait's deadline loop (left never shrinks)."""

    def __init__(self):
        self._t0 = time.monotonic()

    def time(self):
        return _clock.NOW + (time.monotonic() - self._t0)

    def __getattr__(self, name):
        return getattr(time, name)
ROWS = [{"sid": "s1", "cwd": "/w/p", "project": "p", "state": "wait", "plat": "cc"}]
# modules whose request-path callers moved to the snapshot helper — none may hold a sessions() binding again
REQUEST_MODULES = ("state", "timeline", "git", "git_view", "recent", "agent_brief", "routes_post", "burn_scan", "work")


class _Base(unittest.TestCase):
    def setUp(self):
        self.snap0, self.sess0, self.calls = dict(S._SNAP), S.sessions, []
        self.gate = threading.Event()
        self.time0, S.time = S.time, _TickingTime()

        def slow():                          # stands in for a 5-40 s cold sessions(): blocks until released
            self.calls.append(threading.current_thread().name)
            self.gate.wait(5)
            S._SNAP.update({"at": S.time.time(), "rows": [{"sid": "new"}]})
            return []
        S.sessions = slow

    def tearDown(self):
        self.gate.set()
        for t in threading.enumerate():
            if t.name == "sessions_refresh":
                t.join(5)
        S.sessions = self.sess0
        S.time = self.time0
        S._SNAP.update(self.snap0)

    def stale(self, age=300):
        S._SNAP.update({"at": S.time.time() - age, "rows": ROWS})


class Helper(_Base):
    def test_fresh_snapshot_no_refresh(self):
        S._SNAP.update({"at": S.time.time(), "rows": ROWS})
        self.assertEqual(S.sessions_cached(), (ROWS, True))
        self.assertEqual(self.calls, [])

    def test_stale_serves_last_rows_and_refreshes_once_in_background(self):
        self.stale()
        self.assertEqual(S.sessions_cached(wait=0.05), (ROWS, False))
        self.assertEqual(S.sessions_rows(wait=0.05), ROWS)          # joins the running refresh, no second one
        # one call, on the refresh thread: an inline sessions() would be recorded as MainThread
        self.assertEqual(self.calls, ["sessions_refresh"])

    def test_fast_refresh_is_waited_for(self):
        self.stale()
        self.gate.set()
        self.assertEqual(S.sessions_cached(wait=2), ([{"sid": "new"}], True))

    def test_no_snapshot_yet_gives_empty(self):
        S._SNAP.update({"at": 0, "rows": []})
        self.assertEqual(S.sessions_cached(wait=0.05), ([], False))


class Callers(_Base):
    def test_request_modules_hold_no_sessions_binding(self):
        for m in REQUEST_MODULES:
            self.assertFalse(hasattr(sidereus(m), "sessions"), m)

    def test_state_poll_serves_snapshot_under_slow_sessions(self):
        from tests.test_state_guard import _READERS
        st = sidereus("state")
        readers = {k: v for k, v in _READERS.items() if k != "sessions_cached"}
        saved = {k: getattr(st, k) for k in readers}
        self.addCleanup(lambda: [setattr(st, k, v) for k, v in saved.items()])
        for k, v in readers.items():
            setattr(st, k, v)
        self.stale(3)                          # previous 2.5 s poll's rows
        self.assertEqual(st.state()["sessions"], ROWS)
        # the stub blocks until the gate opens, so ROWS above came from the snapshot, not an inline call
        self.assertEqual(self.calls, ["sessions_refresh"])

    def test_allow_list_uses_snapshot(self):
        wk = sidereus("work")
        saved = list(wk._ALLOW)
        self.addCleanup(lambda: wk._ALLOW.__setitem__(slice(None), saved))
        wk._ALLOW[:] = [0, {}]
        self.stale()
        self.assertEqual(list(wk._allowed_cwds()), ["/w/p"])

    def test_mcp_and_scan_names_use_snapshot(self):
        self.stale()
        self.assertEqual(sidereus("agent_brief")._rows(), ROWS)
        bs = sidereus("burn_scan")
        self.assertEqual(bs._slug_name(sidereus("ident")._slug("/w/p")), bs._proj_name("/w/p") or "p")


if __name__ == "__main__":
    unittest.main()
