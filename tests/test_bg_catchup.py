"""Completions while the viewer was down: bell cards after restart, deduped and capped. Fixed clock, temp files only."""
import json
import os
import shutil
import tempfile
import time
import types
import unittest
from datetime import datetime
from unittest import mock

from tests._load import sidereus

bp = sidereus("bgtasks_parse")
notes = sidereus("notes")
cards = sidereus("cards")

NOW = 1_790_000_000.0
FP = "/s/sess.jsonl"


class _DT(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime.fromtimestamp(NOW, tz)


class CatchupTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cards = os.path.join(self.d, "cards.jsonl")
        self.alive = os.path.join(self.d, "bg-alive.json")
        clock = types.SimpleNamespace(time=lambda: NOW)
        self.meta = {"toolu_A": {"agentType": "general-purpose", "description": "fix it", "_id": "aidA"}}
        self.p = [mock.patch.object(bp, "time", clock), mock.patch.object(notes, "time", clock),
                  mock.patch.object(cards, "time", clock), mock.patch.object(cards, "datetime", _DT),
                  mock.patch.object(cards, "CARDS", self.cards), mock.patch.object(notes, "CARDS", self.cards),
                  mock.patch.object(bp, "ALIVE_FILE", self.alive), mock.patch.object(bp, "_alive_last", [0.0]),
                  mock.patch.object(bp, "_agent_meta", lambda sd: self.meta),
                  mock.patch.object(notes, "_agent_meta", lambda sd: self.meta),
                  mock.patch.object(notes, "START_AT", NOW),           # inside the 60 s grace
                  mock.patch.object(notes, "_catchup_n", [0])]
        for p in self.p:
            p.start()
        bp._bg_finished.pop(FP, None)

    def tearDown(self):
        for p in reversed(self.p):
            p.stop()
        bp._bg_finished.pop(FP, None)
        shutil.rmtree(self.d, ignore_errors=True)

    def rows(self):
        try:
            with open(self.cards, encoding="utf-8") as f:
                return [json.loads(x) for x in f]
        except OSError:
            return []

    def seed(self, prev, items):
        """One restart's seeding scan: pop each (key, kind, at), then announce."""
        with mock.patch.object(bp, "_alive_prev", prev):
            for key, kind, at in items:
                lab = "general-purpose: fix it" if kind == "sub" else "npm test"
                bp._bg_pop({key: (kind, lab)}, key, FP, True, at=at)
        notes._note_bg_done(FP, {"project": "p", "cwd": "/w"})

    def test_r1_agent_and_bg_one_card_each(self):
        self.seed({FP: NOW - 600}, [("toolu_A", "sub", NOW - 300), ("toolu_B", "bg", NOW - 200)])
        r = self.rows()
        self.assertEqual([c["kind"] for c in r], ["agent", "bgdone"])
        self.assertEqual((r[0]["aid"], r[0]["tid"]), ("aidA", "toolu_A"))
        self.assertEqual(r[1]["tid"], "toolu_B")
        self.assertEqual(r[1]["done_at"], datetime.fromtimestamp(NOW - 200).isoformat(timespec="seconds"))

    def test_r2_before_alive_time_or_no_line_time_is_silent(self):
        self.seed({FP: NOW - 100}, [("toolu_A", "sub", NOW - 300), ("toolu_B", "bg", 0)])
        self.assertEqual(self.rows(), [])

    def test_r2_unknown_fp_uses_newest_alive_time(self):
        self.seed({"/other.jsonl": NOW - 100}, [("toolu_B", "bg", NOW - 300), ("toolu_C", "bg", NOW - 50)])
        self.assertEqual([c["tid"] for c in self.rows()], ["toolu_C"])

    def test_r2_existing_card_blocks_and_no_resume_bump(self):
        cards._card_add("agent", "p", "Subagent done", "general-purpose: fix it", "/w", {"aid": "aidA"})
        cards._card_add("bgdone", "p", "Background done", "npm test", "/w", {"tid": "toolu_B"})
        self.seed({FP: NOW - 600}, [("toolu_A", "sub", NOW - 300), ("toolu_B", "bg", NOW - 200)])
        r = self.rows()
        self.assertEqual(len(r), 2)
        self.assertNotIn("resumes", r[0])

    def test_r2_two_restarts_one_card(self):
        self.seed({FP: NOW - 600}, [("toolu_B", "bg", NOW - 200)])
        notes._catchup_n[0] = 0
        self.seed({FP: NOW - 600}, [("toolu_B", "bg", NOW - 200)])     # alive file not updated in between
        self.seed({FP: NOW - 10}, [("toolu_B", "bg", NOW - 200)])
        self.assertEqual(len(self.rows()), 1)

    def test_r2_cap_and_age(self):
        items = [("toolu_%d" % i, "bg", NOW - 500 + i) for i in range(25)] + [("toolu_old", "bg", NOW - 90000)]
        self.seed({FP: NOW - 100000}, items)
        r = self.rows()
        self.assertEqual(len(r), notes.CATCHUP_MAX)
        self.assertNotIn("toolu_old", [c["tid"] for c in r])

    def test_r3_unknown_alive_time_silent_in_grace(self):
        self.seed(None, [("toolu_B", "bg", NOW - 200)])
        with open(self.alive, "w", encoding="utf-8") as f:
            f.write("{not json")
        self.assertIsNone(bp._alive_load(self.alive))
        for bad in ([1], {}, {FP: "x"}, {FP: NOW + 3600}):
            with open(self.alive, "w", encoding="utf-8") as f:
                json.dump(bad, f)
            self.assertIsNone(bp._alive_load(self.alive))
        self.seed(bp._alive_load(self.alive), [("toolu_C", "bg", NOW - 200)])
        self.assertEqual(self.rows(), [])

    def fg_result(self, prev, at):
        """Seeding scan of a foreground Agent's tool_result line (synchronous end, body is the report)."""
        ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(at))
        line = json.dumps({"type": "user", "timestamp": ts, "message": {"content": [
            {"type": "tool_result", "tool_use_id": "toolu_A", "content": "report"}]}})
        with mock.patch.object(bp, "_alive_prev", prev):
            bp._bg_on_line(line, {"toolu_A": ("sub", "general-purpose: fix it")}, FP, True, NOW)
        notes._note_bg_done(FP, {"project": "p", "cwd": "/w"})

    def test_r1_foreground_agent_result_after_alive_time(self):
        self.fg_result({FP: NOW - 600}, NOW - 300)
        r = self.rows()
        self.assertEqual([(c["kind"], c["title"], c["aid"]) for c in r], [("agent", "Subagent done", "aidA")])

    def test_r2_foreground_agent_result_before_alive_time(self):
        self.fg_result({FP: NOW - 100}, NOW - 300)
        self.assertEqual(self.rows(), [])

    def test_beat_throttled_and_written_to_temp(self):
        writes = []
        real = bp._atomic_write
        with mock.patch.object(bp, "_atomic_write", lambda p, b, **k: (writes.append(p), real(p, b, **k))), \
                mock.patch.dict(bp._bg_open_at, {FP: NOW}, clear=True), \
                mock.patch.object(bp, "_alive_prev", {"/gone.jsonl": NOW - 90000, "/kept.jsonl": NOW - 60}):
            bp._alive_beat(NOW)
            bp._alive_beat(NOW + 10)
            bp._alive_beat(NOW + 29)
            self.assertEqual(writes, [self.alive])
            bp._alive_beat(NOW + 31)
            self.assertEqual(len(writes), 2)
        self.assertEqual(bp._alive_load(self.alive), {FP: NOW, "/kept.jsonl": NOW - 60})


if __name__ == "__main__":
    unittest.main()
