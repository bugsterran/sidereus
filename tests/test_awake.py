"""sidereus/awake.py: caffeinate hold while sessions are busy (tool/think), grace window, reaping, failure path.

No real process is spawned: subprocess.Popen, sessions(), IS_MAC and the module clock are monkeypatched.
The loop is driven one tick at a time — the fake sleep raises a BaseException the loop does not catch.
"""
import unittest

from tests._load import sidereus

aw = sidereus("awake")


class _Stop(BaseException):
    """Escapes `except Exception` in _awake_loop so one iteration can be observed."""


class _Proc:
    def __init__(self, argv=None, **kw):
        self.argv, self.dead, self.terminated = argv, False, False

    def poll(self):
        return 0 if self.dead else None

    def terminate(self):
        self.terminated = True
        self.dead = True

    def wait(self, timeout=None):
        return 0


class _Clock:
    def __init__(self, t):
        self.t, self.sleeps = t, []

    def time(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        raise _Stop()


class _Base(unittest.TestCase):
    def patch(self, mod, name, val):
        old = getattr(mod, name)
        setattr(mod, name, val)
        self.addCleanup(setattr, mod, name, old)

    def setUp(self):
        self.spawned = []

        def popen(argv, **kw):
            p = _Proc(argv)
            self.spawned.append(p)
            return p
        self.patch(aw.subprocess, "Popen", popen)
        self.patch(aw, "IS_MAC", True)
        self.patch(aw, "IS_WIN", False)
        self.patch(aw, "_win_held", [False])
        self.patch(aw, "_awake", {"on": False, "since": 0.0, "n": 0, "last": 0.0})
        self.patch(aw, "_awake_proc", [None])


class Busy(_Base):
    def test_counts_only_model_side_states(self):
        seen = {}

        def fake(max_age_h=None, cap=None):
            seen.update(max_age_h=max_age_h, cap=cap)
            return [{"state": s} for s in ("tool", "think", "wait", "ask", "done", "", None)] + [{}]
        self.patch(aw, "sessions", fake)
        self.assertEqual(aw._awake_busy(), 2)
        self.assertEqual(seen, {"max_age_h": 2, "cap": 24})

    def test_sessions_error_counts_as_zero(self):
        def boom(**kw):
            raise OSError("x")
        self.patch(aw, "sessions", boom)
        self.assertEqual(aw._awake_busy(), 0)


class Apply(_Base):
    def test_non_mac_is_noop(self):
        self.patch(aw, "IS_MAC", False)
        aw._awake_apply(True)
        self.assertEqual(self.spawned, [])
        self.assertIsNone(aw._awake_proc[0])

    def test_start_is_tied_to_server_pid(self):
        aw._awake_apply(True)
        (p,) = self.spawned
        self.assertEqual(p.argv[:4], ["/usr/bin/caffeinate", "-i", "-s", "-w"])
        self.assertEqual(p.argv[4], str(aw.os.getpid()))   # orphan guard: ends with the server
        self.assertNotIn("-d", p.argv)                      # display may still turn off
        aw._awake_apply(True)
        self.assertEqual(len(self.spawned), 1)              # already alive -> no second child

    def test_release_terminates(self):
        aw._awake_apply(True)
        p = aw._awake_proc[0]
        aw._awake_apply(False)
        self.assertTrue(p.terminated)
        self.assertIsNone(aw._awake_proc[0])

    def test_dead_child_reaped_and_restarted(self):
        aw._awake_apply(True)
        self.spawned[0].dead = True
        aw._awake_apply(False)
        self.assertIsNone(aw._awake_proc[0])
        aw._awake_proc[0] = self.spawned[0]
        aw._awake_apply(True)
        self.assertEqual(len(self.spawned), 2)
        self.assertIs(aw._awake_proc[0], self.spawned[1])

    def test_terminate_error_still_clears(self):
        aw._awake_apply(True)

        def bad():
            raise OSError("gone")
        aw._awake_proc[0].terminate = bad
        aw._awake_apply(False)
        self.assertIsNone(aw._awake_proc[0])


class _Kernel32:
    def __init__(self, ret=1, exc=None):
        self.calls, self.ret, self.exc = [], ret, exc

    def SetThreadExecutionState(self, flags):
        self.calls.append(flags)
        if self.exc:
            raise self.exc
        return self.ret


class Windows(_Base):
    """Windows branch driven through a fake `ctypes.windll` (absent on Mac/Linux)."""

    def setUp(self):
        super().setUp()
        import ctypes
        self.patch(aw, "IS_MAC", False)
        self.patch(aw, "IS_WIN", True)
        self.k = _Kernel32()
        had = hasattr(ctypes, "windll")
        old = getattr(ctypes, "windll", None)
        ctypes.windll = type("W", (), {"kernel32": self.k})()
        self.addCleanup(lambda: setattr(ctypes, "windll", old) if had else delattr(ctypes, "windll"))
        self.warned = []
        self.patch(aw, "warn_once", lambda k, *a, **kw: self.warned.append(k))

    def test_hold_and_release_flags(self):
        aw._awake_apply(True)
        aw._awake_apply(True)                               # already held -> no second call
        self.assertTrue(aw._awake_held())
        aw._awake_apply(False)
        self.assertEqual(self.k.calls, [0x80000001, 0x80000000])
        self.assertFalse(aw._awake_held())
        self.assertEqual(self.spawned, [])                  # no caffeinate on Windows

    def test_call_error_is_quiet_and_off(self):
        self.k.exc = OSError("denied")
        aw._awake_apply(True)
        self.assertFalse(aw._awake_held())
        self.assertEqual(self.warned, ["awake-win"])

    def test_zero_return_reads_off(self):
        self.k.ret = 0
        aw._awake_apply(True)
        self.assertFalse(aw._awake_held())

    def test_loop_reports_on(self):
        clk = _Clock(1000.0)
        self.patch(aw, "time", clk)
        self.patch(aw, "_awake_busy", lambda: 1)
        with self.assertRaises(_Stop):
            aw._awake_loop()
        self.assertEqual((aw._awake["on"], aw._awake["since"]), (True, 1000.0))


class Loop(_Base):
    def tick(self, t, busy):
        clk = _Clock(t)
        self.patch(aw, "time", clk)
        self.patch(aw, "_awake_busy", lambda: busy)
        with self.assertRaises(_Stop):
            aw._awake_loop()
        return clk

    def test_busy_holds_and_records_since(self):
        clk = self.tick(1000.0, 2)
        self.assertEqual(clk.sleeps, [aw.AWAKE_EVERY_S])
        self.assertEqual(aw._awake, {"on": True, "since": 1000.0, "n": 2, "last": 1000.0})
        self.assertEqual(len(self.spawned), 1)

    def test_grace_keeps_hold_then_releases(self):
        self.tick(1000.0, 1)
        self.tick(1000.0 + aw.AWAKE_GRACE_S - 1, 0)
        self.assertTrue(aw._awake["on"])
        self.assertEqual(aw._awake["since"], 1000.0)        # not reset while held
        self.tick(1000.0 + aw.AWAKE_GRACE_S, 0)
        self.assertFalse(aw._awake["on"])
        self.assertTrue(self.spawned[0].terminated)

    def test_idle_from_start_never_holds(self):
        self.tick(1000.0, 0)
        self.assertEqual(self.spawned, [])
        self.assertFalse(aw._awake["on"])

    def test_off_switch_releases(self):
        aw._awake_apply(True)
        aw._awake.update(on=True, n=3)
        self.patch(aw, "AWAKE_HOLD", False)
        self.tick(1000.0, 5)
        self.assertTrue(self.spawned[0].terminated)
        self.assertEqual((aw._awake["on"], aw._awake["n"]), (False, 0))

    def test_exception_warns_records_and_sleeps(self):
        warned = []
        self.patch(aw, "warn_once", lambda k, msg, en="", vars=None: warned.append(k))
        errs = {}
        self.patch(aw, "_LOOP_ERR", errs)

        def boom(want):
            raise RuntimeError("caffeinate missing")
        self.patch(aw, "_awake_apply", boom)
        clk = self.tick(1000.0, 1)
        self.assertEqual(clk.sleeps, [120])                 # the exception path must sleep too
        self.assertEqual(warned, ["loop:awake"])
        self.assertEqual(errs["awake"]["at"], 1000.0)
        self.assertIn("caffeinate missing", errs["awake"]["err"])

    def test_success_clears_loop_error(self):
        errs = {"awake": {"at": 1, "err": "old"}}
        self.patch(aw, "_LOOP_ERR", errs)
        self.tick(1000.0, 1)
        self.assertNotIn("awake", errs)


if __name__ == "__main__":
    unittest.main()
