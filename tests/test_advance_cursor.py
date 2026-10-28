"""mailbox_core.advance_cursor: forward only, written via tmp + os.replace so a reader never sees an emptied cursor file."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import load

load()
import mailbox_core  # noqa: E402  (on sys.path after the loader)


class AdvanceCursor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        p = mock.patch.object(mailbox_core, "HOME", self.tmp)
        p.start()
        self.addCleanup(p.stop)
        self.f = os.path.join(self.tmp, "read-me.cursor")

    def test_forward_only(self):
        self.assertEqual(mailbox_core.advance_cursor("me", 10), 10)
        self.assertEqual(mailbox_core.advance_cursor("me", 7), 10)
        with open(self.f) as fh:
            self.assertEqual(fh.read(), "10")

    def test_replace_not_truncate(self):
        seen = []
        real = os.replace
        def spy(a, b):
            with open(b) as fh:
                seen.append(fh.read())                       # target still holds the old value until the swap
            real(a, b)
        mailbox_core.advance_cursor("me", 5)
        with mock.patch.object(mailbox_core.os, "replace", spy):
            self.assertEqual(mailbox_core.advance_cursor("me", 9), 9)
        self.assertEqual(seen, ["5"])
        self.assertEqual(sorted(os.listdir(self.tmp)), ["read-me.cursor"])


if __name__ == "__main__":
    unittest.main()
