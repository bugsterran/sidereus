"""_agent_ended: a run that reports via the SubagentHandback tool counts as ended (fixtures only)."""
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


class HandbackEnded(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="sidereus-agend-")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _fp(self, *recs):
        fp = os.path.join(self.d, "agent-%d.jsonl" % len(os.listdir(self.d)))
        with open(fp, "w") as f:
            f.write("".join(recs) + json.dumps({"type": "attachment"}) + "\n")
        return fp

    def _call(self, name, tid="t1"):
        return _rec("assistant", [{"type": "tool_use", "id": tid, "name": name, "input": {}}])

    def _res(self, tid="t1", err=False):
        return _rec("user", [{"type": "tool_result", "tool_use_id": tid, "is_error": err, "content": "ok"}])

    def test_handback_result_is_ended(self):
        self.assertTrue(ag._agent_ended(self._fp(self._call("Bash", "t0"), self._res("t0"), self._call("SubagentHandback"), self._res())))

    def test_handback_error_is_not_ended(self):
        self.assertFalse(ag._agent_ended(self._fp(self._call("SubagentHandback"), self._res(err=True))))

    def test_handback_pending_is_not_ended(self):
        self.assertFalse(ag._agent_ended(self._fp(self._call("SubagentHandback"))))

    def test_other_tool_result_is_not_ended(self):
        self.assertFalse(ag._agent_ended(self._fp(self._call("Bash"), self._res())))

    def test_text_report_still_ended(self):
        self.assertTrue(ag._agent_ended(self._fp(self._call("Bash"), self._res(), _rec("assistant", [{"type": "text", "text": "done"}]))))


if __name__ == "__main__":
    unittest.main()
