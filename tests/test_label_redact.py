"""One-line labels (Agent description, SendMessage summary, bg Bash description, room topic) are redacted at the source,
and /api/messages refuses n <= 0. No live files, clock or network (journal fixture is a temp file)."""
import json
import os
import tempfile
import unittest
from urllib.parse import urlparse

from tests._load import sidereus

R = sidereus("redact")
bp = sidereus("bgtasks_parse")
ag = sidereus("agents")
rc = sidereus("recent")
sv = sidereus("state_v1")
rg = sidereus("routes_get")

PW = "FakePw9xyz"
URL = "https://deploy:" + PW + "@registry.example.com/push it"
TOK = "token=" + "Q" * 20


class LabelRedact(unittest.TestCase):
    def test_sub_label_description_and_summary(self):
        lab = bp._sub_label({"agentType": "x", "description": URL, "_id": "a-desc"})
        self.assertNotIn(PW, lab)
        self.assertIn(R.MASK, lab)
        bp._bg_said.put("a-sum", (100.0, TOK))
        lab = bp._sub_label({"agentType": "x", "description": "plain", "_id": "a-sum"})
        self.assertNotIn("Q" * 20, lab)

    def test_launch_labels(self):
        rows = {}
        bp._bg_on_launch({"id": "t1", "name": "Agent", "input": {"subagent_type": "Explore", "description": URL}},
                         {}, rows, "/nonexistent/s.jsonl", 0.0)
        bp._bg_on_launch({"id": "t2", "name": "Bash", "input": {"run_in_background": True, "description": TOK}},
                         {}, rows, "/nonexistent/s.jsonl", 0.0)
        for k in ("t1", "t2"):
            self.assertNotIn(PW, rows[k][1])
            self.assertNotIn("Q" * 20, rows[k][1])
            self.assertIn(R.MASK, rows[k][1])

    def test_recent_agent_desc(self):
        out = rc._agent_desc([{"type": "tool_use", "name": "Agent", "input": {"description": URL}}])
        self.assertNotIn(PW, out)
        self.assertIn(R.MASK, out)

    def test_workflow_journal_label(self):
        fd, fp = tempfile.mkstemp(suffix=".jsonl")
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps({"type": "started", "agentId": "w1", "label": URL, "phase": "p"}) + "\n")
        try:
            lab = ag._wf_journal(fp)["ag"]["w1"]["lab"]
        finally:
            os.unlink(fp)
        self.assertNotIn(PW, lab)
        self.assertIn(R.MASK, lab)

    def test_room_topic_state_and_v1(self):
        rooms = {"r": {"owner": "a", "members": ["a"], "topic": URL}, "q": {"topic": ""}}
        self.assertNotIn(PW, R.redact_rooms(rooms)["r"]["topic"])
        self.assertEqual(rooms["r"]["topic"], URL)          # copy, the loaded dict is not mutated
        self.assertNotIn(PW, sv._rooms(rooms)["r"]["topic"])


class SidecarDescRedact(unittest.TestCase):
    def _meta_pair(self, desc):
        d = tempfile.mkdtemp(prefix="sidereus-lr-")
        fp = os.path.join(d, "agent-a1.jsonl")
        with open(fp[:-6] + ".meta.json", "w") as f:
            json.dump({"agentType": "x", "description": desc, "toolUseId": "t"}, f)
        return fp

    def test_agentcost_side(self):
        fp = self._meta_pair(URL)
        self.assertNotIn(PW, sidereus("agentcost")._agc_side(fp)["d"])

    def test_file_owner_who(self):
        fp = self._meta_pair(URL)
        self.assertNotIn(PW, sidereus("file_owner")._who(fp, True, [])[3])

    def test_every_description_read_is_redacted(self):
        # Static guard for the scan-heavy sources (history, failures, burn): each description read passes through redact().
        for mod in ("history", "failures_scan", "burn_scan", "agentcost", "file_owner"):
            src = open(sidereus(mod).__file__, encoding="utf-8").read().splitlines()
            raw = [ln for ln in src if 'get("description")' in ln and "redact(" not in ln
                   and not ln.lstrip().startswith("#")]
            self.assertEqual(raw, [], mod)


class MessagesN(unittest.TestCase):
    def _get(self, q):
        sent = {}
        fake = type("F", (), {})()
        fake._raw_json = lambda code, out, cache=True: sent.update(code=code, out=out)
        fake._send = lambda code, body, ctype, gz: sent.update(code=code, out=json.loads(body))
        orig = rg.messages_range
        rg.messages_range = lambda a, b, n: [{"id": "m%d" % i} for i in range(n)]
        try:
            rg._GetRoutes._g_messages(fake, urlparse("/api/messages?" + q))
        finally:
            rg.messages_range = orig
        return sent

    def test_non_positive_and_bad_n_refused(self):
        for q in ("n=-1", "n=0", "n=abc"):
            self.assertEqual(self._get(q), {"code": 400, "out": {"error": "bad cursor"}}, q)

    def test_positive_n_ok(self):
        s = self._get("n=2")
        self.assertEqual((s["code"], len(s["out"]["messages"])), (200, 2))


if __name__ == "__main__":
    unittest.main()
