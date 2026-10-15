"""`_bg_drop_save` writes the dismissed list atomically (temp file + os.replace). Temp dir only."""
import os
import tempfile
import unittest

from tests._load import sidereus

bt = sidereus("bgtasks_parse")                          # the drop list and its writer live here


class BgDropAtomic(unittest.TestCase):
    def setUp(self):
        self._dropped = dict(bt._bg_dropped)
        self._orig = bt.BG_DROP
        self._aw = bt._atomic_write
        self._warn = bt.warn_once
        self.d = tempfile.mkdtemp()
        bt.BG_DROP = os.path.join(self.d, "bg-dismissed.txt")
        bt._bg_dropped.clear()

    def tearDown(self):
        bt._bg_dropped.clear()
        bt._bg_dropped.update(self._dropped)
        bt.BG_DROP = self._orig
        bt._atomic_write = self._aw
        bt.warn_once = self._warn
        for f in os.listdir(self.d):
            os.remove(os.path.join(self.d, f))
        os.rmdir(self.d)

    def test_writes_latest_in_order(self):
        bt._bg_drop_save(["a", "b"])
        bt._bg_drop_save(["a"])                    # re-dismissal moves to the end
        with open(bt.BG_DROP, encoding="utf-8") as f:
            self.assertEqual(f.read(), "b\na\n")
        self.assertEqual(os.listdir(self.d), ["bg-dismissed.txt"])   # no temp file left behind

    def test_goes_through_atomic_write(self):
        seen = []
        bt._atomic_write = lambda path, data, **k: seen.append((path, data))
        bt._bg_drop_save(["x"])
        self.assertEqual(seen, [(bt.BG_DROP, b"x\n")])

    def test_failed_write_keeps_old_file_and_warns(self):
        with open(bt.BG_DROP, "w", encoding="utf-8") as f:
            f.write("old\n")

        def boom(path, data, **k):
            raise OSError("disk full")
        warned = []
        bt._atomic_write = boom
        bt.warn_once = lambda key, msg, *a, **k: warned.append(key)
        bt._bg_drop_save(["new"])
        with open(bt.BG_DROP, encoding="utf-8") as f:
            self.assertEqual(f.read(), "old\n")
        self.assertEqual(warned, ["bgdrop"])
        self.assertIn("new", bt._bg_dropped)       # memory side still records the dismissal


if __name__ == "__main__":
    unittest.main()
