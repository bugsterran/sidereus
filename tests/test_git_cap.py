"""Shared git process cap (sidereus/gitinfo.py _git_run/_git_slot) and branch warm-up skip when saturated.
No live git: subprocess.run on gitinfo is replaced by a slow fake; the semaphore is swapped per test."""
import subprocess
import threading
import time
import unittest

from tests._load import sidereus

gi = sidereus("gitinfo")
g = sidereus("git")


class GitCap(unittest.TestCase):
    def setUp(self):
        self._saved = (gi._GIT_SEM, gi.subprocess.run, g.branch_graph, dict(g._br_want), dict(g._branch_cache))
        gi._GIT_SEM = threading.BoundedSemaphore(gi.GIT_MAX_PROCS)
        self.lock = threading.Lock()
        self.live = 0
        self.peak = 0

        def slow(*a, **kw):
            with self.lock:
                self.live += 1
                self.peak = max(self.peak, self.live)
            time.sleep(0.05)
            with self.lock:
                self.live -= 1
            return subprocess.CompletedProcess(a[0], 0, "", "")
        gi.subprocess.run = slow

    def tearDown(self):
        gi._GIT_SEM, gi.subprocess.run, g.branch_graph = self._saved[:3]
        g._br_want.clear(); g._br_want.update(self._saved[3])
        g._branch_cache.clear(); g._branch_cache.update(self._saved[4])

    def test_at_most_cap_run_at_once(self):
        ths = [threading.Thread(target=gi._git_run, args=("/r", ["status"], 5)) for _ in range(12)]
        for t in ths:
            t.start()
        for t in ths:
            t.join()
        self.assertEqual(self.peak, gi.GIT_MAX_PROCS)
        self.assertTrue(gi.git_slot_free(0))          # every slot released

    def test_wait_past_limit_is_timeout(self):
        for _ in range(gi.GIT_MAX_PROCS):
            gi._GIT_SEM.acquire()
        with self.assertRaises(subprocess.TimeoutExpired):
            gi._git_run("/r", ["status"], 5, wait=0.01)
        self.assertEqual(self.peak, 0)

    def test_warm_skips_when_saturated(self):
        calls = []
        g.branch_graph = lambda cwd, n=80, _warm=False: calls.append(cwd) or {"ok": True}
        g._br_want.clear()
        g._branch_cache.clear()
        g._br_want[("/r", 80)] = 1000.0
        for _ in range(gi.GIT_MAX_PROCS):
            gi._GIT_SEM.acquire()
        self.assertEqual(g._br_warm_tick(1000.0), [])
        self.assertEqual(calls, [])
        self.assertIn(("/r", 80), g._br_want)         # still wanted — next tick retries
        gi._GIT_SEM.release()
        self.assertEqual(g._br_warm_tick(1000.0), [("/r", 80)])


if __name__ == "__main__":
    unittest.main()
