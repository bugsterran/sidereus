"""sidereus/boot_queue.py: boot warm-ups run one at a time (R1) and each completion is observable (R4).

The module clock (_now), log (_log) and feature check (_thread_on) are patched; state is a fresh _BQ per test.
"""
import threading
import time
import unittest

from tests._load import sidereus

bq = sidereus("boot_queue")


class _Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class BootQueueTest(unittest.TestCase):
    def setUp(self):
        self._saved = (bq._BQ, bq._now, bq._log, bq._thread_on, bq._WAIT_S)
        bq._BQ = bq._fresh()
        self.clock = _Clock()
        self.logs = []
        bq._now = self.clock
        bq._log = self.logs.append
        bq._thread_on = lambda name: True
        bq._WAIT_S = 0.02

    def tearDown(self):
        bq._BQ, bq._now, bq._log, bq._thread_on, bq._WAIT_S = self._saved

    def _run(self, fn, names):
        ts = [threading.Thread(target=fn, args=(n,), daemon=True) for n in names]
        for t in ts:
            t.start()
        for t in ts:
            t.join(10)
            self.assertFalse(t.is_alive(), "gate deadlocked")

    def test_r1_zero_concurrent_runs(self):
        lock, cur, peak = threading.Lock(), [0], [0]

        def warm(name):
            with bq.gate(name):
                with lock:
                    cur[0] += 1
                    peak[0] = max(peak[0], cur[0])
                time.sleep(0.02)
                with lock:
                    cur[0] -= 1
        self._run(warm, bq.ORDER)
        self.assertEqual(peak[0], 1)
        self.assertTrue(bq.drained())

    def test_r1_waiters_run_in_order(self):
        ran, release = [], threading.Event()

        def hold():
            with bq.gate("unknown_holder"):
                release.wait(5)
        h = threading.Thread(target=hold, daemon=True)
        h.start()
        while bq._BQ["holder"] is None:
            time.sleep(0.005)

        def warm(name):
            with bq.gate(name):
                ran.append(name)
        ts = []
        for n in reversed(bq.ORDER):
            t = threading.Thread(target=warm, args=(n,), daemon=True)
            t.start()
            ts.append(t)
            while not any(v[0] == n for v in bq._BQ["wait"].values()):
                time.sleep(0.002)
        release.set()
        for t in ts + [h]:
            t.join(10)
        self.assertEqual(ran, list(bq.ORDER))

    def test_reentry_same_thread(self):
        with bq.gate("today_loop"):
            with bq.gate("usage_loop"):
                self.assertEqual(bq._BQ["depth"], 2)
        self.assertIsNone(bq._BQ["holder"])
        self.assertIn("today_loop", bq._BQ["done"])

    def test_exception_releases_and_marks_done(self):
        with self.assertRaises(ValueError):
            with bq.gate("fail_loop"):
                raise ValueError("boom")
        self.assertIsNone(bq._BQ["holder"])
        self.assertIn("fail_loop", bq._BQ["done"])
        with bq.gate("win_loop"):
            pass

    def test_r4_drain_all_done_logs_and_status(self):
        for n in bq.ORDER:
            with bq.gate(n):
                self.clock.t += 2
        self.assertTrue(bq.drained())
        st = bq.status()
        self.assertEqual(sorted(st), sorted(bq.ORDER))
        self.assertEqual(st["today_loop"], [1000.0, 1002.0])
        self.assertIn("boot: today_loop 2.0s", self.logs)
        self.assertIn("boot: drained 20.0s", self.logs)
        self.assertEqual(sum(m.startswith("boot: drained") for m in self.logs), 1)

    def test_drain_by_time_then_overlap(self):
        release, inside = threading.Event(), threading.Event()

        def hold():
            with bq.gate("today_loop"):
                release.wait(5)
        h = threading.Thread(target=hold, daemon=True)
        h.start()
        while bq._BQ["holder"] is None:
            time.sleep(0.005)
        self.assertFalse(bq.drained())

        def second():
            with bq.gate("usage_loop"):
                inside.set()
        s = threading.Thread(target=second, daemon=True)
        s.start()
        time.sleep(0.05)
        self.assertFalse(inside.is_set())   # still queued behind the holder
        self.clock.t += bq.BQ_DRAIN_MAX
        self.assertTrue(inside.wait(5))     # drained: overlap allowed
        release.set()
        h.join(5)
        s.join(5)
        self.assertTrue(bq.drained())
        self.assertIn("boot: drained %.1fs" % bq.BQ_DRAIN_MAX, self.logs)
        self.assertIsNotNone(bq.status()["usage_loop"][1])

    def test_switched_off_names_pre_done(self):
        off = {"qburn_warm_start", "struct_warm"}
        seen = []

        def thread_on(name):
            seen.append(name)
            return name not in off
        bq._thread_on = thread_on
        for n in bq.ORDER:
            if n not in ("qburn_warm", "struct_warm"):
                with bq.gate(n):
                    pass
        self.assertIn("qburn_warm_start", seen)
        self.assertIn("br_boot_warm_start", seen)
        self.assertTrue(bq.drained())
        self.assertNotIn("qburn_warm", bq.status())
        self.assertIn("boot: struct_warm off", self.logs)

    def test_thread_on_raising_counts_as_enabled(self):
        def boom(name):
            raise RuntimeError("x")
        bq._thread_on = boom
        with bq.gate("today_loop"):
            pass
        self.assertEqual(bq._BQ["done"], {"today_loop"})
        self.assertFalse(bq.drained())

    def test_r1_done_marks_without_holding_and_drains(self):
        bq.done("toolidx_warm")
        self.assertIn("toolidx_warm", bq._BQ["done"])
        self.assertIsNone(bq._BQ["holder"])
        self.assertIn("boot: toolidx_warm skip", self.logs)
        bq.done("toolidx_warm")                       # repeat is a no-op
        self.assertEqual(self.logs.count("boot: toolidx_warm skip"), 1)
        for n in bq.ORDER[:-1]:
            if n != "toolidx_warm":
                with bq.gate(n):
                    pass
        self.assertTrue(bq.others_done("struct_warm"))
        self.assertFalse(bq.drained())
        bq.done("struct_warm")                        # R4: last skip drains before the time cap
        self.assertTrue(bq.drained())
        bq.done("other")                              # after drain: no-op
        self.assertNotIn("boot: other skip", self.logs)

    def test_others_done_false_while_pending(self):
        self.assertFalse(bq.others_done("struct_warm"))
        bq.done("today_loop")
        self.assertFalse(bq.others_done("struct_warm"))


if __name__ == "__main__":
    unittest.main()
