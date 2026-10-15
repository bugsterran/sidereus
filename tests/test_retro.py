"""Deterministic tests for sidereus/retro.py — the day/week/project fold and the cached endpoint.

No live files, clock or git: `_retro_build` takes `now` and its inputs directly, and `retro()` is run
with history/_fail_events/_retro_commits/_otel_tools_summary/time replaced on the retro module.
"""
import time
import unittest
from unittest import mock

from tests._load import sidereus

R = sidereus("retro")


def _ts(d, h=12):
    return time.mktime(time.strptime("%s %02d" % (d, h), "%Y-%m-%d %H"))


NOW = _ts("2026-09-23", 15)           # a Wednesday; week starts Mon 09-21


def _hist(rows):
    by = {}
    for r in rows:
        by.setdefault(r["date"], []).append(r)
    return {"ok": True, "list": [{"date": d, "rows": rs} for d, rs in sorted(by.items(), reverse=True)]}


def _row(date, sid, project, tok, cost=0.0, cwd=""):
    return {"date": date, "sid": sid, "project": project, "tok": tok, "cost": cost, "cwd": cwd}


HIST = _hist([
    _row("2026-09-23", "s1", "alpha", 1000, 1.0, "/w/alpha"),
    _row("2026-09-22", "s1", "alpha", 500, 0.5, "/w/alpha"),
    _row("2026-09-20", "s2", "beta", 3000, 2.0, "/w/beta"),
    _row("2026-09-10", "s9", "old", 99999),          # outside a 7-day window
])
EVS = [
    {"at": _ts("2026-09-23", 9), "kind": "tool", "grade": "noise", "sig": "Exit code 1"},
    {"at": _ts("2026-09-23", 10), "kind": "tool", "grade": "noise", "sig": "Exit code 1"},
    {"at": _ts("2026-09-21", 10), "kind": "agent", "grade": "cut", "sig": "watchdog"},
    {"at": _ts("2026-09-01", 10), "kind": "api", "grade": "cut", "sig": "529"},   # outside
]
COMMITS = {
    "alpha": [("a1", _ts("2026-09-23")), ("a2", _ts("2026-09-22")), ("a0", _ts("2026-09-01"))],
    "beta": [("a1", _ts("2026-09-23"))],             # same sha reached from two projects
    "gamma": None,                                   # not a git repo
}
TOOLS = {"rows": [["Bash", 50, 5], ["Read", 40, 0], ["Edit", 10, 1]], "since": 123}
RANK = {"top": [{"n": "Bash", "calls": 9, "ok": 100.0, "ms": 12, "tms": 108, "fms": 0}], "rest": [], "restN": 0,
        "calls": 9, "from": "2026-09-20",
        "time": {"rows": [{"n": "Bash", "calls": 9, "ok": 100.0, "ms": 12, "tms": 108, "fms": 0}], "restN": 0}}
CACHE = {"days": [{"d": "2026-09-22", "read": 90, "create": 10, "pct": 10}],
         "sessions": [{"sid": "s2", "read": 5, "create": 5, "pct": 50},
                      {"sid": "0123456789abcdef", "read": 9, "create": 1, "pct": 10}]}

HEAT = {"from": 1, "since": 1, "n": 1, "cells": [[[0, 0]] * 24] * 7}
MODELS = {"from": 1, "since": 1, "n": 1, "rows": [{"model": "m", "count": 1, "tokens": 2, "kinds": {}}]}
HOOKS = {"rows": [{"ev": "Stop", "count": 2, "ms": 30, "avg": 15, "fail": 1}], "n": 2, "from": "2026-09-17"}

class BuildTests(unittest.TestCase):
    def setUp(self):
        self.o = R._retro_build(7, NOW, HIST, EVS, COMMITS, TOOLS)

    def test_daily_covers_exactly_the_window(self):
        ds = [x["d"] for x in self.o["daily"]]
        self.assertEqual(ds[0], "2026-09-17")
        self.assertEqual(ds[-1], "2026-09-23")
        self.assertEqual(len(ds), 7)

    def test_failures_counted_by_day_and_kind_inside_window_only(self):
        o = self.o
        self.assertEqual(o["fails"], 3)
        self.assertEqual(o["kinds"], {"tool": 2, "agent": 1})
        self.assertEqual(o["grades"], {"noise": 2, "cut": 1})
        last = o["daily"][-1]
        self.assertEqual((last["fails"], last["kinds"]), (2, {"tool": 2}))
        self.assertEqual(o["sigs"][0]["sig"], "도구 오류")   # fixed label; raw sig stays server-side (rule 1)
        self.assertEqual(o["sigs"][0]["n"], 2)

    def test_weeks_split_on_monday_with_totals(self):
        w = {x["week"]: x for x in self.o["weeks"]}
        self.assertEqual(sorted(w), ["2026-09-14", "2026-09-21"])
        cur = w["2026-09-21"]
        self.assertEqual((cur["from"], cur["to"], cur["days"]), ("2026-09-21", "2026-09-23", 3))
        self.assertEqual((cur["tok"], cur["sessions"], cur["fails"]), (1500, 1, 3))
        self.assertEqual(cur["commits"], 2)          # a1 once (deduped across projects) + a2
        self.assertEqual(cur["top"], [{"project": "alpha", "tok": 1500}])
        prev = w["2026-09-14"]
        self.assertEqual((prev["days"], prev["tok"], prev["commits"]), (4, 3000, 0))
        self.assertEqual(self.o["weeks"][0]["week"], "2026-09-21")   # newest first

    def test_tokens_per_commit_per_project(self):
        p = {x["project"]: x for x in self.o["projects"]}
        self.assertNotIn("old", p)
        self.assertEqual((p["alpha"]["commits"], p["alpha"]["tpc"]), (2, 750))
        self.assertEqual((p["beta"]["commits"], p["beta"]["tpc"]), (1, 3000))
        self.assertEqual(self.o["projects"][0]["project"], "beta")   # sorted by tokens

    def test_project_without_repo_has_no_ratio(self):
        o = R._retro_build(7, NOW, _hist([_row("2026-09-23", "s", "gamma", 10)]), [], COMMITS, {})
        g = o["projects"][0]
        self.assertEqual((g["commits"], g["tpc"]), (None, None))

    def test_tools_keep_only_failing_rows(self):
        self.assertEqual([r[0] for r in self.o["tools"]["rows"]], ["Bash", "Edit"])
        self.assertEqual(self.o["tools"]["since"], 123)


class WhereTests(unittest.TestCase):
    """Failure drill-down: sessions per signature, metadata only (AGENTS.md rule 1)."""
    SECRET = "rm -rf /secret/output"

    def _evs(self):
        b = {"kind": "tool", "tool": "Bash", "grade": "noise", "text": self.SECRET, "sig": "Exit code 1 " + self.SECRET}
        return [dict(b, at=_ts("2026-09-23", 9), sid="s1", cwd="/w/alpha", proj="alpha"),
                dict(b, at=_ts("2026-09-23", 10), sid="s1", cwd="/w/alpha", proj="alpha"),
                dict(b, at=_ts("2026-09-22", 10), sid="s2", cwd="/w/beta", proj="beta", grade="check"),
                dict(b, at=_ts("2026-09-22", 11), sid="", cwd="", proj="")]

    def test_where_groups_by_session_newest_count_first(self):
        s = R._retro_build(7, NOW, {"list": []}, self._evs(), {}, {})["sigs"][0]
        self.assertEqual((s["n"], s["chk"], s["wn"]), (4, 1, 2))
        self.assertEqual([(w["sid"], w["project"], w["n"]) for w in s["where"]], [("s1", "alpha", 2), ("s2", "beta", 1)])
        self.assertEqual(s["where"][0]["last"], int(_ts("2026-09-23", 10)))

    def test_where_carries_only_metadata_keys(self):
        o = R._retro_build(7, NOW, {"list": []}, self._evs(), {}, {})
        for s in o["sigs"]:
            self.assertNotIn("_w", s)
            for w in s["where"]:
                self.assertEqual(set(w), {"sid", "cwd", "project", "n", "last"})
        blob = repr(o)
        self.assertNotIn(self.SECRET, blob)
        self.assertNotIn("'text'", blob)
        self.assertNotIn("'output'", blob)

    def test_sigs_count_desc_newest_first_on_ties(self):
        ev = lambda sg, h: {"at": _ts("2026-09-23", h), "kind": "api", "grade": "noise", "sig": sg, "sid": "s"}  # noqa: E731
        evs = [ev("a", 9)] + [ev("b", 9)] * 3 + [ev("c", 11)] + [ev("d", 10)] * 2
        sigs = R._retro_build(7, NOW, {"list": []}, evs, {}, {})["sigs"]
        self.assertEqual([(x["sig"], x["n"]) for x in sigs], [("b", 3), ("d", 2), ("c", 1), ("a", 1)])

    def test_check_sigs_kept_beyond_top_eight(self):
        evs = [{"at": _ts("2026-09-23", 9), "kind": "api", "grade": "noise", "sig": "e%d" % i, "sid": "s"}
               for i in range(9) for _ in range(3)]
        evs.append({"at": _ts("2026-09-23", 9), "kind": "api", "grade": "check", "sig": "rare", "sid": "s"})
        sigs = R._retro_build(7, NOW, {"list": []}, evs, {}, {})["sigs"]
        self.assertEqual(len(sigs), 9)
        self.assertEqual((sigs[-1]["sig"], sigs[-1]["chk"]), ("rare", 1))


class CacheJoinTests(unittest.TestCase):
    def test_r3_sessions_joined_to_history_metadata_only(self):
        o = R._retro_build(7, NOW, HIST, EVS, COMMITS, TOOLS, RANK, CACHE)
        ss = o["cache"]["sessions"]
        self.assertEqual(ss[0], {"sid": "s2", "read": 5, "create": 5, "pct": 50, "path": "/w/beta", "project": "beta"})
        self.assertEqual(ss[1], {"sid": "01234567", "read": 9, "create": 1, "pct": 10})   # unmatched: 8-char sid only

    def test_r4_empty_cache_and_time(self):
        o = R._retro_build(7, NOW, HIST, EVS, COMMITS, TOOLS)
        self.assertEqual(o["cache"], {"days": [], "sessions": []})
        self.assertIsNone(o["time"])
        self.assertIsNone(o["heat"])                                     # R3: no heat stays None
        self.assertIsNone(o["models"])                                   # R3: no models stays None

    def test_r1_heat_passthrough(self):
        o = R._retro_build(7, NOW, HIST, EVS, COMMITS, TOOLS, RANK, CACHE, HEAT)
        self.assertIs(o["heat"], HEAT)

    def test_r1_models_passthrough(self):
        o = R._retro_build(7, NOW, HIST, EVS, COMMITS, TOOLS, RANK, CACHE, HEAT, MODELS)
        self.assertIs(o["models"], MODELS)

    def test_r2_hooks_passthrough_and_r3_default_none(self):
        o = R._retro_build(7, NOW, HIST, EVS, COMMITS, TOOLS, RANK, CACHE, HEAT, MODELS, HOOKS)
        self.assertIs(o["hooks"], HOOKS)
        self.assertIsNone(R._retro_build(7, NOW, HIST, EVS, COMMITS, TOOLS)["hooks"])


class EndpointTests(unittest.TestCase):
    def setUp(self):
        R._retro_cache.clear()

    def tearDown(self):
        R._retro_cache.clear()

    def _run(self, days, clock):
        with mock.patch.object(R, "history", return_value=HIST) as h, \
             mock.patch.object(R, "_fail_events", return_value=(EVS, 3, 168)) as f, \
             mock.patch.object(R, "_retro_commits", return_value=COMMITS), \
             mock.patch.object(R, "_otel_tools_summary", return_value=TOOLS), \
             mock.patch.object(R, "_otel_tool_rank", return_value=RANK) as self.rk, \
             mock.patch.object(R, "_oc_view", return_value=CACHE) as self.ov, \
             mock.patch.object(R, "_otel_src_heat", return_value=HEAT) as self.hv, \
             mock.patch.object(R, "_otel_src_models", return_value=MODELS) as self.mv, \
             mock.patch.object(R, "_oh_view", return_value=HOOKS) as self.hk, \
             mock.patch.object(R.time, "time", side_effect=clock):
            return R.retro(days), h, f

    def test_rank_passthrough_from_first_day(self):
        t = iter([NOW] * 20)
        o, _h, _f = self._run(7, lambda: next(t))
        self.assertIs(o["rank"], RANK)
        self.rk.assert_called_once_with("2026-09-17")

    def test_r1_r3_time_and_cache_use_rank_since(self):
        t = iter([NOW] * 20)
        o, _h, _f = self._run(7, lambda: next(t))
        self.assertIs(o["time"], RANK["time"])
        self.ov.assert_called_once_with("2026-09-17")
        self.assertEqual(o["cache"]["days"], CACHE["days"])

    def test_r1_heat_uses_range_start(self):
        t = iter([NOW] * 20)
        o, _h, _f = self._run(7, lambda: next(t))
        self.assertIs(o["heat"], HEAT)
        self.hv.assert_called_once_with(_ts("2026-09-17", 0), NOW)
        self.assertIs(o["models"], MODELS)                               # R1 models: same range start
        self.mv.assert_called_once_with(_ts("2026-09-17", 0), NOW)
        self.assertIs(o["hooks"], HOOKS)                                 # R2 hooks: same range start
        self.hk.assert_called_once_with("2026-09-17")

    def test_unknown_range_falls_back_and_result_is_cached(self):
        t = iter([NOW] * 20)
        o, h, f = self._run("999", lambda: next(t))
        self.assertEqual(o["days"], 7)
        h.assert_called_once_with(7)
        t2 = iter([NOW + 60] * 20)
        o2, h2, _ = self._run(7, lambda: next(t2))
        self.assertIs(o2, o)
        h2.assert_not_called()

    def test_cache_expires_after_ttl(self):
        t = iter([NOW] * 20)
        self._run(30, lambda: next(t))
        t2 = iter([NOW + R.RETRO_TTL_S + 1] * 20)
        _o, h2, _f = self._run(30, lambda: next(t2))
        h2.assert_called_once_with(30)

    def test_failure_window_reaches_back_to_first_day_midnight(self):
        t = iter([NOW] * 20)
        _o, _h, f = self._run(7, lambda: next(t))
        hours = f.call_args[0][0]
        start = NOW - hours * 3600
        self.assertLessEqual(start, _ts("2026-09-17", 0))


class FailScanCapTests(unittest.TestCase):
    """retro asks for every file in the window; the failures tab keeps its count caps."""
    F = sidereus("failures_scan")

    def _files(self, capped):
        F = self.F
        main = [(NOW - i, "/p/m%d.jsonl" % i) for i in range(5)]
        subs = ["/p/s/subagents/agent-%d.jsonl" % i for i in range(7)]
        mt = {fp: NOW - 10 - i for i, fp in enumerate(subs)}
        with mock.patch.object(F, "FAIL_MAX_FILES", 2), mock.patch.object(F, "FAIL_SUB_MAX_FILES", 3), \
             mock.patch.object(F, "_recent_transcripts", return_value=main), \
             mock.patch.object(F.glob, "glob", return_value=subs), \
             mock.patch.object(F.os.path, "getmtime", side_effect=lambda fp: mt[fp]):
            return F._fail_transcripts(NOW, 720, capped)

    def test_capped_by_default(self):
        self.assertEqual(len(self._files(True)), 2 + 3)

    def test_uncapped_takes_every_file_in_window(self):
        self.assertEqual(len(self._files(False)), 5 + 7)

    def test_retro_requests_uncapped_scan(self):
        R._retro_cache.clear()
        try:
            with mock.patch.object(R, "history", return_value=HIST), \
                 mock.patch.object(R, "_fail_events", return_value=(EVS, 3, 720)) as f, \
                 mock.patch.object(R, "_retro_commits", return_value={}), \
                 mock.patch.object(R, "_otel_tools_summary", return_value={}), \
                 mock.patch.object(R, "_otel_tool_rank", return_value=None), \
                 mock.patch.object(R, "_oc_view", return_value={}), \
                 mock.patch.object(R.time, "time", return_value=NOW):
                R.retro(30)
            self.assertIs(f.call_args[1].get("capped"), False)
        finally:
            R._retro_cache.clear()


class CommitSourceTests(unittest.TestCase):
    def test_one_git_call_per_project_from_shortest_cwd(self):
        hist = _hist([_row("2026-09-23", "s1", "alpha", 1, cwd="/w/alpha/.claude/worktrees/agent-x"),
                      _row("2026-09-22", "s2", "alpha", 1, cwd="/w/alpha"),
                      _row("2026-09-22", "s3", "nogit", 1, cwd="/w/nogit")])
        calls = []
        with mock.patch.object(R.os.path, "isdir", return_value=True), \
             mock.patch.object(R, "_git_root", side_effect=lambda c: "" if "nogit" in c else c), \
             mock.patch.object(R, "_retro_git", side_effect=lambda c, s: calls.append(c) or []):
            out = R._retro_commits(hist, 0)
        self.assertEqual(calls, ["/w/alpha"])
        self.assertEqual(out, {"alpha": [], "nogit": None})


if __name__ == "__main__":
    unittest.main()
