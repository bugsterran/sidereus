"""Git slot misses never poison caches: _git_state (poll path), warm branch_graph, and _br_seen_note persistence.
No live git or files: subprocess/_git_run faked, semaphore swapped, paths in a temp dir."""
import json
import os
import subprocess
import tempfile
import threading
import time
import unittest

from tests._load import sidereus

gi = sidereus("gitinfo")
g = sidereus("git")


class GitStateSlotMiss(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self._saved = (gi._GIT_SEM, gi.subprocess.run, dict(gi._git_cache))
        gi._GIT_SEM = threading.BoundedSemaphore(gi.GIT_MAX_PROCS)
        gi._git_cache.clear()

        def boom(*a, **kw):
            raise AssertionError("git must not run while slots are saturated")
        gi.subprocess.run = boom

    def tearDown(self):
        gi._GIT_SEM, gi.subprocess.run = self._saved[:2]
        gi._git_cache.clear(); gi._git_cache.update(self._saved[2])
        self.td.cleanup()

    def test_saturated_returns_previous_immediately_uncached(self):
        cwd = self.td.name
        gi._git_cache[cwd] = (time.time() - 100, "↑2 ~1", 20)     # expired entry with a real answer
        waits = []

        class FullSem:                                            # saturated slots; records every acquire timeout
            def acquire(self, blocking=True, timeout=None):
                waits.append(timeout)
                return False

            def release(self):
                raise AssertionError("release without acquire")
        gi._GIT_SEM = FullSem()
        self.assertEqual(gi._git_state(cwd), "↑2 ~1")
        self.assertEqual(waits, [0])                              # one non-blocking probe, never a GIT_WAIT_S slot wait
        self.assertEqual(gi._git_cache[cwd][1], "↑2 ~1")
        self.assertLess(gi._git_cache[cwd][0], time.time() - 50)  # entry not refreshed -> next poll retries

    def test_saturated_without_previous_caches_nothing(self):
        for _ in range(gi.GIT_MAX_PROCS):
            gi._GIT_SEM.acquire()
        self.assertEqual(gi._git_state(self.td.name), "")
        self.assertNotIn(self.td.name, gi._git_cache)


class WarmBuildSubTimeout(unittest.TestCase):
    K = ("/repo/x", 80)

    def setUp(self):
        names = ("_git_run", "wt_signals", "remote_info", "wt_order")
        self._saved = {k: getattr(g, k) for k in names}
        self._cache = dict(g._branch_cache)
        g._branch_cache.clear()

        def fake_run(cwd, args, timeout, wait=None):
            if args[0] == "worktree":
                raise subprocess.TimeoutExpired(gi._SLOT_CMD, wait)
            if args[0] == "for-each-ref" and "refs/heads" in args:
                row = g._BR_SEP.join(["refs/heads/main", "abc1234", "", "", "1700000000", "*"])
                return subprocess.CompletedProcess(args, 0, row + "\n", "")
            return subprocess.CompletedProcess(args, 1, "", "")
        g._git_run = fake_run
        g.wt_signals = lambda *a, **kw: {"wtSig": {}, "wtTok": {}}
        g.remote_info = lambda cwd: []
        g.wt_order = lambda *a, **kw: []

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(g, k, v)
        g._branch_cache.clear(); g._branch_cache.update(self._cache)

    def test_warm_timeout_keeps_previous_entry(self):
        good = (123.0, {"ok": True, "worktrees": [{"path": "/repo/x"}], "wtSig": {}})
        g._branch_cache[self.K] = good
        out = g.branch_graph(self.K[0], self.K[1], _warm=True)
        self.assertEqual(out["worktrees"], [])                    # degraded build ...
        self.assertIs(g._branch_cache[self.K], good)              # ... never replaces the good entry

    def test_clean_warm_build_is_cached(self):
        g._git_run = lambda cwd, args, timeout, wait=None: subprocess.CompletedProcess(args, 0, "", "")
        g.branch_graph(self.K[0], self.K[1], _warm=True)
        self.assertIn(self.K, g._branch_cache)


class SeenNoteConcurrent(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self._saved = (g.BR_WARM_FILE, g._atomic_write, dict(g._br_seen))
        g.BR_WARM_FILE = os.path.join(self.td.name, "branch-warm.json")
        g._br_seen.clear()
        real = self._saved[1]
        order = []

        def slow_write(path, data):
            order.append(1)
            time.sleep(0.05 * max(0, 5 - len(order)))              # earlier (smaller) snapshots land later without the lock
            real(path, data)
        g._atomic_write = slow_write

    def tearDown(self):
        g.BR_WARM_FILE, g._atomic_write = self._saved[:2]
        g._br_seen.clear(); g._br_seen.update(self._saved[2])
        self.td.cleanup()

    def test_all_keys_persisted(self):
        keys = [("/r/%d" % i, 80) for i in range(g.BR_PERSIST_MAX)]
        now = time.time()
        ths = [threading.Thread(target=g._br_seen_note, args=(k, now + i * 0.001)) for i, k in enumerate(keys)]
        for t in ths:
            t.start()
        for t in ths:
            t.join()
        with open(g.BR_WARM_FILE, encoding="utf-8") as f:
            got = {(r["cwd"], r["n"]) for r in json.load(f)}
        self.assertEqual(got, set(keys))


if __name__ == "__main__":
    unittest.main()
