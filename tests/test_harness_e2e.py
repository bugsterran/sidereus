"""Harness end-to-end replays (tests/fixtures/harness_e2e/<case>/case.json): real recorder → harness_flow.flow node / harness_plat._results.

The replay itself lives in scripts/harness_selfcheck.py (the guard self-check runner); this file asserts the node details.
Guard: hooks/pl_flow.py main() (which loads hooks/pl_guard.py) writes plmark/<sid>.runs.json. Gate/Kept: scripts/evidence_rec.py
writes evidence.jsonl rows as check.sh does. Tmp dirs only, fixed clock; git only in a temp repo with fixed dates.
"""
import importlib.util
import os
import shutil
import tempfile
import unittest

from tests._clock import NOW
from tests._load import ROOT, load, sidereus

load()
HP, HT = sidereus("harness_plat"), sidereus("harness_trail")


def _mod(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


RUN = _mod("harness_selfcheck_e2e_t", "scripts/harness_selfcheck.py")
FX = RUN.FX
case = RUN.case


class _Base(unittest.TestCase):
    def setUp(self):
        self.assertEqual(RUN.NOW, NOW)
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="hfe2e-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.r = RUN.Replay(self.tmp).__enter__()
        self.addCleanup(self.r.__exit__, None, None, None)
        self.proj = self.r.proj


class Cases(unittest.TestCase):
    """Every case carries the self-check fields and a pair with the opposite outcome under the same guard."""

    def test_fields_and_pairs(self):
        names = sorted(n for n in os.listdir(FX) if os.path.isdir(os.path.join(FX, n)))
        with open(os.path.join(FX, "README.md"), encoding="utf-8") as f:
            readme = f.read()
        for n in names:
            fx = case(n)
            self.assertEqual([k for k in ("guard", "situation", "expect", "pair") if not isinstance(fx.get(k), str)], [], n)
            self.assertIn(fx["guard"], ("guard", "gate", "keep"), n)
            p = case(fx["pair"])
            self.assertEqual(p["guard"], fx["guard"], n)
            self.assertNotEqual(p["expect"], fx["expect"], n)
            # mutual, or a shared control whose own partner is another case with this case's outcome
            self.assertTrue(p["pair"] == n or case(p["pair"])["expect"] == fx["expect"], n)
            self.assertIn("`%s`" % n, readme, n)


class Guard(_Base):
    """R1: the guard hook's deny reaches the guard node."""

    def run_case(self, name):
        fx = case(name)
        res = self.r.run(name)
        self.assertEqual(res["denied"], [e["denied"] for e in fx["ev"] if e.get("e") == "pre"])
        self.assertEqual(len(self.r.flows()), 1)
        g = res["node"]
        self.assertEqual(res["actual"], fx["expect"])
        self.assertEqual("blocked" if g["v"]["deny"] else "allowed", fx["expect"])
        want = fx["node"]["guard"]
        self.assertEqual((g["st"], g["v"]["deny"]), (want["st"], want["deny"]))
        self.assertEqual([r["code"] for r in g["rec"] if r["k"] == "deny"], want["codes"])
        gd = HP._results(self.proj)["guards"]   # the «before edit» checkpoint counts the same denials
        self.assertEqual((gd["runs"], gd["deny"], sum(gd["codes"].values())), (1, want["deny"], len(want["codes"])))

    def test_jump(self):
        self.run_case("guard-jump")

    def test_jump_declared(self):
        self.run_case("guard-jump-declared")

    def test_commit_before_gate(self):
        self.run_case("guard-commit")

    def test_commit_after_fail(self):
        self.run_case("guard-commit-after-fail")

    def test_commit_after_pass(self):
        self.run_case("guard-commit-after-pass")

    def test_skip_of_required_gate(self):
        self.run_case("guard-skip-required")

    def test_skip_declared(self):
        self.run_case("guard-skip-declared")


class Gate(_Base):
    """R2: check.sh evidence rows reach the gate node; Red->Green only after a FAIL."""

    def run_case(self, name):
        fx = case(name)
        res = self.r.run(name)
        self.assertEqual(len(self.r.flows()), 1)
        g = res["node"]
        self.assertEqual(res["actual"], fx["expect"])
        self.assertEqual("r2g" if g["v"]["r2g"] else "no r2g", fx["expect"])
        want = fx["node"]["gate"]
        self.assertEqual((g["st"], g["v"]["r2g"], g["v"]["rows"]), (want["st"], want["r2g"], want["rows"]))

    def test_red_green(self):
        self.run_case("gate-red-green")

    def test_pass_only(self):
        self.run_case("gate-pass-only")


class Kept(_Base):
    """R3: a PASS at commit A, judged by harness_trail against a real temp repo, reaches the keep node."""

    def git(self, *args):
        return self.r.git(*args)

    def run_case(self, name):
        fx = case(name)
        res = self.r.run(name)
        self.assertEqual(len(self.r.flows()), 1)
        self.assertEqual(res["actual"], fx["expect"])
        k = res["node"]
        self.assertEqual((k["v"] or {}).get("state"), fx["expect"])
        want = fx["node"]["keep"]
        self.assertEqual((k["st"], (k["v"] or {}).get("state")), (want["st"], want["state"]))

    def test_held(self):
        self.run_case("keep-held")

    def test_reverted(self):
        self.run_case("keep-reverted")

    def test_report_kept_vs_reverted(self):
        """R1/R2: a FAIL->PASS incident at commit B reads «held» while B stays, «reverted» once a commit restores A's tree."""
        self.git("init", "-q")
        for i, body in enumerate(("1\n", "2\n")):
            with open(os.path.join(self.proj, "a.txt"), "w", encoding="utf-8") as f:
                f.write(body)
            self.git("add", "-A")
            self.git("commit", "-q", "-m", "c%d" % i)
            if i == 0:
                self.r.record("fast", 1, [["tests", 1, 10, 2, 1]], head=self.git("rev-parse", "--short", "HEAD"), ts=NOW - 500)
        self.r.record("fast", 0, [["tests", 0, 10, 0, 1]], head=self.git("rev-parse", "--short", "HEAD"), ts=NOW - 400)
        rep = HP._results(self.proj)["report"]
        self.assertEqual(rep["counts"], {"caught": 1, "held": 1, "again": 0, "reverted": 0, "gone": 0, "unchecked": 0, "checked": 1, "person": 0})
        inc = rep["incidents"][0]
        self.assertEqual((inc["cp"], inc["commits"], inc["fail"]["rc"], inc["fail"]["failed"]), ("fast", 1, 1, 2))
        with open(os.path.join(self.proj, "a.txt"), "w", encoding="utf-8") as f:
            f.write("1\n")
        self.git("commit", "-q", "-am", "revert")
        HT._TR_CACHE.clear()   # HEAD is reused for TR_HEAD_TTL; a new commit needs a fresh lookup
        rep = HP._results(self.proj)["report"]
        self.assertEqual(rep["counts"], {"caught": 1, "held": 0, "again": 0, "reverted": 1, "gone": 0, "unchecked": 0, "checked": 1, "person": 0})


if __name__ == "__main__":
    unittest.main()
