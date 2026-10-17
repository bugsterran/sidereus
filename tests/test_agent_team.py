"""Agent teams: tasks/<sid>/*.json + teams/<sid>/inboxes/*.json + the leader's subagent metas → one team node.
Task descriptions and inbox message text never reach the row (AGENTS.md rule 1)."""
import json
import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

from tests._load import load, sidereus

load()
ag = sidereus("agents")
S = sidereus("sessions")

SID = "ec5938f2-0000-1111-2222-333344445555"
SECRET_D, SECRET_T = "SECRET-TASK-DESCRIPTION", "SECRET-INBOX-TEXT"


def _w(fp, obj):
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(obj, f)


class AgentTeam(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="sidereus-team-")
        self.sd = os.path.join(self.home, "projects", "-w-repo", SID)
        sub = os.path.join(self.sd, "subagents")
        for i, (st, own) in enumerate((("completed", "alpha"), ("in_progress", "beta"), ("pending", "beta"),
                                       ("pending", "gamma")), 1):
            _w(os.path.join(self.home, "tasks", SID, "%d.json" % i),
               {"id": str(i), "subject": "task %d" % i, "description": SECRET_D, "status": st,
                "blocks": [], "blockedBy": [], "owner": own})
        ib = os.path.join(self.home, "teams", SID, "inboxes")
        _w(os.path.join(ib, "alpha.json"), [{"from": "team-lead", "text": SECRET_T, "read": True, "msg_id": "1"}])
        _w(os.path.join(ib, "beta.json"), [{"from": "team-lead", "text": SECRET_T, "read": False, "msg_id": "2"},
                                           {"from": "alpha", "text": SECRET_T, "read": False, "msg_id": "3"}])
        _w(os.path.join(ib, "team-lead.json"), [{"from": "beta", "text": SECRET_T, "read": False, "msg_id": "4"}])
        for n, (name, last) in enumerate((("alpha", "text"), ("beta", "tool_use"))):
            _w(os.path.join(sub, "agent-a%d.meta.json" % n),
               {"agentType": "general-purpose", "description": "Teammate", "name": name, "model": "haiku",
                "toolUseId": "toolu_%d" % n, "spawnDepth": 1})
            blk = {"type": "text", "text": "done"} if last == "text" else {"type": "tool_use", "name": "Read", "input": {}}
            with open(os.path.join(sub, "agent-a%d.jsonl" % n), "w", encoding="utf-8") as f:
                f.write(json.dumps({"type": "assistant", "message": {"content": [blk]}}) + "\n")
        ag._AGENT_META.clear()
        self.p = mock.patch.object(ag, "TEAM_ROOT", self.home)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        ag._AGENT_META.clear()
        shutil.rmtree(self.home, ignore_errors=True)

    def test_team_node(self):
        t = ag.team_info(self.sd)
        self.assertEqual((t["done"], t["total"]), (1, 4))
        self.assertEqual(t["tasks"], {"pending": 2, "in_progress": 1, "completed": 1})
        by = {m["name"]: m for m in t["members"]}
        self.assertEqual(sorted(by), ["alpha", "beta", "gamma"])        # the leader's own inbox is not a member
        self.assertEqual(by["alpha"]["st"], "done")
        self.assertEqual(by["beta"]["st"], "run")
        self.assertEqual(by["beta"]["tsub"], "task 2")                   # in_progress wins over pending
        self.assertEqual(by["alpha"]["tsub"], "")                      # completed is not current
        self.assertEqual((by["alpha"]["unread"], by["beta"]["unread"]), (0, 2))
        self.assertTrue(t["run"])

    def test_row_is_metadata_only(self):
        blob = json.dumps(S._team_row(self.sd + ".jsonl"))
        self.assertNotIn(SECRET_D, blob)
        self.assertNotIn(SECRET_T, blob)

    def test_no_team_and_quiet_team(self):
        self.assertIsNone(ag.team_info(os.path.join(self.home, "projects", "-w-repo", "other-sid")))
        old = time.time() - 7200
        for root, _d, fs in os.walk(self.home):
            for fn in fs:
                if fn.endswith(".json") and "tasks" in root:
                    with open(os.path.join(root, fn), encoding="utf-8") as f:
                        t = json.load(f)
                    t["status"] = "completed"
                    _w(os.path.join(root, fn), t)
        for root, _d, fs in os.walk(self.home):
            for fn in fs:
                os.utime(os.path.join(root, fn), (old, old))
        self.assertIsNone(ag.team_info(self.sd))


if __name__ == "__main__":
    unittest.main()
