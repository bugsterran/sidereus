"""scripts/mem_sample.py: footprint parsing and the summary line, with the process probes patched."""
import importlib.util
import io
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("mem_sample", os.path.join(ROOT, "scripts", "mem_sample.py"))
ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ms)


class MemSample(unittest.TestCase):
    def test_parse_footprint(self):
        self.assertEqual(ms.parse_footprint("Python [1]: 64-bit    Footprint: 218 MB (16384 bytes per page)"), 218)
        self.assertEqual(ms.parse_footprint("Footprint: 1.5 GB"), 1536)
        self.assertIsNone(ms.parse_footprint("no such process"))
        self.assertIsNone(ms.parse_footprint(None))

    def test_summary_uses_footprint_median(self):
        seq = iter([("25:00", 200.0, 100.0), ("27:00", 220.0, 104.0), ("29:00", 210.0, 102.0)])
        out = io.StringIO()
        with mock.patch.object(ms, "sample", lambda pid: next(seq)), mock.patch.object(ms.time, "sleep", lambda s: None), \
                redirect_stdout(out):
            rc = ms.main(["--pid", "7", "--minutes", "4", "--step", "120"])
        self.assertEqual(rc, 0)
        last = out.getvalue().strip().splitlines()[-1]
        self.assertIn("3 samples", last)
        self.assertIn("footprint min/median/max 200/210/220 MB", last)
        self.assertIn("rss median 102 MB", last)

    def test_no_viewer(self):
        out = io.StringIO()
        with mock.patch.object(ms, "viewer_pid", lambda: None), redirect_stdout(out):
            self.assertEqual(ms.main([]), 2)


if __name__ == "__main__":
    unittest.main()
