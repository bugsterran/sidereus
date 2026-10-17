"""Pipeline evaluation core (sidereus/pl_eval.py): seeds, matching, holdout secrecy, flaky gates, red-check store."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

PE = sidereus("pl_eval")
AV = sidereus("arch_verify")
C1 = "a" * 40
NOW = 1_800_000_000.0
TPL = [{"id": "secrets", "title": {"ko": "비밀값 검사", "en": "Secrets"},
        "gate": "python3 /a/scripts/arch_checks.py --verify --last --category security"}]
STAGES = [{"title": "구현", "agent": "x"},
          {"title": "검사 실행", "agent": "x", "gate": "/usr/bin/python3 scripts/arch_checks.py --verify --last --category security"},
          {"title": "리뷰", "agent": "x"}]


def rd(fp):
    with open(fp, encoding="utf-8") as f:
        return f.read()


def seed(i, **kw):
    return dict({"id": i, "kind": "secret", "file": "src/a.ts", "line": 10, "expectStage": "검사 실행"}, **kw)


def item(tool, line, rule="no-unused-vars", f="src/a.ts", pkg=None):
    return {"tool": tool, "file": f, "line": line, "rule": rule, "pkg": pkg}


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-pleval-"))
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        for mod, k, v in ((PE, "EVAL_DIR", os.path.join(self.tmp, "eval")), (AV, "ARCH_DIR", os.path.join(self.tmp, "arch")),
                          (PE, "EVAL_EV_FILE", os.path.join(self.tmp, "ev.jsonl"))):
            p = mock.patch.object(mod, k, v)
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class Seeds(Tmp):
    def test_validation(self):
        self.assertEqual(PE.seed_errors({"v": 1, "seeds": [seed("a"), seed("b", holdout=True, rule="r", pkg="lodash")]}), [])
        bad = {"v": 1, "seeds": [seed("A"), seed("b", kind="x"), seed("c", file="../x"), seed("d", line=0),
                                 seed("e", rule="bad rule"), seed("f", expectStage=""), seed("g", holdout="yes"),
                                 seed("h", msg="text"), seed("i", file="/abs"), seed("j"), seed("j"), seed("k", kind="lint")]}
        self.assertEqual(PE.seed_errors(bad), ["seeds[0].id", "seeds[1].kind: secret|dep|sast|logic",
                                               "seeds[2].file: repo-relative path", "seeds[3].line", "seeds[4].rule",
                                               "seeds[5].expectStage", "seeds[6].holdout", "seeds[7]: keys",
                                               "seeds[8].file: repo-relative path", "seeds[10].id",
                                               "seeds[11].kind: secret|dep|sast|logic"])
        self.assertTrue(PE.seed_errors({"v": 2, "seeds": []}))
        self.assertEqual(PE.seed_errors({"v": 1, "seeds": [seed("s", kind="sast", rule="insecure-random-token")]}), [])
        self.assertTrue(PE.seed_errors({"v": 1, "seeds": [], "x": 1}))

    def test_store_mode_and_roundtrip(self):
        d = {"v": 1, "seeds": [seed("a"), seed("h", holdout=True)]}
        PE.save_seeds(self.repo, d)
        fp = os.path.join(PE.EVAL_DIR, AV.repo_key(self.repo), "seeds.json")
        self.assertEqual(os.stat(fp).st_mode & 0o777, 0o600)
        self.assertEqual(PE.load_seeds(self.repo), d)
        self.assertEqual(PE.counts(d), {"n": 2, "public": 1, "holdout": 1})
        with self.assertRaises(ValueError):
            PE.save_seeds(self.repo, {"v": 1, "seeds": [seed("BAD")]})


class Match(unittest.TestCase):
    def test_line_rule_pkg_tool(self):
        s = seed("a", rule="no-unused-vars")
        self.assertTrue(PE.matches(s, item("gitleaks", 12)))
        self.assertTrue(PE.matches(s, item("gitleaks", 8)))
        self.assertFalse(PE.matches(s, item("gitleaks", 13)))
        self.assertFalse(PE.matches(s, item("gitleaks", 10, rule="other")))
        self.assertFalse(PE.matches(s, item("semgrep", 10)))
        self.assertFalse(PE.matches(s, item("gitleaks", 10, f="src/b.ts")))
        self.assertTrue(PE.matches(seed("a"), item("gitleaks", 11, rule="anything")))   # no rule on the seed
        dep = seed("d", kind="dep", file="package-lock.json", pkg="lodash")
        del dep["line"]
        self.assertTrue(PE.matches(dep, item("osv-scanner", 0, rule="GHSA-x", f="package-lock.json", pkg="lodash")))
        self.assertFalse(PE.matches(dep, item("npm-audit", 0, rule="1094", f="package-lock.json", pkg="minimist")))
        dep["file"] = "package.json"   # the advisory names the lockfile; the package decides
        self.assertTrue(PE.matches(dep, item("npm-audit", 1, rule="GHSA-y", f="package-lock.json", pkg="lodash")))
        logic = seed("l", kind="logic")
        self.assertTrue(PE.matches(logic, item("", 10, rule=None)))
        self.assertFalse(PE.matches(logic, item("gitleaks", 10)))
        sast = seed("s", kind="sast", rule="insecure-random-token")
        self.assertTrue(PE.matches(sast, item("semgrep", 11, rule="insecure-random-token")))
        self.assertTrue(PE.matches(sast, item("semgrep", 10, rule="rules.insecure-random-token")))   # dotted id
        self.assertFalse(PE.matches(sast, item("semgrep", 10, rule="no-eval")))
        self.assertFalse(PE.matches(sast, item("gitleaks", 10, rule="insecure-random-token")))
        self.assertFalse(PE.matches(sast, item("semgrep", 13, rule="insecure-random-token")))
        self.assertTrue(PE.matches(seed("b", kind="sast", rule="B311"), item("bandit", 10, rule="B311")))
        self.assertFalse(PE.matches(seed("l", rule="a.b"), item("gitleaks", 10, rule="b")))   # only sast strips dots

    def test_stage_resolution(self):
        self.assertEqual(PE.stage_index("리뷰", STAGES, TPL), 2)
        self.assertEqual(PE.stage_index("secrets", STAGES, TPL), 1)       # catalog id -> same gate mode
        self.assertEqual(PE.stage_index("비밀값 검사", STAGES, TPL), 1)      # catalog title.ko
        self.assertIsNone(PE.stage_index("nope", STAGES, TPL))


class Score(Tmp):
    def test_holdout_secrecy_and_counts(self):
        seeds = [seed("pub-hit"), seed("pub-miss", line=40), seed("secret-holdout-id", holdout=True),
                 seed("logic-1", kind="logic", expectStage="리뷰"), seed("lost", expectStage="nowhere")]
        items = {1: [item("gitleaks", 11)]}
        st, hold, unres = PE.score(seeds, STAGES, lambda i: items.get(i, []), [item("", 10, rule=None)], TPL)
        self.assertEqual([(s["n"], s["caught"], s["missed"]) for s in st], [(0, 0, []), (2, 1, ["pub-miss"]), (1, 1, [])])
        self.assertEqual((hold, unres), ({"n": 1, "caught": 1}, 1))
        d = PE.save_eval(self.repo, C1, "p", NOW, st, hold)
        raw = rd(os.path.join(PE.EVAL_DIR, AV.repo_key(self.repo), C1, "eval.json"))
        self.assertNotIn("secret-holdout-id", raw)
        self.assertEqual(json.loads(raw), d)
        got = PE.load_eval(AV.repo_key(self.repo), C1)
        self.assertEqual((got["holdout"], got["stages"][1]["missed"]), ({"n": 1, "caught": 1}, ["pub-miss"]))
        self.assertIsNone(PE.load_eval("../x", C1))
        row = PE.eval_row(self.repo, C1, st, NOW)
        self.assertEqual((row["kind"], row["mode"], row["rc"], row["steps"][0]["name"]), ("eval", "eval-catch", 1, "s1"))
        self.assertNotIn("secret-holdout-id", json.dumps(row))

    def test_checks_items(self):
        d = os.path.join(AV.ARCH_DIR, AV.repo_key(self.repo), C1)
        os.makedirs(d)
        with open(os.path.join(d, "checks-security.json"), "w", encoding="utf-8") as f:
            json.dump({"items": [{"tool": "gitleaks", "file": "a.cfg", "line": 1, "rule": "generic-api-key", "sev": "error"},
                                 {"tool": "gitleaks", "file": "/abs", "line": 1, "rule": "x", "sev": "error"}]}, f)
        self.assertEqual(PE.checks_items(self.repo, C1, "checks-security"),
                         [{"tool": "gitleaks", "file": "a.cfg", "line": 1, "rule": "generic-api-key", "pkg": None}])
        self.assertEqual(PE.checks_items(self.repo, C1, "fast"), [])


class Flaky(Tmp):
    def rows(self):
        r = lambda ts, rc, mode="fast", head="abcd", dirty=False: {"v": 1, "kind": "check", "ts": ts, "mode": mode,
                                                                   "repo": self.repo, "head": head, "dirty": dirty, "rc": rc}
        return [r(NOW - 100, 0), r(NOW - 50, 1),                               # fast: same head both ways -> unstable
                r(NOW - 100, 0, "full"), r(NOW - 50, 1, "full", head="beef"),  # different heads: real change
                r(NOW - 100, 0, "full", head="cafe"), r(NOW - 50, 1, "full", head="cafe", dirty=True),
                r(NOW - 20 * 86400, 0, "checks-security"), r(NOW - 10, 1, "checks-security")]

    def test_flaky(self):
        self.assertEqual(PE.flaky(self.rows(), NOW), ["fast"])
        self.assertEqual(PE.flaky(self.rows(), NOW, days=30), ["checks-security", "fast"])
        with open(PE.EVAL_EV_FILE, "w", encoding="utf-8") as f:
            for x in self.rows() + [dict(self.rows()[1], repo="/elsewhere", mode="full", head="beef", rc=0)]:
                f.write(json.dumps(x) + "\n")
            f.write("not json\n")
        self.assertEqual(PE.flaky_modes(self.repo, NOW), ["fast"])
        P = {"stages": [{"title": "a", "gate": "bash scripts/check.sh --fast"}, {"title": "b", "gate": "bash scripts/check.sh --full"},
                        {"title": "c", "gate": "make x"}, {"title": "d"}]}
        self.assertEqual(PE.gate_agreement(P, self.repo, NOW, "abcd"), {"a": {"k": 1, "n": 2}, "b": {"k": 1, "n": 1}})

    def test_agreement(self):
        r = lambda ts, rc, head="abcd": {"kind": "check", "ts": ts, "mode": "fast", "repo": "/r", "head": head, "dirty": False, "rc": rc}
        rows = [r(NOW - 9, 0), r(NOW - 8, 0), r(NOW - 7, 1), r(NOW - 5, 0, "beef"), r(NOW - 4, 0, "beef")]
        self.assertEqual(PE.agreement(rows, NOW, "abcd"), {"fast": (2, 3)})
        self.assertEqual(PE.agreement(rows, NOW, "abcd" + "0" * 36), {"fast": (2, 3)})   # full sha vs short evidence head
        self.assertEqual(PE.agreement(rows, NOW, "cafe"), {"fast": (2, 2)})   # no rows at HEAD -> newest row's commit
        self.assertEqual(PE.agreement(rows + [dict(rows[0], dirty=True)], NOW, None), {"fast": (2, 2)})
        self.assertEqual(PE.agreement([], NOW, "abcd"), {})

    def test_red_store_and_graded(self):
        g1 = STAGES[1]["gate"]
        P = {"name": "p", "stages": STAGES + [{"title": "검증", "agent": "x", "gate": "bash scripts/check.sh --fast"}]}
        self.assertEqual(PE.graded_summary(P, self.repo, NOW), {"n": 0, "m": 4, "unred": ["검사 실행", "검증"], "unstable": []})
        PE.save_red(g1, {"pipeline": "p", "stage": "검사 실행", "mode": "checks-security", "key": "k", "verdict": "pass",
                         "why": "", "at": NOW, "ms": 5})
        PE.save_red("bash scripts/check.sh --fast", {"pipeline": "q", "stage": "x", "mode": "fast", "key": "k",
                                                     "verdict": "pass", "why": "", "at": NOW, "ms": 5})
        j = json.loads(rd(os.path.join(PE.EVAL_DIR, "redcheck.json")))
        self.assertEqual(sorted(j["gates"]), sorted([PE.gate_key(g1), PE.gate_key("bash scripts/check.sh --fast")]))
        self.assertEqual(len(PE.gate_key(g1)), 16)
        st = PE.redcheck_status("p", P["stages"])
        self.assertEqual((st["검사 실행"]["verdict"], st["검사 실행"]["same"], st["검증"]["same"]), ("pass", True, False))
        self.assertEqual(PE.graded_summary(P, self.repo, NOW), {"n": 2, "m": 4, "unred": [], "unstable": []})
        with open(PE.EVAL_EV_FILE, "w", encoding="utf-8") as f:
            for x in self.rows()[:2]:
                f.write(json.dumps(x) + "\n")
        self.assertEqual(PE.graded_summary(P, self.repo, NOW), {"n": 1, "m": 4, "unred": [], "unstable": ["검증"]})
        with self.assertRaises(ValueError):
            PE.save_red(g1, {"verdict": "maybe"})


if __name__ == "__main__":
    unittest.main()
