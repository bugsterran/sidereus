"""hooks/mail_wait.py: one waiter per session, check() only when bus.jsonl changes, no OS branch. Tmp dirs only."""
import ast
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

_H = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks")
_spec = importlib.util.spec_from_file_location("mail_wait_t", os.path.join(_H, "mail_wait.py"))
MW = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(MW)


class FakeTime(object):
    """Injected clock + sleep: sleep advances the clock and runs an optional per-call hook."""

    def __init__(self, on_sleep=None):
        self.t, self.n, self.on_sleep = 0.0, 0, on_sleep

    def clock(self):
        return self.t

    def sleep(self, s):
        self.n += 1
        self.t += max(s, 0.5)
        if self.on_sleep:
            self.on_sleep(self.n)


class MailWait(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.store)
        self.bus = os.path.join(self.store, "bus.jsonl")
        open(self.bus, "w", encoding="utf-8").close()
        self.calls = 0

    def append(self):
        with open(self.bus, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.time_ns()}) + "\n")

    def check_none(self):
        self.calls += 1
        return None

    def test_R5_poll_only_on_stat_change(self):
        ft = FakeTime(on_sleep=lambda n: self.append() if n == 5 else None)
        st, got = MW.wait(self.store, "s1", "me", self.check_none, 40, poll_s=2, sleep=ft.sleep, clock=ft.clock,
                          retry_s=1000)
        self.assertEqual((st, got), ("timeout", None))
        self.assertGreater(ft.n, 10)                       # many polls ...
        self.assertEqual(self.calls, 2)                    # ... but check() only at start and after the one append

    def test_retry_without_bus_change(self):
        # check() can return None for non-bus reasons (time budget, cursor); it must be retried without a new post
        ft = FakeTime()
        res = iter([None, "mail"])
        st, got = MW.wait(self.store, "s1", "me", lambda: next(res), 100, poll_s=2, sleep=ft.sleep, clock=ft.clock,
                          retry_s=30)
        self.assertEqual((st, got), ("hit", "mail"))
        self.assertGreaterEqual(ft.t, 30)                  # not before the retry interval

    def test_hit_returns_check_value(self):
        hits = []
        ft = FakeTime(on_sleep=lambda n: self.append() if n == 3 else None)

        def check():
            hits.append(1)
            return "mail" if len(hits) == 2 else None
        self.assertEqual(MW.wait(self.store, "s1", "me", check, 100, sleep=ft.sleep, clock=ft.clock), ("hit", "mail"))
        self.assertFalse(os.path.exists(MW.lock_path(self.store, "s1")))      # released on exit

    def test_missing_bus_checks_once_then_on_creation(self):
        os.remove(self.bus)
        ft = FakeTime(on_sleep=lambda n: self.append() if n == 4 else None)
        MW.wait(self.store, "s1", "me", self.check_none, 20, sleep=ft.sleep, clock=ft.clock)
        self.assertEqual(self.calls, 2)

    def test_R5_no_platform_branch(self):
        for name in ("mail_wait.py", "mailbox_wake.py"):
            with open(os.path.join(_H, name), encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                    self.assertNotIn((node.value.id, node.attr), {("sys", "platform"), ("os", "name")}, name)
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    mods = [a.name for a in node.names] + [getattr(node, "module", None) or ""]
                    self.assertNotIn("platform", mods, name)

    def test_one_waiter_per_session(self):
        lp = MW.lock_path(self.store, "s1")
        os.makedirs(os.path.dirname(lp))
        with open(lp, "w", encoding="utf-8") as f:
            f.write("999999")                              # fresh heartbeat held by another waiter
        ft = FakeTime()
        self.assertEqual(MW.wait(self.store, "s1", "me", self.check_none, 5, sleep=ft.sleep, clock=ft.clock)[0], "busy")
        self.assertEqual(self.calls, 0)
        old = time.time() - 60
        os.utime(lp, (old, old))                           # stale -> taken over
        self.assertEqual(MW.wait(self.store, "s1", "me", self.check_none, 5, sleep=ft.sleep, clock=ft.clock)[0],
                         "timeout")
        self.assertFalse(os.path.exists(lp))

    def test_newer_waiter_takes_the_slot(self):
        lp = MW.lock_path(self.store, "s1")

        def steal(n):
            if n == 2:
                with open(lp, "w", encoding="utf-8") as f:
                    f.write("999999")
        ft = FakeTime(on_sleep=steal)
        self.assertEqual(MW.wait(self.store, "s1", "me", self.check_none, 50, sleep=ft.sleep, clock=ft.clock)[0], "lost")
        self.assertTrue(os.path.exists(lp))                # the new owner's lock stays

    def test_waiting_writes_watch_heartbeat(self):
        ft = FakeTime()
        MW.wait(self.store, "s1", "me", self.check_none, 3, sleep=ft.sleep, clock=ft.clock)
        self.assertTrue(os.path.exists(os.path.join(self.store, "presence-me.watch")))

    def test_lock_path_sanitises_sid(self):
        self.assertEqual(os.path.basename(MW.lock_path(self.store, "../a b/c")), "abc.lock")


if __name__ == "__main__":
    unittest.main()
