"""Idle background shells: output path from the receipt, idle by output-file mtime, row key `bgIdle`. No live files."""
import json
import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

from tests._load import sidereus

bt = sidereus("bgtasks")
bp = sidereus("bgtasks_parse")
ss = sidereus("sessions")

NOW = 1_800_000_000.0


def _rec(kind, content, ts="2027-01-15T08:00:00.000Z"):
    return {"type": kind, "timestamp": ts, "message": {"content": content}}


def _launch(tuid, inp):
    return _rec("assistant", [{"type": "tool_use", "id": tuid, "name": "Bash", "input": inp}])


def _result(tuid, text):
    return _rec("user", [{"type": "tool_result", "tool_use_id": tuid, "content": text}])


def _out(d, tid):
    return os.path.join(d, "private", "tmp", "claude-501", "proj", "sid", "tasks", tid + ".output")


class _Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.fp = os.path.join(self.dir, "sess.jsonl")
        os.makedirs(os.path.join(self.dir, "sess", "subagents"))
        os.makedirs(os.path.dirname(_out(self.dir, "x")))
        self._boot = bt.boot_time
        bt.boot_time = lambda: 0

    def tearDown(self):
        bt.boot_time = self._boot
        for d in (bt._bg_open, bt._bg_open_at, bt._bg_offset):
            for k in list(d):
                if k.startswith(self.dir):
                    d.pop(k, None)
        bt._bg_seeded.discard(self.fp)
        shutil.rmtree(self.dir, ignore_errors=True)

    def add(self, *recs, path=None):
        with open(path or self.fp, "a", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")

    def touch(self, tid, age, body="x"):
        p = _out(self.dir, tid)
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)
        os.utime(p, (NOW - age, NOW - age))
        return p


class BgIdleJudge(_Base):
    def test_R1_idle_by_mtime(self):
        p16, p14 = self.touch("b16", 16 * 60), self.touch("b14", 14 * 60)
        with mock.patch.dict(bt._bg_open, {self.fp: {"T1": ("bg", "a", NOW - 3600, p16),
                                                       "T2": ("bg", "b", NOW - 3600, p14),
                                                       "T3": ("sub", "c", NOW)}}):
            got = bt.bg_idle(self.fp, NOW)
            self.assertEqual(got, {"n": 2, "idle": 1, "max": 16 * 60})
            # content rewritten but mtime kept old: still idle (only mtime is read)
            with open(p16, "w", encoding="utf-8") as f:
                f.write("new output")
            os.utime(p16, (NOW - 20 * 60, NOW - 20 * 60))
            self.assertEqual(bt.bg_idle(self.fp, NOW)["max"], 20 * 60)
            os.utime(p16, (NOW - 60, NOW - 60))
            self.assertIsNone(bt.bg_idle(self.fp, NOW))

    def test_R1_receipt_path(self):
        p1, p2, p3 = _out(self.dir, "b111"), _out(self.dir, "b222"), _out(self.dir, "b333")
        self.add(_launch("IDLE_B1", {"command": "npm run dev", "description": "Dev", "run_in_background": True}),
                 _result("IDLE_B1", "Command running in background with ID: b111. Output is being written to: " + p1),
                 _launch("IDLE_F1", {"command": "load.sh", "description": "Load"}),
                 _result("IDLE_F1", [{"type": "text", "text": "Command did not complete within its 120s timeout and was "
                                  "moved to the background (ID: b222). Output is being written to: " + p2}]))
        sub = os.path.join(self.dir, "sess", "subagents", "agent-a1.jsonl")
        self.add(_launch("IDLE_S1", {"command": "watch", "description": "Sub", "run_in_background": True}),
                 _result("IDLE_S1", "Command running in background with ID: b333. Output is being written to: " + p3),
                 path=sub)
        rows = bt._running_bg(self.fp)
        opened = bt._bg_open[self.fp]
        self.assertEqual(opened["IDLE_B1"][3], p1)
        self.assertEqual(opened["IDLE_F1"][3], p2)
        self.assertEqual(opened["IDLE_S1"][3], p3)       # receipt line has no "Bash" — still read from the subagent log
        self.assertNotIn(self.dir, json.dumps(rows))  # path never reaches a row
        self.assertEqual(sorted(r[0] for r in rows[1]), ["Dev", "Load", "Sub"])

    def test_R1_receipt_path_windows_and_dotdot(self):
        win = "C:\\Users\\me\\AppData\\Local\\Temp\\claude\\proj\\sid\\tasks\\b444.output"
        bad = "/private/tmp/claude-501/../../etc/tasks/b555.output"
        self.add(_launch("IDLE_W1", {"command": "a", "description": "Win", "run_in_background": True}),
                 _result("IDLE_W1", "Command running in background with ID: b444. Output is being written to: " + win),
                 _launch("IDLE_D1", {"command": "b", "description": "Dot", "run_in_background": True}),
                 _result("IDLE_D1", "Command running in background with ID: b555. Output is being written to: " + bad))
        bt._running_bg(self.fp)
        opened = bt._bg_open[self.fp]
        self.assertEqual(opened["IDLE_W1"][3], win)
        self.assertEqual(len(opened["IDLE_D1"]), 3)  # `..` segment refused: row stays open, no path
        self.assertIsNone(bp._bg_out("Output is being written to: C:\\x\\..\\tasks\\b6.output"))


class BgIdleOpenAndExcluded(_Base):
    def test_R4_old_shell_counted(self):
        p = self.touch("bold", 3 * 3600)
        opened = {"T1": ("bg", "old", NOW - 3 * 3600, p)}
        bt._bg_expire(opened, NOW)
        self.assertIn("T1", opened)                  # not expired by the 2-hour backstop
        with mock.patch.dict(bt._bg_open, {self.fp: opened}):
            self.assertEqual(bt.bg_idle(self.fp, NOW), {"n": 1, "idle": 1, "max": 3 * 3600})

    def test_R4_excluded(self):
        p1, p2 = _out(self.dir, "b111"), _out(self.dir, "b222")
        self.add(_launch("IDLE_B1", {"command": "a", "description": "A", "run_in_background": True}),
                 _result("IDLE_B1", "Command running in background with ID: b111. Output is being written to: " + p1),
                 _launch("IDLE_B2", {"command": "b", "description": "B", "run_in_background": True}),
                 _result("IDLE_B2", "Command running in background with ID: b222. Output is being written to: " + p2))
        bt._running_bg(self.fp)
        self.assertEqual(set(bt._bg_open[self.fp]), {"IDLE_B1", "IDLE_B2"})
        # completion notice pops TB1
        self.add({"type": "queue-operation", "operation": "enqueue", "timestamp": "2027-01-15T08:01:00.000Z",
                  "content": "<task-notification>\n<task-id>b111</task-id>\n<tool-use-id>IDLE_B1</tool-use-id>\n"
                             "<status>completed</status>\n<summary>done</summary>\n</task-notification>"})
        bt._running_bg(self.fp)
        self.assertEqual(set(bt._bg_open[self.fp]), {"IDLE_B2"})
        # previous session ended: the stopped-ids list pops TB2 by its output file name
        self.add({"type": "queue-operation", "operation": "enqueue", "timestamp": "2027-01-15T08:02:00.000Z",
                  "content": "<task-notification>\n<summary>1 background tasks didn't finish before the previous "
                             "session ended. Task ids: b222.</summary>\n</task-notification>"})
        bt._running_bg(self.fp)
        self.assertEqual(bt._bg_open[self.fp], {})
        # missing file and pre-boot mtime are never idle
        p3 = self.touch("b333", 3600)
        opened = {"T4": ("bg", "gone", NOW, _out(self.dir, "nope")), "T5": ("bg", "boot", NOW, p3)}
        with mock.patch.dict(bt._bg_open, {self.fp: opened}):
            bt.boot_time = lambda: NOW - 1800
            self.assertIsNone(bt.bg_idle(self.fp, NOW))

    def test_R4_dead_row_has_no_bgIdle(self):
        calls = []

        def fake(fp, now):
            calls.append(fp)
            return {"n": 2, "idle": 1, "max": 1000}
        with mock.patch.object(ss, "bg_idle", fake), \
                mock.patch.object(ss, "_team_row", lambda fp: None), \
                mock.patch.object(ss, "plm_of", lambda sid, now: None), \
                mock.patch.object(ss, "_wf_sets", lambda fp, now, dead: ([], [])), \
                mock.patch.object(ss, "_pl_off", lambda *a: False), \
                mock.patch.object(ss, "_mon_rows", lambda *a: []), \
                mock.patch.object(ss.pl_runs, "pl_model", lambda *a: []), \
                mock.patch.object(ss.pl_runs, "pl_none", lambda sid: None):
            p = {"sid": "s1", "cwd": "/w", "sub": [], "bgs": []}
            self.assertNotIn("bgIdle", ss._row_children(self.fp, p, NOW, True))
            self.assertEqual(calls, [])
            self.assertEqual(ss._row_children(self.fp, p, NOW, False)["bgIdle"], {"n": 2, "idle": 1, "max": 1000})


if __name__ == "__main__":
    unittest.main()
