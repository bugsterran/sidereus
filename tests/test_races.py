"""Race regressions: window-evidence save vs. concurrent learn (live_win.py), wreck map refresh (failures.py).

No live files: WIN_FILE / _atomic_write / warn_once / wreckage are monkeypatched on the owning module.
"""
import sys
import threading
import unittest
from unittest import mock

from tests._load import sidereus

L = sidereus("live_win")
F = sidereus("failures")


class WinSaveRaceTests(unittest.TestCase):
    def setUp(self):
        self.ev = {}
        self.p = [mock.patch.object(L, "_win_ev", self.ev),
                  mock.patch.object(L, "_win_seen", {}),
                  mock.patch.object(L, "_win_scanned", {}),
                  mock.patch.object(L, "_atomic_write", lambda *a, **k: None),
                  mock.patch.object(L, "warn_once", self._warn)]
        self.warns = []
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def _warn(self, key, msg, *a, **k):
        self.warns.append((key, msg))

    def test_save_and_model_win_while_another_thread_learns(self):
        w = L.WIN_STEPS[0]

        def learner():
            for i in range(20000):   # bounded: new model keys resize _win_ev while saves iterate it
                L._win_learn("m%d" % i, w, "s")

        old = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)   # force frequent thread switches so an unlocked iteration would collide
        t = threading.Thread(target=learner)
        t.start()
        try:
            while t.is_alive():
                L._win_save()
                L._model_win("m1")
        finally:
            t.join()
            sys.setswitchinterval(old)
        self.assertEqual([k for k, _ in self.warns if k == "winsave"], [])

    def test_model_win_picks_window_with_more_sessions(self):
        a, b = L.WIN_STEPS[0], L.WIN_STEPS[-1]
        L._win_learn("m", a, "x")
        L._win_learn("m", b, "y")
        L._win_learn("m", b, "z")
        self.assertEqual(L._model_win("m"), (b, 2))
        self.assertEqual(L._model_win("none"), (0, 0))


class WreckRefreshTests(unittest.TestCase):
    def test_map_never_empty_mid_refresh_when_keys_persist(self):
        m = F._WRECK_BY_CWD
        saved = dict(m)
        m.clear()
        m.update({"/a": 1, "/gone": 2})
        seen = {"miss": 0, "n": 0}

        rows = [{"dirty": 3, "cwd": "/a"}, {"dirty": 1, "cwd": "/b"}]
        try:
            with mock.patch.object(F, "wreckage", lambda hrs: {"rows": rows}):
                # Observe the shared map after every mutation step via a sampler thread.
                stop = threading.Event()

                def sampler():
                    while not stop.is_set():
                        seen["n"] += 1
                        seen["miss"] += not m.get("/a")

                t = threading.Thread(target=sampler)
                t.start()
                for _ in range(2000):
                    F._wreck_by_cwd()
                stop.set()
                t.join()
            self.assertEqual(seen["miss"], 0)
            self.assertEqual(dict(m), {"/a": 3, "/b": 1})
        finally:
            m.clear()
            m.update(saved)


if __name__ == "__main__":
    unittest.main()
