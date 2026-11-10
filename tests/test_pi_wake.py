"""ext-hooks/pi_wake.py: temp store, fake stdin/stdout, fake sleep and clock (R1-R4)."""
import importlib.util
import json
import os
import queue
import shutil
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("pi_wake_t", os.path.join(ROOT, "ext-hooks", "pi_wake.py"))
pw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pw)
SID = "0b1c2d3e-aaaa-4bbb-8ccc-0123456789ab"


class FakeIn(object):
    """Blocking line stream: readline() waits for a pushed line; None = EOF."""

    def __init__(self):
        self.q = queue.Queue()

    def push(self, line):
        self.q.put(line)

    def readline(self):
        x = self.q.get(timeout=30)
        return "" if x is None else x


class FakeOut(object):
    """Collects JSON lines; on a wake line pushes `reply` into the paired stdin."""

    def __init__(self, fin, reply):
        self.fin, self.reply, self.lines, self.buf = fin, reply, [], ""

    def write(self, s):
        self.buf += s

    def flush(self):
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            o = json.loads(line)
            self.lines.append(o)
            if "wake" in o and self.reply is not None:
                self.fin.push(self.reply)


class PiWake(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cwd = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, True)
        self.addCleanup(shutil.rmtree, self.cwd, True)
        self.me = os.path.basename(self.cwd) + "-pi"
        self.ident({self.cwd: "claude-a"})
        open(os.path.join(self.d, "bus.jsonl"), "w", encoding="utf-8").close()
        self.old = (pw.LIFE_S, pw.FIRST_S)
        pw.LIFE_S, pw.FIRST_S = 100.0, 0.0
        self.now = [0.0]

    def tearDown(self):
        pw.LIFE_S, pw.FIRST_S = self.old

    def ident(self, d):
        with open(os.path.join(self.d, "identity.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)

    def mail(self, room=None):
        row = {"id": "m%d" % time.time_ns(), "t": time.time_ns(), "from": "zed",
               "subject": "SECRET-SUBJ", "body": "SECRET-BODY"}
        if room:
            row["room"] = room
        else:
            row["to"] = self.me
        with open(os.path.join(self.d, "bus.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    def clock(self):
        return self.now[0]

    def sleep(self, s):
        self.now[0] += max(s, 0.5)

    def go(self, reply="ok", fin=None, on_sleep=None, ack_s=5.0):
        fin = fin or FakeIn()
        out = FakeOut(fin, reply)

        def sl(s):
            if on_sleep:
                on_sleep(fin)
            self.sleep(s)
        tag = pw.run(SID, self.cwd, store=self.d, stdin=fin, stdout=out, sleep=sl, clock=self.clock, ack_s=ack_s)
        fin.push(None)
        return tag, out.lines

    def state(self):
        p = os.path.join(self.d, ".stop-hook", "pi_" + SID + ".json")
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except OSError:
            return {}

    def test_R1_wake_line_ids_only(self):
        self.mail()
        tag, lines = self.go()
        self.assertEqual(tag, "fired")
        self.assertEqual(len(lines), 1)
        w = lines[0]["wake"]
        self.assertTrue(w.startswith("[mailbox] 1 new mail for `%s`" % self.me), w)
        self.assertIn("zed(DM)", w)
        self.assertNotIn("SECRET", json.dumps(lines))   # Rule 1: no subject, no body

    def test_R1_room_line(self):
        with open(os.path.join(self.d, "rooms.json"), "w", encoding="utf-8") as f:
            json.dump({"ops": {"members": [self.me, "zed"]}}, f)
        self.mail(room="ops")
        _, lines = self.go()
        self.assertIn("zed(room ops)", lines[0]["wake"])

    def test_R3_ok_ack_marks_then_silent(self):
        self.mail()
        self.assertEqual(self.go()[0], "fired")
        self.assertGreater(int(self.state().get("last_t") or 0), 0)
        tag, lines = self.go()
        self.assertEqual(tag, "timeout")          # the same mail never wakes twice
        self.assertEqual(lines, [{"end": "timeout"}])

    def test_R3_no_ack_leaves_mail(self):
        self.mail()
        self.assertEqual(self.go(reply="no")[0], "rejected")
        self.assertNotIn("last_t", self.state())
        self.assertEqual(self.go(reply=None, ack_s=0.2)[0], "rejected")   # ack timeout: still unmarked
        self.assertNotIn("last_t", self.state())
        self.assertEqual(self.go()[0], "fired")

    def test_R2_no_mail_only_timeout(self):
        tag, lines = self.go()
        self.assertEqual(tag, "timeout")
        self.assertEqual(lines, [{"end": "timeout"}])
        self.assertFalse(os.path.exists(os.path.join(self.d, ".wake", SID + ".lock")))

    def test_R4_eof_silent_and_frees_slot(self):
        fin = FakeIn()
        fin.push(None)
        self.mail()
        tag, lines = self.go(fin=fin, on_sleep=lambda f: time.sleep(0.05))
        self.assertEqual(tag, "gone")
        self.assertEqual(lines, [])
        self.assertNotIn("last_t", self.state())
        self.assertFalse(os.path.exists(os.path.join(self.d, ".wake", SID + ".lock")))

    def test_R4_second_waiter_busy(self):
        os.makedirs(os.path.join(self.d, ".wake"))
        with open(os.path.join(self.d, ".wake", SID + ".lock"), "w", encoding="utf-8") as f:
            f.write("999999")
        self.mail()
        tag, lines = self.go()
        self.assertEqual(tag, "busy")
        self.assertEqual(lines, [])

    def test_R4_claude_id_clash_off(self):
        self.ident({self.cwd: self.me})
        self.mail()
        tag, lines = self.go()
        self.assertEqual(tag, "off")
        self.assertEqual(lines, [{"end": "off"}])

    def test_R1_explicit_pi_mapping_may_name_a_claude_id(self):
        # an explicit `pi:<cwd>` entry is a declaration; only the derived `<folder>-pi` default is clash-guarded
        self.ident({self.cwd: "advocate", "pi:" + self.cwd: "advocate"})
        self.me = "advocate"
        self.mail()
        tag, lines = self.go()
        self.assertEqual(tag, "fired")
        self.assertIn("advocate", lines[0]["wake"])

    def test_R4_watch_alive_off(self):
        with open(os.path.join(self.d, ".watch-%s.pid" % self.me), "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        self.mail()
        self.assertEqual(self.go()[1], [{"end": "off"}])

    def test_bad_sid(self):
        self.assertEqual(pw.run("../x", self.cwd, store=self.d, stdin=FakeIn(), stdout=FakeOut(None, None)), "bad-args")


if __name__ == "__main__":
    unittest.main()
