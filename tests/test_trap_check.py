"""scripts/trap_check.py: a sidereus/*.py fix needs a docs/dev/traps/*.md entry; git failure is FAIL, never PASS."""
import contextlib
import importlib.util
import io
import os
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("trap_check", os.path.join(ROOT, "scripts", "trap_check.py"))
tc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tc)


def _cp(rc, out="", err=""):
    return subprocess.CompletedProcess(["git"], rc, out, err)


class Verdict(unittest.TestCase):
    def test_code_alone_fails(self):
        self.assertFalse(tc.verdict(["sidereus/x.py"])[0])

    def test_code_with_trap_passes(self):
        self.assertTrue(tc.verdict(["sidereus/x.py", "docs/dev/traps/ui.md"])[0])

    def test_web_only_passes(self):
        self.assertTrue(tc.verdict(["web/js/48-pipeline.js"])[0])

    def test_tests_only_passes(self):
        self.assertTrue(tc.verdict(["tests/test_x.py"])[0])

    def test_trap_index_is_not_an_entry(self):
        self.assertFalse(tc.verdict(["sidereus/x.py", "docs/dev/TRAPS.md"])[0])


class Main(unittest.TestCase):
    def _run(self, fake):
        orig = tc._git
        tc._git = fake
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = tc.main([], cwd="/nonexistent")
        finally:
            tc._git = orig
        return rc, buf.getvalue()

    def test_git_error_is_unknown_fail(self):
        rc, out = self._run(lambda a, c: _cp(128, err="fatal: not a git repository"))
        self.assertEqual(rc, 1)
        self.assertIn("FAIL unknown", out)

    def test_git_raises_is_unknown_fail(self):
        def boom(a, c):
            raise OSError("git missing")
        rc, out = self._run(boom)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL unknown", out)

    def test_untracked_trap_and_rename_parse(self):
        out = " M sidereus/x.py\0?? docs/dev/traps/ui.md\0R  sidereus/new.py\0sidereus/old.py\0"
        self.assertEqual(tc.parse_porcelain_z(out), (["sidereus/x.py", "docs/dev/traps/ui.md", "sidereus/new.py"], set()))
        rc, text = self._run(lambda a, c: _cp(0, out))
        self.assertEqual(rc, 0, text)
        self.assertIn("PASS", text)

    def test_deleted_trap_is_not_an_entry(self):
        for st in ("D ", " D"):
            rc, text = self._run(lambda a, c, st=st: _cp(0, " M sidereus/x.py\0%s docs/dev/traps/ui.md\0" % st))
            self.assertEqual(rc, 1, text)

    def test_deleted_code_still_needs_trap(self):
        rc, text = self._run(lambda a, c: _cp(0, " D sidereus/x.py\0"))
        self.assertEqual(rc, 1, text)

    def test_code_without_trap_fails(self):
        rc, text = self._run(lambda a, c: _cp(0, " M sidereus/x.py\0"))
        self.assertEqual(rc, 1)
        self.assertIn("FAIL", text)


if __name__ == "__main__":
    unittest.main()
