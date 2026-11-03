"""Red check `rc` runs the gate on the clean clone first; the «Gate red-checked» count takes only verdict «pass»."""
import os
import unittest
from unittest import mock

from tests import _load
from tests.test_pl_eval_cli import Base, git

_load.load()
from sidereus import pipeline as PL  # noqa: E402

# Fails only when a syntax error is present (clean = rc 0, broken = rc 1).
SYNTAX = ("import ast, os, sys\n"
          "for d, _ds, fs in os.walk('.'):\n"
          "    for f in fs:\n"
          "        if f.endswith('.py') and '.git' not in d:\n"
          "            try:\n"
          "                ast.parse(open(os.path.join(d, f)).read())\n"
          "            except SyntaxError:\n"
          "                sys.exit(1)\n")


@unittest.skipUnless(os.name == "posix", "gate fixture calls /usr/bin/python3")
class CleanFirst(Base):
    def pfile(self):
        return os.path.join(self.repo, ".claude", "pipelines", "p.json")

    def red(self, gate, check=None):
        self.w("src/mod.py", "x = 1\n")
        if check is not None:
            self.w("check.py", check)
        self.commit([{"title": "Verify", "agent": "x", "gate": gate}])
        before = git(self.repo, "status", "--porcelain")
        rc, out = self.main("redcheck", "--pipeline", self.pfile(), "--stage", "Verify", "--repo", self.repo, "--timeout", "60")
        self.assertEqual(git(self.repo, "status", "--porcelain"), before)   # user repo untouched
        return rc, out.strip()

    def test_always_failing_gate_is_skip_not_pass(self):
        # before the fix this recorded «pass — gate rc 1 on a broken repo»
        self.assertEqual(self.red("/usr/bin/false"), (2, "redcheck: skip — gate fails on a clean clone"))

    def test_missing_test_tool_in_gate_is_skip(self):
        self.assertEqual(self.red("/usr/bin/python3 no_such_test.py"), (2, "redcheck: skip — gate fails on a clean clone"))

    def test_clean_pass_broken_fail_is_pass(self):
        self.assertEqual(self.red("/usr/bin/python3 check.py", SYNTAX), (0, "redcheck: pass — gate rc 1 on a broken repo"))

    def test_clean_pass_broken_pass_is_fail(self):
        self.assertEqual(self.red("/usr/bin/true"), (1, "redcheck: fail — gate passed on a broken repo"))


class ChecklistCount(unittest.TestCase):
    def count(self, verdicts):
        rows = [{"ok": True, "stages": [{"title": str(i), "gate": "g%d" % i} for i in range(len(verdicts))]}]
        from sidereus import pl_eval
        with mock.patch.object(pl_eval, "redcheck_status",
                               lambda _n, st: {s["title"]: {"verdict": v} for s, v in zip(st, verdicts) if v}):
            return PL._red_counts(rows)[0]["red"]

    def test_skip_and_fail_do_not_count(self):
        self.assertEqual(self.count(["skip", "fail", None]), 0)

    def test_pass_counts(self):   # negative control: the same fixture with a pass is counted
        self.assertEqual(self.count(["skip", "pass", "pass"]), 2)


if __name__ == "__main__":
    unittest.main()
