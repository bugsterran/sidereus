"""scripts/check.sh: a step that checked 0 files is a FAIL («EMPTY»), never a green 0 problems.

Hermetic: check.sh is copied into a tmp skeleton with an empty sidereus/; evidence and logs go to tmp.
"""
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = os.path.join(ROOT, "scripts", "check.sh")


class CheckEmptyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = os.path.join(self.tmp, "repo")
        for d in ("scripts", "sidereus", "web/js", "tmp"):
            os.makedirs(os.path.join(self.repo, d))
        shutil.copy(CHECK, os.path.join(self.repo, "scripts", "check.sh"))

    def test_fast_fails_on_empty_py_compile(self):
        env = dict(os.environ)
        env["SIDEREUS_EVIDENCE"] = os.path.join(self.tmp, "evidence.jsonl")
        env["TMPDIR"] = os.path.join(self.repo, "tmp")
        env["GIT_CEILING_DIRECTORIES"] = self.tmp
        p = subprocess.run(["bash", os.path.join(self.repo, "scripts", "check.sh"), "--fast"],
                           cwd=self.repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           universal_newlines=True, timeout=60, encoding="utf-8")
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertIn("EMPTY: py_compile", p.stdout)
        self.assertNotIn("ok    py_compile", p.stdout)


if __name__ == "__main__":
    unittest.main()
