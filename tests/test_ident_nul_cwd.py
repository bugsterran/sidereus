"""A cwd holding NUL gets «no identity» from mbox_pi/mbox_codex instead of raising (realpath raises on NUL on newer builds)."""
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


if __name__ == "__main__":
    unittest.main()
