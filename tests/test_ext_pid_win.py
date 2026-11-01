"""Windows CLI pid + start time without /bin/ps: hook parent walk (Toolhelp) and GetProcessTimes, all ctypes faked."""
import ctypes
import importlib.util
import os
import time
import unittest
from unittest import mock

import tests._load  # noqa: F401  (sets SIDEREUS_HOOK_NO_PID before the hook runs)
from tests._load import sidereus

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("ext_hook_win", os.path.join(ROOT, "ext-hooks", "ext_hook.py"))
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)
config = sidereus("config")
st = sidereus("ext_store")

EPOCH = 1793530800                                   # fixed instant, never the clock
FT = EPOCH * 10000000 + 116444736000000000           # same instant as a FILETIME


class _Fn(object):
    """Stands in for one kernel32 function; accepts restype/argtypes assignment."""

    def __init__(self, f):
        self.f = f

    def __call__(self, *a):
        return self.f(*a)


class FakeK32(object):
    def __init__(self, table=None, ft=FT, open_ok=True, err=87, images=None):
        self.table = list((table or {}).items())
        self.images = images or {}
        self.opened = 0
        self.i = 0
        self.closed = []
        self.err = err

        def first(snap, ref):
            self.i = 0
            return nxt(snap, ref)

        def nxt(snap, ref):
            if self.i >= len(self.table):
                return 0
            pid, (ppid, exe) = self.table[self.i]
            self.i += 1
            ref._obj.th32ProcessID, ref._obj.th32ParentProcessID, ref._obj.szExeFile = pid, ppid, exe
            return 1

        def times(h, c, e, k, u):
            if ft is None:
                return 0
            c._obj.value = ft
            return 1
        self.CreateToolhelp32Snapshot = _Fn(lambda flags, pid: 77)
        self.Process32FirstW = _Fn(first)
        self.Process32NextW = _Fn(nxt)
        def open_(acc, inh, pid):
            self.opened = pid
            return 55 if open_ok else 0

        def image(h, flags, buf, n):
            path = self.images.get(self.opened)
            if path is None:
                return 0
            buf.value = path
            return 1
        self.OpenProcess = _Fn(open_)
        self.QueryFullProcessImageNameW = _Fn(image)
        self.GetProcessTimes = _Fn(times)
        self.CloseHandle = _Fn(lambda h: self.closed.append(h) or 1)


def _windll(k32):
    return mock.patch.object(ctypes, "WinDLL", lambda name, use_last_error=False: k32, create=True)


# node.exe (CLI) -> cmd.exe -> py.exe -> python.exe (the hook's parent)
TABLE = {300: (200, "python.exe"), 200: (150, "py.exe"), 150: (100, "cmd.exe"), 100: (50, "node.exe"),
         50: (4, "explorer.exe")}


class HookWin(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch.object(hook, "IS_WIN", True, create=True),
                  mock.patch.object(hook.os, "getppid", lambda: 300),
                  mock.patch.dict(os.environ, {"SIDEREUS_HOOK_NO_PID": ""}),
                  mock.patch.object(hook, "_ps", lambda pid: self.fail("ps must not run on Windows"))):
            p.start()
            self.addCleanup(p.stop)

    def test_walks_past_wrappers_to_cli(self):
        with _windll(FakeK32(TABLE)):
            self.assertEqual(hook.cli_pid(), (100, config.lstart_fmt(EPOCH)))

    def test_skip_list_honoured(self):
        t = {300: (200, "python3.11.exe"), 200: (150, "pwsh.exe"), 150: (120, "powershell.exe"),
             120: (110, "conhost.exe"), 110: (100, "bash.exe"), 100: (50, "codex.exe")}
        with _windll(FakeK32(t)):
            self.assertEqual(hook.cli_pid()[0], 100)

    def test_ctypes_failure_is_zero(self):
        boom = mock.patch.object(ctypes, "WinDLL", mock.Mock(side_effect=OSError("no kernel32")), create=True)
        with boom:
            self.assertEqual(hook.cli_pid(), (0, ""))

    def test_parent_missing_is_zero(self):
        with _windll(FakeK32({1: (0, "node.exe")})):
            self.assertEqual(hook.cli_pid(), (0, ""))

    def test_start_failure_keeps_pid(self):
        with _windll(FakeK32(TABLE, ft=None)):
            self.assertEqual(hook.cli_pid(), (100, ""))

    def test_codex_daemon_is_unknown(self):
        t = {300: (200, "python.exe"), 200: (34256, "cmd.exe"), 34256: (26440, "codex.exe"), 26440: (1, "node.exe")}
        daemon = r"C:\Users\u\.codex\packages\app-server-daemon\releases\0.166.0\bin\codex.exe"
        with _windll(FakeK32(t, images={34256: daemon})):
            self.assertEqual(hook.cli_pid(), (0, ""))                # never the daemon, never past it
        with _windll(FakeK32(t, images={34256: r"C:\Users\u\AppData\npm\codex.exe"})):
            self.assertEqual(hook.cli_pid(), (34256, config.lstart_fmt(EPOCH)))

    def test_formats_match_server(self):
        for e in (EPOCH, EPOCH + 86400 * 9 + 3661, 0):
            self.assertEqual(hook._lstart_fmt(e), config.lstart_fmt(e))
        # ext_presence._start_ts parses the same text back to the instant
        self.assertEqual(sidereus("ext_presence")._start_ts(config.lstart_fmt(EPOCH)), EPOCH)


class HookPosixDaemon(unittest.TestCase):
    def setUp(self):
        tree = {100: (90, "Thu Sep 24 10:00:01 2026", "sh"), 90: (1, "Thu Sep 24 10:00:00 2026", "codex")}
        self.args = {}
        for p in (mock.patch.object(hook, "IS_WIN", False),
                  mock.patch.object(hook.os, "getppid", lambda: 100),
                  mock.patch.dict(os.environ, {"SIDEREUS_HOOK_NO_PID": ""}),
                  mock.patch.object(hook, "_ps", tree.get),
                  mock.patch.object(hook, "_ps_args", lambda pid: self.args.get(pid, ""), create=True)):
            p.start()
            self.addCleanup(p.stop)

    def test_app_server_is_unknown(self):
        self.args[90] = "/home/dev/.codex/packages/app-server-daemon/bin/codex app-server --listen unix://x"
        self.assertEqual(hook.cli_pid(), (0, ""))

    def test_plain_codex_keeps_pid(self):
        self.args[90] = "codex --model gpt-5"
        self.assertEqual(hook.cli_pid(), (90, "Thu Sep 24 10:00:00 2026"))

    def test_daemon_payload_marks_pid_none(self):
        self.args[90] = "/home/dev/.codex/packages/app-server-daemon/bin/codex app-server --listen unix://x"
        out, _ = hook.build("codex", {"hook_event_name": "Stop", "session_id": "c1"})
        self.assertNotIn("pid", out)
        self.assertEqual(out.get("pid_none"), "daemon")

    def test_ps_timeout_sends_no_marker(self):
        with mock.patch.object(hook, "_ps", lambda pid: None):     # ps timed out (1 s): lookup failure, not a finding
            out, _ = hook.build("codex", {"hook_event_name": "Stop", "session_id": "c1"})
        self.assertNotIn("pid", out)
        self.assertNotIn("pid_none", out)


class StoreWin(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(config, "IS_WIN", True)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(st.subprocess, "run", side_effect=AssertionError("ps must not run on Windows")).start()

    def test_pid_start_from_process_times(self):
        k = FakeK32()
        with _windll(k):
            self.assertEqual(st._pid_start(4242), config.lstart_fmt(EPOCH))
        self.assertEqual(k.closed, [55])

    def test_pid_start_times_failure_none(self):
        with _windll(FakeK32(ft=None)):
            self.assertIsNone(st._pid_start(4242))

    def test_pid_start_no_such_pid_empty(self):
        k = FakeK32(open_ok=False)
        with _windll(k), mock.patch.object(ctypes, "get_last_error", lambda: 87, create=True):
            self.assertEqual(st._pid_start(4242), "")
        with _windll(k), mock.patch.object(ctypes, "get_last_error", lambda: 5, create=True):
            self.assertIsNone(st._pid_start(4242))

    def test_pid_start_ctypes_missing_none(self):
        with mock.patch.object(ctypes, "WinDLL", mock.Mock(side_effect=OSError()), create=True):
            self.assertIsNone(st._pid_start(4242))

    def test_reused_pid_is_gone(self):
        mock.patch.object(st, "pid_alive", lambda pid: True).start()
        with _windll(FakeK32()):
            self.assertTrue(st._pid_gone(4242, "Mon Jan 1 00:00:00 2001"))
            self.assertFalse(st._pid_gone(4242, config.lstart_fmt(EPOCH)))


class PidAliveWin(unittest.TestCase):
    """config.pid_alive on Windows: OpenProcess + WaitForSingleObject(h, 0), kernel32 faked."""

    def setUp(self):
        p = mock.patch.object(config, "IS_WIN", True)
        p.start()
        self.addCleanup(p.stop)
        self.kill = mock.patch.object(config.os, "kill", side_effect=AssertionError("os.kill kills on Windows"))
        self.kill.start()
        self.addCleanup(self.kill.stop)

    def _run(self, errs=(), wait=0x102):
        """errs: last-error per OpenProcess call (0 = success). Returns (result, access masks tried)."""
        tried, errs, last = [], list(errs), [0]

        def open_(acc, inh, pid):
            tried.append(acc)
            last[0] = errs.pop(0) if errs else 0
            return 0 if last[0] else 9
        k = FakeK32()
        k.OpenProcess = _Fn(open_)
        k.WaitForSingleObject = _Fn(lambda h, ms: wait)
        with _windll(k), mock.patch.object(ctypes, "get_last_error", lambda: last[0], create=True):
            return config.pid_alive(4242), tried, k.closed

    def test_exited_but_open_handle_is_gone(self):
        r, tried, closed = self._run(wait=0)          # WAIT_OBJECT_0
        self.assertIs(r, False)
        self.assertEqual((tried, closed), ([0x00101000], [9]))

    def test_running_is_alive(self):
        self.assertIs(self._run(wait=0x102)[0], True)

    def test_access_denied_exists(self):
        r, tried, _ = self._run(errs=(5, 5))
        self.assertIs(r, True)
        self.assertEqual(tried, [0x00101000, 0x00100000])
        r, tried, _ = self._run(errs=(5, 0), wait=0)  # SYNCHRONIZE alone opens: the wait still decides
        self.assertIs(r, False)

    def test_invalid_pid_gone_other_error_unknown(self):
        self.assertIs(self._run(errs=(87,))[0], False)
        self.assertIsNone(self._run(errs=(6,))[0])
        self.assertIsNone(self._run(wait=0xFFFFFFFF)[0])   # WAIT_FAILED


if __name__ == "__main__":
    unittest.main()
