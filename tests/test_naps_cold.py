"""naps() with an empty cache: returns [] at once and fills the cache on one background fetch.

`_naps_fetch` is monkeypatched with a sleeping stub — pmset is never run.
"""
import threading
import time
import unittest

from tests._load import sidereus

tl = sidereus("timeline_scan")


class NapsCold(unittest.TestCase):
    def setUp(self):
        self.saved = (tl._naps_fetch, tl._naps_refresh, dict(tl._naps_cache))
        tl._naps_cache.clear(); tl._naps_cache.update({"at": 0.0, "v": []})
        self.calls = 0
        self.refreshed = threading.Event()
        now = time.time()
        self.val = [(now - 600, now - 60)]

        def fetch():
            self.calls += 1
            time.sleep(1.5)             # above the 1.0s bound below — an inline fetch would fail it
            return self.val
        tl._naps_fetch = fetch
        real = self.saved[1]

        def refresh():
            try:
                real()
            finally:
                self.refreshed.set()
        tl._naps_refresh = refresh

    def tearDown(self):
        self.refreshed.wait(3)          # let the stub thread finish before restoring
        tl._naps_fetch, tl._naps_refresh = self.saved[0], self.saved[1]
        tl._naps_cache.clear(); tl._naps_cache.update(self.saved[2])

    def test_first_call_returns_empty_at_once(self):
        t = time.perf_counter()
        self.assertEqual(tl.naps(1), [])
        self.assertLess(time.perf_counter() - t, 1.0)   # catches an inline 1.5s fetch, not a benchmark; 0.05 flaked under load

    def test_next_call_after_refresh_has_naps(self):
        tl.naps(1)
        self.assertTrue(self.refreshed.wait(3))
        self.assertEqual(tl.naps(1), [[int(self.val[0][0]), int(self.val[0][1])]])
        self.assertEqual(self.calls, 1)

    def test_concurrent_first_calls_fetch_once(self):
        go = threading.Barrier(4)
        res = []

        def call():
            go.wait()
            res.append(tl.naps(1))
        ths = [threading.Thread(target=call) for _ in range(4)]
        for th in ths:
            th.start()
        for th in ths:
            th.join(2)
        self.assertEqual(res, [[]] * 4)
        self.assertTrue(self.refreshed.wait(3))
        self.assertEqual(self.calls, 1)


if __name__ == "__main__":
    unittest.main()
