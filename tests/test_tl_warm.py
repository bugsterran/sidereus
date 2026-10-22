"""Timeline warm-up: default window then 72h, errors swallowed per pass, no thread at import."""
import contextlib
import threading
import unittest

from tests._load import sidereus

tl = sidereus("timeline")
bq = sidereus("boot_queue")


class TlWarm(unittest.TestCase):
    def setUp(self):
        self._saved = (tl.agents_timeline, tl.time.sleep, tl.warn_once, bq.gate)
        bq.gate = lambda name: contextlib.nullcontext()   # ⚠never touch the process-wide boot queue
        self.calls, self.warns, self.slept = [], [], []
        tl.time.sleep = lambda s: self.slept.append(s)
        tl.warn_once = lambda key, msg, **kw: self.warns.append(key)

    def tearDown(self):
        tl.agents_timeline, tl.time.sleep, tl.warn_once, bq.gate = self._saved

    def test_default_then_72h_after_delay(self):
        tl.agents_timeline = lambda h: self.calls.append(h)
        tl._tl_warm()
        self.assertEqual(self.slept, [tl.TL_WARM_DELAY_S])
        self.assertEqual(self.calls, [tl.TL_HOURS, 72])
        self.assertEqual(self.warns, [])

    def test_failure_is_swallowed_and_72h_still_runs(self):
        def boom(h):
            self.calls.append(h)
            if h == tl.TL_HOURS:
                raise OSError("x")
        tl.agents_timeline = boom
        tl._tl_warm()
        self.assertEqual(self.calls, [tl.TL_HOURS, 72])
        self.assertEqual(self.warns, ["tl-warm-%s" % tl.TL_HOURS])   # per-window key: a later 72h failure still reports

    def test_no_warm_thread_on_import(self):
        self.assertNotIn("tl_warm", [t.name for t in threading.enumerate()])


if __name__ == "__main__":
    unittest.main()
