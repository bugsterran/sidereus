"""ident._slug matches the harness folder name (ASCII only); _cwd_from_slug resolves Windows drive slugs."""
import ntpath
import types
import unittest

from tests._load import sidereus

ident = sidereus("ident")


class Slug(unittest.TestCase):
    def test_non_ascii_becomes_dash(self):
        self.assertEqual(ident._slug("/Users/me/\ud55c\uae00-caf\u00e9"), "-Users-me----caf-")

    def test_ascii_unchanged(self):
        self.assertEqual(ident._slug("/home/me/.mailbox-mcp"), "-home-me--mailbox-mcp")


def _fake_os(name, mod, dirs):
    path = types.SimpleNamespace(join=mod.join, isdir=lambda p: p in dirs)
    return types.SimpleNamespace(name=name, path=path)


class CwdFromSlug(unittest.TestCase):
    def patch(self, fake):
        old = ident.os
        ident.os = fake
        self.addCleanup(setattr, ident, "os", old)

    def test_windows_drive_slug(self):
        dirs = {"C:\\Users", "C:\\Users\\me", "C:\\Users\\me\\repo-A"}
        self.patch(_fake_os("nt", ntpath, dirs))
        self.assertEqual(ident._cwd_from_slug("C--Users-me-repo-A"), "C:\\Users\\me\\repo-A")

    def test_drive_shape_ignored_off_windows(self):
        import posixpath
        self.patch(_fake_os("posix", posixpath, {"/C", "/C/Users"}))
        self.assertEqual(ident._cwd_from_slug("C--Users"), "/C/Users")

    def test_posix_unchanged(self):
        import posixpath
        self.patch(_fake_os("posix", posixpath, {"/home", "/home/me", "/home/me/bot-A"}))
        self.assertEqual(ident._cwd_from_slug("-home-me-bot-A"), "/home/me/bot-A")


if __name__ == "__main__":
    unittest.main()
