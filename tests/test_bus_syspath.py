"""sidereus/bus.py imports mailbox_core on every poll: sys.path must not grow with each call."""
import sys
import unittest

from tests._load import sidereus

bus = sidereus("bus")


class BusSysPath(unittest.TestCase):
    def test_presence_does_not_grow_sys_path(self):
        saved = bus.warn_once
        bus.warn_once = lambda *a, **k: None
        self.addCleanup(setattr, bus, "warn_once", saved)
        bus.presence()
        n = len(sys.path)
        for _ in range(3):
            bus.presence()
        self.assertEqual(len(sys.path), n)


if __name__ == "__main__":
    unittest.main()
