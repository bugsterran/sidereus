"""tests/run.sh with test file paths runs those modules instead of failing in discover."""
import os
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


class RunShFileArgs(unittest.TestCase):
    def _run(self, *args):
        env = dict(os.environ, PYTHON=sys.executable)
        return subprocess.run(["bash", "tests/run.sh", *args], cwd=ROOT, env=env,
                              capture_output=True, text=True, encoding="utf-8", timeout=60)

    def test_file_path_runs_module(self):
        r = self._run("tests/test_light_contrast_css.py")
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertNotIn("not importable", r.stderr)
        self.assertIn("Ran 1 test", r.stderr)

    def test_missing_file_is_named(self):
        r = self._run("tests/test_no_such_file.py")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no such test file", r.stderr)


if __name__ == "__main__":
    unittest.main()
