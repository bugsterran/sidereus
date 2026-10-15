"""mailbox_config._merge: prefs-owned top-level keys pass silently, other unknown keys still warn."""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mailbox_config as mc


class Merge(unittest.TestCase):
    def setUp(self):
        self.warned = []
        self._orig = mc._warn_once
        mc._warn_once = lambda key, msg, *a, **k: self.warned.append(key)

    def tearDown(self):
        mc._warn_once = self._orig

    def test_prefs_keys_silent(self):
        mc._merge({"port": 1}, {"features": {"x": False}, "pipeline_apply": {"mode": "ask", "projects": {}}})
        self.assertEqual(self.warned, [])

    def test_other_unknown_warns(self):
        mc._merge({"port": 1}, {"nope": 1})
        self.assertEqual(self.warned, ["unknown:nope"])

    def test_nested_prefs_name_still_warns(self):
        mc._merge({"self": {"ids": []}}, {"self": {"features": 1}})
        self.assertEqual(self.warned, ["unknown:self.features"])


if __name__ == "__main__":
    unittest.main()
