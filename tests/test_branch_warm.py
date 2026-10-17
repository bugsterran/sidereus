"""Branch graph background warm-up (sidereus/git.py _br_warm_tick): rebuild only recently requested keys near expiry.
No git, no live files: branch_graph is replaced by a fake, and the clock is passed in."""
import os
import time
import unittest

from tests._load import sidereus

g = sidereus("git")
K = ("/repo/a", 80)


class BranchWarm(unittest.TestCase):
    def setUp(self):
        self._saved = (g.branch_graph, dict(g._br_want), dict(g._branch_cache))
        g._br_want.clear()
        g._branch_cache.clear()
        self.calls = []
        self.now = 1000.0

        def fake(cwd, n=80, _warm=False):
            self.calls.append((cwd, n, _warm))
            g._branch_cache[(cwd, n)] = (self.now, {"ok": True})
            return {"ok": True}
        g.branch_graph = fake

    def tearDown(self):
        g.branch_graph = self._saved[0]
        g._br_want.clear(); g._br_want.update(self._saved[1])
        g._branch_cache.clear(); g._branch_cache.update(self._saved[2])

    def test_fresh_entry_left_alone(self):
        g._br_want[K] = self.now
        g._branch_cache[K] = (self.now - 5, {"ok": True})
        self.assertEqual(g._br_warm_tick(self.now), [])
        self.assertEqual(self.calls, [])

    def test_near_expiry_rebuilt_as_warm(self):
        g._br_want[K] = self.now - 30
        g._branch_cache[K] = (self.now - (g.BRANCH_TTL - g.BR_WARM_LEAD_S), {"ok": True})
        self.assertEqual(g._br_warm_tick(self.now), [K])
        self.assertEqual(self.calls, [(K[0], K[1], True)])
        self.assertEqual(g._branch_cache[K][0], self.now)

    def test_missing_entry_built(self):
        g._br_want[K] = self.now
        self.assertEqual(g._br_warm_tick(self.now), [K])

    def test_not_requested_recently_dropped(self):
        g._br_want[K] = self.now - g.BR_WARM_WANT_S - 1
        self.assertEqual(g._br_warm_tick(self.now), [])
        self.assertEqual(self.calls, [])
        self.assertNotIn(K, g._br_want)

    def test_warm_rebuild_does_not_extend_want(self):
        g._br_want[K] = self.now - 100
        g._br_warm_tick(self.now)
        self.assertEqual(g._br_want[K], self.now - 100)

    def test_nothing_requested_no_work(self):
        self.assertEqual(g._br_warm_tick(self.now), [])
        self.assertEqual(self.calls, [])


class BranchBootWarm(unittest.TestCase):
    """Persisted request set (BR_WARM_FILE) -> one startup build. Temp dir only; builder and guard faked."""

    def setUp(self):
        import tempfile
        self.td = tempfile.TemporaryDirectory()
        self.a = os.path.join(self.td.name, "a")
        self.b = os.path.join(self.td.name, "b")
        os.mkdir(self.a)
        os.mkdir(self.b)
        names = ("BR_WARM_FILE", "branch_graph", "_branch_ok", "git_slot_free", "_br_warm_start", "_git_run")
        self._saved = {k: getattr(g, k) for k in names}
        self._dicts = (dict(g._br_want), dict(g._branch_cache), dict(g._br_seen))
        for d in (g._br_want, g._branch_cache, g._br_seen):
            d.clear()
        g.BR_WARM_FILE = os.path.join(self.td.name, "branch-warm.json")
        self.allowed = {self.a, self.b}
        g._branch_ok = lambda cwd: cwd in self.allowed
        g.git_slot_free = lambda wait=0.0: True
        g._br_warm_start = lambda: None
        self.calls = []
        self.now = 100000.0

        def fake(cwd, n=80, _warm=False):
            self.calls.append((cwd, n, _warm))
            g._branch_cache[(cwd, n)] = (self.now, {"ok": True, "worktrees": [], "wtSig": {}})
            return {"ok": True}
        g.branch_graph = fake

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(g, k, v)
        for d, v in zip((g._br_want, g._branch_cache, g._br_seen), self._dicts):
            d.clear()
            d.update(v)
        self.td.cleanup()

    def test_round_trip(self):
        self.assertTrue(g._br_seen_note((self.a, 80), self.now))
        self.assertTrue(g._br_seen_note((self.b, 120), self.now + 1))
        self.assertFalse(g._br_seen_note((self.a, 80), self.now + 2))   # throttled re-save
        g._br_seen.clear()
        self.assertEqual(g._br_seen_load(self.now + 3), {(self.a, 80): self.now, (self.b, 120): self.now + 1})

    def test_stale_dropped_and_capped(self):
        g._br_seen_note((self.a, 80), self.now - g.BR_PERSIST_KEEP_S - 10)
        for i in range(g.BR_PERSIST_MAX + 2):
            g._br_seen_note((self.b, i + 1), self.now + i)
        got = g._br_seen_load(self.now + 10)
        self.assertNotIn((self.a, 80), got)
        self.assertEqual(len(got), g.BR_PERSIST_MAX)
        self.assertNotIn((self.b, 1), got)                              # oldest beyond the cap

    def test_missing_or_bad_file(self):
        self.assertEqual(g._br_seen_load(self.now), {})
        with open(g.BR_WARM_FILE, "w", encoding="utf-8") as f:
            f.write("{not json")
        self.assertEqual(g._br_seen_load(self.now), {})

    def test_boot_skips_disallowed_and_warms(self):
        g._br_seen_note((self.a, 80), self.now - 60)
        g._br_seen_note((self.b, 80), self.now - 30)
        g._br_seen_note(("/nonexistent/c", 80), self.now - 10)
        self.allowed = {self.a}
        g._br_seen.clear()
        self.assertEqual(g.br_boot_warm(self.now), [(self.a, 80)])
        self.assertEqual(self.calls, [(self.a, 80, True)])
        self.assertIn((self.a, 80), g._br_want)                         # warm loop keeps it for BR_WARM_WANT_S

    def test_first_request_after_boot_is_hit(self):
        g._br_seen_note((self.a, 80), self.now - 60)
        g.br_boot_warm(self.now)
        g.branch_graph = self._saved["branch_graph"]
        g._git_run = lambda *a, **k: self.fail("cache miss ran git")
        g._branch_cache[(self.a, 80)] = (time.time(), g._branch_cache[(self.a, 80)][1])
        out = g.branch_graph(self.a, 80)
        self.assertTrue(out.get("cached"))


if __name__ == "__main__":
    unittest.main()
