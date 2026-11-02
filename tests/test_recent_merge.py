"""«Recently ended sessions» merges every `done` row of the session list (sidereus/recent.py _done_rows):
external CLI rows and cc rows missing from the index appear once, live rows stay out, newest first, metadata only."""
import json
import unittest

from tests import test_recent as TR

R, NOW = TR.R, TR.NOW


class RecentMerge(unittest.TestCase):
    tearDown = TR.RecentList.tearDown
    add = TR.RecentList.add

    def setUp(self):
        TR.RecentList.setUp(self)
        self.saved["_snap_at"], R._snap_at = R._snap_at, lambda: NOW - 50   # snapshot taken 50 s ago

    def test_union_dedupe_live_and_order(self):
        a = self.add(1, 3600)                                     # cc row from the index
        self.live_snap = [
            {"sid": a, "state": "done", "plat": "cc", "ageSec": 3600},                         # already listed: once
            {"sid": "cx-1", "state": "done", "plat": "cx", "cwd": "/w/q", "project": "q", "ageSec": 120,
             "model": "gpt-5-codex", "ctx": 50_000, "win": 200_000, "targ": "SECRET-TARG", "tool": "Bash"},
            {"sid": "cc-miss", "state": "done", "plat": "cc", "cwd": "/w/r", "project": "r", "ageSec": 30,
             "wt": {"root": "/w/r2", "main": "/w/r", "name": "r2"}, "acct": "work", "acctDir": "/h/.claude-work"},
            {"sid": "gm-live", "state": "wait", "plat": "gm", "ageSec": 5},                    # live: excluded
        ]
        out = R.recent_sessions(7)
        sids = [r["sid"] for r in out["rows"]]
        self.assertEqual(sids, ["cc-miss", "cx-1", a])           # endedAt desc
        self.assertEqual(out["n"], 3)
        self.assertEqual(out["total"], 3)
        cx = out["rows"][1]
        self.assertEqual((cx["plat"], cx["name"], cx["pct"], cx["endedAt"], cx["agentDesc"]), ("cx", "q", 25, int(NOW - 50 - 120), ""))
        self.assertTrue(cx["gone"])                               # /w/q does not exist here
        miss = out["rows"][0]
        self.assertEqual((miss["plat"], miss["name"], miss["pct"], miss["acct"], miss["acctDir"]), ("cc", "r", None, "work", "/h/.claude-work"))
        self.assertNotIn("plat", out["rows"][2])                  # index rows keep their keys
        self.assertNotIn("SECRET", json.dumps(out))
        self.assertFalse({"targ", "tool", "task", "reply"} & set(cx))

    def test_no_snapshot_time_uses_now(self):
        R._snap_at = lambda: 0
        self.live_snap = [{"sid": "cu-1", "state": "done", "plat": "cu", "ageSec": 10}]
        self.assertEqual(R.recent_sessions(7)["rows"][0]["endedAt"], int(NOW - 10))

    def test_external_only(self):
        self.live_snap = [{"sid": "cu-1", "state": "done", "plat": "cu", "ageSec": 10}]
        out = R.recent_sessions(7)
        self.assertEqual([(r["sid"], r["plat"], r["name"], r["gone"]) for r in out["rows"]], [("cu-1", "cu", "?", False)])


if __name__ == "__main__":
    unittest.main()
