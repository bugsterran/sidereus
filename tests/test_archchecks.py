"""Project checks: parsers, detection, judge, runner (subprocess and git patched) and the /api/arch loader."""
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tests._load import sidereus, ROOT

AC = sidereus("arch_checks")
AP = sidereus("arch_checks_parse")
AV = sidereus("arch_verify")
FX = os.path.join(ROOT, "tests", "fixtures", "archchecks")
C1, C2 = "a" * 40, "b" * 40


def fx(name, repo="/r"):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return f.read().replace("@REPO@", repo)


def cli():
    spec = importlib.util.spec_from_file_location("arch_checks_cli", os.path.join(ROOT, "scripts", "arch_checks.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m._record = lambda *a: False   # ⚠never append to the live evidence file; tests/test_sec_checks.py covers _record
    return m


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-archchecks-"))
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def w(self, rel, text=""):
        fp = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(text)
        return fp


class ParserTest(unittest.TestCase):
    def test_checkstyle_file_and_stdout(self):
        want = [{"file": "/r/src/main/java/shop/A.java", "line": 3, "rule": "MissingJavadocMethodCheck", "sev": "warning",
                 "help": {"desc": "", "url": "https://checkstyle.org/checks/javadoc/missingjavadocmethod.html#MissingJavadocMethod"}},
                {"file": "/r/src/main/java/shop/A.java", "line": 9, "rule": "AvoidStarImportCheck", "sev": "error",
                 "help": {"desc": "", "url": "https://checkstyle.org/checks/imports/avoidstarimport.html#AvoidStarImport"}}]
        self.assertEqual(AC.parse_checkstyle(fx("checkstyle.xml")), want)
        self.assertEqual(AC.parse_checkstyle("Starting audit...\n" + fx("checkstyle.xml") + "Audit done.\n"), want)
        self.assertNotIn("secret", json.dumps(want))

    def test_pmd6_and_7(self):
        self.assertEqual(AC.parse_pmd(fx("pmd6.xml")),
                         [{"file": "/r/src/main/java/shop/A.java", "line": 4, "rule": "EmptyCatchBlock", "sev": "error"},
                          {"file": "/r/src/main/java/shop/A.java", "line": 7, "rule": "ShortVariable", "sev": "warning"}])
        self.assertEqual(AC.parse_pmd(fx("pmd7.xml")),
                         [{"file": "src/main/java/shop/B.java", "line": 12, "rule": "UnusedPrivateField", "sev": "error",
                           "help": {"desc": "", "url": "https://example.com"}}])

    def test_json_tools(self):
        self.assertEqual([(x["rule"], x["sev"], x["line"]) for x in AC.parse_ruff(fx("ruff.json"))],
                         [("F401", "warning", 1), ("syntax", "error", 2)])
        self.assertEqual([(x["rule"], x["sev"]) for x in AC.parse_eslint(fx("eslint.json"))],
                         [("no-unused-vars", "error"), ("@typescript-eslint/no-explicit-any", "warning"), ("parse", "error")])
        self.assertEqual([(x["file"], x["line"], x["rule"], x["sev"]) for x in AC.parse_clippy(fx("clippy.jsonl"))],
                         [("src/lib.rs", 7, "clippy::needless_return", "warning"), ("src/main.rs", 3, "rustc", "error")])
        with self.assertRaises(ValueError):
            AC.parse_ruff("not json")

    def test_rule_help(self):
        self.assertEqual(AP.checkstyle_url("com.puppycrawl.tools.checkstyle.checks.NewlineAtEndOfFileCheck"),
                         "https://checkstyle.org/checks.html")
        self.assertEqual(AP.checkstyle_url("org.example.MyCheck"), "")
        es = AC.parse_eslint(fx("eslint_meta.json"))
        self.assertEqual([x.get("help") for x in es],
                         [{"desc": "Disallow unused variables", "url": "https://eslint.org/docs/latest/rules/no-unused-vars"},
                          {"desc": "Require the use of === and !==", "url": ""}])     # control char and bad url dropped
        self.assertEqual(AC.parse_ruff(fx("ruff.json"))[0]["help"],
                         {"desc": "unused import", "url": "https://docs.astral.sh/ruff/rules/unused-import"})
        self.assertEqual(AC.parse_mypy(fx("mypy.txt"))[0]["help"]["url"],
                         "https://mypy.readthedocs.io/en/stable/error_code_list.html#code-return-value")
        self.assertNotIn("help", AC.parse_mypy(fx("mypy.txt"))[1])
        self.assertEqual(AC.parse_clippy(fx("clippy.jsonl"))[0]["help"]["url"],
                         "https://rust-lang.github.io/rust-clippy/master/#needless_return")
        self.assertIsNone(AC.clean_help("", "http://x"))
        self.assertIsNone(AC.clean_help(None, "https://x/" + "a" * 300))
        self.assertEqual(AC.clean_help("d" * 200, "")["desc"], "d" * 140)

    def test_text_tools(self):
        self.assertEqual([(x["file"], x["line"], x["rule"]) for x in AC.parse_tsc(fx("tsc.txt"))],
                         [("src/a.ts", 12, "TS2322"), ("src/b.ts", 3, "TS2304")])
        self.assertEqual([(x["file"], x["line"], x["rule"], x["sev"]) for x in AC.parse_mypy(fx("mypy.txt"))],
                         [("pkg/mod.py", 12, "return-value", "error"), ("pkg/other.py", 4, "mypy", "error")])
        self.assertEqual([(x["file"], x["line"], x["rule"]) for x in AC.parse_govet(fx("govet.txt"))],
                         [("./pay/gateway.go", 12, "printf"), ("pay/other.go", 3, "vet")])

    def test_doctype_and_truncated_refused(self):
        bomb = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><checkstyle><file name="a">&a;</file></checkstyle>'
        with self.assertRaises(ValueError):
            AC.parse_checkstyle(bomb)
        with self.assertRaises(ValueError):
            AC.parse_pmd(fx("pmd6.xml")[:200])
        with self.assertRaises(ValueError):
            AC.parse_checkstyle("")

class DetectTest(Tmp):
    def which(self, have):
        return lambda n: ("/bin/" + n) if n in have else None

    def ids(self, plans):
        return {p["id"]: (p["rules"], p.get("status")) for p in plans}

    def test_gradle_project_mode(self):
        self.w("build.gradle", "plugins { id 'java'\n id 'checkstyle'\n id 'pmd' }\n")
        self.w("src/main/java/a/A.java", "class A {}")
        gw = self.w("gradlew", "#!/bin/sh\n")
        os.chmod(gw, 0o755)
        ps = AC.detect(self.repo, self.which(set()))
        cs = [p for p in ps if p["id"] == "checkstyle"][0]
        self.assertEqual(cs["argv"], [gw, "--offline", "--no-daemon", "-q", "checkstyleMain", "pmdMain"])
        self.assertEqual((cs["rules"], cs["src"]), ("project", "reports"))
        self.assertNotIn("spotbugs", self.ids(ps))                     # build does not declare it
        self.w("build.gradle", "plugins { id 'java'\n id 'checkstyle'\n id 'com.github.spotbugs' }\n")
        self.assertEqual(self.ids(AC.detect(self.repo, self.which(set())))["spotbugs"], ("project", "skipped"))

    def test_maven_project_mode(self):
        self.w("pom.xml", "<project><build><plugins><plugin><artifactId>maven-pmd-plugin</artifactId></plugin></plugins></build></project>")
        self.w("src/main/java/a/A.java", "class A {}")
        ps = AC.detect(self.repo, self.which({"mvn", "checkstyle"}))
        pmd = [p for p in ps if p["id"] == "pmd"][0]
        self.assertEqual(pmd["argv"], ["/bin/mvn", "-o", "-q", "pmd:pmd"])
        self.assertEqual(pmd["reports"], [("target", "pmd.xml")])
        self.assertEqual(sorted(self.ids(ps)), ["pmd"])                 # checkstyle CLI on PATH is not used

    def test_java_without_lint_plugin_runs_nothing(self):
        self.w("build.gradle", "plugins { id 'java' }\n")
        self.w("src/main/java/a/A.java", "class A {}")
        ps = AC.detect(self.repo, self.which({"checkstyle", "pmd", "gradle"}))
        self.assertFalse({"checkstyle", "pmd", "spotbugs"} & set(self.ids(ps)))
        self.w("build.gradle", "plugins { id 'java'\n id 'pmd' }\n")
        self.assertEqual(self.ids(AC.detect(self.repo, self.which(set())))["pmd"], ("project", "missing"))

    def test_python_node_go_rust(self):
        self.w("pyproject.toml", "[project]\nname='x'\n\n[tool.ruff]\nline-length = 100\n\n[tool.mypy]\nfiles = ['pkg']\n")
        self.w("pkg/a.py", "")
        self.w("web/package.json", "{}")
        self.w("web/tsconfig.json", "{}")
        self.w("web/node_modules/.bin/tsc", "")
        self.w("go.mod", "module x\n")
        self.w("Cargo.toml", "[package]\n")
        ps = {p["id"]: p for p in AC.detect(self.repo, self.which({"ruff", "mypy", "go"}))}
        self.assertEqual(ps["ruff"]["rules"], "project")
        self.assertNotIn("--isolated", ps["ruff"]["argv"])
        self.assertNotIn(".", ps["mypy"]["argv"])                      # config names its files
        self.assertEqual(ps["tsc"]["cwd"], os.path.join(self.repo, "web"))
        self.assertNotIn("eslint", ps)
        self.assertEqual(ps["govet"]["env"], {"GOPROXY": "off"})
        self.assertEqual((ps["clippy"]["status"], ps["clippy"]["rules"]), ("missing", "project"))

    def test_tsc_solution_style_in_subfolder(self):
        with open(os.path.join(FX, "tsconfig.solution.json"), encoding="utf-8") as f:
            self.w("frontend/tsconfig.json", f.read())
        for x in ("tsconfig.app.json", "tsconfig.node.json", "packages/shared/tsconfig.json", "package.json",
                  "node_modules/.bin/tsc", ".eslintrc.json", "node_modules/.bin/eslint"):
            self.w("frontend/" + x, "{}")
        fe = os.path.join(self.repo, "frontend")
        ps = [p for p in AC.detect(self.repo, self.which(set())) if p["id"] in ("tsc", "eslint")]
        self.assertEqual({p["cwd"] for p in ps}, {fe})
        self.assertEqual([p["argv"][1:3] for p in ps if p["id"] == "tsc"],
                         [["-p", "tsconfig.app.json"], ["-p", "tsconfig.node.json"], ["-p", "packages/shared/tsconfig.json"]])
        self.assertEqual([(p["argv"][1:], p["fallback"][1:]) for p in ps if p["id"] == "eslint"],
                         [(["-f", "json-with-metadata", "."], ["-f", "json", "."])])
        self.w("frontend/src/a.ts")
        self.assertIn("--listFiles", [p for p in ps if p["id"] == "tsc"][0]["argv"])
        out = "src/a.ts(3,1): error TS2304: x\n%s\nsrc/a.ts\n%s\n" % (
            os.path.join(fe, "node_modules/typescript/lib/lib.d.ts"), os.path.join(self.tmp, "outside.ts"))
        st, _w, its, nf = AC.judge([p for p in ps if p["id"] == "tsc"][0], {"rc": 2, "out": out}, self.repo)
        self.assertEqual((st, [x["file"] for x in its], nf), ("ok", ["frontend/src/a.ts"], 1))
        self.w("frontend/tsconfig.json", '{"files": [], "include": ["src"], "references": [{"path": "./tsconfig.app.json"}]}')
        self.assertEqual(AC.tsc_projects(fe), ["tsconfig.json"])        # has its own include: not solution-style
        self.w("frontend/tsconfig.json", "{ broken")
        self.assertEqual(AC.tsc_projects(fe), ["tsconfig.json"])

    def test_merge_tool(self):
        a = {"id": "tsc", "status": "ok", "why": None, "ms": 5, "files": 4}
        AC.merge_tool(a, {"id": "tsc", "status": "fail", "why": "exit 2", "ms": 7, "files": 0})
        AC.merge_tool(a, {"id": "tsc", "status": "ok", "why": None, "ms": 1, "files": 3})
        self.assertEqual(a, {"id": "tsc", "status": "fail", "why": "exit 2", "ms": 13, "files": 7})

    def test_python_without_ruff_config_runs_nothing(self):
        self.w("a.py", "")
        self.assertEqual(AC.detect(self.repo, self.which({"ruff", "mypy"})), [])
        self.w("ruff.toml", "")
        ps = {p["id"]: p for p in AC.detect(self.repo, self.which(set()))}
        self.assertEqual((ps["ruff"]["status"], ps["ruff"]["why"], ps["ruff"]["rules"]), ("missing", AC.SC.install_hint("ruff"), "project"))

    def test_checks_runnable(self):
        with mock.patch.dict(AC._RUNNABLE, clear=True):
            self.w("a.py", "")
            self.w("ruff.toml", "")
            self.assertTrue(AC.checks_runnable(self.repo, self.which({"ruff"}), now=0.0))
            self.assertTrue(AC.checks_runnable(self.repo, self.which(set()), now=10.0))     # cached within the TTL
            self.assertFalse(AC.checks_runnable(self.repo, self.which(set()), now=AC.RUNNABLE_TTL_S + 1.0))   # ruff missing
        with mock.patch.dict(AC._RUNNABLE, clear=True):
            java = os.path.join(self.repo, "j")
            self.w("j/build.gradle", "plugins { id 'java' }\n")
            self.w("j/src/main/java/a/A.java", "class A {}")
            self.assertFalse(AC.checks_runnable(java, self.which({"checkstyle", "pmd", "gradle"}), now=0.0))


CS_FILES = fx("checkstyle.xml").count("<file ")


class JudgeTest(Tmp):
    def test_stdout_items_normalised(self):
        self.w("src/main/java/shop/A.java")
        p = {"id": "checkstyle", "src": "stdout", "cwd": self.repo, "ok_rc": None}
        st, why, its, nf = AC.judge(p, {"rc": 1, "out": fx("checkstyle.xml", self.repo), "err": ""}, self.repo)
        self.assertEqual((st, why, nf), ("ok", None, CS_FILES))
        self.assertEqual({x["file"] for x in its}, {"src/main/java/shop/A.java"})
        self.assertEqual(its[0]["tool"], "checkstyle")

    def test_offline_fail_and_exit(self):
        p = {"id": "checkstyle", "src": "reports", "reports": [("build/reports/checkstyle", None)], "cwd": self.repo}
        r = AC.judge(p, {"rc": 1, "out": "", "err": "No cached version of x available for offline mode.", "t0": 0}, self.repo)
        self.assertEqual(r, ("fail", AC.WHY_OFFLINE, [], 0))
        p2 = {"id": "ruff", "src": "stdout", "cwd": self.repo}
        self.assertEqual(AC.judge(p2, {"rc": 2, "out": "[]", "err": "boom"}, self.repo), ("fail", "exit 2", [], 0))
        self.assertEqual(AC.judge(p2, {"timeout": True}, self.repo)[0], "timeout")

    def test_old_reports_ignored_after_failed_build(self):
        self.w("src/main/java/shop/A.java")
        fp = self.w("build/reports/checkstyle/main.xml", fx("checkstyle.xml", self.repo))
        os.utime(fp, (1000, 1000))
        p = {"id": "checkstyle", "src": "reports", "reports": [("build/reports/checkstyle", None)], "cwd": self.repo}
        self.assertEqual(AC.judge(p, {"rc": 1, "out": "", "err": "", "t0": 5000}, self.repo)[:2], ("fail", "no report (exit 1)"))
        os.utime(fp, (6000, 6000))
        st, _w, its, nf = AC.judge(p, {"rc": 1, "out": "", "err": "", "t0": 5000}, self.repo)
        self.assertEqual((st, len(its), nf), ("ok", 2, CS_FILES))

    def test_files_counts(self):
        res = {"rc": 0, "out": "", "err": ""}
        self.w("x/A.java"), self.w("x/B.java"), self.w("node_modules/C.java"), self.w(".hid/D.java"), self.w("a.py")
        p = {"id": "pmd", "src": "stdout", "cwd": self.repo, "ok_rc": (0, 4)}
        self.assertEqual(AC.judge(p, dict(res, out="<pmd></pmd>"), self.repo)[3], 2)
        for tid, n in (("ruff", 1), ("govet", 0), ("clippy", 0)):
            self.assertEqual(AC.judge(dict(p, id=tid), dict(res, out="[]" if tid == "ruff" else ""), self.repo)[3], n)
        esl = {"id": "eslint", "src": "stdout", "cwd": self.repo, "ok_rc": (0, 1)}
        self.assertEqual(AC.judge(esl, dict(res, out='{"results": [{"messages": []}, {"messages": []}]}'), self.repo)[3], 2)
        self.assertEqual(AC.judge(esl, dict(res, out='[{"messages": []}]'), self.repo)[3], 1)
        my = {"id": "mypy", "src": "stdout", "cwd": self.repo, "ok_rc": (0, 1)}
        self.assertEqual(AC.judge(my, dict(res, out="Success: no issues found in 7 source files\n"), self.repo)[3], 7)
        out = "a.py:1: error: x  [name-defined]\nFound 1 error in 1 file (checked 9 source files)\n"
        st, _w, its, nf = AC.judge(my, dict(res, rc=1, out=out), self.repo)
        self.assertEqual((st, len(its), nf), ("ok", 1, 9))
        self.assertEqual(AC.judge(p, {"timeout": True}, self.repo)[3], 0)


class FindReportsTest(Tmp):
    def test_skips_and_dangling(self):
        spec = [("build/reports/checkstyle", None), ("target", "pmd.xml")]
        want = [self.w("m/build/reports/checkstyle/main.xml"), self.w("target/pmd.xml")]
        self.w("node_modules/x/build/reports/checkstyle/main.xml")
        self.w(".git/build/reports/checkstyle/main.xml")
        self.w("target/sub/target/pmd.xml")                     # never below target/
        self.w("m/build/classes/build/reports/checkstyle/x.xml")  # build/ entered only for reports/
        os.symlink(os.path.join(self.tmp, "gone"), os.path.join(self.repo, "m/build/reports/checkstyle/dead.xml"))
        self.assertEqual(AC.find_reports(self.repo, spec), sorted(want))


class ExecTest(unittest.TestCase):
    def test_timeout_drain_is_bounded(self):
        import subprocess
        c, seen = cli(), []

        class P:
            pid, returncode = 99999999, None

            def communicate(self, timeout=None):
                seen.append(timeout)
                raise subprocess.TimeoutExpired("x", timeout)

            def kill(self):
                seen.append("kill")
        with mock.patch.object(c.subprocess, "Popen", lambda *a, **k: P()), \
                mock.patch.object(c.os, "killpg", mock.Mock(side_effect=OSError)):
            r = c._exec({"argv": ["x"], "cwd": "/"}, 3, "/t")
        self.assertTrue(r["timeout"])
        self.assertEqual(seen, [3, "kill", 10])


class RunnerTest(Tmp):
    def setUp(self):
        super().setUp()
        self.store = os.path.join(self.tmp, "store")
        self.cli = cli()
        self.w("a.py", "x = 1\n")
        self.w("ruff.toml", "")
        self.por = ["", ""]
        git = lambda repo, args: (C1 + "\n") if args[0] == "rev-parse" else self.por.pop(0)
        out = json.dumps([{"code": "F401", "filename": os.path.join(self.repo, "a.py"), "location": {"row": 1},
                           "url": "https://docs.astral.sh/ruff/rules/unused-import", "message": "secret"}])
        self.p = [mock.patch.object(AV, "ARCH_DIR", self.store), mock.patch.object(self.cli, "_git", git),
                  mock.patch.object(self.cli, "_which", lambda n: "/bin/" + n if n == "ruff" else None),
                  mock.patch.object(self.cli, "_exec", lambda p, t, tmp: {"rc": 0, "out": out, "err": "", "t0": 0, "ms": 5})]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        super().tearDown()

    def test_run_writes_and_verifies(self):
        self.por = ["", "?? new.txt\n"]
        rc, line = self.cli.run(self.repo)
        self.assertEqual((rc, line), (0, "arch_checks: 1 tools · 0 errors · 1 warnings · source changed by a tool"))
        j = AV.read_json(os.path.join(self.store, AV.repo_key(self.repo), C1, AC.CHECKS_FILE))
        self.assertEqual((j["commit"], j["dirty"], j["src_changed"]), (C1, False, True))
        self.assertEqual(j["files"], {"a.py": {"error": 0, "warning": 1}})
        self.assertEqual(j["rules"], {"ruff:F401": {"desc": "unused import", "url": "https://docs.astral.sh/ruff/rules/unused-import"}})
        self.assertEqual(AC.checks_errors(dict(j, rules={"ruff:F401": {"desc": "", "url": "http://x"}})), ["rules"])
        self.assertEqual(AC.checks_errors(j, self.repo, C1), [])
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(self.cli.main(["--verify", "--last"]), 0)
        self.assertEqual(j["tools"][0]["files"], 1)
        self.assertEqual(AC.checks_errors(dict(j, tools=[dict(j["tools"][0], ms=True)])), ["tools[0]"])
        for bad in (True, -1, "3", None):
            self.assertEqual(AC.checks_errors(dict(j, tools=[dict(j["tools"][0], files=bad)])), ["tools[0]"])
        t = dict(j["tools"][0])
        del t["files"]
        self.assertEqual(AC.checks_errors(dict(j, tools=[t])), ["tools[0]"])
        j["items"][0]["msg"] = "leak"
        with open(os.path.join(self.store, AV.repo_key(self.repo), C1, AC.CHECKS_FILE), "w") as f:
            json.dump(j, f)
        with redirect_stdout(out):
            self.assertEqual(self.cli.main(["--verify", "--last"]), 1)

    def rewrite(self, tools):
        fp = os.path.join(self.store, AV.repo_key(self.repo), C1, AC.CHECKS_FILE)
        j = AV.read_json(fp)
        j["tools"] = tools
        with open(fp, "w") as f:
            json.dump(j, f)

    def test_verify_empty(self):
        self.cli.run(self.repo)
        ok = {"id": "ruff", "rules": "default", "status": "ok", "ms": 1, "files": 1, "n": {"error": 0, "warning": 0}}
        miss = dict(ok, status="missing", why="install: brew install ruff", files=0)
        for tools, rc, want in (([ok], 0, "arch_checks: 1 tools"),
                                ([dict(ok, files=0)], 1, "arch_checks: EMPTY: ruff examined 0 files"),
                                ([miss, dict(miss, id="pmd", why=None)], 1,
                                 "arch_checks: EMPTY: no tool ran (missing: ruff (install: brew install ruff), pmd)"),
                                ([], 1, "arch_checks: EMPTY: the repo configures no checks — skip the stage")):
            self.rewrite(tools)
            rc2, line = self.cli.verify(self.repo, C1)
            self.assertEqual(rc2, rc, line)
            self.assertTrue(line.startswith(want), line)
        self.assertIn("[pl-skip:project-checks/", line)

    def test_porcelain_same_is_not_changed(self):
        self.por = [" M a.py\n", " M a.py\n"]
        self.cli.run(self.repo)
        j = AV.read_json(os.path.join(self.store, AV.repo_key(self.repo), C1, AC.CHECKS_FILE))
        self.assertEqual((j["dirty"], j["src_changed"]), (True, False))

    def test_usage(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(self.cli.main([]), 2)
            self.assertEqual(self.cli.main(["--verify", "--last"]), 1)     # nothing written yet


class LoadTest(Tmp):
    def setUp(self):
        super().setUp()
        self.rdir = os.path.join(self.tmp, "store", AV.repo_key(self.repo))
        self.mdir = os.path.join(self.rdir, C1)
        os.makedirs(self.mdir)
        self.m = {"modules": [{"id": "web", "name": "web", "path": "web", "kind": "module"},
                              {"id": "core", "name": "core", "path": "core", "kind": "module"},
                              {"id": "db", "name": "DB", "path": "", "kind": "external"}]}

    def put(self, commit, files, items, **kw):
        d = os.path.join(self.rdir, commit)
        os.makedirs(d, exist_ok=True)
        j = {"v": 1, "repo": self.repo, "commit": commit, "dirty": False, "src_changed": False, "at": 123.0,
             "tools": [{"id": "ruff", "rules": "project", "status": "ok", "ms": 3, "files": 5, "n": {"error": 1, "warning": 2}},
                       {"id": "nope", "rules": "x", "status": "ok", "ms": 0, "n": {}}],
             "files": files, "items": items}
        j.update(kw)
        with open(os.path.join(d, AC.CHECKS_FILE), "w") as f:
            json.dump(j, f)

    def test_none_without_file(self):
        self.assertIsNone(AC.load_checks(self.repo, self.mdir, self.m, C1))

    def test_aggregate_and_sanitise(self):
        with open(os.path.join(self.mdir, "plan.json"), "w") as f:
            json.dump({"modules": [{"id": "core", "globs": ["lib/*"]}]}, f)
        files = {"web/a.py": {"error": 1, "warning": 0}, "lib/b.py": {"error": 0, "warning": 2},
                 "tools/c.py": {"error": 0, "warning": 1}, "../x.py": {"error": 9, "warning": 9}}
        items = [{"tool": "ruff", "file": "web/a.py", "line": 3, "rule": "E9", "sev": "error"},
                 {"tool": "ruff", "file": "lib/b.py", "line": 1, "rule": "bad rule!", "sev": "warning"},
                 {"tool": "ruff", "file": "../x.py", "line": 1, "rule": "F1", "sev": "warning"},
                 {"tool": "ruff", "file": "lib/b.py", "line": 2, "rule": "F2", "sev": "warning", "msg": "secret"}]
        self.put(C1, files, items, rules={"ruff:E9": {"desc": "syntax error", "url": "https://docs.astral.sh/ruff/rules/e9"},
                                          "ruff:F2": {"desc": "x", "url": "http://insecure"}, "ruff:F9": {"desc": "unused"}})
        c = AC.load_checks(self.repo, self.mdir, self.m, C1)
        self.assertEqual(set(c), {"commit", "at", "stale", "dirty", "src_changed", "tools", "mods", "other", "top", "rules",
                                  "security"})
        self.assertIsNone(c["security"])
        self.assertEqual(c["mods"], {"web": {"error": 1, "warning": 0}, "core": {"error": 0, "warning": 2}})
        self.assertEqual(c["other"], {"error": 0, "warning": 1})
        self.assertEqual([(t["id"], t["files"]) for t in c["tools"]], [("ruff", 5)])
        self.assertEqual(c["top"], [{"tool": "ruff", "file": "web/a.py", "line": 3, "rule": "E9", "sev": "error", "mod": "web",
                                     "rk": "ruff:E9"},
                                    {"tool": "ruff", "file": "lib/b.py", "line": 2, "rule": "F2", "sev": "warning", "mod": "core",
                                     "rk": "ruff:F2"}])
        self.assertEqual(c["rules"], {"ruff:E9": {"desc": "syntax error", "url": "https://docs.astral.sh/ruff/rules/e9"},
                                      "ruff:F2": {"desc": "x", "url": ""}})      # insecure url dropped, unused F9 not sent
        self.assertNotIn("secret", json.dumps(c))
        self.assertFalse(c["stale"])

    def test_stale_and_foreign_repo(self):
        self.put(C2, {}, [])
        self.assertTrue(AC.load_checks(self.repo, self.mdir, self.m, C1)["stale"])
        self.put(C2, {}, [], repo="/elsewhere")
        self.assertIsNone(AC.load_checks(self.repo, self.mdir, self.m, C1))


if __name__ == "__main__":
    unittest.main()
