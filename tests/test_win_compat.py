"""Windows-only gaps simulated on any OS: missing os.O_NOFOLLOW/O_NONBLOCK (git_view) and `%-m` strftime (structure_scan)."""
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from unittest import mock

from tests._load import sidereus

gv = sidereus("git_view")
ss = sidereus("structure_scan")


class _NoFlagOs:
    """`os` without the POSIX-only open flags, like Windows."""

    def __getattr__(self, name):
        if name in ("O_NOFOLLOW", "O_NONBLOCK"):
            raise AttributeError(name)
        return getattr(os, name)


class ReadSmallNoFlags(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)

    def test_reads_and_still_refuses_symlink(self):
        real = os.path.join(self.d, "real")
        with open(real, "w", encoding="utf-8") as fh:
            fh.write("a\n")
        with mock.patch.object(gv, "os", _NoFlagOs()):
            self.assertEqual(gv._read_small(real), b"a\n")
            if hasattr(os, "symlink"):
                ln = os.path.join(self.d, "ln")
                try:
                    os.symlink(real, ln)
                except OSError:
                    return            # no symlink privilege (Windows without developer mode)
                self.assertIsNone(gv._read_small(ln))


class StructLabel(unittest.TestCase):
    def test_portable_format(self):
        class D(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 10, 17, 12, 0)
        ts_now = datetime(2026, 3, 5, 9, 7).timestamp()
        ts_old = datetime(2024, 1, 2, 9, 7).timestamp()
        with mock.patch.object(ss, "datetime", D):
            self.assertEqual(ss._struct_label(ts_now), "3/5 09:07")
            self.assertEqual(ss._struct_label(ts_old), "2024.1.2")


if __name__ == "__main__":
    unittest.main()
