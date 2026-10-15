"""`usage._ccusage_exe`: known absolute paths first, then a PATH lookup (Windows npm installs `ccusage.cmd`).

`os.path.exists` and `shutil.which` are patched on the module — no live filesystem or PATH.
"""
import unittest
from unittest import mock

from tests import _load

u = _load.sidereus("usage")


class CcusageWhichCase(unittest.TestCase):
    def test_known_path_wins(self):
        with mock.patch.object(u.os.path, "exists", lambda p: p == "/usr/local/bin/ccusage"), \
             mock.patch.object(u.shutil, "which", lambda n: r"C:\npm\ccusage.cmd"):
            self.assertEqual(u._ccusage_exe(), "/usr/local/bin/ccusage")

    def test_which_fallback(self):
        with mock.patch.object(u.os.path, "exists", lambda p: False), \
             mock.patch.object(u.shutil, "which", lambda n: r"C:\npm\ccusage.cmd" if n == "ccusage" else None):
            self.assertEqual(u._ccusage_exe(), r"C:\npm\ccusage.cmd")

    def test_none_when_missing(self):
        with mock.patch.object(u.os.path, "exists", lambda p: False), \
             mock.patch.object(u.shutil, "which", lambda n: None):
            self.assertIsNone(u._ccusage_exe())


if __name__ == "__main__":
    unittest.main()
