"""A subagent waiting on a long tool call is busy, not idle: its last tool_use has no later tool_result
(agents._agent_busy), and the row carries `busy` (agents._bg_show) so the screen does not say «Idle»."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import load, sidereus

load()
ag = sidereus("agents")


def _rec(kind, content):
    return json.dumps({"type": kind, "message": {"content": content}}) + "\n"


USE = _rec("assistant", [{"type": "tool_use", "id": "toolu_b1", "name": "Bash", "input": {"command": "x"}}])
RES = _rec("user", [{"type": "tool_result", "tool_use_id": "toolu_b1", "content": "ok"}])


class AgentBusy(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="sidereus-busy-")
        self.addCleanup(shutil.rmtree, self.d, True)
        saved = dict(ag._AGENT_LAST)
        ag._AGENT_LAST.clear()
        self.addCleanup(lambda: (ag._AGENT_LAST.clear(), ag._AGENT_LAST.update(saved)))

    def log(self, *recs):
        fp = os.path.join(self.d, "agent-%d.jsonl" % len(os.listdir(self.d)))
        with open(fp, "w", encoding="utf-8") as f:
            f.write(_rec("user", "task") + "".join(recs))
        return fp

    def test_pending_tool_is_busy(self):
        fp = self.log(USE)
        self.assertTrue(ag._agent_busy(fp))
        self.assertEqual(ag._agent_last(fp), "Bash")   # existing callers keep the plain string

    def test_answered_tool_is_not_busy(self):
        fp = self.log(USE, RES)
        self.assertFalse(ag._agent_busy(fp))
        self.assertEqual(ag._agent_last(fp), "Bash")

    def test_no_tool_is_not_busy(self):
        self.assertFalse(ag._agent_busy(self.log(_rec("assistant", [{"type": "text", "text": "hi"}]))))

    def test_row_flag_only_when_true(self):
        base = ["lab", 0, "Bash", 1, "toolu_p", 300, "a1", ""]
        rows = ag._bg_show([base + [True], base + [False], base], 0, False)
        self.assertEqual([r.get("busy") for r in rows], [1, None, None])


if __name__ == "__main__":
    unittest.main()
