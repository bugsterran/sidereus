"""Tests for history_units (GET /api/history/units) and the finished-session lookup in /work.

Synthetic transcripts in a temp dir; CLAUDE_PROJECTS, the usage index and liveness are patched on the modules.
"""
import json
import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

from tests._load import sidereus

H = sidereus("history")
W = sidereus("work")

SID = "0123abcd-0000-4000-8000-000000000001"
CWD = "/w/proj"
SLUG = "-w-proj"


def _line(**kw):
    return json.dumps(kw, separators=(",", ":")) + "\n"   # compact, like real transcripts


class HistoryUnitsTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        pd = os.path.join(self.root, SLUG)
        sd = os.path.join(pd, SID, "subagents")
        os.makedirs(sd)
        self.main = os.path.join(pd, SID + ".jsonl")
        with open(self.main, "w", encoding="utf-8") as f:
            f.write(_line(type="user", cwd=CWD, message={"role": "user", "content": "hi"}))
        self.agent = os.path.join(sd, "agent-aaa1.jsonl")
        with open(self.agent, "w", encoding="utf-8") as f:
            f.write(_line(type="assistant", message={"content": [
                {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "/w/proj/x"}}]}))
            f.write(_line(type="assistant", message={"content": [{"type": "text", "text": "done"}]}))
        with open(os.path.join(sd, "agent-aaa1.meta.json"), "w", encoding="utf-8") as f:
            json.dump({"agentType": "Explore", "description": "find the thing", "toolUseId": "toolu_X",
                       "spawnDepth": 1}, f)
        # Main file lives 10h past now; activity only in two hour buckets inside it (a resumed session's shape)
        self.b0 = (int(time.time()) // 3600 + 2) * 3600
        os.utime(self.main, (self.b0 + 36000, self.b0 + 36000))
        files = {self.main: {"sl": SLUG, "h": {str(self.b0): {"m": [1, 2, 3, 0]},
                                                str(self.b0 + 7200): {"m": [4, 0, 0, 0]}}},
                 self.agent: {"sl": SLUG, "h": {"3600": {"m": [10, 0, 0, 0]}}}}
        H._units_cache.clear()
        self.p = [mock.patch.object(H, "CLAUDE_PROJECTS", self.root),
                  mock.patch.object(H, "_uidx", {"files": files}),
                  mock.patch.object(H, "_uidx_refresh", lambda *a, **k: None),
                  mock.patch.object(H, "sid_alive", lambda s: False),
                  mock.patch.object(H, "_cwd_from_slug", lambda s: CWD if s == SLUG else ""),
                  mock.patch.object(W, "CLAUDE_PROJECTS", self.root),
                  mock.patch.object(W, "_sid_transcript", lambda s: ""),
                  mock.patch.object(W, "_allowed_cwds", lambda ttl=5: {})]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        H._units_cache.clear()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_units_metadata_only(self):
        out = H.history_units(SID)
        self.assertTrue(out["ok"])
        self.assertEqual(out["cwd"], CWD)
        m, a = out["units"]
        self.assertEqual((m["kind"], m["tid"], m["tok"], m["tc"], m["st"]), ("main", "sess:" + CWD + "|" + SID, 10, None, "end"))
        self.assertEqual((a["type"], a["desc"], a["tid"], a["tok"], a["tc"], a["st"]),
                         ("Explore", "find the thing", "toolu_X|" + SID, 10, 1, "done"))
        self.assertEqual(set(a), {"kind", "tid", "aid", "type", "desc", "start", "end", "tok", "tc", "depth", "st"})

    def test_main_span_from_index_buckets(self):
        m = H.history_units(SID)["units"][0]
        self.assertEqual((m["start"], m["end"], m["hours"]), (self.b0, self.b0 + 3 * 3600, 2))

    def test_main_span_falls_back_to_file_times(self):
        H._uidx["files"][self.main]["h"] = {}
        m = H.history_units(SID)["units"][0]
        self.assertEqual((m["end"], m["hours"]), (self.b0 + 36000, None))

    def test_bad_sid_rejected(self):
        self.assertFalse(H.history_units("../etc/passwd")["ok"])
        self.assertFalse(H.history_units("ffffffff-0000")["ok"])

    def test_work_opens_finished_session_and_agent(self):
        self.assertTrue(W.session_work(CWD, SID)["ok"])
        a = W.agent_work(CWD, "toolu_X", SID)
        self.assertTrue(a["ok"])
        self.assertEqual(a["type"], "Explore")

    def test_work_by_agent_id(self):   # resumed agent: row tid = SendMessage id (not in meta) -> the agent id opens it
        sd = os.path.dirname(self.agent)
        shutil.copy(self.agent, os.path.join(sd, "agent-a0123456789abcdef.jsonl"))
        with open(os.path.join(sd, "agent-a0123456789abcdef.meta.json"), "w", encoding="utf-8") as f:
            json.dump({"agentType": "Plan", "description": "d", "toolUseId": "toolu_Y"}, f)
        self.assertEqual(W.agent_work(CWD, "a0123456789abcdef", SID)["type"], "Plan")
        for bad in ("toolu_SENDMSG", "", "aaa1", "../a0123456789abcdef", "a0123456789abcdef/x", "/etc/passwd", "a0123456789abcdee"):  # gitleaks:allow
            self.assertFalse(W.agent_work(CWD, bad, SID)["ok"], bad)   # unknown, off-pattern or path-like ids are refused

    def test_work_rejects_mismatched_cwd(self):
        self.assertFalse(W.session_work("/other", SID)["ok"])
        self.assertFalse(W.agent_work("/other", "toolu_X", SID)["ok"])
        self.assertFalse(W.session_work(CWD, "")["ok"])   # no sid: live list only, as before


if __name__ == "__main__":
    unittest.main()
