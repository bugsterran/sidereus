"""sidereus/live.py _live_pid_cwds: a fresh map covering the pids is reused (no second lsof within PID_CWD_TTL)."""
import types
import unittest
from unittest import mock

from tests._load import sidereus

L = sidereus("live")


class PidCwdTTL(unittest.TestCase):
    def setUp(self):
        self.saved = list(L._live_pid_cwd)
        self.calls = []

        def fake_run(argv, **k):
            self.calls.append(argv)
            pids = argv[-1].split(",")
            return types.SimpleNamespace(stdout="".join("p%s\nn/w/%s\n" % (p, p) for p in pids))
        self.patches = [mock.patch.object(L.subprocess, "run", fake_run), mock.patch.object(L, "IS_MAC", True),
                        mock.patch.object(L.time, "time", lambda: self.now)]
        for p in self.patches:
            p.start()
        self.now = 1000.0
        L._live_pid_cwd[0], L._live_pid_cwd[1] = 0.0, {}

    def tearDown(self):
        for p in self.patches:
            p.stop()
        L._live_pid_cwd[0], L._live_pid_cwd[1] = self.saved

    def test_reuse_then_refresh(self):
        self.assertEqual(L._live_pid_cwds(["1", "2"]), {"1": "/w/1", "2": "/w/2"})
        self.assertEqual(L._live_pid_cwds(["2"]), {"2": "/w/2"})   # reused map, trimmed to the request
        self.assertEqual(len(self.calls), 1)
        L._live_pid_cwds(["3"])                  # a pid not in the map -> new lsof
        self.assertEqual(len(self.calls), 2)
        self.now += L.PID_CWD_TTL                # expired -> new lsof
        L._live_pid_cwds(["3"])
        self.assertEqual(len(self.calls), 3)


if __name__ == "__main__":
    unittest.main()
