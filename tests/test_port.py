"""Port resolution: env SIDEREUS_PORT > config `port` > 8799 — mailbox_config.port() and the standalone hook copies.

⚠Every case points MAILBOX_CONFIG at a temp file; the live config.local.json is never read.
"""
import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MC = _load("mailbox_config.py", "mailbox_config_port_t")
# Standalone copies (hooks never import the repo); each must agree with mailbox_config.port().
HOOKS = [_load("hooks/file_peers_notice.py", "fpn_port_t").sidereus_port,
         _load("ext-hooks/ext_hook.py", "exthook_port_t").sidereus_port]


class PortResolution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-port-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cfg = os.path.join(self.tmp, "config.local.json")
        p = mock.patch.dict(os.environ, {"MAILBOX_CONFIG": self.cfg, "SIDEREUS_PORT": ""})
        p.start()
        self.addCleanup(p.stop)
        q = mock.patch.object(MC, "_warn_once", lambda *a: None)
        q.start()
        self.addCleanup(q.stop)

    def _all(self, cfg=None, env=""):
        if cfg is not None:
            with open(self.cfg, "w", encoding="utf-8") as f:
                f.write(cfg if isinstance(cfg, str) else json.dumps(cfg))
        with mock.patch.dict(os.environ, {"SIDEREUS_PORT": env}):
            MC.load(reload=True)
            return [MC.port()] + [h() for h in HOOKS]

    def test_default_without_file(self):
        self.assertEqual(self._all(), [8799] * 3)

    def test_config_port(self):
        self.assertEqual(self._all({"port": 9123}), [9123] * 3)

    def test_env_wins(self):
        self.assertEqual(self._all({"port": 9123}, env="9200"), [9200] * 3)

    def test_bad_values_fall_back(self):
        self.assertEqual(self._all({"port": 9123}, env="x"), [9123] * 3)
        self.assertEqual(self._all({"port": 70000}), [8799] * 3)
        self.assertEqual(self._all({"port": "9123"}), [8799] * 3)
        self.assertEqual(self._all({"port": True}), [8799] * 3)
        self.assertEqual(self._all("{broken"), [8799] * 3)


if __name__ == "__main__":
    unittest.main()
