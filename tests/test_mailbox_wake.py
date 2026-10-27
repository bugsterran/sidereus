"""Async Stop hook hooks/mailbox_wake.py: wakes (exit 2) only on new mail or renewal; one waiter per session. Tmp dirs only."""
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

_H = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks")
sys.path.insert(0, _H)
_spec = importlib.util.spec_from_file_location("mailbox_wake_t", os.path.join(_H, "mailbox_wake.py"))
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)


class Wake(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.store)
        with open(os.path.join(self.store, "identity.json"), "w", encoding="utf-8") as f:
            json.dump({"/proj": "me"}, f)
        self.inp = {"session_id": "sess-0001", "cwd": "/proj"}

    def post(self, **m):
        m.setdefault("t", time.time_ns())
        m.setdefault("id", "p%d" % m["t"])
        with open(os.path.join(self.store, "bus.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(m) + "\n")

    def run_w(self, life=0.05, on_sleep=None):
        err = io.StringIO()
        calls = []

        def sleep(s):
            calls.append(s)
            if on_sleep:
                on_sleep(len(calls))
        rc = W.run(self.inp, store=self.store, life_s=life, poll_s=0, first_s=0, err=err, sleep=sleep)
        return rc, err.getvalue()

    def test_new_dm_wakes_with_metadata_only(self):
        self.post(**{"from": "peer", "to": "me", "body": "SECRET BODY"})
        rc, out = self.run_w(life=5)
        self.assertEqual(rc, 2)
        self.assertIn("peer(DM)", out)
        self.assertNotIn("SECRET BODY", out)
        self.assertIn("The wait hook woke you", out)
        self.assertNotIn("No mailbox watch is running", out)
        rc2, out2 = self.run_w(life=0.01)           # same post never wakes twice (shared cursor)
        self.assertEqual(rc2, 2)
        self.assertIn("watch renewed", out2)

    def test_mail_arriving_while_waiting(self):
        def later(n):
            if n == 2:
                self.post(**{"from": "peer", "to": "me"})
        rc, out = self.run_w(life=5, on_sleep=later)
        self.assertEqual(rc, 2)
        self.assertIn("1 new mail", out)

    def test_own_posts_and_unregistered_cwd_stay_silent(self):
        self.post(**{"from": "me", "to": "me"})
        rc, out = self.run_w(life=0.01)
        self.assertIn("watch renewed", out)              # only the renewal, not the own post
        self.inp["cwd"] = "/other"
        self.assertEqual(self.run_w()[0], 0)

    def test_one_waiter_per_session(self):
        lp = W.lock_path(self.store, "sess-0001")
        os.makedirs(os.path.dirname(lp))
        with open(lp, "w", encoding="utf-8") as f:
            f.write("999999")                      # fresh heartbeat held by another waiter
        self.assertEqual(self.run_w(life=5)[0], 0)
        old = time.time() - 60
        os.utime(lp, (old, old))                   # stale -> taken over
        self.post(**{"from": "peer", "to": "me"})
        self.assertEqual(self.run_w(life=5)[0], 2)
        self.assertFalse(os.path.exists(lp))       # released on exit

    def test_waiting_writes_watch_heartbeat(self):
        self.run_w(life=0.01)
        self.assertTrue(os.path.exists(os.path.join(self.store, "presence-me.watch")))

    def _stage(self):
        """The sync Stop hook blocks with stop_hook_active: the post is staged as pending, not confirmed."""
        out = io.StringIO()
        W.MS.T0 = time.monotonic()                 # the sync hook's budget runs from process start
        W.MS.run(dict(self.inp, stop_hook_active=False), out, store=self.store)
        self.assertIn("block", out.getvalue())

    def _state(self):
        with open(W.MS.state_path(self.store, self.inp["session_id"]), encoding="utf-8") as f:
            return json.load(f)

    def test_pending_only_does_not_wake(self):
        self.post(**{"from": "peer", "to": "me"})
        self._stage()
        rc, out = self.run_w(life=0.01)
        self.assertIn("watch renewed", out)
        self.assertIn("pending", self._state())

    def test_new_mail_delivers_pending_and_new_then_clears(self):
        self.post(**{"from": "peer", "to": "me"})
        self._stage()
        self.post(**{"from": "other", "to": "me"})
        rc, out = self.run_w(life=5)
        self.assertEqual(rc, 2)
        self.assertIn("2 new mail", out)
        st = self._state()
        self.assertNotIn("pending", st)
        self.assertGreater(st["last_t"], 0)

    def test_R1_claude_unchanged(self):
        # Exit codes and stderr are what Claude's asyncRewake contract expects; plan() runs only on bus changes.
        real, n = W.MS.plan, []

        def plan(*a, **k):
            n.append(1)
            return real(*a, **k)
        with mock.patch.object(W.MS, "plan", plan):
            rc, out = self.run_w(life=0.05)
            self.assertEqual((rc, out), (2, W.RENEW + "\n"))
            self.assertEqual(len(n), 1)                     # empty bus never changed: one check only
            self.post(**{"from": "peer", "to": "me"})
            rc, out = self.run_w(life=5)
        self.assertEqual(rc, 2)
        self.assertTrue(out.startswith("[mailbox] 1 new mail"), out)
        self.assertTrue(out.endswith("(The wait hook woke you. The same mail will not wake you again.)\n"), out)
        self.assertIs(W.lock_path, W.MW.lock_path)

    def test_bad_input_never_wakes(self):
        self.inp = {}
        self.assertEqual(self.run_w()[0], 0)

    def test_headless_entrypoint_exits_without_reading(self):
        self.assertTrue(W.headless({"CLAUDE_CODE_ENTRYPOINT": "sdk-cli"}))
        self.assertFalse(W.headless({"CLAUDE_CODE_ENTRYPOINT": "cli"}))
        self.assertFalse(W.headless({}))
        orig_stdin = sys.stdin
        try:
            with mock.patch.dict(os.environ, {"CLAUDE_CODE_ENTRYPOINT": "sdk-cli"}, clear=True):
                sys.stdin = io.StringIO("not read")   # run() never reached: no lock, no wait
                self.assertEqual(W.main(), 0)
                self.assertEqual(sys.stdin.read(), "not read")
        finally:
            sys.stdin = orig_stdin
        self.assertFalse(os.path.exists(os.path.join(self.store, ".wake")))

    def test_session_start_clear_arms_waiter_without_backlog(self):
        self.post(**{"from": "peer", "to": "me"})           # surfaced by the pre-/clear sid already
        self.inp = {"session_id": "sess-new", "cwd": "/proj", "hook_event_name": "SessionStart", "source": "clear"}
        held = []
        real = W.MW.wait

        def wait(*a, **k):
            held.append(os.path.exists(W.lock_path(self.store, "sess-new")))
            return real(*a, **k)
        with mock.patch.object(W.MW, "wait", wait), mock.patch.object(W.MW, "take_lock", wraps=W.MW.take_lock) as tl:
            rc, out = self.run_w(life=0.01)
        self.assertEqual(tl.call_args[0][0], W.lock_path(self.store, "sess-new"))
        self.assertEqual(held, [False])
        self.assertEqual((rc, out), (2, W.RENEW + "\n"))  # waited (renewal), no wake on the old post
        self.assertTrue(os.path.exists(os.path.join(self.store, "presence-me.watch")))
        self.post(**{"from": "peer", "to": "me"})
        rc, out = self.run_w(life=5)
        self.assertEqual(rc, 2)
        self.assertIn("1 new mail", out)

    def test_stop_while_session_start_waiter_holds_lock_is_quiet(self):
        lp = W.lock_path(self.store, "sess-0001")
        os.makedirs(os.path.dirname(lp))
        with open(lp, "w", encoding="utf-8") as f:
            f.write("999999")                              # SessionStart waiter's fresh heartbeat
        self.post(**{"from": "peer", "to": "me"})
        self.inp = dict(self.inp, hook_event_name="Stop", stop_hook_active=False, last_assistant_message="x")
        self.assertEqual(self.run_w(life=5), (0, ""))
        with open(lp, encoding="utf-8") as f:
            self.assertEqual(f.read(), "999999")           # holder untouched

    def test_plugin_session_start_runs_waiter(self):
        with open(os.path.join(os.path.dirname(_H), "plugin", "hooks", "hooks.json"), encoding="utf-8") as f:
            groups = json.load(f)["hooks"]["SessionStart"]
        hs = [(g.get("matcher"), h) for g in groups for h in g["hooks"]
              if h["command"].rstrip('"').endswith("/mailbox_wake.py")]
        self.assertEqual(len(hs), 1)
        self.assertIn("clear", hs[0][0].split("|"))
        self.assertIs(hs[0][1].get("asyncRewake"), True)


if __name__ == "__main__":
    unittest.main()
