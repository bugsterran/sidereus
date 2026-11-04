"""scripts/commit_msg_check.py: closing keywords only in the release commit (CHANGELOG.md staged). Pure check(), no git."""
import importlib.util
import os
import unittest

from tests._load import ROOT

_spec = importlib.util.spec_from_file_location("commit_msg_check", os.path.join(ROOT, "scripts", "commit_msg_check.py"))
cmc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cmc)

CODE = ["sidereus/a.py"]
REL = ["CHANGELOG.md", "pyproject.toml"]


class CommitMsgCheck(unittest.TestCase):
    def test_closes_rejected_outside_release(self):
        err = cmc.check("Fix thing\n\nCloses #64\n", CODE)
        self.assertIsNotNone(err)
        self.assertIn("Refs #N", err)
        self.assertIn("to-do 64", err)

    def test_closes_allowed_in_release(self):
        self.assertIsNone(cmc.check("Release 0.15.0\n\nCloses #64\n", REL))

    def test_refs_allowed(self):
        self.assertIsNone(cmc.check("Fix thing\n\nRefs #64\n", CODE))

    def test_variants_caught(self):
        for msg in ("fixes #3", "Resolved: #3", "closes o/r#3", "FIXED #3", "fix #3 typo"):
            self.assertIsNotNone(cmc.check(msg, CODE), msg)

    def test_non_keywords_allowed(self):
        for msg in ("prefix #3", "#3", "suffix #3", "fixture #3", "closer #3"):
            self.assertIsNone(cmc.check(msg, CODE), msg)

    def test_comment_lines_ignored(self):
        self.assertIsNone(cmc.check("Fix thing\n# Closes #64 (template)\n", CODE))

    def test_verbose_diff_below_scissors_ignored(self):
        msg = ("Fix thing\n\nRefs #3\n# Please enter the commit message.\n" + cmc.SCISSORS + "\n"
               "# Do not modify or remove the line above.\ndiff --git a/x b/x\n+Fixes #3\n")
        self.assertIsNone(cmc.check(msg, CODE))
        self.assertIsNotNone(cmc.check("Closes #3\n" + cmc.SCISSORS + "\n+x\n", CODE))

    def test_message_only_amend_of_release(self):
        self.assertIsNone(cmc.check("Release\n\nCloses #4\n", [], head=REL))
        self.assertIsNotNone(cmc.check("Closes #4\n", [], head=CODE))
        self.assertIsNotNone(cmc.check("Closes #4\n", [], head=()))
        # staged files win: HEAD's CHANGELOG does not excuse a new code commit
        self.assertIsNotNone(cmc.check("Closes #4\n", CODE, head=REL))

    def test_main_reads_head_only_when_nothing_staged(self):
        calls = []
        orig = (cmc._staged, cmc._head_files)
        cmc._staged = lambda: []
        cmc._head_files = lambda: calls.append(1) or ["CHANGELOG.md"]
        try:
            import tempfile
            with tempfile.NamedTemporaryFile("w", suffix=".msg", delete=False) as fh:
                fh.write("Release\n\nCloses #4\n")
            self.assertEqual(cmc.main(["x", fh.name]), 0)
            self.assertEqual(calls, [1])
        finally:
            cmc._staged, cmc._head_files = orig
            os.unlink(fh.name)


if __name__ == "__main__":
    unittest.main()
