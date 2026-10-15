"""`bg_dismiss` mutates _bg_open under _bg_lock, so a concurrent iterator never sees a resize. No live files."""
import threading
import unittest

from tests._load import sidereus

bt = sidereus("bgtasks")
bp = sidereus("bgtasks_parse")                          # owns BG_DROP / warn_once read by _bg_drop_save


class BgDismiss(unittest.TestCase):
    def setUp(self):
        self._saved = dict(bt._bg_open)
        self._dropped = dict(bt._bg_dropped)
        self._orig_bg_drop = bp.BG_DROP
        bp.BG_DROP = "/nonexistent-dir/bg_drop"      # write fails -> warn path; never a live file
        self._warn = bp.warn_once
        bp.warn_once = lambda *a, **k: None
        bt._bg_open.clear()

    def tearDown(self):
        bt._bg_open.clear()
        bt._bg_open.update(self._saved)
        bt._bg_dropped.clear()
        bt._bg_dropped.update(self._dropped)
        bp.BG_DROP = self._orig_bg_drop
        bp.warn_once = self._warn

    def test_filters(self):
        bt._bg_open["/a"] = {"t1": ("sub", "x"), "t2": ("task", "y"), "t3": ("bg", "z")}
        bt._bg_open["/b"] = {"t4": ("sub", "w")}
        n = bt.bg_dismiss("/cwd-a", "", lambda fp: "/cwd-a" if fp == "/a" else "/cwd-b")
        self.assertEqual(n, 2)
        self.assertEqual(set(bt._bg_open["/a"]), {"t2"})
        self.assertIn("t1", bt._bg_dropped)
        self.assertEqual(bt.bg_dismiss("", "t4", lambda fp: None), 1)

    def test_concurrent_iteration_does_not_raise(self):
        errors, stop = [], threading.Event()
        fp = "/a"

        def reader():
            # Mimics _running_bg_locked: iterates the dict while holding _bg_lock.
            while not stop.is_set():
                with bt._bg_lock:
                    try:
                        opened = bt._bg_open.get(fp, {})
                        for k in list(opened):
                            opened[k]
                        for v in opened.values():
                            v[0]
                    except (RuntimeError, KeyError) as e:
                        errors.append(e)

        th = threading.Thread(target=reader)
        th.start()
        try:
            for i in range(300):
                with bt._bg_lock:
                    bt._bg_open[fp] = {"t%d_%d" % (i, j): ("sub", "x") for j in range(20)}
                bt.bg_dismiss("", "", lambda _fp: None)
        finally:
            stop.set()
            th.join()
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
