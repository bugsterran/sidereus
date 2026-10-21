"""Compact tool usage index (sidereus/toolidx.py): events past TI_MAX_DAYS are dropped, ids in several files count
once (earliest copy), and counts match the per-event dict algorithm it replaced. Temp transcripts only."""
import json
import os
import random
import shutil
import tempfile
import unittest

from tests._load import load, sidereus
from tests.test_toolidx import NOW, _iso, _tu

load()
ti = sidereus("toolidx")
DAY = 86400


class ToolIdxCompactTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-tic-")
        self.saved = (ti.CLAUDE_PROJECTS, ti.TI_BG, ti.TI_REINDEX_MIN)
        ti.CLAUDE_PROJECTS, ti.TI_BG = self.tmp, False
        ti.reset()

    def tearDown(self):
        ti.CLAUDE_PROJECTS, ti.TI_BG, ti.TI_REINDEX_MIN = self.saved
        ti.reset()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name, recs):
        p = os.path.join(self.tmp, "-proj", name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(r) + "\n" for r in recs))
        os.utime(p, (NOW - 60, NOW - 60))
        return p

    def _events(self):
        return sum(len(e["ids"]) for e in ti._TI_FILES.values())

    def test_events_past_window_dropped_at_scan(self):
        self._write("a.jsonl", [_tu("toolu_old", "Skill", {"skill": "s"}, NOW - 100 * DAY),
                                _tu("toolu_new", "Skill", {"skill": "s"}, NOW - DAY)])
        u = ti.tool_uses(90, now=NOW)
        self.assertEqual((u["skill:s"]["n"], u["tool:Skill"]["n"]), (1, 1))
        self.assertEqual(self._events(), 2)                  # the new call's two keys only

    def test_events_aging_out_trimmed_from_active_file(self):
        p = self._write("a.jsonl", [_tu("toolu_1", "Bash", {}, NOW - 80 * DAY), _tu("toolu_2", "Bash", {}, NOW - DAY)])
        self.assertEqual(ti.tool_uses(90, now=NOW)["tool:Bash"]["n"], 2)
        later = NOW + 20 * DAY
        os.utime(p, (later - 60, later - 60))                 # file still active, its first call now 100 days old
        self.assertEqual(ti.tool_uses(90, now=later)["tool:Bash"]["n"], 1)
        self.assertEqual(self._events(), 1)

    def test_dedup_across_files_earliest_wins(self):
        self._write("a.jsonl", [_tu("toolu_x", "mcp__docs__q", {}, NOW - 3 * DAY)])
        self._write("b.jsonl", [_tu("toolu_x", "mcp__docs__q", {}, NOW - 5 * DAY),
                                _tu("toolu_x", "mcp__docs__q", {}, NOW - 2 * DAY)])   # repeat in one file: first copy
        u = ti.tool_uses(30, now=NOW)
        self.assertEqual(u["mcp:docs"], {"n": 1, "last": int(NOW - 5 * DAY)})
        self.assertNotIn("mcp:docs", ti.tool_uses(4, now=NOW))          # the earliest copy is outside 4 days
        self.assertEqual(ti.mcp_status(30, now=NOW)["mcp:docs"]["ok_at"], int(NOW - 3 * DAY))   # newest call per file

    def test_matches_dict_algorithm(self):
        ti.TI_REINDEX_MIN = 8                                 # several reindexes while scanning
        rnd = random.Random(7)
        names = ["Bash", "Read", "Skill", "Agent", "mcp__docs__q", "mcp__web__get"]
        files = {}
        for f in range(6):
            recs = []
            for _ in range(60):
                tid = "toolu_%d" % rnd.randrange(150)        # shared pool: many ids repeat within and across files
                nm = rnd.choice(names)
                inp = {"skill": "s%d" % rnd.randrange(3)} if nm == "Skill" else {"subagent_type": "r"} if nm == "Agent" else {}
                recs.append(_tu(tid, nm, inp, NOW - rnd.uniform(0, 89) * DAY))
            recs.append({"type": "attachment", "uuid": "h%d" % rnd.randrange(20), "timestamp": _iso(NOW - rnd.uniform(0, 89) * DAY),
                         "attachment": {"type": "hook_success", "hookName": "Stop", "command": "c"}})
            files[self._write("f%d.jsonl" % f, recs)] = recs
        merged = {}
        for recs in files.values():                          # reference: per-file first copy, then earliest across files
            own = {}
            for d in recs:
                ts = ti.iso_epoch(d["timestamp"], 0.0)
                evs = [("t#" + b["id"], "tool:" + b["name"]) for b in (d.get("message") or {}).get("content", [])
                       if b.get("type") == "tool_use"]
                for eid, k in evs + ti._line_events(d):
                    own.setdefault(eid, (k, ts))
            for eid, kt in own.items():
                if eid not in merged or kt[1] < merged[eid][1]:
                    merged[eid] = kt
        for days in (1, 7, 30, 90):
            want = {}
            for k, ts in merged.values():
                if ts >= NOW - days * DAY:
                    r = want.setdefault(k, {"n": 0, "last": 0})
                    r["n"] += 1
                    r["last"] = max(r["last"], int(ts))
            self.assertEqual(ti.tool_uses(days, now=NOW), want, days)
        self.assertTrue(ti._TI_DUP)


if __name__ == "__main__":
    unittest.main()
