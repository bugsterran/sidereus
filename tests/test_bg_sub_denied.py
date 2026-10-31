"""A subagent's hook-denied `Bash(run_in_background)` closes its row; a receipted launch stays open. No live files."""
import json
import os
import shutil
import tempfile
import time
import unittest

from tests._load import sidereus

bt = sidereus("bgtasks")


def _ts():
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time()))


def _launch(tuid):
    return {"type": "assistant", "timestamp": _ts(), "message": {"content": [
        {"type": "tool_use", "id": tuid, "name": "Bash", "input": {"command": "sleep 1", "run_in_background": True}}]}}


def _result(tuid, text, is_error=False):
    res = {"type": "tool_result", "tool_use_id": tuid, "content": text}
    if is_error:
        res["is_error"] = True
    return {"type": "user", "timestamp": _ts(), "message": {"content": [res]}}


class SubDeniedBg(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.fp = os.path.join(self.dir, "sess.jsonl")
        self.sub = os.path.join(self.dir, "sess", "subagents", "agent-x.jsonl")
        os.makedirs(os.path.dirname(self.sub))
        self._boot = bt.boot_time
        bt.boot_time = lambda: 0
        with open(self.fp, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "user", "timestamp": _ts(), "message": {"content": "go"}}) + "\n")

    def tearDown(self):
        bt.boot_time = self._boot
        for d in (bt._bg_open, bt._bg_open_at, bt._bg_offset, bt._bg_finished):
            d.pop(self.fp, None)
        bt._bg_offset.pop(self.sub, None)
        bt._bg_seeded.discard(self.fp)
        shutil.rmtree(self.dir, ignore_errors=True)

    def write_sub(self, *recs, compact=True):
        # Real transcripts are compact JSON ('"is_error":true'); the spaced form is covered too.
        sep = (",", ":") if compact else (", ", ": ")
        with open(self.sub, "w", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r, separators=sep) + "\n")

    def test_hook_denied_launch_leaves_no_row(self):
        for compact in (True, False):
            with self.subTest(compact=compact):
                self.tearDown()
                self.setUp()
                self.write_sub(_launch("TD1"), _result("TD1", "PreToolUse:hook denied this tool call",
                                                       is_error=True), compact=compact)
                self.assertEqual(bt._running_bg(self.fp)[1], [])
                self.assertFalse(bt._bg_finished.get(self.fp))

    def test_receipted_launch_stays_open(self):
        self.write_sub(_launch("TR1"), _result("TR1", "Command running in background with ID: b1abc. "
                                                      "Output is being written to: /x"))
        self.assertEqual(len(bt._running_bg(self.fp)[1]), 1)


if __name__ == "__main__":
    unittest.main()
