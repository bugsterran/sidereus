"""Blocked false positives: permissionMode scrolled out of the tail window, and a pending Bash
whose transcript mtime was pushed past the shell start by queued lines.

No live files or clock: a temp transcript, and tool_busy/shell_starts/time patched on live_probe.
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

lp = sidereus("live_probe")
parse = sidereus("parse")
sessions = sidereus("sessions")


class _Clock:
    def __init__(self, t):
        self.t = t

    def time(self):
        return self.t


class PmodeOutOfWindowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        parse._PMODE_SEEN.clear()

    def test_auto_mode_before_tail_window_is_kept(self):
        fp = os.path.join(self.tmp, "s.jsonl")
        ts = "2026-11-02T00:00:00.000Z"
        with open(fp, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "user", "permissionMode": "auto", "sessionId": "s1", "timestamp": ts,
                                "message": {"role": "user", "content": "go"}}) + "\n")
            pad = "x" * 2000
            for i in range(400):             # ~800 KB of tool traffic pushes the prompt line out of the 400 KB tail
                f.write(json.dumps({"type": "assistant", "timestamp": ts, "message": {"id": "m%d" % i, "role": "assistant",
                                    "content": [{"type": "tool_use", "id": "t%d" % i, "name": "Read", "input": {"p": pad}}]}}) + "\n")
                f.write(json.dumps({"type": "user", "timestamp": ts, "message": {"role": "user",
                                    "content": [{"type": "tool_result", "tool_use_id": "t%d" % i, "content": "ok"}]}}) + "\n")
            f.write(json.dumps({"type": "assistant", "timestamp": ts, "message": {"id": "mz", "role": "assistant",
                                "content": [{"type": "tool_use", "id": "tz", "name": "Bash", "input": {"command": "sleep 300"}}]}}) + "\n")
        self.assertGreater(os.path.getsize(fp), 500_000)
        self.assertEqual(parse._parse_transcript(fp)["pmode"], "auto")

    def test_mode_past_600_rows_but_inside_400kb_is_found(self):
        fp = os.path.join(self.tmp, "r.jsonl")
        ts = "2026-11-02T00:00:00.000Z"
        with open(fp, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "user", "permissionMode": "auto", "timestamp": ts,
                                "message": {"role": "user", "content": "go"}}) + "\n")
            for i in range(700):             # short rows: 700 lines stay well under 400 KB, prompt is row 701 from the end
                f.write(json.dumps({"type": "user", "timestamp": ts, "message": {"role": "user",
                                    "content": [{"type": "tool_result", "tool_use_id": "t%d" % i, "content": "ok"}]}}) + "\n")
        self.assertLess(os.path.getsize(fp), 400_000)
        self.assertEqual(parse._parse_transcript(fp)["pmode"], "auto")

    def test_quoted_mode_inside_a_string_is_ignored(self):
        fp = os.path.join(self.tmp, "q.jsonl")
        with open(fp, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "user", "message": {"content": '"permissionMode":"auto"'}}) + "\n")
            f.write("{" + "y" * 500_000 + "\n")
        self.assertEqual(parse._pmode_before(fp, 400_000), "")


class BashAgeFromToolUseTest(unittest.TestCase):
    def test_age_measured_from_tool_use_not_mtime(self):
        t0 = 50_000.0
        now = t0 + 100
        for name, val in (("tool_busy", lambda ttl=2: {"/c": True}), ("shell_starts", lambda ttl=2: {"/c": [t0]}),
                          ("time", _Clock(now))):
            p = mock.patch.object(lp, name, val)
            p.start()
            self.addCleanup(p.stop)
        p = {"tool": "Bash", "cwd": "/c", "actAt": int(t0), "pmode": "", "bgs": []}
        self.assertEqual(sessions._row_status("tool", None, p, now, t0 + 70)["blocked"], "")


if __name__ == "__main__":
    unittest.main()
