"""Monitor watcher rows and background Bash in `_running_bg`, using the current Claude Code line formats. No live files."""
import json
import os
import shutil
import tempfile
import time
import unittest

from tests._load import sidereus

bt = sidereus("bgtasks")


def _ts(off=0):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() + off))


def _launch(tuid, name, inp):
    return {"type": "assistant", "timestamp": _ts(), "message": {"content": [
        {"type": "tool_use", "id": tuid, "name": name, "input": inp}]}}


def _result(tuid, text):
    return {"type": "user", "timestamp": _ts(), "message": {"content": [
        {"type": "tool_result", "tool_use_id": tuid, "content": text}]}}


def _queued(body):
    return {"type": "attachment", "timestamp": _ts(), "attachment": {
        "type": "queued_command", "commandMode": "task-notification", "prompt": body}}


def _started(task):
    return ("Monitor started (task %s, expires in 30m unless the source ends first; you get one notice at expiry"
            " — re-arm if you still need the watch). You will be notified." % task)


def _expired(task, desc):
    return ("<task-notification>\n<task-id>%s</task-id>\n<summary>Monitor event: \"%s\"</summary>\n"
            "<event>[Monitor expired after 30m with no events delivered. Re-arm it if you still need the watch.]"
            "</event>\n</task-notification>" % (task, desc))


class BgMonitor(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.fp = os.path.join(self.dir, "sess.jsonl")
        os.makedirs(os.path.join(self.dir, "sess", "subagents"))
        self._boot = bt.boot_time
        bt.boot_time = lambda: 0

    def tearDown(self):
        bt.boot_time = self._boot
        for d in (bt._bg_open, bt._bg_open_at, bt._bg_offset):
            d.pop(self.fp, None)
        bt._bg_seeded.discard(self.fp)
        shutil.rmtree(self.dir, ignore_errors=True)

    def add(self, *recs):
        with open(self.fp, "a", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")

    def mons(self):
        return sorted(r[0] for r in bt._running_bg(self.fp)[2])

    def test_monitor_shows_from_launch_and_expiry_ends_it(self):
        self.add(_launch("TM1", "Monitor", {"command": "~/watch.sh A", "description": "Sidereus 상태"}),
                 _result("TM1", _started("b0nbtoz0c")))
        self.assertEqual(self.mons(), ["감시 Sidereus 상태"])      # no event yet, still a live watcher
        self.add(_queued(_expired("b0nbtoz0c", "Sidereus 상태")))
        self.assertEqual(self.mons(), [])                      # expiry notice is not a heartbeat
        self.add(_launch("TM2", "Monitor", {"command": "~/watch.sh A", "description": "Sidereus 상태"}),
                 _result("TM2", [{"type": "text", "text": _started("bgfwkew4t")}]))
        self.assertEqual(self.mons(), ["감시 Sidereus 상태"])      # re-armed
        rows = bt._running_bg(self.fp)[2]
        self.assertNotIn("watch.sh", json.dumps(rows))         # command text never reaches a row

    def test_resume_stopped_list_closes_watchers(self):
        self.add(_launch("TM3", "Monitor", {"command": "x", "description": "w"}), _result("TM3", _started("bqokxx1u7")))
        self.assertEqual(self.mons(), ["감시 w"])
        self.add(_queued("<task-notification>\n<summary>2 background tasks didn't finish before the previous session "
                         "ended. Task ids: bqokxx1u7, b32ifugft.</summary>\n<note>marked stopped</note>\n"
                         "</task-notification>"))
        self.assertEqual(self.mons(), [])

    def test_background_bash_counts_until_notice(self):
        self.add(_launch("TB1", "Bash", {"command": "npm run dev", "description": "Start dev server",
                                         "run_in_background": True}),
                 _result("TB1", "Command running in background with ID: b3lm4j8g0. Output is being written to: /x"))
        bgs = bt._running_bg(self.fp)[1]
        self.assertEqual([r[0] for r in bgs], ["Start dev server"])
        self.add({"type": "queue-operation", "operation": "enqueue", "timestamp": _ts(),
                  "content": "<task-notification>\n<task-id>b3lm4j8g0</task-id>\n<tool-use-id>TB1</tool-use-id>\n"
                             "<status>killed</status>\n<summary>Background command \"Start dev server\" was stopped"
                             "</summary>\n</task-notification>"})
        self.assertEqual(bt._running_bg(self.fp)[1], [])

    def _notice(self, task, tuid):
        self.add({"type": "queue-operation", "operation": "enqueue", "timestamp": _ts(),
                  "content": "<task-notification>\n<task-id>%s</task-id>\n<tool-use-id>%s</tool-use-id>\n"
                             "<status>completed</status>\n<summary>Background command done</summary>\n"
                             "</task-notification>" % (task, tuid)})

    def test_timeout_moved_bash_in_subagent_counts_until_notice(self):
        # A subagent's foreground Bash moved to the background at its timeout: recorded only in the agent's
        # transcript, closed by the notice in the parent transcript.
        sub = os.path.join(self.dir, "sess", "subagents", "agent-a1.jsonl")
        with open(sub, "w", encoding="utf-8") as f:
            for r in (_launch("TS1", "Bash", {"command": "load.sh", "description": "Reload files into MySQL"}),
                      _result("TS1", "Command did not complete within its 120s timeout and was moved to the "
                                     "background (ID: bo02ikjet). Output is being written to: /x")):
                f.write(json.dumps(r) + "\n")
        self.add(_launch("TM0", "Bash", {"command": "true", "description": "noop"}))
        self.assertEqual([r[0] for r in bt._running_bg(self.fp)[1]], ["Reload files into MySQL"])
        self._notice("bo02ikjet", "TS1")
        self.assertEqual(bt._running_bg(self.fp)[1], [])
        bt._bg_offset.pop(sub, None)

    def test_output_mentioning_the_phrase_does_not_open_a_row(self):
        self.add(_launch("TG1", "Bash", {"command": "grep x", "description": "Search transcripts"}),
                 _result("TG1", "found: Command did not complete within its 120s timeout and was moved to the "
                                "background (ID: b1)"))
        self.assertEqual(bt._running_bg(self.fp)[1], [])


class BgExpiry(unittest.TestCase):
    NOW = 1_800_000_000.0

    def _at(self, rec, ts):
        rec["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(ts))
        return json.dumps(rec)

    def test_long_running_bg_shell_survives_age_expiry_until_notice(self):
        fp, op, t0 = "/nonexistent/sess.jsonl", {}, self.NOW - 3 * 3600
        bt._bg_on_line(self._at(_launch("TL1", "Bash", {"command": "npm run dev", "description": "Dev server",
                                                        "run_in_background": True}), t0), op, fp, False, self.NOW)
        bt._bg_on_line(self._at(_result("TL1", "Command running in background with ID: x"), t0), op, fp, False, self.NOW)
        op["S1"] = ("sub", "old agent", t0)
        bt._bg_expire(op, self.NOW)
        self.assertEqual(op["TL1"][0], "bg")          # a 3h-old shell is still open
        self.assertNotIn("S1", op)                    # agents keep the 2h backstop
        bt._bg_on_notice(json.dumps({"type": "queue-operation", "operation": "enqueue", "content":
                         "<task-notification>\n<task-id>x</task-id>\n<tool-use-id>TL1</tool-use-id>\n"
                         "<status>completed</status>\n</task-notification>"}), op, fp, True, self.NOW)
        self.assertNotIn("TL1", op)


if __name__ == "__main__":
    unittest.main()
