"""launchd labels: neutral public default, per-job override from config (temp config only, never the live one)."""
import importlib.util
import json
import os
import shutil
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fresh_config_module(cfg_path):
    """A private copy of mailbox_config bound to cfg_path (the shared module's cache stays untouched)."""
    os.environ["MAILBOX_CONFIG"] = cfg_path
    spec = importlib.util.spec_from_file_location("mailbox_config_t", os.path.join(ROOT, "mailbox_config.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._cache = None
    return mod


class LaunchdLabel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = os.path.join(self.tmp, "config.local.json")
        self._env = os.environ.get("MAILBOX_CONFIG")

    def tearDown(self):
        if self._env is None:
            os.environ.pop("MAILBOX_CONFIG", None)
        else:
            os.environ["MAILBOX_CONFIG"] = self._env
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, data):
        with open(self.cfg, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_default_is_neutral(self):
        self._write({})
        mc = _fresh_config_module(self.cfg)
        self.assertEqual(mc.launchd_label("viewer"), "io.sidereus.viewer")
        self.assertEqual(mc.launchd_label("watch"), "io.sidereus.watch")

    def test_prefix(self):
        self._write({"launchd_label_prefix": "org.example"})
        mc = _fresh_config_module(self.cfg)
        self.assertEqual(mc.launchd_label("databackup"), "org.example.databackup")

    def test_full_label_override(self):
        self._write({"launchd_labels": {"viewer": "my.old-viewer"}})
        mc = _fresh_config_module(self.cfg)
        self.assertEqual(mc.launchd_label("viewer"), "my.old-viewer")
        self.assertEqual(mc.launchd_label("watch"), "io.sidereus.watch")   # other jobs keep the prefix

    def test_example_config_matches_defaults(self):
        with open(os.path.join(ROOT, "config.example.json"), encoding="utf-8") as f:
            ex = json.load(f)
        self.assertEqual(ex["launchd_label_prefix"], "io.sidereus")
        self.assertEqual(sorted(ex["launchd_labels"]), ["databackup", "viewer", "watch"])


if __name__ == "__main__":
    unittest.main()
