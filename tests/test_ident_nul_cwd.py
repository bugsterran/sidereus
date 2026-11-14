"""A cwd holding NUL gets «no identity» from mbox_pi/mbox_codex and is skipped by project_list/review roots instead of raising (realpath raises on NUL on newer builds)."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

ident = sidereus("ident")


def _strict_realpath(p):
    # Mimics 3.12+/Windows realpath; stock macOS 3.9.6 swallows NUL in islink, so the bug never shows there.
    if "\0" in p:
        raise ValueError("embedded null byte")
    return p


class NulCwd(unittest.TestCase):
    def setUp(self):
        self.p = [mock.patch.object(ident, "_load", lambda name, default: {} if name == "identity.json" else default),
                  mock.patch.object(ident.os.path, "realpath", _strict_realpath)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def test_pi_nul_cwd_no_identity(self):
        self.assertEqual(ident.mbox_pi("/w/\0proj"), ("", "none"))

    def test_codex_nul_cwd_no_identity(self):
        self.assertEqual(ident.mbox_codex("/w/\0proj"), ("", "none"))

    def test_plain_cwd_unchanged(self):
        self.assertEqual(ident.mbox_pi("/w/proj"), ("proj-pi", "folder"))


class NulCwdProjectsReview(unittest.TestCase):
    """A NUL-cwd session row must not 500 the project list nor empty review roots for the other rows."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.good = os.path.join(self.tmp, "good")
        os.makedirs(self.good)
        self.rows = {"/w/\0bad": {"cwd": "/w/\0bad", "root": "/w/\0bad", "repos": ["/w/\0bad"]},
                     self.good: {"cwd": self.good, "root": self.good, "repos": [self.good]}}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_project_list_skips_nul_row(self):
        pp = sidereus("pipeline_projects")
        with mock.patch.object(pp, "_allowed_cwds", lambda: self.rows), \
                mock.patch.object(pp, "known_projects", lambda: []), \
                mock.patch.object(pp, "_remembered", lambda: []), \
                mock.patch.object(pp, "CODE_DIR", self.tmp), \
                mock.patch.object(pp.config, "IS_CLONE", True), \
                mock.patch.object(pp.os.path, "realpath", _strict_realpath):
            lst, _self_only = pp.project_list()
        self.assertIn(self.good, lst)

    def test_review_roots_skip_nul(self):
        rv = sidereus("review")
        with mock.patch.object(rv, "_git_root", lambda p: ""), \
                mock.patch.object(rv.os.path, "realpath", _strict_realpath):
            self.assertEqual(rv._roots({"cwd": "/w/\0bad", "repos": [self.good]}), {self.good})


if __name__ == "__main__":
    unittest.main()
