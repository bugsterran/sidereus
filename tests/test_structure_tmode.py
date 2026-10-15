"""Structure code filter — tests=0 (source) · 1 (all) · only (tests only), 2026-09-25."""
import unittest

from tests._load import sidereus

SC = sidereus("structure_scan")

ITEMS = [("pkg/core.py", b"def f():\n    return 1\n"),
         ("tests/test_core.py", b"def test_f():\n    assert 1\n"),
         ("web/app.test.js", b"function t(){\n  return 1;\n}\n")]


class TModeTest(unittest.TestCase):
    def test_normalize(self):
        for v, want in ((False, 0), (True, 1), (0, 0), (1, 1), (2, 2), ("only", 2), ("2", 2),
                        ("1", 1), ("on", 1), ("0", 0), ("", 0), (None, 0)):
            self.assertEqual(SC._struct_tmode(v), want, v)

    def test_old_keys_unchanged(self):
        # 0/1 must format and hash like the old bool — existing disk/memory cache keys stay valid
        self.assertEqual(sidereus("structure_cache")._struct_fc_key("/r", True), "fc|/r|1")
        self.assertEqual(sidereus("structure_cache")._struct_fc_key("/r", False), "fc|/r|0")
        self.assertEqual(hash(("r", SC._struct_tmode(True))), hash(("r", True)))

    def _files(self, mode):
        got = SC._struct_build(list(ITEMS), mode)
        return {f["file"] for f in got[1]}, got[5], got[6]

    def test_source_only(self):
        files, ex, tf = self._files(0)
        self.assertEqual(files, {"pkg/core.py"})
        self.assertEqual(ex["test"], 2)
        self.assertNotIn("core", ex)
        self.assertEqual(tf, set())

    def test_all(self):
        files, ex, tf = self._files(1)
        self.assertEqual(files, {"pkg/core.py", "tests/test_core.py", "web/app.test.js"})
        self.assertEqual(tf, {"tests/test_core.py", "web/app.test.js"})

    def test_tests_only(self):
        files, ex, tf = self._files("only")
        self.assertEqual(files, {"tests/test_core.py", "web/app.test.js"})
        self.assertEqual((ex["core"], ex["coreLines"]), (1, 3))
        self.assertEqual(tf, set())               # nothing greyed out — every area is a test area


if __name__ == "__main__":
    unittest.main()
