"""R1/R4: red-check mode `rc` for gates outside GATE_MODES (npm test, pytest, ...) and the pipeline row `red` count."""
import json
import os
import unittest
from unittest import mock

from tests import _load
from tests.test_pl_eval_cli import AV, PE, Base, git

_load.load()
from sidereus import pipeline as PL, pipeline_schema as PS  # noqa: E402

GATE = "/usr/bin/python3 check.py"
CHECK = ("import ast, os, sys\n"
         "for d, _ds, fs in os.walk('.'):\n"
         "    for f in fs:\n"
         "        if f.endswith('.py') and '.git' not in d:\n"
         "            try:\n"
         "                ast.parse(open(os.path.join(d, f)).read())\n"
         "            except SyntaxError:\n"
         "                sys.exit(1)\n")


@unittest.skipUnless(os.name == "posix", "gate fixture calls /usr/bin/python3")
class RcMode(Base):
    def pfile(self):
        return os.path.join(self.repo, ".claude", "pipelines", "p.json")

    def test_rc_gate_pass_fail(self):
        self.assertIsNone(PS.gate_mode(GATE))   # not an evidence mode: GATE_MODES unchanged
        self.w("src/mod.py", "x = 1\n")
        self.w("check.py", CHECK)
        self.commit([{"title": "Verify", "agent": "x", "gate": GATE}])
        before = git(self.repo, "status", "--porcelain")
        rc, out = self.main("redcheck", "--pipeline", self.pfile(), "--stage", "Verify", "--repo", self.repo, "--timeout", "60")
        self.assertEqual((rc, out.strip()), (0, "redcheck: pass — gate rc 1 on a broken repo"))
        self.assertEqual(git(self.repo, "status", "--porcelain"), before)   # the break stayed in the temp clone
        with open(os.path.join(PE.EVAL_DIR, "redcheck.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["gates"][PE.red_key(AV.repo_key(self.repo), GATE)]["mode"], "rc")
        self.assertEqual([(r["mode"], r["steps"][0]["name"]) for r in self.rows()], [("redcheck", "rc")])

    def test_rc_gate_never_red(self):
        self.w("a.py", "x = 1\n")
        self.commit([{"title": "Verify", "agent": "x", "gate": "/usr/bin/true"}])
        rc, out = self.main("redcheck", "--pipeline", self.pfile(), "--stage", "Verify", "--repo", self.repo)
        self.assertEqual((rc, out.strip()), (1, "redcheck: fail — gate passed on a broken repo"))

    def test_inject_picks_main_language(self):
        self.w("a.py", "x = 1\n")
        self.w("web/b.js", "let a = 1;\n")
        self.w("web/c.js", "let c = 1;\n")
        self.w("web/d.d.ts", "")
        exp, why = self.cli.inject("rc", self.repo)
        self.assertEqual((exp, why), ([], "syntax error in web/b.js"))
        with open(os.path.join(self.repo, "web", "b.js"), encoding="utf-8") as f:
            self.assertTrue(f.read().endswith("function sidereus_red_check( {\n"))
        self.assertEqual(self.cli.inject("rc", os.path.join(self.repo, "web", "none")), (None, "no source file to break"))


class RedCount(unittest.TestCase):
    def test_counts_by_current_gate_text(self):
        rows = [{"ok": True, "stages": [{"title": "A", "gate": "npm test"}, {"title": "B", "gate": "old"}, {"title": "C"}]},
                {"ok": True, "stages": [{"title": "A", "gate": "go test"}]}, {"ok": False}]
        calls = []

        def status(name, stages, key):
            calls.append(len(stages))
            return {s["title"]: {"verdict": "pass"} for s in stages if s["gate"] in ("npm test", "go test")}
        from sidereus import pl_eval
        with mock.patch.object(pl_eval, "redcheck_status", status):
            out = PL._red_counts(rows, "/p")
        self.assertEqual([r.get("red") for r in out], [1, 1, None])
        self.assertEqual(calls, [3])   # one store read for every pipeline

    def test_unreadable_store_is_unknown(self):
        from sidereus import pl_eval

        def boom(name, stages, key):
            raise OSError
        with mock.patch.object(pl_eval, "redcheck_status", boom):
            self.assertNotIn("red", PL._red_counts([{"ok": True, "stages": []}], "/p")[0])


if __name__ == "__main__":
    unittest.main()
