"""Pipeline result layer (sidereus/pl_outcome.py): ledger, loop-back split, broke / fix-followed PASSes, sentences.
`_git`, `_now`, `OC_EVAL_DIR` and `harness_evidence.EV_FILE` are patched; no real git, clock or live files."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import load, sidereus

load()
OC = sidereus("pl_outcome")
EV = sidereus("harness_evidence")
TR = sidereus("harness_trail")
D = 86400
P = 1000000000.0   # PASS time
N = "change"
FILL = [("%040x" % (k + 1), int(P - 5000 - k), ["old%d.py" % k]) for k in range(3)]   # unrelated older commits: keeps test files under the «common file» share


class Git(object):
    """Fake git: rev-parse HEAD + one `log --name-only` built from [(sha, ct, files)] newest first."""

    def __init__(self, commits):
        self.commits, self.calls, self.side = commits, [], set()

    def __call__(self, repo, args):
        self.calls.append(list(args))
        if args[0] == "rev-parse":
            return 0, "f" * 40 + "\n"
        if args[0] == "log":
            return 0, "".join("\x1e%s\x1f%d\n\n%s\n" % (s, ct, "\n".join(fs)) for s, ct, fs in self.commits)
        if args[0] == "rev-list":   # linear history: everything newer than C, minus side-branch commits
            c = args[-1].split("..")[0]
            shas = [x[0] for x in self.commits]
            return 0, "".join(x + "\n" for x in shas[:shas.index(c)] if x not in self.side)
        return None


class TrGit(object):
    """harness_trail git: HEAD known, every PASS head an ancestor unless in `gone`; `fail` = git never answers."""

    def __init__(self):
        self.gone, self.fail = set(), False

    def __call__(self, repo, args):
        if self.fail and args[0] != "rev-parse":
            return None
        if args[0] == "rev-parse":
            return 0, ("f" * 40 if args[-1] == "HEAD" else "1" * 40) + "\n"
        if args[0] == "merge-base":
            return (1, "") if args[2] in self.gone else (0, "")
        return 0, ""


class Outcome(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pl-oc-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(self.proj)
        self.evf = os.path.join(self.tmp, "evidence.jsonl")
        self.now = P + 20 * D
        self.git, self.tr = Git([]), TrGit()
        saved = [(OC, "OC_EVAL_DIR", os.path.join(self.tmp, "eval")), (OC, "_git", self.git), (OC, "_now", lambda: self.now),
                 (EV, "EV_FILE", self.evf), (TR, "_git", self.tr)]
        for mod, k, v in saved:
            old = getattr(mod, k)
            setattr(mod, k, v)
            self.addCleanup(setattr, mod, k, old)
        OC._OC_MEMO.clear()
        self.ledger([{"name": N, "t0": P - 100, "end": P + 10, "lb": [], "deny": 0, "dc": {}}])

    def ledger(self, rows, junk=False):
        d = os.path.join(self.tmp, "eval", OC.repo_key(self.proj))
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "runs.jsonl"), "w", encoding="utf-8") as f:
            if junk:
                f.write("{half\n" + json.dumps({"name": "../x", "end": 1}) + "\n")
            f.write("".join(json.dumps(r) + "\n" for r in rows))

    def evidence(self, *rows):
        with open(self.evf, "w", encoding="utf-8") as f:
            for ts, rc, head, dirty in rows:
                if not isinstance(ts, (int, float)):
                    f.write(ts + "\n")
                    continue
                f.write(json.dumps({"v": 1, "kind": "check", "repo": os.path.realpath(self.proj), "ts": ts, "mode": "fast",
                                    "rc": rc, "head": head, "dirty": dirty, "steps": [{"name": "tests", "rc": rc}]}) + "\n")

    def result(self, commits):
        self.git.commits = commits
        OC._OC_MEMO.clear()
        return OC.outcome(self.proj, N, ["review"])["result"]

    def test_fix_window_and_files(self):
        self.evidence((P, 0, "aaaaaaa", False))
        base = [("b" * 40, int(P + 15 * D), ["b.py"]),   # day 15: too late
                ("c" * 40, int(P + 3 * D), ["c.py"]),     # untouched file
                ("a" * 40, int(P - 30), ["a.py", "b.py"])] + FILL
        r = self.result(base)
        self.assertEqual((r["n"], r["broke"], r["fixed"]), (1, 0, 0))
        self.assertEqual(r["list"], [{"sha": "a" * 12, "files": ["a.py", "b.py"], "broke": False, "fixed": False}])
        r = self.result([("d" * 40, int(P + 13 * D), ["a.py"])] + base)   # day 13 touching a.py
        self.assertEqual((r["n"], r["fixed"]), (1, 1))

    def test_dirty_resolves_to_next_commit(self):
        self.evidence((P, 0, "aaaaaaa", True))
        self.assertEqual(self.result([("e" * 40, int(P + 300), ["x.py"])])["n"], 0)   # landed after the run: unchecked
        r = self.result([("e" * 40, int(P + 300), ["x.py"]), ("a" * 40, int(P + 30), ["x.py"])] + FILL)
        self.assertEqual((r["n"], r["fixed"], r["list"][0]["sha"]), (1, 1, "a" * 12))

    def test_passes_on_one_commit_are_one_entry(self):
        self.ledger([{"name": N, "t0": P - 100, "end": P + 10}, {"name": N, "t0": P + 100, "end": P + 200}])
        self.evidence((P, 0, "aaaaaaa", False), (P + 5, 0, "aaaaaaa", False), (P + 150, 0, "aaaaaaa", False))
        r = self.result([("d" * 40, int(P + 3 * D), ["a.py"]), ("a" * 40, int(P - 30), ["a.py"])] + FILL)
        self.assertEqual((r["n"], r["fixed"], [x["sha"] for x in r["list"]]), (1, 1, ["a" * 12]))

    def test_same_run_commit_not_a_fix(self):
        self.evidence((P, 0, "aaaaaaa", False))
        r = self.result([("d" * 40, int(P + 40), ["a.py"]), ("a" * 40, int(P - 30), ["a.py"])] + FILL)   # run end P+10, +60 s
        self.assertEqual((r["n"], r["fixed"]), (1, 0))

    def test_common_file_overlap_not_a_fix(self):
        self.evidence((P, 0, "aaaaaaa", False))
        log = [("d" * 40, int(P + 3 * D), ["CHANGELOG.md"]), ("a" * 40, int(P - 30), ["a.py", "CHANGELOG.md"])]
        log += [(s, ct, fs + ["CHANGELOG.md"]) for s, ct, fs in FILL]   # CHANGELOG.md in every commit
        self.assertEqual(self.result(log)["fixed"], 0)
        log[0] = ("d" * 40, int(P + 3 * D), ["CHANGELOG.md", "a.py"])   # a later commit sharing a rare file still counts
        self.assertEqual(self.result(log)["fixed"], 1)

    def test_broke_from_later_fail(self):
        self.evidence((P, 0, "aaaaaaa", False), (P + 5, 1, "aaaaaaa", False))
        r = self.result([("a" * 40, int(P - 30), ["a.py"])])
        self.assertEqual((r["n"], r["broke"]), (1, 1))

    def test_side_branch_commit_not_a_fix(self):
        self.evidence((P, 0, "aaaaaaa", False))
        log = [("d" * 40, int(P + 3 * D), ["a.py"]), ("a" * 40, int(P - 30), ["a.py"])] + FILL
        self.git.side = {"d" * 40}
        self.assertEqual(self.result(log)["fixed"], 0)
        self.git.side = set()
        self.assertEqual(self.result(log)["fixed"], 1)

    def test_old_pass_broke_beyond_repo_wide_newest_30(self):
        self.ledger([{"name": N, "t0": P - 100, "end": P + 10}, {"name": "other", "t0": P + 1000, "end": P + 2000}])
        rows = [(P, 0, "c" * 7, False)] + [(P + 1000 + i * 10, 0, "d" * 7, False) for i in range(49)]
        self.evidence(*rows)
        self.tr.gone = {"c" * 7}
        r = self.result([("d" * 40, int(P + 900), ["z.py"]), ("c" * 40, int(P - 30), ["a.py"])])
        self.assertEqual((r["n"], r["broke"], r["unchecked"], r["partial"]), (1, 1, 0, False))

    def test_git_miss_is_unchecked_not_held(self):
        self.evidence((P, 0, "aaaaaaa", False))
        self.tr.fail = True
        r = self.result([("a" * 40, int(P - 30), ["a.py"])])
        self.assertEqual((r["n"], r["unchecked"], r["partial"]), (0, 1, True))
        self.tr.fail = False
        self.evidence((P, 0, "aaaaaaa", True))   # dirty, no commit landed in the run: unchecked, but not a git miss
        r = self.result([("a" * 40, int(P - 3000), ["a.py"])])
        self.assertEqual((r["n"], r["unchecked"], r["partial"]), (0, 1, False))

    def test_pass_outside_run_window_ignored(self):
        self.evidence((P + 500, 0, "aaaaaaa", False))
        self.assertEqual(self.result([("a" * 40, int(P - 30), ["a.py"])])["n"], 0)

    def test_git_argv_read_only(self):
        self.evidence((P, 0, "aaaaaaa", False))
        self.result([("a" * 40, int(P - 30), ["a.py"])])
        self.assertTrue(self.git.calls)
        for a in self.git.calls:
            self.assertFalse({"-p", "--patch", "--stat", "cat-file", "show", "diff"} & set(a), a)
            if a[0] in ("log", "diff-tree"):
                self.assertIn("--name-only", a)
            if a[0] == "rev-list":
                self.assertIn("--ancestry-path", a)

    def test_loopback_split_and_procedure(self):
        lb = [{"f": "review", "g": "impl", "n": 1}]
        self.ledger([{"name": N, "t0": self.now - 40 * D, "end": self.now - 40 * D, "lb": lb, "dc": {}},
                     {"name": N, "t0": self.now - 35 * D, "end": self.now - 35 * D, "lb": [], "dc": {}},
                     {"name": N, "t0": self.now - 2 * D, "end": self.now - 2 * D, "lb": lb, "dc": {"jump": 2, "zz": 5}},
                     {"name": N, "t0": self.now - D, "end": self.now - D, "lb": [{"f": "verify", "g": "impl", "n": 1}], "dc": {}},
                     {"name": "other", "t0": self.now - D, "end": self.now - D, "lb": lb, "dc": {"jump": 9}},
                     {"name": N, "t0": self.now - 70 * D, "end": self.now - 70 * D, "lb": lb, "dc": {}}], junk=True)
        o = OC.outcome(self.proj, N, ["review"])
        self.assertEqual(o["proc"], {"runs": 2, "jump": 2})
        self.assertEqual(o["lb"], {"cur": {"n": 2, "k": 1}, "prev": {"n": 2, "k": 1}})

    def test_ledger_rows_allow_listed(self):
        self.ledger([{"name": N, "t0": 1, "end": 2, "lb": [{"f": "a", "g": "b", "n": 1, "x": "body"}], "deny": 1,
                      "dc": {"jump": 1}, "h0": "abcd123", "h1": "not hex", "msg": "secret"}])
        rows = OC.ledger(OC.repo_key(self.proj), 0)
        self.assertEqual(rows, [{"name": N, "t0": 1.0, "end": 2.0, "lb": [{"f": "a", "g": "b", "n": 1}], "deny": 1,
                                 "dc": {"jump": 1}, "h0": "abcd123", "h1": ""}])

    def test_counts_and_sentences(self):
        o = {"proc": {"runs": 8, "jump": 1}, "lb": {"cur": {"n": 8, "k": 1}, "prev": {"n": 4, "k": 1}},
             "result": {"n": 5, "broke": 1, "fixed": 2, "list": [{"sha": "a", "files": ["x"]}]}}
        c = OC.counts(o)
        self.assertNotIn("list", c["result"])
        self.assertNotIn("files", json.dumps(c))
        self.assertEqual(OC.sentences({"n": 2, "m": 3}, o), [
            "Gate: 2 of 3 gates confirmed able to fail", "Procedure: 8 runs, 1 order violations blocked",
            "Result: 1 of 5 passes broke later, fix followed 2",
            "Review loop-backs: 13% of runs (last 30 days) vs 25% (30 days before)"])   # 12.5 rounds half up
        o["lb"]["prev"] = {"n": 0, "k": 0}
        self.assertEqual(OC.sentences(None, o)[-1], "Review loop-backs: 13% of runs (last 30 days), no earlier data")
        o["lb"]["cur"] = {"n": 0, "k": 0}
        self.assertEqual(len(OC.sentences(None, o)), 3)

    def test_latest_report(self):
        self.assertIsNone(OC.latest_report(self.proj))
        d = os.path.join(self.tmp, "eval", OC.repo_key(self.proj), "reports")
        os.makedirs(d)
        for n in ("2026-10-01.md", "2026-10-09.md", "notes.md"):
            open(os.path.join(d, n), "w", encoding="utf-8").close()
        self.assertEqual(OC.latest_report(self.proj), {"date": "2026-10-09", "path": os.path.join(d, "2026-10-09.md")})

    def test_states_since(self):
        rows = [{"kind": "check", "ts": t, "mode": "fast", "rc": rc, "head": "", "dirty": False,
                 "steps": [{"name": "tests", "rc": rc}]} for t, rc in ((10, 0), (20, 0), (30, 1))]
        st = TR.states(rows, "", 15, git=False)
        self.assertEqual([(s["ts"], s["state"]) for s in st], [(20.0, "broke")])
        st = TR.states(rows, "", 0, git=False, only={10.0})   # filtered to the given PASS set before the cap
        self.assertEqual([(s["ts"], s["state"]) for s in st], [(10.0, "broke")])


if __name__ == "__main__":
    unittest.main()
