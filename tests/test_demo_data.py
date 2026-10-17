"""sidereus/demo_data.py + demo.World: demo payloads keep the real builders' key sets and stay metadata-only.

★The page reads demo and real payloads with the same code, so a key the real builder emits but the demo lacks
  breaks the demo screen (and the README screenshots) silently. Real key sets come from the real builders
  (sessions._session_row, ext.ext_rows, work.session_work/agent_work) fed synthetic inputs — no live files.
tests/test_demo.py already covers route shapes, determinism across Worlds and the name denylist.
"""
import json
import os
import re
import shutil
import tempfile
import time
import unittest

from tests._load import sidereus

demo = sidereus("demo")
dd = sidereus("demo_data")
parse = sidereus("parse")
sessions = sidereus("sessions")
ext = sidereus("ext")
work = sidereus("work")

A = 1_790_000_000
SECRET = "SECRET-91c2 cat /w/private"
UUID4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


class _Patch(unittest.TestCase):
    def patch(self, mod, name, val):
        old = getattr(mod, name)
        setattr(mod, name, val)
        self.addCleanup(setattr, mod, name, old)

    def world(self, anchor=A):
        return demo.World(anchor=anchor, page_build="b", now=anchor)


def _real_session_row(t):
    cwd, t0 = "/w/repo-d", "2026-09-24T00:58:18.937Z"
    line = json.dumps({"type": "assistant", "sessionId": "s1", "cwd": cwd, "timestamp": t0, "message": {"content": [
        {"type": "tool_use", "id": "a1", "name": "Agent", "input": {"description": "d", "prompt": SECRET}}]}})
    t.patch(parse, "_tail_lines", lambda fp, nbytes=0, limit=0: [line])
    t.patch(parse, "_running_bg", lambda fp: ([], [], []))
    t.patch(parse, "_cwd_from_slug", lambda s: cwd)
    p = parse._parse_transcript("/x/-w-repo-d/s1.jsonl")
    for n, v in {"_ctx_window": lambda *a: (1000000, "obs"), "_otel_state": lambda sid: None,
                 "_bg_show": lambda *a: [], "_mon_rows": lambda *a: [], "_bg_age": lambda *a: 0,
                 "session_repos": lambda *a: [], "_wt_of": lambda *a: None, "mbox_of": lambda *a: ("", ""),
                 "_projcost_of": lambda *a: 0.0, "_git_state": lambda *a: "", "_model_win": lambda *a: (0, 0),
                 "_dead": lambda *a: False}.items():
        t.patch(sessions, n, v)
    now = time.time()
    return sessions._session_row("/nonexistent/s1.jsonl", now - 30, now, {cwd: 1}, p)


class SameKeysAsRealBuilders(_Patch):
    def test_claude_rows_match_session_row(self):
        real = set(_real_session_row(self))
        rows = [r for r in self.world().state()["sessions"] if r["plat"] == "cc"]
        self.assertEqual(len(rows), 6)
        for r in rows:
            # `team` only on a leader row (sessions._row_children); `term` is set later by term.term_attach in state()
            # `plrun` too: the real _session_row adds it only when the session has pipeline runs
            # `acct`/`acctDir`: only on a row from a non-primary Claude root (sessions._row_acct)
            self.assertEqual(set(r) - {"team", "term", "plrun", "acct", "acctDir"}, real, r["id"])

    def test_gemini_row_matches_ext_rows(self):
        now = time.time()
        reg = {("gemini", "g-sid-1"): {"cwd": "/w/g", "state": "wait", "firstSeen": now - 60, "lastSeen": now}}
        self.patch(ext, "_ext", reg)
        for n, v in {"ext_gone_check": lambda now: None, "_ext_prune_locked": lambda now: None,
                     "ext_tok_refresh": lambda *a: None, "ext_tok": lambda *a: {}}.items():
            self.patch(ext, n, v)
        (real,) = ext.ext_rows()
        # goneWhy: set only by ext_rows (the page treats a missing value as ""), not carried by the fixture.
        self.assertEqual(set(dd.GEM_ROW), set(real) - {"goneWhy"})
        self.assertEqual(set(dd.GEM_ROW["tokSplit"]), set(real["tokSplit"]))
        self.assertEqual(set(dd.GEM_ROW["runmin"]), set(real["runmin"]))

    def _work_env(self):
        d = tempfile.mkdtemp(prefix="sidereus-demo-work-")
        self.addCleanup(shutil.rmtree, d, True)
        fp = os.path.join(d, "s.jsonl")
        open(fp, "w", encoding="utf-8").close()
        scan = ([{"t": "2026-09-24T00:00:00", "tool": "Read", "targ": "a", "arg": "", "id": "i"}],
                [{"t": "2026-09-24T00:00:00", "text": "x"}], {}, "p", "f", "l", "u")
        self.patch(work, "_allowed_cwds", lambda: {"/w/r": {"project": "r"}})
        self.patch(work, "_past_row", lambda *a: None)
        self.patch(work, "_sid_path", lambda cwd, sid: fp)
        self.patch(work, "_open_or_tail", lambda *a, **k: [])
        self.patch(work, "_work_scan", lambda rows, cwd: (scan, ""))
        self.patch(work, "CLAUDE_PROJECTS", d)
        self.patch(work, "_slug", lambda cwd: "")
        self.patch(work, "_agent_meta", lambda base, ttl=0: {"t1": {"_file": fp, "agentType": "x", "description": "y"}})

    def test_session_work_keys(self):
        self._work_env()
        real = work.session_work("/w/r", "s-1")
        self.assertTrue(real["ok"], real)
        w = self.world()
        mine = w.session_work(w.sess[0]["sid"])
        self.assertEqual(set(mine), set(real))
        self.assertEqual(set(mine["steps"][0]), set(real["steps"][0]) - {"res"})

    def test_agent_work_keys(self):
        self._work_env()
        real = work.agent_work("/w/r", "t1")
        self.assertTrue(real["ok"], real)
        w = self.world()
        mine = w.agent_work(w.subs[0]["tid"])
        self.assertEqual(set(mine), set(real))


    def test_plrun_stack_keys(self):
        # Stacked demo runs (2 open + 1 ended) keep pl_model's row/stage/agent key sets.
        (row,) = [r for r in self.world().state()["sessions"] if r.get("plrun")]
        pl = row["plrun"]
        self.assertEqual([(r["name"], bool(r["end"])) for r in pl],
                         [("change-flow", False), ("hotfix", False), ("release-check", True)])
        self.assertEqual([r["t1"] for r in pl], sorted((r["t1"] for r in pl), reverse=True))   # newest first
        for r in pl:
            self.assertEqual(set(r), {"name", "proj", "sid", "cur", "end", "t0", "t1", "stages"})
            for s in r["stages"].values():
                self.assertLessEqual(set(s), {"o", "n", "t0", "t1", "from", "p0", "k", "ag", "ps", "cm"})
                cm = s.get("cm", [])   # commit stamps: epoch numbers only
                self.assertTrue(isinstance(cm, list) and len(cm) <= 4 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in cm), cm)
                for a in s["ag"]:
                    self.assertEqual(set(a), {"aid", "tid", "lab", "run", "t0", "t1"})


class MetadataOnly(_Patch):
    def test_session_rows_carry_no_body(self):
        st = self.world().state()
        for r in st["sessions"]:
            self.assertNotIn("reply", r)
            self.assertNotIn("task", r)
            if r["plat"] == "cc" and r["tool"] not in ("Agent", "Task"):
                self.assertEqual(r["targ"], "", r["id"])       # e.g. the Bash command of «cart» is dropped
        blob = json.dumps(st["sessions"], ensure_ascii=False)
        self.assertNotIn("npm test -- cart", blob)

    def test_ask_abort_cards_have_no_text(self):
        for c in self.world().cards():
            if c["kind"] in ("ask", "abort"):
                self.assertEqual(c["text"], "")

    def test_no_body_keys_outside_work_popups(self):
        """reply/task/prompt/says/arg/command/input may appear only in the work popups (rule 1 exception)."""
        from tests.test_demo import all_responses
        bad = {"reply", "task", "prompt", "says", "arg", "command", "input", "old_string"}
        hits = []

        def walk(x, path):
            if isinstance(x, dict):
                hits.extend((path, k) for k in x if k in bad)
                for v in x.values():
                    walk(v, path)
            elif isinstance(x, list):
                for v in x:
                    walk(v, path)
        w = self.world()
        for path, (_c, out) in all_responses(demo, w):
            if not path.startswith(("/api/session/work", "/api/agent/work")):
                walk(out, path)
        self.assertEqual(hits, [])


class SyntheticAndDeterministic(_Patch):
    def test_ids_follow_seed_not_anchor(self):
        w1, w2 = self.world(A), self.world(A + 86400)
        self.assertEqual([s["sid"] for s in w1.sess], [s["sid"] for s in w2.sess])
        self.assertEqual([s["tid"] for s in w1.subs], [s["tid"] for s in w2.subs])
        for s in w1.sess:
            self.assertRegex(s["sid"], UUID4)
            self.assertEqual(s["id"], s["sid"][:8])
        self.assertEqual(len({s["sid"] for s in w1.sess}), len(w1.sess))

    def test_wall_clock_does_not_leak_when_pinned(self):
        a = json.dumps(self.world().state(), sort_keys=True)
        real = time.time
        self.patch(time, "time", lambda: real() + 12345)
        b = json.dumps(self.world().state(), sort_keys=True)
        self.assertEqual(a, b)

    def test_anchor_shifts_times_only(self):
        s1 = self.world(A).quota_burn()["cur"]
        s2 = self.world(A + 600).quota_burn()["cur"]
        self.assertEqual(s2["start"] - s1["start"], 600)
        self.assertEqual(s1["now_pct"], s2["now_pct"])

    def test_paths_are_under_demo_root(self):
        self.assertTrue(dd.ROOT.startswith("/home/demo/"))
        st = self.world().state()
        cwds = [r["cwd"] for r in st["sessions"]] + [r["cwd"] for r in st["attention"]["rows"]] \
            + [c["cwd"] for c in st["cards"]]
        for main, wts in dd.REPOS.values():
            cwds += [main] + [p for p, _ in wts]
        for c in cwds:
            self.assertTrue(c.startswith(dd.ROOT + "/"), c)

    def test_fixture_ids_are_well_formed(self):
        for row in (dd.GEM_ROW, dd.CX):
            self.assertRegex(row["sid"], UUID4)
            self.assertEqual(row["id"], row["sid"][:8])
        self.assertRegex(dd.GEM_CHILD["sid"], UUID4)
        self.assertEqual(dd.CX["tok"], sum(dd.CX["tokSplit"].values()))
        self.assertEqual(dd.GEM_ROW["tok"], sum(dd.GEM_ROW["tokSplit"].values()))

    def test_retro_sigs_count_desc(self):
        # the page renders sigs in payload order; real retro sorts (-n, -last) and the demo must match
        s = self.world().retro()["sigs"]
        self.assertEqual([(x["n"], x["last"]) for x in s], sorted(((x["n"], x["last"]) for x in s), reverse=True))

    def test_retro_honours_days_and_ships_rank(self):
        for days in (7, 30):
            r = self.world().retro(days)
            self.assertEqual((r["days"], len(r["daily"])), (days, days))
            self.assertEqual(len({x["d"] for x in r["daily"]}), days)
            k = r["rank"]
            self.assertTrue(k["calls"] > 0 and k["top"])
            self.assertEqual((k["restN"], k["from"]), (len(k["rest"]), r["daily"][0]["d"]))

    def test_retro_account_split_sums_to_all(self):
        w = self.world()
        a, p, k = w.retro(7), w.retro(7, "personal"), w.retro(7, "work")
        self.assertNotIn("acct", a)
        self.assertEqual(w.retro(7, "zzz"), a)
        self.assertEqual((p["acct"], k["acct"], p["acctSince"]), ("personal", "work", a["daily"][2]["d"]))
        self.assertEqual({x for x in a if a[x] != p[x]}, {"rank", "time", "cache", "heat", "models", "hooks"})
        self.assertEqual(p["rank"]["calls"] + k["rank"]["calls"], a["rank"]["calls"])
        self.assertEqual(p["heat"]["n"] + k["heat"]["n"], a["heat"]["n"])
        self.assertEqual(p["models"]["n"] + k["models"]["n"], a["models"]["n"])
        self.assertEqual(p["hooks"]["n"] + k["hooks"]["n"], a["hooks"]["n"])
        self.assertEqual([x["create"] + y["create"] for x, y in zip(p["cache"]["days"], k["cache"]["days"])],
                         [x["create"] for x in a["cache"]["days"]])

    def test_wkuse_account_split_sums_to_all(self):
        w = self.world()
        a, p, k = w.wkuse(7), w.wkuse(7, "personal"), w.wkuse(7, "work")
        self.assertEqual((a["acct"], p["acct"], k["acct"], w.wkuse(7, "zzz")["acct"]), ("", "personal", "work", ""))
        self.assertEqual(p["total"] + k["total"], a["total"])
        self.assertEqual([x + y for x, y in zip((d["tok"] for d in p["daily"]), (d["tok"] for d in k["daily"]))],
                         [d["tok"] for d in a["daily"]])
        self.assertEqual({r["name"] for r in k["rows"]}, {"docs-site", "billing-api"})
        self.assertEqual((p["liveAdd"], k["liveAdd"]), (0, 0))
        self.assertTrue(a["liveAdd"] > 0)

    def test_history_cc_rows_carry_acct(self):
        rows = [r for d in self.world().history(7)["list"] for r in d["rows"]]
        self.assertTrue(rows and all(r["plat"] == "cc" for r in rows))
        self.assertEqual({r.get("acct", "") for r in rows}, {"", "work"})


if __name__ == "__main__":
    unittest.main()
