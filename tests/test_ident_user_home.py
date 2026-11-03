"""ident._real_home honours SIDEREUS_USER_HOME only when it is an absolute path to an existing dir. Temp dirs only."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

ident = sidereus("ident")


class UserHome(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-uhome-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        with mock.patch.dict(os.environ):
            os.environ.pop("SIDEREUS_USER_HOME", None)
            self.base = ident._real_home()

    def home(self, val):
        with mock.patch.dict(os.environ, {"SIDEREUS_USER_HOME": val}):
            return ident._real_home()

    def test_absolute_existing_dir_honoured(self):
        self.assertEqual(self.home(self.tmp), self.tmp)

    def test_relative_falls_back(self):
        self.assertEqual(self.home(os.path.basename(self.tmp)), self.base)

    def test_missing_falls_back(self):
        self.assertEqual(self.home(os.path.join(self.tmp, "missing")), self.base)

    def test_file_falls_back(self):
        fp = os.path.join(self.tmp, "f")
        open(fp, "w", encoding="utf-8").close()
        self.assertEqual(self.home(fp), self.base)

    def test_empty_falls_back(self):
        self.assertEqual(self.home(""), self.base)


if __name__ == "__main__":
    unittest.main()
