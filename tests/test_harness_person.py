"""Harness «Found by a person first» (sidereus/harness_person.py): catch=person pipelines, run windows, tests/ filter,
git budget and cache. Temp project + ledger dir; `_git`, `_now` and `pl_outcome.OC_EVAL_DIR` are patched."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import load, sidereus

load()
HPS = sidereus("harness_person")
OC = sidereus("pl_outcome")


def _w(p, body):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(body if isinstance(body, str) else json.dumps(body))


def _log_text(rows):
    return "".join("\x1e%s\x1f%d\n%s\n" % (sha, ct, "\n".join(files)) for sha, ct, files in rows)


class HarnessPersonTest(unittest.TestCase):
    def setUp(self):
        t = self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-hps-"))
        self.proj = os.path.join(t, "proj")
        pd = os.path.join(self.proj, ".claude", "pipelines")
        _w(os.path.join(pd, "fix-a.json"), {"v": 1, "name": "fix-a", "catch": "person"})
        _w(os.path.join(pd, "fix-b.json"), {"v": 1, "name": "fix-b", "catch": "person"})
        _w(os.path.join(pd, "change.json"), {"v": 1, "name": "change"})
        _w(os.path.join(pd, "odd.json"), {"v": 1, "name": "odd", "catch": "gate"})
        _w(os.path.join(pd, "broken.json"), "{not json")
        self.saved = [(HPS, "_git", HPS._git), (HPS, "_now", HPS._now), (OC, "OC_EVAL_DIR", OC.OC_EVAL_DIR)]
        OC.OC_EVAL_DIR = os.path.join(t, "eval")
        HPS._now = lambda: 10000.0
        self.calls, self.log = [], []
        HPS._git = self._git
        HPS._PS_CACHE.clear()

    def tearDown(self):
        for mod, k, v in self.saved:
            setattr(mod, k, v)
        HPS._PS_CACHE.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _git(self, repo, args):
        self.calls.append(args[0])
        if args[0] == "rev-parse":
            return 0, "abcdef1234567890\n"
        return 0, _log_text(self.log)

    def _ledger(self, rows):
        _w(os.path.join(OC.OC_EVAL_DIR, OC.repo_key(self.proj), "runs.jsonl"), "\n".join(json.dumps(r) for r in rows) + "\n")

    def test_r1_counts_only_catch_person(self):
        self._ledger([{"name": "fix-a", "t0": 100, "end": 200}, {"name": "change", "t0": 300, "end": 400},
                      {"name": "odd", "t0": 500, "end": 600}, {"name": "fix-b", "t0": 700, "end": 800}])
        p = HPS.person(self.proj)
        self.assertEqual((p["pipes"], p["runs"]), (["fix-a", "fix-b"], 2))
        self.assertEqual([c["name"] for c in p["cards"]], ["fix-b", "fix-a"])   # newest first

    def test_r1_missing_or_invalid_is_zero(self):
        self.assertEqual(HPS.person(self.proj)["runs"], 0)   # no ledger
        self.assertEqual(HPS.person(os.path.join(self.tmp, "nope"))["runs"], 0)
        self.assertEqual(HPS.person("")["runs"], 0)
        self.assertEqual(self.calls, [])

    def test_r4_window_grace_next_run_cap(self):
        runs = [{"name": "fix-a", "t0": 1000, "end": 2000}, {"name": "change", "t0": 2500, "end": 4000},
                {"name": "fix-b", "t0": 5000, "end": 6000}]
        log = [("c" * 40, 6000 + HPS.PS_GRACE_S + 1, ["tests/test_late.py"]),   # past grace
               ("b" * 40, 6000 + HPS.PS_GRACE_S, ["tests/test_b.py", "tests/test_b.py"]),
               ("9" * 40, 2600, ["tests/test_next.py"]),                       # after the next run started
               ("a" * 40, 2400, ["tests/test_a.py"]), ("8" * 40, 999, ["tests/test_early.py"])]
        p = HPS.shape(runs, log, ["fix-a", "fix-b"])
        fb, fa = p["cards"]
        self.assertEqual((fb["commits"], fb["tests"]), (["b" * 12], ["tests/test_b.py"]))
        self.assertEqual((fa["commits"], fa["tests"]), (["a" * 12], ["tests/test_a.py"]))
        self.assertEqual((p["runs"], p["git"]), (2, True))

    def test_r4_overlapping_row_does_not_cap(self):
        runs = [{"name": "fix-a", "t0": 1000, "end": 3000}, {"name": "change", "t0": 1500, "end": 1600},   # another session
                {"name": "change", "t0": 3200, "end": 3500}]
        log = [("c" * 40, 3300, ["tests/test_next.py"]), ("b" * 40, 2500, ["tests/test_mine.py"])]
        c = HPS.shape(runs, log, ["fix-a"])["cards"][0]
        self.assertEqual((c["commits"], c["tests"]), (["b" * 12], ["tests/test_mine.py"]))

    def test_r4_truncated_log_is_unknown(self):
        runs = [{"name": "fix-a", "t0": 100, "end": 200}, {"name": "fix-a", "t0": 10000, "end": 10100}]
        log = [("%040x" % (k + 1), 10050 - k, ["tests/t.py"]) for k in range(HPS.PS_LOG_MAX)]
        new, old = HPS.shape(runs, log, ["fix-a"])["cards"]
        self.assertEqual((old["commits"], old["tests"]), (None, []))   # older than the oldest commit read
        self.assertEqual(len(new["commits"]), HPS.PS_COMMITS_MAX)
        short = HPS.shape(runs, log[:-1], ["fix-a"])["cards"][1]
        self.assertEqual(short["commits"], [])

    def test_r4_no_commit_vs_git_miss(self):
        runs = [{"name": "fix-a", "t0": 1000, "end": 2000}]
        self.assertEqual(HPS.shape(runs, [], ["fix-a"])["cards"][0]["commits"], [])
        miss = HPS.shape(runs, None, ["fix-a"])
        self.assertEqual((miss["cards"][0]["commits"], miss["git"]), (None, False))

    def test_r4_tests_filter_and_caps(self):
        runs = [{"name": "fix-a", "t0": i * 10, "end": i * 10 + 5} for i in range(30)]
        log = [("%040x" % (k + 1), 295, ["src/secret_name.py", "tests/t%d.py" % k, "docs/tests/x.md"]) for k in range(12)]
        p = HPS.shape(runs, log, ["fix-a"])
        self.assertEqual((p["runs"], len(p["cards"])), (30, HPS.PS_CARD_MAX))
        c = p["cards"][0]
        self.assertEqual((len(c["commits"]), len(c["tests"])), (HPS.PS_COMMITS_MAX, HPS.PS_TESTS_MAX))
        self.assertTrue(all(t.startswith("tests/") for t in c["tests"]))

    def test_r4_non_test_names_absent_from_json(self):
        self._ledger([{"name": "fix-a", "t0": 1000, "end": 2000}])
        self.log = [("a" * 40, 1500, ["sidereus/private_mod.py", "tests/test_ok.py", "README.md"])]
        s = json.dumps(HPS.person(self.proj))
        self.assertIn("tests/test_ok.py", s)
        self.assertNotIn("private_mod", s)
        self.assertNotIn("README", s)

    def test_budget_cache_and_git_miss(self):
        self._ledger([{"name": "fix-a", "t0": 1000, "end": 2000}])
        self.log = [("a" * 40, 1500, ["tests/test_ok.py"])]
        p = HPS.person(self.proj)
        self.assertEqual(self.calls, ["rev-parse", "log"])   # ≤2 spawns
        del self.calls[:]
        self.assertIs(HPS.person(self.proj), p)
        self.assertEqual(self.calls, [])                     # HEAD memo + cache hit: no spawn
        HPS._PS_CACHE.clear()
        HPS._git = lambda repo, args: self.calls.append(args[0]) or (None if args[0] == "log" else (0, "abcdef12\n"))
        p = HPS.person(self.proj)
        self.assertEqual((p["cards"][0]["commits"], p["git"], p["runs"]), (None, False, 1))
        self.assertEqual([k for k in HPS._PS_CACHE if k[0] != "head"], [])   # a git miss is not cached
        del self.calls[:]
        HPS.person(self.proj, git=False)
        self.assertEqual(self.calls, [])

    def test_join_does_not_mutate_trail_cache(self):
        """harness_plat._results copies the report: the harness_trail cache entry keeps its counts."""
        TR, HP = sidereus("harness_trail"), sidereus("harness_plat")
        saved = (HP.harness_evidence.scan, HP.harness_flow.guards, HP.sec_runtime.view, TR._git, TR._now)
        rows = [{"kind": "check", "ts": 100.0, "mode": "fast", "rc": 1, "head": "abcd", "steps": [{"name": "t", "rc": 1}]},
                {"kind": "check", "ts": 200.0, "mode": "fast", "rc": 0, "head": "abcd", "steps": [{"name": "t", "rc": 0}]}]
        HP.harness_evidence.scan = lambda proj: (rows, 0)
        HP.harness_flow.guards = lambda proj, runs=None: {}
        HP.sec_runtime.view = lambda d, now: {}
        TR._git = lambda repo, args: (0, "abcdef1234\n") if args[0] == "rev-parse" else (0, "")
        TR._now = lambda: 10000.0
        TR._TR_CACHE.clear()
        self._ledger([{"name": "fix-a", "t0": 1000, "end": 2000}])
        try:
            HP._results(self.proj)
            HP._results(self.proj)
            cached = [v for k, v in TR._TR_CACHE.items() if k[0] == "report"]
            self.assertEqual(len(cached), 1)
            for v in cached:
                self.assertNotIn("person", v["counts"])
                self.assertNotIn("person", v)
        finally:
            HP.harness_evidence.scan, HP.harness_flow.guards, HP.sec_runtime.view, TR._git, TR._now = saved
            TR._TR_CACHE.clear()


if __name__ == "__main__":
    unittest.main()
