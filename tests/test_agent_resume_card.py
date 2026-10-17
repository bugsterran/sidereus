"""A resumed agent's completion bumps its earlier card; the bell group counts distinct agents (synthetic cards only)."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus
from tests._node import node_e

notes = sidereus("notes")
cards = sidereus("cards")

JS = os.path.join(os.path.dirname(__file__), "..", "web", "js", "15-alarms.js")
CORE = os.path.join(os.path.dirname(__file__), "..", "web", "js", "00-core.js")


class ResumeBumpTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.f = os.path.join(self.d, "cards.jsonl")
        self.meta = {"toolu_A": {"agentType": "general-purpose", "description": "Warm quota/burn at startup",
                                 "_id": "af3c", "_file": os.path.join(self.d, "agent-af3c.jsonl")}}
        self.p = [mock.patch.object(cards, "CARDS", self.f),
                  mock.patch.object(notes, "_agent_meta", lambda sd: self.meta)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        shutil.rmtree(self.d, ignore_errors=True)

    def rows(self):
        with open(self.f, encoding="utf-8") as fh:
            return [json.loads(ln) for ln in fh]

    def test_resume_bumps_one_card_with_real_type(self):
        info = {"project": "p", "cwd": "/w"}
        notes._note_agent_done("/s/x.jsonl", info, "agent: Warm quota/burn at startup")          # launch without subagent_type
        notes._note_agent_done("/s/x.jsonl", info, "general-purpose: Warm quota/burn at startup")  # resume via SendMessage
        r = self.rows()
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["text"], "general-purpose: Warm quota/burn at startup")
        self.assertEqual((r[0]["aid"], r[0]["resumes"]), ("af3c", 1))

    def test_bump_keeps_other_cards_and_moves_to_end(self):
        cards._card_add("agent", "p", "서브에이전트 완료", "general-purpose: Warm quota/burn at startup", "/w", {"aid": "af3c"})
        cards._card_add("ask", "p", "질문 대기", "", "/w")
        notes._note_agent_done("/s/x.jsonl", {"project": "p", "cwd": "/w"}, "general-purpose: Warm quota/burn at startup")
        self.assertEqual([c["kind"] for c in self.rows()], ["ask", "agent"])

    def test_same_brief_two_aids_stay_two_cards(self):
        info = {"project": "p", "cwd": "/w"}
        notes._note_agent_done("/s/x.jsonl", info, "general-purpose: Warm quota/burn at startup", "af3c")
        notes._note_agent_done("/s/x.jsonl", info, "general-purpose: Warm quota/burn at startup", "zz99")  # relaunch
        r = self.rows()
        self.assertEqual([c["aid"] for c in r], ["af3c", "zz99"])
        self.assertFalse(any(c.get("resumes") for c in r))

    def test_sub_identity_real_type_and_aid(self):
        bg = sidereus("bgtasks_parse")                  # _sub_identity reads _agent_meta from here
        with mock.patch.object(bg, "_agent_meta", lambda sd: self.meta), \
             mock.patch.dict(bg._bg_resume, {"toolu_SEND": "af3c"}, clear=True):
            self.assertEqual(bg._sub_identity("/s/x.jsonl", "toolu_A", "agent: Warm quota/burn at startup"),
                             ("general-purpose: Warm quota/burn at startup", "af3c"))       # launch without subagent_type
            self.assertEqual(bg._sub_identity("/s/x.jsonl", "toolu_SEND", "agent: Warm quota/burn at startup"),
                             ("general-purpose: Warm quota/burn at startup", "af3c"))       # resume row key
            self.assertEqual(bg._sub_identity("/s/x.jsonl", "toolu_X", "Explore: y"), ("Explore: y", ""))

    def test_different_agent_same_folder_gets_own_card(self):
        self.meta["toolu_B"] = {"agentType": "Explore", "description": "Other job", "_id": "b1", "_file": ""}
        info = {"project": "p", "cwd": "/w"}
        notes._note_agent_done("/s/x.jsonl", info, "general-purpose: Warm quota/burn at startup")
        notes._note_agent_done("/s/x.jsonl", info, "Explore: Other job")
        self.assertEqual(len(self.rows()), 2)


def _fn(src, name):
    return re.search(r"^function " + name + r"\(.*?^}", src, re.S | re.M).group(0)


def _plstrip():
    # cardText calls plStrip (00-core.js), a one-line function.
    return re.search(r"^function plStrip\(.*$", open(CORE, encoding="utf-8").read(), re.M).group(0)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class GroupDistinctTest(unittest.TestCase):
    def test_group_counts_distinct_agents(self):
        src = open(JS, encoding="utf-8").read()
        items = [{"kind": "agent", "at": "2026-09-24T14:10:00", "text": "general-purpose: Warm quota/burn at startup"},
                 {"kind": "agent", "at": "2026-09-24T14:05:00", "text": "Explore: Other job"},
                 {"kind": "agent", "at": "2026-09-24T13:59:00", "text": "agent: Warm quota/burn at startup"}]
        js = "\n".join([
            "const T = s => s;", _plstrip(),
            re.search(r"^function cardText\(.*$", src, re.M).group(0),
            re.search(r"^const agDesc = .*$", src, re.M).group(0),
            _fn(src, "grpRows"),
            "console.log(JSON.stringify(grpRows({kind: 'agent', items: " + json.dumps(items) + "})));",
        ])
        r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = json.loads(r.stdout)
        self.assertEqual(len(rows), 2)
        self.assertEqual((rows[0]["t"], rows[0]["n"]), ("general-purpose: Warm quota/burn at startup", 2))

    def test_group_keeps_two_aids_with_same_brief(self):
        src = open(JS, encoding="utf-8").read()
        items = [{"kind": "agent", "at": "2026-09-24T14:10:00", "text": "general-purpose: Same brief", "aid": "a1"},
                 {"kind": "agent", "at": "2026-09-24T14:05:00", "text": "general-purpose: Same brief", "aid": "a2"}]
        js = "\n".join(["const T = s => s;", _plstrip(), re.search(r"^function cardText\(.*$", src, re.M).group(0),
                        re.search(r"^const agDesc = .*$", src, re.M).group(0), _fn(src, "grpRows"),
                        "console.log(grpRows({kind: 'agent', items: " + json.dumps(items) + "}).length);"])
        r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "2"), r.stderr)


if __name__ == "__main__":
    unittest.main()
