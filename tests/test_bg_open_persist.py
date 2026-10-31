"""Open bg rows survive a restart once the subagent log is past the 6 h scan window. Synthetic files only."""
import json
import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

from tests import _clock
from tests._load import sidereus

bt = sidereus("bgtasks")
bp = sidereus("bgtasks_parse")
bo = sidereus("bgtasks_open")


def _ts(off=0):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(_clock.NOW + off))


class BgOpenPersist(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.fp = os.path.join(self.dir, "sess.jsonl")
        self.sub = os.path.join(self.dir, "sess", "subagents", "agent-x.jsonl")
        self.out = os.path.join(self.dir, "tasks", "b1dev.output")
        os.makedirs(os.path.dirname(self.sub))
        os.makedirs(os.path.dirname(self.out))
        open(self.out, "w", encoding="utf-8").close()
        self.file = os.path.join(self.dir, "bg-open.json")
        fz = _clock.frozen(bt, bp, sidereus("agents"), sidereus("file_owner"))
        fz.__enter__()
        self.addCleanup(fz.__exit__, None, None, None)
        for p in (mock.patch.object(bt, "boot_time", lambda: 0), mock.patch.object(bo, "BG_OPEN_FILE", self.file),
                  mock.patch.object(bo, "_bg_open_prev", {}), mock.patch.object(bo, "_bg_open_saved", {})):
            p.start()
            self.addCleanup(p.stop)
        self.add({"type": "user", "timestamp": _ts(), "message": {"content": "go"}})
        with open(self.sub, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "timestamp": _ts(), "message": {"content": [
                {"type": "tool_use", "id": "TB1", "name": "Bash",
                 "input": {"command": "npm run dev", "description": "Dev server", "run_in_background": True}}]}}) + "\n")
            f.write(json.dumps({"type": "user", "timestamp": _ts(), "message": {"content": [
                {"type": "tool_result", "tool_use_id": "TB1", "content": "Command running in background with ID: b1dev. "
                 "Output is being written to: " + self.out}]}}, separators=(",", ":")) + "\n")

    def tearDown(self):
        self.reset()
        bp._bg_dropped.pop("TB1", None)
        bp._bg_popped.pop("TB1", None)       # a consumed notice blocks the same tid from opening in the next test
        shutil.rmtree(self.dir, ignore_errors=True)

    def add(self, rec):
        with open(self.fp, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

    def reset(self):
        for d in (bt._bg_open, bt._bg_open_at, bt._bg_offset, bt._bg_finished):
            d.pop(self.fp, None)
        bt._bg_offset.pop(self.sub, None)
        bt._bg_seeded.discard(self.fp)

    def restart(self):
        """Previous run ran with a fresh sub log; then the log ages past 6 h and the viewer restarts."""
        self.assertEqual([b[0] for b in bt._running_bg(self.fp)[1]], ["Dev server"])
        t = _clock.NOW - 7 * 3600
        os.utime(self.sub, (t, t))
        self.reset()
        bo._bg_open_prev = bo._bg_open_load(self.file)
        bo._bg_open_saved = {k: dict(v) for k, v in bo._bg_open_prev.items()}

    def saved(self):
        with open(self.file, encoding="utf-8") as f:
            return json.load(f)

    def test_row_survives_restart(self):
        self.restart()
        self.assertEqual([b[0] for b in bt._running_bg(self.fp)[1]], ["Dev server"])

    def test_notice_closes_and_unsaves(self):
        self.restart()
        self.add({"type": "attachment", "timestamp": _ts(), "attachment": {
            "type": "queued_command", "commandMode": "task-notification",
            "prompt": "<task-notification>\n<task-id>b1dev</task-id>\n<tool-use-id>TB1</tool-use-id>\n"
                      "<status>completed</status>\n<summary>done</summary>\n</task-notification>"}})
        self.assertEqual(bt._running_bg(self.fp)[1], [])
        self.assertNotIn(self.fp, self.saved())

    def test_missing_output_dropped(self):
        self.restart()
        os.remove(self.out)
        self.assertEqual(bt._running_bg(self.fp)[1], [])

    def test_dismissed_not_restored(self):
        self.restart()
        bp._bg_dropped["TB1"] = _clock.NOW
        self.assertEqual(bt._running_bg(self.fp)[1], [])

    def test_output_before_boot_dropped(self):
        self.restart()
        t = _clock.NOW - 3600
        os.utime(self.out, (t, t))
        with mock.patch.object(bt, "boot_time", lambda: _clock.NOW - 60):
            self.assertEqual(bt._running_bg(self.fp)[1], [])


if __name__ == "__main__":
    unittest.main()
