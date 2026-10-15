"""hooks/mailbox_stop.py (Stop hook): synthetic data dir only — never the live bus, identity or state."""
import json
import os
import resource
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "hooks", "mailbox_stop.py")
CWD = "/p/work"
ME = "alice"


def _child_cpu():
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    return r.ru_utime + r.ru_stime


class MailboxStop(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.now = time.time_ns()
        self.n = 0
        self.w("identity.json", {CWD: ME, "/p/other": "bob"})
        self.w("rooms.json", {"r1": {"members": [ME, "bob"]}, "r2": {"members": ["bob", "carol"]}})
        open(self.p("bus.jsonl"), "w").close()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def p(self, name):
        return os.path.join(self.d, name)

    def w(self, name, data):
        with open(self.p(name), "w", encoding="utf-8") as f:
            json.dump(data, f)

    def post(self, frm, to=None, room=None, raw=None):
        self.n += 1
        mid = f"m{self.n}"
        line = raw if raw is not None else json.dumps(
            {"id": mid, "t": self.now + self.n * 1000, "from": frm, "to": to, "room": room, "body": "SECRET-BODY"})
        with open(self.p("bus.jsonl"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
        return mid

    def run_hook(self, cwd=CWD, sid="s1", active=False):
        """active=None omits the stop_hook_active key (the commit-at-once path)."""
        env = dict(os.environ, MAILBOX_DIR=self.d)
        inp = {"session_id": sid, "cwd": cwd, "transcript_path": "/x", "hook_event_name": "Stop"}
        if active is not None:
            inp["stop_hook_active"] = active
        inp = json.dumps(inp)
        c0 = _child_cpu()
        r = subprocess.run(["/usr/bin/python3", HOOK], input=inp, capture_output=True, text=True,
                           env=env, timeout=10)
        self.cpu = _child_cpu() - c0
        self.assertEqual(r.returncode, 0)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def test_no_id_is_silent(self):
        self.post("bob", to=ME)
        self.assertIsNone(self.run_hook(cwd="/p/unregistered"))
        self.assertIsNone(self.run_hook(cwd="/p/work/sub"))      # no ancestor fallback

    def test_watch_running_is_silent(self):
        self.post("bob", to=ME)
        with open(self.p(f".watch-{ME}.pid"), "w") as f:
            f.write(str(os.getpid()))
        self.assertIsNone(self.run_hook())

    def test_dead_watch_lock_does_not_silence(self):
        self.post("bob", to=ME)
        with open(self.p(f".watch-{ME}.pid"), "w") as f:
            f.write("999999")
        self.assertIsNotNone(self.run_hook())

    def test_block_once_then_newer_blocks_again(self):
        self.post("bob", to=ME)
        self.post("bob", room="r1")
        out = self.run_hook()
        self.assertEqual(out["decision"], "block")
        self.assertIn("2건", out["reason"])
        self.assertIn("bob(DM)", out["reason"])
        self.assertIn("bob(방 r1)", out["reason"])
        self.assertNotIn("SECRET-BODY", out["reason"])
        self.assertIsNone(self.run_hook(active=True))           # same set -> never twice
        self.assertIsNone(self.run_hook(active=False))
        self.post("carol", to=ME)
        out = self.run_hook(active=True)
        self.assertIn("1건", out["reason"])
        self.assertIn("carol(DM)", out["reason"])

    def test_state_is_per_session(self):
        self.post("bob", to=ME)
        self.assertIsNotNone(self.run_hook(sid="s1"))
        self.assertIsNotNone(self.run_hook(sid="s2"))

    def test_ignores_not_mine_own_read_and_acked(self):
        self.post(ME, room="r1")                    # own post
        self.post("bob", room="r2")                 # room alice is not in
        self.post("bob", to="carol")                # someone else's DM
        self.assertIsNone(self.run_hook(sid="a"))
        read = self.post("bob", to=ME)
        with open(self.p(f"read-{ME}.cursor"), "w") as f:
            f.write(str(self.now + self.n * 1000))  # cursor at the last post
        self.assertIsNone(self.run_hook(sid="b"))
        os.unlink(self.p(f"read-{ME}.cursor"))
        with open(self.p("acks.jsonl"), "w") as f:
            f.write(json.dumps({"id": read, "who": ME, "kind": "ack", "t": self.now}) + "\n")
        self.assertIsNone(self.run_hook(sid="c"))

    def test_old_messages_outside_lookback_ignored(self):
        with open(self.p("bus.jsonl"), "a") as f:
            f.write(json.dumps({"id": "old", "t": self.now - 7 * 3600 * 10 ** 9, "from": "bob", "to": ME}) + "\n")
        self.assertIsNone(self.run_hook())

    def test_malformed_lines_ignored(self):
        self.post("x", raw="{not json")
        self.post("x", raw='"a string"')
        self.post("x", raw='{"t": "NaN", "from": "bob", "to": "alice"}')
        self.post("bob", to=ME)
        out = self.run_hook()
        self.assertIn("1건", out["reason"])

    def test_broken_inputs_exit_zero(self):
        with open(self.p("identity.json"), "w") as f:
            f.write("{broken")
        self.assertIsNone(self.run_hook())
        env = dict(os.environ, MAILBOX_DIR=self.d)
        r = subprocess.run(["/usr/bin/python3", HOOK], input="not json", capture_output=True, text=True, env=env)
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_time_budget_on_large_bus(self):
        # ⚠Child CPU time against a small-bus baseline from this run: wall time failed under parallel load (0.65s).
        base = []
        for _ in range(2):
            self.post("bob", to=ME)
            self.assertIsNotNone(self.run_hook())
            base.append(self.cpu)
        big = json.dumps({"id": "z", "t": self.now - 10 ** 12, "from": "bob", "room": "r1", "body": "x" * 400})
        with open(self.p("bus.jsonl"), "a") as f:
            f.write((big + "\n") * 60000)          # ~27 MB: a full scan costs >= 0.12 s CPU, the tail read ~5 ms
        cost = []
        for _ in range(2):
            self.post("bob", to=ME)
            self.assertIsNotNone(self.run_hook())
            cost.append(self.cpu)
        self.assertLess(min(cost), min(base) + 0.06, (base, cost))
        self.assertLess(min(cost), 0.3)            # hook budget

    # --- Sidereus relays (kind:relay, idSrc:viewer) ---
    def relay(self, sid=None, src="viewer", body="DO-THIS", to=ME):
        self.n += 1
        mid = f"r{self.n}"
        row = {"id": mid, "t": self.now + self.n * 1000, "from": "human", "to": to, "kind": "relay",
               "idSrc": src, "body": body}
        if sid:
            row["sid"] = sid
        self.post("x", raw=json.dumps(row))
        return mid

    def hooked(self):
        try:
            with open(self.p("acks.jsonl")) as f:
                return [json.loads(x) for x in f if '"hooked"' in x]
        except OSError:
            return []

    def test_relay_matching_sid_blocks_with_body(self):
        mid = self.relay(sid="s1")
        out = self.run_hook(sid="s1")
        self.assertEqual(out["decision"], "block")
        self.assertIn("DO-THIS", out["reason"])
        self.assertIn(f"id {mid}", out["reason"])
        self.assertIn("mailbox_ack(id)", out["reason"])
        self.assertNotIn("[메일박스]", out["reason"])       # relays are not in the metadata notice
        self.assertEqual(self.hooked(), [])                 # staged until the block is honoured
        self.assertIsNone(self.run_hook(sid="s1", active=True))
        h = self.hooked()
        self.assertEqual([(x["id"], x["who"], x["note"]) for x in h], [(mid, ME, "s1")])

    def test_relay_other_sid_or_source_ignored(self):
        self.relay(sid="other")
        self.assertIsNone(self.run_hook(sid="s1"))
        self.relay(src="mcp")                               # not from Sidereus -> plain mail, metadata only
        out = self.run_hook(sid="s1")
        self.assertIn("[메일박스]", out["reason"])
        self.assertNotIn("DO-THIS", out["reason"])
        self.assertEqual(self.hooked(), [])

    def test_relay_second_run_adds_nothing(self):
        self.relay()
        self.assertIsNotNone(self.run_hook())
        self.assertIsNone(self.run_hook(active=True))
        self.assertIsNone(self.run_hook(sid="s1b"))       # hooked receipt covers other sessions too
        self.assertEqual(len(self.hooked()), 1)

    def test_relay_already_hooked_or_acked_skipped(self):
        a = self.relay()
        b = self.relay()
        with open(self.p("acks.jsonl"), "w") as f:
            f.write(json.dumps({"id": a, "who": ME, "kind": "hooked", "t": self.now}) + "\n")
            f.write(json.dumps({"id": b, "who": ME, "kind": "ack", "t": self.now}) + "\n")
        self.assertIsNone(self.run_hook())

    def test_relay_watcher_delivered_still_handed_over(self):
        # A watcher's "delivered" only notifies — the body must still reach the session.
        a = self.relay(body="BODY-W")
        with open(self.p("acks.jsonl"), "w") as f:
            f.write(json.dumps({"id": a, "who": ME, "kind": "delivered", "t": self.now}) + "\n")
        out = self.run_hook()
        self.assertIn("BODY-W", out["reason"])

    def test_relay_cap_then_rest(self):
        ids = [self.relay(body=f"B{i}") for i in range(5)]
        out = self.run_hook()
        for i in ids[:3]:
            self.assertIn(f"id {i}", out["reason"])
        self.assertNotIn(f"id {ids[3]}", out["reason"])
        self.assertIsNone(self.run_hook(active=True))      # promote only
        out = self.run_hook()
        self.assertIn(f"id {ids[3]}", out["reason"])
        self.assertIn(f"id {ids[4]}", out["reason"])
        self.assertIsNone(self.run_hook(active=True))
        self.assertIsNone(self.run_hook())

    def test_relay_body_cut_and_notice_appended(self):
        self.post("bob", to=ME)
        mid = self.relay(body="y" * 21000)
        out = self.run_hook()
        r = out["reason"]
        self.assertTrue("y" * 20000 + f"… (잘림 — mailbox_inbox 로 전문 확인, id {mid})" in r)
        self.assertFalse("y" * 20001 in r)
        self.assertLess(r.index("[아고라 전달"), r.index("[메일박스]"))
        self.assertIn("1건", r)                            # the relay is not counted as mail

    def test_relay_ui_sized_body_whole(self):
        self.relay(body="z" * 19000)
        r = self.run_hook()["reason"]
        self.assertTrue("z" * 19000 + "\n" in r)
        self.assertNotIn("잘림", r)

    def test_relay_total_cap_defers_not_cuts(self):
        a = self.relay(body="A" * 15000)
        b = self.relay(body="B" * 15000)
        r = self.run_hook()["reason"]
        self.assertIn(f"id {a}", r)
        self.assertNotIn(f"id {b}", r)
        self.assertIsNone(self.run_hook(active=True))
        self.assertEqual([x["id"] for x in self.hooked()], [a])
        r = self.run_hook()["reason"]
        self.assertTrue(f"id {b}" in r and "B" * 15000 in r)
        self.assertIsNone(self.run_hook(active=True))
        self.assertIsNone(self.run_hook())

    def _inproc(self, fail):
        """Run main() in-process with save_state or the receipt append failing; returns stdout."""
        import importlib.util, io
        spec = importlib.util.spec_from_file_location("mailbox_stop_t", HOOK)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if fail == "save":
            def boom(p, d):
                raise OSError("disk full")
            mod.save_state = boom
        real_open = open

        def fopen(path, mode="r", *a, **k):
            if fail == "append" and str(path).endswith("acks.jsonl") and "a" in mode:
                raise OSError("disk full")
            return real_open(path, mode, *a, **k)
        mod.open = fopen
        inp = json.dumps({"session_id": "s1", "cwd": CWD})
        old = (sys.stdin, sys.stdout, os.environ.get("MAILBOX_DIR"))
        sys.stdin, sys.stdout, os.environ["MAILBOX_DIR"] = io.StringIO(inp), io.StringIO(), self.d
        try:
            mod.main()
            return sys.stdout.getvalue()
        finally:
            sys.stdin, sys.stdout = old[0], old[1]
            if old[2] is None:
                os.environ.pop("MAILBOX_DIR", None)
            else:
                os.environ["MAILBOX_DIR"] = old[2]

    def test_relay_save_failure_prints_and_marks_nothing(self):
        self.relay(sid="s1")
        self.assertEqual(self._inproc("save"), "")
        self.assertEqual(self.hooked(), [])
        self.assertFalse(os.path.exists(os.path.join(self.d, ".stop-hook")))
        self.assertIn("DO-THIS", self.run_hook()["reason"])     # still pending afterwards

    def test_relay_receipt_failure_after_print(self):
        self.relay(sid="s1")
        out = json.loads(self._inproc("append"))
        self.assertIn("DO-THIS", out["reason"])
        self.assertEqual(self.hooked(), [])
        self.assertIsNone(self.run_hook())                      # relay_t cursor saved: this session not blocked again

    # --- two-phase delivery (stop_hook_active) ---
    def state(self, sid="s1"):
        with open(os.path.join(self.d, ".stop-hook", sid + ".json")) as f:
            return json.load(f)

    def test_block_stages_pending_cursor_unchanged(self):
        self.post("bob", to=ME)
        mid = self.relay()
        self.assertIsNotNone(self.run_hook())
        st = self.state()
        self.assertEqual((st["last_t"], st["relay_t"]), (0, 0))
        self.assertEqual(sorted(st["pending"]), ["at", "last_t", "receipts", "relay_t"])
        self.assertGreater(st["pending"]["last_t"], 0)
        self.assertIn(mid, st["pending"]["receipts"])
        self.assertNotIn("SECRET-BODY", json.dumps(st))
        self.assertNotIn("DO-THIS", json.dumps(st))
        self.assertEqual(self.hooked(), [])

    def test_honoured_block_promotes(self):
        self.post("bob", to=ME)
        mid = self.relay()
        self.run_hook()
        pend = self.state()["pending"]
        self.assertIsNone(self.run_hook(active=True))
        st = self.state()
        self.assertNotIn("pending", st)
        self.assertEqual((st["last_t"], st["relay_t"]), (pend["last_t"], pend["relay_t"]))
        self.assertEqual([x["id"] for x in self.hooked()], [mid])
        self.assertIsNone(self.run_hook())

    def test_overridden_block_blocks_same_set_again(self):
        self.post("bob", to=ME)
        mid = self.relay()
        first = self.run_hook()
        again = self.run_hook(active=False)      # another hook's continue:false ended that turn
        self.assertEqual(first["reason"], again["reason"])
        self.assertIn(f"id {mid}", again["reason"])
        self.assertEqual(self.hooked(), [])

    def _edit_pending(self, **kv):
        st = self.state()
        st["pending"].update(kv)
        with open(os.path.join(self.d, ".stop-hook", "s1.json"), "w") as f:
            json.dump(st, f)

    def test_stale_pending_with_true_is_redelivered(self):
        self.post("bob", to=ME)
        mid = self.relay()
        first = self.run_hook()
        self._edit_pending(at=time.time_ns() - 11 * 60 * 10 ** 9)
        again = self.run_hook(active=True)      # not the stop that staged it: re-plan, never promote
        self.assertEqual(first["reason"], again["reason"])
        self.assertEqual(self.hooked(), [])
        self.assertIsNone(self.run_hook(active=True))
        self.assertEqual([x["id"] for x in self.hooked()], [mid])

    def test_corrupt_pending_dropped_fail_open(self):
        self.post("bob", to=ME)
        first = self.run_hook()
        self._edit_pending(last_t="garbage", at="x")
        again = self.run_hook(active=True)
        self.assertEqual(first["reason"], again["reason"])
        self.assertIsInstance(self.state()["pending"]["last_t"], int)   # re-staged cleanly

    def test_missing_key_commits_at_once(self):
        self.post("bob", to=ME)
        mid = self.relay()
        self.assertIsNotNone(self.run_hook(active=None))
        st = self.state()
        self.assertNotIn("pending", st)
        self.assertGreater(st["last_t"], 0)
        self.assertEqual([x["id"] for x in self.hooked()], [mid])
        self.assertIsNone(self.run_hook(active=None))

    def test_relay_delivered_while_watcher_alive(self):
        self.post("bob", to=ME)
        self.relay()
        with open(self.p(f".watch-{ME}.pid"), "w") as f:
            f.write(str(os.getpid()))
        out = self.run_hook()
        self.assertIn("DO-THIS", out["reason"])
        self.assertNotIn("[메일박스]", out["reason"])

    def test_relay_older_than_24h_ignored(self):
        with open(self.p("bus.jsonl"), "a") as f:
            f.write(json.dumps({"id": "old", "t": self.now - 25 * 3600 * 10 ** 9, "from": "h", "to": ME,
                                "kind": "relay", "idSrc": "viewer", "body": "x"}) + "\n")
        self.assertIsNone(self.run_hook())

    def test_relay_corrupt_bus_exit_zero(self):
        with open(self.p("bus.jsonl"), "wb") as f:
            f.write(b"\xff\xfe{broken\n" + os.urandom(2000))
        self.assertIsNone(self.run_hook())


if __name__ == "__main__":
    unittest.main()
