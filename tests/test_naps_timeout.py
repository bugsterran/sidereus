"""_naps_fetch timeout: the pmset|grep pipeline runs in its own process group and the whole group is killed.

subprocess/os/signal are faked on the module — pmset is never run.
"""
import subprocess
import types
import unittest

from tests._load import sidereus

tl = sidereus("timeline_scan")


class FakeProc:
    pid = 4242

    def __init__(self, log):
        self.log = log
        self.calls = 0

    def communicate(self, timeout=None):
        self.calls += 1
        self.log.append(("communicate", timeout))
        if self.calls == 1:
            raise subprocess.TimeoutExpired("sh", timeout)
        return "", ""

    def kill(self):
        self.log.append(("kill",))


class NapsTimeout(unittest.TestCase):
    def setUp(self):
        self.saved = (tl.subprocess, tl.os, tl.signal, tl.IS_MAC, tl.warn_once, dict(tl._naps_cache))
        self.log = []
        self.popen_kw = {}

        def popen(argv, **kw):
            self.popen_kw = kw
            self.proc = FakeProc(self.log)
            return self.proc

        def killpg(pid, sig):
            self.log.append(("killpg", pid, sig))
            raise ProcessLookupError   # group already gone must not break the reap
        tl.subprocess = types.SimpleNamespace(Popen=popen, PIPE=subprocess.PIPE,
                                              TimeoutExpired=subprocess.TimeoutExpired)
        tl.os = types.SimpleNamespace(killpg=killpg)
        tl.signal = types.SimpleNamespace(SIGKILL=9)
        tl.IS_MAC = True
        tl.warn_once = lambda *a, **k: None

    def tearDown(self):
        tl.subprocess, tl.os, tl.signal, tl.IS_MAC, tl.warn_once = self.saved[:5]
        tl._naps_cache.clear(); tl._naps_cache.update(self.saved[5])

    def test_timeout_kills_group_and_returns_none(self):
        self.assertIsNone(tl._naps_fetch())
        self.assertTrue(self.popen_kw.get("start_new_session"))
        self.assertIn(("killpg", 4242, 9), self.log)
        # reaped after the kill
        self.assertEqual([e[0] for e in self.log], ["communicate", "killpg", "kill", "communicate"])

    def test_refresh_keeps_last_good_cache(self):
        good = [(1000.0, 2000.0)]
        tl._naps_cache.clear(); tl._naps_cache.update({"at": 0.0, "v": list(good), "busy": True})
        tl._naps_refresh()
        self.assertEqual(tl._naps_cache["v"], good)
        self.assertFalse(tl._naps_cache["busy"])
        self.assertIn(("killpg", 4242, 9), self.log)


if __name__ == "__main__":
    unittest.main()
