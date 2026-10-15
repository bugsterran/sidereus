"""An assistant text line that closes the turn by itself (stop_reason end_turn/stop_sequence or a
"<synthetic>" reply) is the turn-ended shape even with no turn_duration/stop_hook_summary after it.

Synthetic transcript tails only — parse._tail_lines/_running_bg/_cwd_from_slug are monkeypatched.
"""
import json
import unittest

from tests._load import sidereus

parse = sidereus("parse")
notes = sidereus("notes")

CWD = "/w/repo-t"
T0 = "2026-10-13T00:00:00.000Z"


def asst(stop=None, model="claude-x"):
    return json.dumps({"type": "assistant", "sessionId": "s1", "cwd": CWD, "timestamp": T0,
                       "message": {"model": model, "stop_reason": stop,
                                   "content": [{"type": "text", "text": "x"}]}})


BOOKKEEPING = [json.dumps({"type": "cost-state", "sessionId": "s1"}),
               json.dumps({"type": "last-prompt", "sessionId": "s1"}),
               json.dumps({"type": "mode", "sessionId": "s1"})]


class TurnEndByStopReason(unittest.TestCase):
    def patch(self, mod, name, val):
        old = getattr(mod, name)
        setattr(mod, name, val)
        self.addCleanup(setattr, mod, name, old)

    def parse(self, lines):
        self.patch(parse, "_tail_lines", lambda fp, nbytes=0, limit=0: list(lines))
        self.patch(parse, "_running_bg", lambda fp: ([], [], []))
        self.patch(parse, "_cwd_from_slug", lambda s: CWD)
        return parse._parse_transcript("/x/-w-repo-t/s1.jsonl")

    def st(self, p):
        return notes._sess_state(p["cwd"], p["shape"], {CWD: 1}, p["ask"], p["abort"], p["err"],
                                 sid=p["sid"], ask_tool=p["askTool"])

    def test_synthetic_stop_sequence_tail_is_text(self):
        p = self.parse([asst(stop="stop_sequence", model="<synthetic>")] + BOOKKEEPING)
        self.assertEqual(p["shape"], "text")
        self.assertNotEqual(self.st(p), "think")

    def test_end_turn_tail_is_text(self):
        p = self.parse([asst(stop="end_turn")] + BOOKKEEPING)
        self.assertEqual(p["shape"], "text")
        self.assertEqual(self.st(p), "wait")

    def test_null_stop_reason_mid_turn_stays_result(self):
        p = self.parse([asst(stop=None)] + BOOKKEEPING)
        self.assertEqual(p["shape"], "result")
        self.assertEqual(self.st(p), "think")


if __name__ == "__main__":
    unittest.main()
