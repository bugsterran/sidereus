"""Hooks that walk up parent directories must stop at a Windows drive root (ntpath.dirname("C:\\") == "C:\\")."""
import importlib.util
import ntpath
import os
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    spec = importlib.util.spec_from_file_location(name + "_drv", os.path.join(ROOT, "hooks", name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _bounded_dirname():
    # ⚠ bind now: on Windows os.path IS ntpath, so a late lookup would hit this patched wrapper
    real = ntpath.dirname
    calls = []

    def dn(p):
        calls.append(p)
        if len(calls) > 50:
            raise AssertionError("parent walk did not stop at the drive root")
        return real(p)
    return dn


class DriveRootWalk(unittest.TestCase):
    def test_invite_notice_whoami_stops(self):
        m = _load("invite_notice")
        with mock.patch.object(m, "load", return_value={}), \
             mock.patch.object(m.os.path, "dirname", _bounded_dirname()), \
             mock.patch.dict(os.environ, {"MAILBOX_ME": ""}):
            self.assertEqual(m.whoami("C:\\Users\\me\\proj"), ("", ""))

    def test_room_auto_whoami_stops(self):
        m = _load("room_auto")
        with mock.patch.object(m, "load", return_value={}), \
             mock.patch.object(m.os.path, "dirname", _bounded_dirname()), \
             mock.patch.dict(os.environ, {"MAILBOX_ME": ""}):
            self.assertEqual(m.whoami("C:\\Users\\me\\proj"), "")


if __name__ == "__main__":
    unittest.main()
