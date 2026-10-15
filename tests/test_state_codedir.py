"""state() carries `codeDir` (the clone path the first-visit tour prints) from sidereus.config.CODE_DIR.
No live files: every reader state() calls is replaced on the state module (same set as test_state_guard)."""
import os
import unittest

from tests._load import sidereus
from tests.test_state_guard import _READERS

st = sidereus("state")
cfg = sidereus("config")


class StateCodeDir(unittest.TestCase):
    def setUp(self):
        saved = {k: getattr(st, k) for k in list(_READERS) + ["warn_once", "state_off"]}
        self.addCleanup(lambda: [setattr(st, k, v) for k, v in saved.items()])
        for k, v in _READERS.items():
            setattr(st, k, v)
        st.warn_once = lambda *a, **k: None
        old = cfg.CODE_DIR
        self.addCleanup(setattr, cfg, "CODE_DIR", old)
        cfg.CODE_DIR = os.path.join(os.devnull, "sidereus-clone")

    def test_code_dir_from_config(self):
        st.state_off = lambda: set()
        self.assertEqual(st.state()["codeDir"], os.path.realpath(os.path.join(os.devnull, "sidereus-clone")))

    def test_core_key_survives_switched_off_features(self):
        st.state_off = lambda: {"quota", "saver"}
        self.assertIn("codeDir", st.state())


if __name__ == "__main__":
    unittest.main()
