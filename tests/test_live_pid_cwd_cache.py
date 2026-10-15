"""sidereus/live.py _live_pid_cwds: cwd cached per pid — same pids spawn no lsof, a new pid spawns lsof for it only."""
import types
import unittest
from unittest import mock

from tests._load import sidereus

L = sidereus("live")


class PidCwdCache(unittest.TestCase):
    def setUp(self):
        self.saved = list(L._live_pid_cwd)
        self.calls = []

        def fake_run(argv, **k):
            self.calls.append(argv[-1].split(","))
            return types.SimpleNamespace(stdout="".join("p%s\nn/w/%s\n" % (p, p) for p in argv[-1].split(",")))
        self.now = 1000.0
        self.patches = [mock.patch.object(L.subprocess, "run", fake_run), mock.patch.object(L, "IS_MAC", True),
                        mock.patch.object(L.time, "time", lambda: self.now)]
        for p in self.patches:
            p.start()
        L._live_pid_cwd[0], L._live_pid_cwd[1] = 0.0, {}

    def tearDown(self):
        for p in self.patches:
            p.stop()
        L._live_pid_cwd[0], L._live_pid_cwd[1] = self.saved

    def test_same_pids_no_spawn_new_pid_only(self):
        self.assertEqual(L._live_pid_cwds(["1", "2"]), {"1": "/w/1", "2": "/w/2"})
        self.now += 2.5                          # next poll, same pids
        self.assertEqual(L._live_pid_cwds(["1", "2"]), {"1": "/w/1", "2": "/w/2"})
        self.assertEqual(self.calls, [["1", "2"]])
        self.now += 2.5                          # pid 1 died, pid 3 appeared
        self.assertEqual(L._live_pid_cwds(["2", "3"]), {"2": "/w/2", "3": "/w/3"})
        self.assertEqual(self.calls[-1], ["3"])
        self.assertEqual(L._live_pid_cwd[1], {"2": "/w/2", "3": "/w/3"})   # dead pid dropped

    def test_safety_recheck_queries_all(self):
        L._live_pid_cwds(["1", "2"])
        self.now += L.PID_CWD_TTL
        L._live_pid_cwds(["1", "2", "3"])
        self.assertEqual(self.calls[-1], ["1", "2", "3"])


if __name__ == "__main__":
    unittest.main()
