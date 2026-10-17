"""A permission prompt (hook «ask» or normal) stays «waiting for approval» when queue-operation lines land after it.
Fake transcript tail -> parse._scan_tail actAt -> perm_marks.perm_rows. Tmp dirs only, fixed clock."""
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

from sidereus import parse as P
from sidereus import perm_marks as LP

SID = "0123abcd-0000-4000-8000-0123456789ab"
T0 = 1_800_000_000          # tool_use time


def _ts(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _tool_use(t):
    return {"type": "assistant", "sessionId": SID, "cwd": "/x", "timestamp": _ts(t),
            "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "tu1", "name": "Bash", "input": {}}]}}


def _queue(t):
    return {"type": "queue-operation", "operation": "enqueue", "sessionId": SID, "timestamp": _ts(t), "content": "x"}


def _result(t, err=False):
    return {"type": "user", "sessionId": SID, "cwd": "/x", "timestamp": _ts(t),
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu1", "content": "r", "is_error": err}]}}


class PermQueueActivity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.tp = os.path.join(self.tmp, "t.jsonl")   # the same fake tail feeds perm_marks._pend_ts (never live paths)
        for obj, k, v in ((LP, "PERM_DIR", self.tmp), (LP, "tool_busy", lambda: None), (LP, "_DEC_AT", {}),
                          (LP, "_pend_cache", {}), (LP, "_sid_transcript", lambda sid: self.tp)):
            p = mock.patch.object(obj, k, v)
            p.start()
            self.addCleanup(p.stop)
        with open(os.path.join(self.tmp, SID + ".json"), "w", encoding="utf-8") as f:
            json.dump({"sid": SID, "t": T0 + 17}, f)          # Notification permission_prompt lands after the 6 s delay

    def _blocked(self, recs, now):
        with open(self.tp, "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(r) + "\n" for r in recs))
        LP._pend_cache.clear()
        act =P._scan_tail([json.dumps(r) for r in recs])["actAt"]
        row = {"sid": SID, "state": "tool", "tool": "Bash", "ageSec": int(now - act), "blocked": "", "cwd": "/x"}
        return LP.perm_rows([row], now=now)[0].get("blocked")

    def test_r1_queued_lines_after_prompt_keep_it_pending(self):
        recs = [_tool_use(T0), _queue(T0 + 80), _queue(T0 + 81)]
        self.assertEqual(self._blocked(recs, T0 + 200), "Bash waiting for approval")

    def test_r2_plain_prompt_unchanged(self):
        self.assertEqual(self._blocked([_tool_use(T0)], T0 + 200), "Bash waiting for approval")

    def test_r3_tool_result_after_prompt_clears(self):
        for err in (False, True):              # Yes runs the tool; No writes an error tool_result
            recs = [_tool_use(T0), _queue(T0 + 80), _result(T0 + 90, err)]
            self.assertFalse(self._blocked(recs, T0 + 200))

    def test_queued_command_attachment_is_not_activity(self):
        att = {"type": "attachment", "sessionId": SID, "timestamp": _ts(T0 + 80),
               "attachment": {"type": "queued_command", "commandMode": "task-notification"}}
        self.assertEqual(P._scan_tail([json.dumps(r) for r in (_tool_use(T0), att)])["actAt"], T0)
        self.assertEqual(self._blocked([_tool_use(T0), att], T0 + 200), "Bash waiting for approval")

    def test_queue_only_tail_still_has_activity_from_earlier_line(self):
        recs = [_tool_use(T0), _queue(T0 + 80)]
        self.assertEqual(P._scan_tail([json.dumps(r) for r in recs])["actAt"], T0)


if __name__ == "__main__":
    unittest.main()
