"""An auto-compact summary (`user` line with isCompactSummary) must not decide turn shape or task label."""
import importlib
import json
import unittest

from tests._load import load

SUMMARY = "This session is being continued from a previous conversation. SECRET-SUMMARY-TEXT"


def _rows(*recs):
    out = []
    for i, r in enumerate(recs):
        r = dict(r)
        r.setdefault("timestamp", "2026-10-13T10:00:%02dZ" % i)
        r.setdefault("sessionId", "s1")
        r.setdefault("cwd", "/tmp/proj")
        out.append(json.dumps(r))
    return out


def _asst(content, mid="m1"):
    return {"type": "assistant", "message": {"id": mid, "role": "assistant", "content": content}}


TEXT = _asst([{"type": "text", "text": "done"}])
TOOL = _asst([{"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}])
RESULT = {"type": "user", "message": {"role": "user",
                                      "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}}
BOUNDARY = {"type": "system", "subtype": "compact_boundary"}
COMPACT = {"type": "user", "isCompactSummary": True, "message": {"role": "user", "content": SUMMARY}}
TAIL = [{"type": "attachment"}, {"type": "attachment"},
        {"type": "system", "subtype": "informational"},
        {"type": "last-prompt"}, {"type": "permission-mode"}]


class CompactStateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        load()
        cls.p = importlib.import_module("sidereus.parse")
        cls.n = importlib.import_module("sidereus.notes")

    def scan(self, *recs):
        return self.p._scan_tail(_rows(*recs))

    def state(self, r):
        s = r["shp"]
        return self.n._sess_state("/tmp/proj", s["shape"], {"/tmp/proj"}, s["ask"], s["abort"], s["err"])

    def test_ended_turn_then_compact_is_wait(self):
        r = self.scan(TEXT, {"type": "system", "subtype": "stop_hook_summary"},
                      {"type": "system", "subtype": "turn_duration"}, BOUNDARY, COMPACT, *TAIL)
        self.assertEqual(r["shp"]["shape"], "text")
        self.assertEqual(self.state(r), "wait")
        self.assertNotIn("SECRET-SUMMARY-TEXT", r["task"])

    def test_tool_result_before_compact_keeps_result(self):
        r = self.scan(TOOL, RESULT, BOUNDARY, COMPACT, *TAIL)
        self.assertEqual(r["shp"]["shape"], "result")

    def test_tool_use_before_compact_keeps_tool(self):
        r = self.scan(TOOL, BOUNDARY, COMPACT, *TAIL)
        self.assertEqual(r["shp"]["shape"], "tool")

    def test_assistant_after_summary_decides(self):
        r = self.scan(TEXT, {"type": "system", "subtype": "turn_duration"}, BOUNDARY, COMPACT,
                      _asst([{"type": "tool_use", "id": "t2", "name": "Read", "input": {}}], "m2"))
        self.assertEqual(r["shp"]["shape"], "tool")
        self.assertNotIn("SECRET-SUMMARY-TEXT", r["task"])


if __name__ == "__main__":
    unittest.main()
