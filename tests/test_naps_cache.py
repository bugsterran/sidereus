"""naps(): a stale cache is served at once and refreshed in the background.

`_naps_fetch` is monkeypatched — pmset is never run.
"""
import threading
import time
import unittest

from tests._load import sidereus

tl = sidereus("timeline_scan")      # naps and its cache/fetch live here since the 2026-09-24 split


class _Clock:
    """Real `time` module with `time()` pinned — patched onto timeline_scan only (the refresh runs in a worker thread)."""
    def __init__(self, t):
        self.t = t

    def time(self):
        return self.t

    def __getattr__(self, name):
        return getattr(time, name)


NOW = time.mktime((2026, 9, 24, 12, 30, 0, 0, 0, -1))


class NapsCache(unittest.TestCase):
    def setUp(self):
        self.patch(tl, time=_Clock(NOW))
        self.saved = (tl._naps_fetch, dict(tl._naps_cache))
        self.calls = 0
        self.gate = threading.Event()
        self.done = threading.Event()

    def patch(self, mod, **kw):
        for k, v in kw.items():
            self.addCleanup(setattr, mod, k, getattr(mod, k))
            setattr(mod, k, v)

    def tearDown(self):
        tl._naps_fetch = self.saved[0]
        tl._naps_cache.clear()
        tl._naps_cache.update(self.saved[1])

    def fetch(self, val, block=False):
        def f():
            self.calls += 1
            if block:
                self.gate.wait(2)
            self.done.set()
            return val
        return f

    # The empty-cache (first call) case lives in tests/test_naps_cold.py: it no longer waits.

    def test_stale_served_while_refreshing(self):
        now = NOW
        old = [(now - 900, now - 800)]
        tl._naps_cache.clear(); tl._naps_cache.update({"at": now - tl.NAP_TTL_S - 5, "v": old})
        tl._naps_fetch = self.fetch([(now - 300, now - 100)], block=True)
        real_refresh, refreshed = tl._naps_refresh, threading.Event()

        def refresh():
            try:
                real_refresh()
            finally:
                refreshed.set()
        tl._naps_refresh = refresh
        self.addCleanup(setattr, tl, "_naps_refresh", real_refresh)
        # The fetch cannot finish before gate is set, so getting the stale value here proves naps() did not wait.
        self.assertEqual(tl.naps(1), [[int(now - 900), int(now - 800)]])
        self.assertFalse(self.gate.is_set())
        self.assertTrue(tl._naps_cache.get("busy"))
        tl.naps(1)                                                          # second stale call spawns no second refresh
        self.gate.set(); self.assertTrue(refreshed.wait(2))
        self.assertFalse(tl._naps_cache.get("busy"))
        self.assertEqual(self.calls, 1)
        self.assertEqual(tl.naps(1), [[int(now - 300), int(now - 100)]])

    def test_failure_keeps_previous_bands(self):
        now = NOW
        old = [(now - 900, now - 800)]
        tl._naps_cache.clear(); tl._naps_cache.update({"at": now - tl.NAP_TTL_S - 5, "v": old, "busy": True})
        tl._naps_fetch = self.fetch(None)                                   # None = pmset timeout/error
        tl._naps_refresh()
        self.assertEqual(tl._naps_cache["v"], old)
        self.assertFalse(tl._naps_cache["busy"])
        age = NOW - tl._naps_cache["at"]
        # Not cached as fresh: stale again after NAP_RETRY_S, well before the full TTL.
        self.assertEqual(age, tl.NAP_TTL_S - tl.NAP_RETRY_S)
        self.assertLess(tl.NAP_RETRY_S, tl.NAP_TTL_S)

    def test_genuine_empty_replaces(self):
        now = NOW
        tl._naps_cache.clear(); tl._naps_cache.update({"at": now - tl.NAP_TTL_S - 5, "v": [(now - 900, now - 800)], "busy": True})
        tl._naps_fetch = self.fetch([])
        tl._naps_refresh()
        self.assertEqual(tl._naps_cache["v"], [])
        self.assertEqual(tl._naps_cache["at"], NOW)


if __name__ == "__main__":
    unittest.main()
