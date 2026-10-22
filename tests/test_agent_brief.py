"""sidereus/agent_brief.py — read-only briefs for the MCP server. No live files: every reader is monkeypatched."""
import json
import os
import unittest
from tests._load import sidereus

ab = sidereus("agent_brief")
SECRET = "SECRET-CONVERSATION-TEXT"
ROOT = "/r/repo"


def _rows():
    return [
        {"sid": "aaaaaaaa-1", "project": "repo", "branch": "main", "state": "tool", "tool": "Edit", "ctx": 250000,
         "win": 1000000, "ageSec": 5, "model": "opus", "task": SECRET, "reply": SECRET, "targ": SECRET,
         "wt": {"root": ROOT, "main": "", "name": "repo"},
         "sub": [{"aid": "bbbbbbbbcc", "lab": "general-purpose: " + SECRET, "now": "Bash · " + SECRET, "idle": 0}]},
        {"sid": "cccccccc-2", "project": "repo", "branch": "feat", "state": "ask", "tool": "", "ctx": 0, "win": 0,
         "ageSec": 50, "wt": {"root": "/r/repo-wt", "main": ROOT, "name": "repo-wt"}, "task": SECRET},
        {"sid": "dddddddd-3", "project": "other", "state": "think", "wt": {"root": "/r/other", "main": "", "name": "o"}},
        {"sid": "eeeeeeee-4", "project": "repo", "state": "done", "wt": {"root": ROOT, "main": "", "name": "repo"}},
    ]


class Patch(unittest.TestCase):
    def patch(self, mod, name, val):
        old = getattr(mod, name)
        setattr(mod, name, val)
        self.addCleanup(setattr, mod, name, old)


class TestPeers(Patch):
    def test_same_repo_live_only_and_no_text(self):
        self.patch(ab, "_wt_of", lambda c: {"root": ROOT, "main": "", "name": "repo"})
        out = ab.brief_peers(ROOT, rows=_rows())
        self.assertTrue(out["ok"])
        self.assertEqual([p["sid8"] for p in out["peers"]], ["aaaaaaaa", "cccccccc"])
        self.assertTrue(out["peers"][0]["sameWorktree"])
        self.assertFalse(out["peers"][1]["sameWorktree"])
        self.assertEqual(out["peers"][0]["ctxPct"], 25)
        self.assertEqual(out["peers"][0]["subagents"], [{"aid8": "bbbbbbbb", "type": "general-purpose", "idle": False}])
        self.assertNotIn(SECRET, json.dumps(out))

    def test_not_git(self):
        self.patch(ab, "_wt_of", lambda c: None)
        out = ab.brief_peers("/tmp/x", rows=[{"state": "run", "wt": {}}])  # nosec B108 -- fake cwd, _wt_of is patched
        self.assertTrue(out["ok"])                     # neutral, not an MCP error
        self.assertEqual((out["peers"], out["n"]), ([], 0))
        self.assertIn("not a git repo", out["note"])


class TestFile(Patch):
    def test_recent_editors_live_and_dirty(self):
        now = 10000.0
        p = os.path.normpath(ROOT + "/a.py")   # brief_file normpaths (backslashes on Windows)
        idx = {p: {("aaaaaaaa-1", "main"): {"ts": now - 60, "agent": "", "desc": SECRET, "cwd": ROOT},
                   ("aaaaaaaa-1", "bbbbbbbbcc"): {"ts": now - 120, "agent": "general-purpose", "desc": SECRET,
                                                  "cwd": ROOT},
                   ("dddddddd-3", "main"): {"ts": now - 4000, "agent": "", "desc": "", "cwd": ROOT}}}
        self.patch(ab._fo, "index", lambda n=None: idx)
        self.patch(ab._fo, "_dirty", lambda root, n: {p})
        self.patch(ab, "_edit_target", lambda x: {"cwd": ROOT, "path": "a.py"})
        out = ab.brief_file("a.py", ROOT, rows=_rows(), now=now)
        self.assertEqual(out["path"], p)
        self.assertTrue(out["uncommitted"])
        self.assertEqual(out["n"], 2)               # 4000 s old edit is outside the 30 min window
        self.assertEqual(out["liveN"], 2)
        self.assertEqual([e["unit"] for e in out["editors"]], ["main", "bbbbbbbb"])
        self.assertNotIn(SECRET, json.dumps(out))

    def test_missing_file_flagged(self):
        self.patch(ab._fo, "index", lambda n=None: {})
        self.patch(ab, "_edit_target", lambda x: None)
        self.patch(ab, "_exists", lambda p: False)
        self.assertIs(ab.brief_file("/r/repo/123", "", rows=[], now=1.0)["exists"], False)

    def test_relative_without_cwd(self):
        self.assertFalse(ab.brief_file("a.py", "", rows=[])["ok"])


class TestQuota(Patch):
    def _base(self, view, saver):
        self.patch(ab, "quota", lambda: {"age": 3, "five_hour": {"pct": 55.0, "resets_at": "x", "leftSec": 7000},
                                         "seven_day": {"pct": 38.0, "resets_at": "y", "leftSec": 90000}})
        self.patch(ab, "quota_burn", lambda: {"head": {"tok": 200_000_000, "eff": 150_000_000, "cap": "7d"},
                                              "cur": {"used_local": 27_000_000}, "proj": {"over_at": 2000}})
        self.patch(ab, "_saver_state", lambda p, l: saver)
        self.patch(ab, "_saver_view", lambda: view)
        self.patch(ab, "claude_accounts", lambda: [{"label": "main", "dir": "/c/main", "primary": True},
                                                   {"label": "work", "dir": "/c/work", "primary": False}])

    def test_fast_pace_says_slow_down(self):
        self._base({"at": 1000, "lv": 1, "lvNm": "빠름", "earlyMin": 29, "goal": 100, "mode": "auto", "rec": 1,
                    "head": SECRET}, {"on": False, "why": "auto"})
        out = ab.brief_quota(now=1010)
        self.assertEqual(out["used5Tok"], 27_000_000)
        self.assertEqual(out["emptyAt"], 2000)
        self.assertTrue(out["advice"].startswith("slow down"))
        self.assertEqual(out["sevenDay"]["pct"], 38.0)

    def test_no_token_headroom(self):
        # ★2026-10-02: tokens per 1% has no stable denominator — never hand agents a token headroom.
        self._base({"at": 1000, "lv": 0}, {"on": False, "why": "auto"})
        out = ab.brief_quota(now=1001)
        self.assertNotIn("leftTok", out)
        self.assertNotIn("leftCap", out)

    def test_saver_on_wins_and_stale_view_ignored(self):
        self._base({"at": 0, "lv": -2}, {"on": True, "why": "quota", "stage": 1, "cap": 2})
        out = ab.brief_quota(now=10_000)
        self.assertIsNone(out["pace"]["lv"])
        self.assertIn("stage 1", out["advice"])

    def test_on_pace_ok(self):
        self._base({"at": 1000, "lv": 0}, {"on": False, "why": "auto"})
        self.assertTrue(ab.brief_quota(now=1001)["advice"].startswith("ok"))

    def test_no_verdict_is_not_on_pace(self):
        # mode off -> lv None: never "on pace"; over_at 2000 is before the reset (now + 7000) -> warn.
        self._base({"at": 1000, "lv": None, "mode": "off"}, {"on": False, "why": "auto"})
        adv = ab.brief_quota(now=1001)["advice"]
        self.assertNotIn("on pace", adv)
        self.assertIn("empties before it resets", adv)
        self.patch(ab, "quota_burn", lambda: {"cur": {"used_local": 1}, "proj": {"over_at": 99_999}})
        adv = ab.brief_quota(now=1001)["advice"]
        self.assertEqual(adv, "no pace verdict (pace mode off)")

    def test_fresh_install_no_pace_data_is_neutral(self):
        self._base(None, {"on": False, "why": "auto"})
        self.patch(ab, "quota_burn", lambda: {})
        adv = ab.brief_quota(now=1001)["advice"]
        self.assertEqual(adv, "no pace data yet")
        self.assertNotIn("missing", adv)


class TestQuotaAcct(Patch):
    _base = TestQuota._base

    def test_primary_unchanged_plus_acct(self):
        # R2: no account = today's body; only the label is added.
        self._base({"at": 1000, "lv": 0}, {"on": False, "why": "auto"})
        out = ab.brief_quota(now=1001)
        self.assertEqual(out["acct"], "main")
        self.assertEqual(out, ab.brief_quota(now=1001, acct="main"))
        self.assertEqual(out["fiveHour"]["pct"], 55.0)
        self.assertNotIn("err", out)

    def test_extra_account_reads_its_own_row(self):
        self._base({"at": 1000, "lv": 2}, {"on": False, "why": "auto"})
        self.patch(ab, "quota_accounts", lambda: [{"label": "work", "age": 9, "err": None,
                                                   "five_hour": {"pct": 12.0, "resets_at": "w", "leftSec": 5000},
                                                   "seven_day": {"pct": 4.0, "resets_at": "v", "leftSec": 80000}}])
        self.patch(ab, "quota_burn_acct", lambda lab: {"ok": True, "acct": lab, "proj": {"over_at": 3000}})
        self.patch(ab, "_saver_views", lambda: {"work": {"at": 1000, "lv": -1, "mode": "auto"}})
        out = ab.brief_quota(now=1001, acct="work")
        self.assertTrue(out["ok"])
        self.assertEqual((out["acct"], out["fiveHour"]["pct"], out["sevenDay"]["pct"]), ("work", 12.0, 4.0))
        self.assertEqual((out["emptyAt"], out["used5Tok"], out["pace"]["lv"]), (3000, None, -1))

    def test_extra_saver_from_own_view_else_fallback(self):
        self._base(None, {"on": False, "why": "auto"})
        self.patch(ab, "quota_accounts", lambda: [{"label": "work", "five_hour": {"pct": 90.0, "leftSec": 900}}])
        self.patch(ab, "quota_burn_acct", lambda lab: {})
        self.patch(ab, "_saver_views", lambda: {"work": {"at": 1000, "mode": "auto", "stage": 2}})
        sv = ab.brief_quota(now=1001, acct="work")["saver"]
        self.assertEqual((sv["on"], sv["stage"], sv["cap"], sv["why"]), (True, 2, 1, "hook"))
        self.patch(ab, "_saver_views", lambda: {})      # missing view -> the derived rule
        self.assertEqual(ab.brief_quota(now=1001, acct="work")["saver"]["why"], "auto")

    def test_extra_unmeasured_is_not_primary(self):
        self._base({"at": 1000, "lv": 0}, {"on": False, "why": "auto"})
        self.patch(ab, "quota_accounts", lambda: [])
        self.patch(ab, "quota_burn_acct", lambda lab: {"ok": False, "why": "not measured"})
        self.patch(ab, "_saver_views", lambda: {})
        out = ab.brief_quota(now=1001, acct="work")
        self.assertFalse(out["ok"])
        self.assertEqual((out["acct"], out["err"], out["fiveHour"]["pct"]), ("work", "not measured", None))


class TestAttention(Patch):
    def test_labels_only(self):
        self.patch(ab, "cards", lambda n: [])
        self.patch(ab, "quota", lambda: {})
        self.patch(ab, "attention", lambda r, c, q: {"rows": [{"sid": "aaaaaaaa-1", "project": "repo", "branch": "m",
                                                               "why": "질문 대기", "score": 90, "cwd": ROOT,
                                                               "sigs": [{"k": "ask"}]}]})
        out = ab.brief_attention(rows=[])
        # MCP output is English: why is rebuilt from the signal kinds, not the Korean screen label.
        self.assertEqual(out["rows"], [{"sid8": "aaaaaaaa", "project": "repo", "branch": "m", "why": "Asked a question",
                                        "score": 90}])


class TestRoutes(unittest.TestCase):
    def test_routes_registered(self):
        from tests._load import load
        r = load().Handler._GET_ROUTES
        for p in ("/api/agent/quota", "/api/agent/peers", "/api/agent/file", "/api/agent/attention"):
            self.assertIn(p, r)

    def test_quota_dir_resolves_account(self):
        rg = sidereus("routes_get")
        seen = []
        for name, val in (("claude_accounts", lambda: [{"label": "main", "dir": "/c/main", "primary": True},
                                                       {"label": "work", "dir": "/c/work", "primary": False}]),
                          ("brief_quota", lambda acct=None: seen.append(acct) or {"ok": True, "acct": acct})):
            old = getattr(rg, name)
            setattr(rg, name, val)
            self.addCleanup(setattr, rg, name, old)
        self.assertEqual(rg._agent_quota("/c/work")["acct"], "work")
        self.assertEqual(rg._agent_quota(""), {"ok": True, "acct": None})
        for bad in ("/c/nope", "/c/\x00work"):
            self.assertEqual(rg._agent_quota(bad), {"ok": False, "err": "unknown account"})
        self.assertEqual(seen, ["work", None])


if __name__ == "__main__":
    unittest.main()
