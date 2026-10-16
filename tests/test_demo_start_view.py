"""`--demo` opens on Pipelines: ui_prefs.memory_only(seed) seeds the in-memory prefs; the real viewer keeps its file.

⚠ui_prefs.PATH points at a temp file — the live ui-prefs.json is never read or written.
"""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import load, sidereus

cs = load()
U = sidereus("ui_prefs")
DEMO = sidereus("demo")


class DemoStartView(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-demoview-")
        self.path = os.path.join(self.tmp, "ui-prefs.json")
        p = mock.patch.multiple(U, PATH=self.path, BAK_DIR=os.path.join(self.tmp, "bak"), _MEM={})
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_seed_is_loaded(self):
        U.memory_only({"mbMainView": "pipe"})
        self.assertEqual(U.load(), {"mbMainView": "pipe"})
        self.assertFalse(os.path.exists(self.path))   # the seed never reaches the file

    def test_no_seed_is_empty(self):
        U.memory_only()
        self.assertEqual(U.load(), {})

    def test_file_path_without_memory_only(self):
        self.assertIsNone(U.load())                    # real viewer: no file -> migration signal, no seed
        self.assertFalse(os.path.exists(self.path))

    def test_demo_main_seeds_pipelines(self):
        seen = []
        with mock.patch.object(cs, "argv", ["chat_server.py", "--demo", "--no-open"]), \
                mock.patch.object(cs, "ui_prefs_memory_only", lambda seed=None: seen.append(seed)), \
                mock.patch.object(cs, "pl_reqs_memory_only", lambda: None), \
                mock.patch.object(DEMO, "serve", lambda *a: None):
            cs.main()
        self.assertEqual(seen, [{"mbMainView": "pipe"}])


if __name__ == "__main__":
    unittest.main()
