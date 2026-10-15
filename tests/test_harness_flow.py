"""Harness «흐름» (sidereus/harness_flow.py): tmp plmark dir, fixture rows; `HF_DIR`, `_diff`, `_now` patched — no git, no clock."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import load, sidereus

load()
HF = sidereus("harness_flow")
NOW = 1_800_000_000.0
KEYS = ["req", "guard", "edit", "gate", "review", "commit", "keep"]


def _row(ts, mode, rc, head="aaaa111", dirty=False):
    return {"kind": "check", "ts": ts, "mode": mode, "head": head, "dirty": dirty, "rc": rc,
            "steps": [{"name": "tests", "rc": rc, "n": 10, "failed": int(rc != 0), "secs": 1.0}]}


def _run(proj, t0, t1, end=0.0, st=None, lb=None):
    return {"proj": proj, "t0": t0, "t1": t1, "end": end, "cur": "", "cwd": "/secret/cwd", "loops": {"x": 1},
            "st": st if st is not None else {"구현": {"s": "done", "t0": t0, "t1": t1, "n": 1}}, "lb": lb or []}


class FlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hf-")
        self.plm = os.path.join(self.tmp, "plmark")
        self.repo = os.path.realpath(os.path.join(self.tmp, "repo"))
        os.makedirs(os.path.join(self.repo, ".git"))
        os.makedirs(os.path.join(self.repo, "sub"))
        os.makedirs(self.plm)
        self.calls = []
        self.old = (HF.HF_DIR, HF._diff, HF._now)
        HF.HF_DIR, HF._now = self.plm, (lambda: NOW)
        HF._diff = self._fake_diff
        HF._HF_CACHE.clear()

    def tearDown(self):
        HF.HF_DIR, HF._diff, HF._now = self.old
        HF._HF_CACHE.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fake_diff(self, repo, a, b):
        self.calls.append((repo, a, b))
        return [{"path": "src/a.py", "add": 3, "del": 1}], 1, 2

    def _write(self, sid, runs, mtime=NOW):
        fp = os.path.join(self.plm, sid + ".runs.json")
        with open(fp, "w") as f:
            f.write(runs if isinstance(runs, str) else json.dumps({"v": 1, "runs": runs}))
        os.utime(fp, (mtime, mtime))

    def _nodes(self, fl):
        return dict((n["k"], n) for n in fl["nodes"])

    def test_filter_by_proj_and_git_root(self):
        self._write("aaaaaaaa1111", {"mine": _run(self.repo, NOW - 900, NOW - 100), "other": _run("/elsewhere", NOW - 900, NOW - 50)})
        self._write("bbbbbbbb2222", {"sub-run": _run(os.path.join(self.repo, "sub"), NOW - 800, NOW - 90)})
        out = HF.flow(os.path.join(self.repo, "sub"), [], {})
        self.assertEqual([f["name"] for f in out], ["sub-run", "mine"])   # newest t1 first; root run kept for a subdir proj
        self.assertEqual(out[0]["src"], "plrun")
        self.assertEqual(sorted(out[0]), ["end", "floor", "id", "name", "nodes", "sid8", "src", "t0", "t1"])
        self.assertNotIn("secret", json.dumps(out))

    def test_window_edges_and_nodes(self):
        t0, end = NOW - 1000, NOW - 200
        st = {"설계": {"s": "skip", "t0": t0, "t1": t0, "n": 0}, "구현": {"s": "done", "t0": t0, "t1": end, "n": 2},
              "Review": {"s": "done", "t0": end - 50, "t1": end, "n": 1}}
        lb = [{"f": "Review", "g": "구현", "n": 2, "t": t0 + 10}]
        self._write("aaaaaaaa1111", {"chg": _run(self.repo, t0, end, end, st, lb)})
        rows = [_row(end + 61, "full", 0, "ffff999"),             # past +60
                _row(end + 60, "full", 0, "cccc333"),             # PASS on the edge
                _row(t0 + 100, "full", 1, "bbbb222", dirty=True),
                _row(t0 - 5, "fast", 0, "bbbb222"),               # on the -5 edge
                _row(t0 - 6, "full", 0, "aaaa111")]               # before: base head
        trail = {"held": [{"mode": "full", "head": "cccc333", "state": "broke", "ts": end + 60}]}
        n = self._nodes(HF.flow(self.repo, rows, trail)[0])
        self.assertEqual([x["k"] for x in HF.flow(self.repo, rows, trail)[0]["nodes"]], KEYS)
        for x in n.values():
            self.assertEqual(sorted(x), ["k", "rec", "st", "v", "why"])
            self.assertIn(x["st"], HF.HF_ST)
        self.assertEqual(n["gate"]["v"]["rows"], 3)
        self.assertTrue(n["gate"]["v"]["r2g"])
        self.assertEqual(n["gate"]["st"], "ok")
        self.assertIsNone(n["guard"]["v"]["deny"])
        self.assertEqual((n["guard"]["v"]["skip"], n["guard"]["v"]["loop"]), (1, 2))
        self.assertEqual(n["guard"]["rec"][0], {"k": "skip", "title": "설계"})
        self.assertEqual(n["review"]["v"], {"o": "done", "n": 1, "back": 2})
        self.assertEqual((n["edit"]["v"]["from"], n["edit"]["v"]["to"], n["edit"]["v"]["files"]), ("aaaa111", "cccc333", 1))
        self.assertEqual(self.calls, [(self.repo, "aaaa111", "cccc333")])
        self.assertEqual(n["commit"]["v"], {"head": "cccc333", "dirty": False})
        self.assertEqual((n["keep"]["st"], n["keep"]["v"]["state"]), ("ng", "broke"))
        self.assertEqual(n["req"]["st"], "ok")

    def test_no_review_no_keep_open_run(self):
        self._write("aaaaaaaa1111", {"chg": _run(self.repo, NOW - 500, NOW - 10)})
        n = self._nodes(HF.flow(self.repo, [_row(NOW - 100, "fast", 1)], {"held": []})[0])
        self.assertEqual((n["review"]["st"], n["review"]["v"]), ("none", None))
        self.assertIsNone(n["keep"]["v"])
        self.assertEqual((n["req"]["st"], n["gate"]["st"]), ("run", "ng"))
        self.assertFalse(n["gate"]["v"]["r2g"])
        self.assertIsNone(n["edit"]["v"]["files"])   # no base head before the window

    def test_guard_deny_count_and_log(self):
        r = _run(self.repo, NOW - 500, NOW - 10)
        r["deny"], r["dl"] = 3, [{"t": NOW - 300, "title": "검증", "c": "jump", "x": "secret"},
                                 {"t": NOW - 200, "title": "", "c": "evil<code>"},
                                 {"t": NOW - 100, "title": "구현", "c": "agent"}]
        z = _run(self.repo, NOW - 600, NOW - 20)
        z["deny"], z["dl"] = 0, []
        self._write("aaaaaaaa1111", {"chg": r, "zero": z, "old": _run(self.repo, NOW - 700, NOW - 30)})
        out = dict((f["name"], self._nodes(f)["guard"]) for f in HF.flow(self.repo, [], {}))
        g = out["chg"]
        self.assertEqual((g["st"], g["v"]["deny"]), ("ok", 3))
        self.assertEqual(g["rec"][:2], [{"k": "deny", "ts": NOW - 100, "code": "agent", "title": "구현"},
                                        {"k": "deny", "ts": NOW - 300, "code": "jump", "title": "검증"}])
        self.assertEqual((out["zero"]["st"], out["zero"]["v"]["deny"]), ("ok", 0))
        self.assertEqual((out["old"]["st"], out["old"]["v"]["deny"]), ("none", None))   # pre-field run: no count, never 0
        self.assertNotIn("secret", json.dumps(g))
        self.assertNotIn("evil", json.dumps(g))

    def test_evidence_fallback(self):
        rows = [_row(NOW - 100, "full", 0, "bbbb222"), _row(NOW - 3000, "full", 1, "bbbb222"), _row(NOW - 9000, "full", 0, "aaaa111")]
        out = HF.flow(self.repo, rows, {})
        self.assertEqual(len(out), 1)
        self.assertEqual((out[0]["src"], out[0]["id"]), ("evidence", "evidence"))
        n = self._nodes(out[0])
        self.assertEqual(n["gate"]["v"]["rows"], 2)
        self.assertTrue(n["gate"]["v"]["r2g"])
        self.assertIsNone(n["guard"]["v"])
        self.assertEqual(HF.flow(self.repo, [], {}), [])

    def test_cap_junk_and_stale(self):
        for i in range(8):
            self._write("cccccccc%04d" % i, {"r%d" % i: _run(self.repo, NOW - 900, NOW - 100 - i)})
        self._write("dddddddd0000", "{not json")
        self._write("eeeeeeee0000", {"old": _run(self.repo, NOW - HF.HF_KEEP_S - 900, NOW - HF.HF_KEEP_S - 1)})
        self._write("ffffffff0000", {"BAD NAME": _run(self.repo, NOW - 900, NOW - 1), "ok-run": "junk"})
        out = HF.flow(self.repo, [], {})
        self.assertEqual([f["name"] for f in out], ["r0", "r1", "r2", "r3", "r4", "r5"])

    def test_diff_budget_and_cache(self):
        runs = {}
        for i in range(5):
            runs["r%d" % i] = _run(self.repo, NOW - 1000 * (i + 1), NOW - 1000 * i - 500, NOW - 1000 * i - 500)
        self._write("aaaaaaaa1111", runs)
        rows = [_row(NOW - 1000 * i - 600, "full", 0, "%04x111" % (i + 1)) for i in range(6)]
        HF.flow(self.repo, rows, {})
        self.assertEqual(len(self.calls), HF.HF_DIFF_MAX)
        HF.flow(self.repo, rows, {})
        self.assertEqual(len(self.calls), HF.HF_DIFF_MAX + 2)   # cached three reused, the rest fetched

    def test_old_run_windows_past_newest_120_rows(self):
        t0, end = NOW - 90000, NOW - 89000
        self._write("aaaaaaaa1111", {"old": _run(self.repo, t0, end, end)})
        rows = [_row(NOW - 10 * i, "fast", 0, "eeee555") for i in range(300)] + \
               [_row(end - 10, "full", 0, "cccc333"), _row(t0 + 10, "full", 1, "bbbb222"), _row(t0 - 100, "full", 0, "aaaa111")]
        n = self._nodes(HF.flow(self.repo, rows, {})[0])
        self.assertEqual((n["gate"]["st"], n["gate"]["v"]["rows"], n["gate"]["v"]["r2g"]), ("ok", 2, True))
        self.assertEqual((n["edit"]["st"], n["edit"]["v"]["from"], n["edit"]["v"]["to"]), ("ok", "aaaa111", "cccc333"))

    def test_run_heads_and_commits_without_evidence(self):
        t0, end = NOW - 1000, NOW - 200
        r = _run(self.repo, t0, end, end)
        r["h0"], r["h1"] = "aaaa111", "dddd444"
        self._write("aaaaaaaa1111", {"chg": r})
        cms = [{"h": "ffff999", "ct": NOW - 10}, {"h": "cccc333", "ct": end + 30}, {"h": "bbbb222", "ct": t0 + 50}, {"h": "<x>", "ct": end}]
        n = self._nodes(HF.flow(self.repo, [], {}, commits=cms)[0])
        self.assertEqual((n["edit"]["st"], n["edit"]["v"]["from"], n["edit"]["v"]["to"]), ("ok", "aaaa111", "cccc333"))
        self.assertEqual((n["commit"]["st"], n["commit"]["v"], n["commit"]["why"]), ("ok", {"head": "cccc333", "dirty": None}, ""))
        n = self._nodes(HF.flow(self.repo, [], {})[0])   # no commit in the window: runs.json h1
        self.assertEqual((n["edit"]["v"]["to"], n["commit"]["v"]["head"]), ("dddd444", "dddd444"))
        r["h1"] = "aaaa111"   # nothing committed
        self._write("aaaaaaaa1111", {"chg": r})
        self.assertEqual(self._nodes(HF.flow(self.repo, [], {})[0])["commit"]["st"], "none")

    def test_bad_run_heads_dropped(self):
        r = _run(self.repo, NOW - 1000, NOW - 200, NOW - 200)
        r["h0"], r["h1"] = "zzzz;rm", "AAAA1111"
        self._write("aaaaaaaa1111", {"chg": r})
        n = self._nodes(HF.flow(self.repo, [], {})[0])
        self.assertEqual((n["edit"]["st"], n["edit"]["v"]["from"], n["edit"]["v"]["to"]), ("none", "", ""))
        self.assertEqual(n["edit"]["why"], "norec")
        self.assertEqual(self.calls, [])

    def test_why_values(self):
        t0 = NOW - 1000
        st = {"구현": {"s": "done", "t0": t0, "t1": t0, "n": 1}, "Review": {"s": "skip", "t0": t0, "t1": t0, "n": 0}}
        self._write("aaaaaaaa1111", {"open": _run(self.repo, t0, NOW - 10, 0.0, st)})
        why = lambda fl: dict((x["k"], x["why"]) for x in fl["nodes"])
        w = why(HF.flow(self.repo, [], {})[0])   # nothing recorded, whole file read
        self.assertEqual((w["gate"], w["edit"], w["commit"], w["keep"], w["review"], w["req"]), ("norec", "norec", "norec", "norec", "", ""))
        fl = HF.flow(self.repo, [], {}, floor=t0 + 100)[0]
        self.assertEqual((fl["floor"], why(fl)["gate"], why(fl)["edit"]), (t0 + 100, "window", "window"))
        w = why(HF.flow(self.repo, [_row(t0 - 3000, "full", 0, "aaaa111")], {}, floor=t0 - 4000)[0])
        self.assertEqual((w["gate"], w["commit"], w["edit"]), ("pending", "pending", ""))   # run still open
        w = why(HF.flow(self.repo, [_row(t0 + 10, "full", 0, "bbbb222", dirty=True)], {})[0])
        self.assertEqual((w["commit"], w["keep"], w["gate"]), ("pending", "pending", ""))   # dirty commit, keep before a clean one
        self._write("aaaaaaaa1111", {"noreview": _run(self.repo, t0, NOW - 10, NOW - 10)})
        row = _row(t0 + 10, "full", 0, "bbbb222")
        n = self._nodes(HF.flow(self.repo, [row], {"held": [{"mode": "full", "head": "bbbb222", "state": "unchecked"}]})[0])
        self.assertEqual((n["review"]["why"], n["keep"]["why"], n["commit"]["why"]), ("na", "pending", ""))
        shutil.rmtree(self.plm)
        os.makedirs(self.plm)
        w = why(HF.flow(self.repo, [row], {})[0])   # evidence-only flow
        self.assertEqual((w["guard"], w["review"], w["req"]), ("na", "na", "na"))


if __name__ == "__main__":
    unittest.main()
