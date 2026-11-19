"""Every test process refuses live machine probes (tests/__init__.py): no real `ps` result can enter a module cache."""
import subprocess
import unittest
from unittest import mock

import tests
from tests import _load


class LiveProbeGuard(unittest.TestCase):
    def test_probe_commands_refused(self):
        for argv in (["ps", "-Ao", "pid="], ["/bin/ps", "-o", "pid="], ["lsof", "-p", "1"], ("claude", "agents", "--json")):
            with self.assertRaises(FileNotFoundError, msg=argv):
                subprocess.run(argv, capture_output=True, timeout=4)

    def test_other_commands_pass_through(self):
        seen = []
        with mock.patch.object(tests, "_real_run", lambda *a, **k: seen.append(a[0] if a else k["args"]) or "ok"):
            self.assertEqual(subprocess.run(["git", "--version"]), "ok")
            self.assertEqual(subprocess.run(args=["node", "--check", "x.js"]), "ok")
        self.assertEqual(seen, [["git", "--version"], ["node", "--check", "x.js"]])

    def test_sessions_refresh_leaves_no_live_ps_rows(self):
        _load.load()
        lp = __import__("sidereus.live_probe", fromlist=["x"])
        with mock.patch.object(lp, "IS_MAC", True), mock.patch.object(lp, "on_request_path", lambda: False), \
                mock.patch.object(lp, "_ps_snap_cache", [0.0, None]), mock.patch.object(lp, "_ps_res", [0.0, {}]), \
                mock.patch.object(lp, "_ps_snap_fail", [0.0, None]):
            with self.assertRaises(FileNotFoundError):
                lp._ps_snap()
            self.assertEqual(lp._ps_res, [0.0, {}])


if __name__ == "__main__":
    unittest.main()
