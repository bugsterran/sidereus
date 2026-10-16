"""Security checks runner (subprocess and git patched): run, gate, usage, and the /api/arch `checks` loader.
Scanner plans / parsers / secrets: tests/test_sec_checks.py; security log: tests/test_sec_log.py."""
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
AV = sidereus("arch_verify")
SC = sidereus("sec_checks")
C1, C2 = "a" * 40, "b" * 40


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


BANDIT = {"results": [{"filename": "./a.py", "line_number": 1, "test_id": "B105", "issue_severity": "LOW",
                       "more_info": "https://bandit.readthedocs.io/en/latest/plugins/b105_hardcoded_password_string.html",
                       "test_name": "hardcoded_password_string", "code": "secret", "issue_text": "secret"}],
          "metrics": {"./a.py": {}, "_totals": {}}}


class RunnerTest(Tmp):
    def setUp(self):
        super().setUp()
        self.store = os.path.join(self.tmp, "store")
        self.cli = cli()
        self.w("a.py", "x = 1\n")
        self.por = ["", ""]
        git = lambda repo, args: (C1 + "\n") if args[0] == "rev-parse" else self.por.pop(0)
        out = json.dumps(BANDIT)
        self.p = [mock.patch.object(AV, "ARCH_DIR", self.store), mock.patch.object(self.cli, "_git", git),
                  mock.patch.object(self.cli, "_which", lambda n: "/bin/" + n if n == "bandit" else None),
                  mock.patch.object(self.cli, "_exec", lambda p, t, tmp: {"rc": 1, "out": out, "err": "", "t0": 0, "ms": 5})]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        super().tearDown()

    def fp(self):
        return os.path.join(self.store, AV.repo_key(self.repo), C1, SC.SEC_FILE)

    def main(self, *a):
        with redirect_stdout(io.StringIO()) as out:
            rc = self.cli.main(list(a))
        return rc, out.getvalue()

    def test_run_writes_and_verifies(self):
        self.por = ["", "?? new.txt\n"]
        rc, line = self.cli.run(self.repo)
        self.assertEqual((rc, line.split(" · gitleaks")[0].split(" · missing")[0]),
                         (0, "arch_checks: security · 1 tools · 0 errors · 1 warnings"))
        self.assertTrue(line.endswith(" · source changed by a tool"), line)
        j = AV.read_json(self.fp())
        self.assertEqual((j["commit"], j["dirty"], j["src_changed"]), (C1, False, True))
        self.assertEqual(j["files"], {"a.py": {"error": 0, "warning": 1}})
        self.assertNotIn("secret", json.dumps(j))
        self.assertEqual(AC.checks_errors(j, self.repo, C1, SC.SEC_IDS), [])
        self.assertEqual(AC.checks_errors(j), ["rules", "tools[0]", "tools[1]", "tools[2]", "items"])   # no ids: nothing accepted
        self.assertEqual(self.main("--verify", "--last", "--category", "security")[0], 0)
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(self.fp()), "checks.json")))
        j["items"][0]["msg"] = "leak"
        with open(self.fp(), "w") as f:
            json.dump(j, f)
        self.assertEqual(self.main("--verify", "--last", "--category", "security")[0], 1)

    def rewrite(self, tools):
        j = AV.read_json(self.fp())
        j["tools"] = tools
        with open(self.fp(), "w") as f:
            json.dump(j, f)

    def test_verify_empty(self):
        self.cli.run(self.repo)
        ok = {"id": "bandit", "rules": "default", "status": "ok", "ms": 1, "files": 1, "n": {"error": 0, "warning": 0}}
        miss = dict(ok, status="missing", why="install: pip install bandit", files=0)
        for tools, rc, want in (([ok], 0, "arch_checks: security · 1 tools"),
                                ([dict(ok, files=0)], 1, "arch_checks: EMPTY: bandit examined 0 files"),
                                ([miss, dict(miss, id="semgrep", why=None)], 1,
                                 "arch_checks: EMPTY: no tool ran (missing: bandit (install: pip install bandit), semgrep)"),
                                ([], 1, "arch_checks: EMPTY: the repo configures no checks — skip the stage")):
            self.rewrite(tools)
            rc2, line = self.cli.verify(self.repo, C1)
            self.assertEqual(rc2, rc, line)
            self.assertTrue(line.startswith(want), line)
        self.assertIn("[pl-skip:security-checks/", line)

    def test_porcelain_same_is_not_changed(self):
        self.por = [" M a.py\n", " M a.py\n"]
        self.cli.run(self.repo)
        j = AV.read_json(self.fp())
        self.assertEqual((j["dirty"], j["src_changed"]), (True, False))

    def test_usage(self):
        self.assertEqual(self.main()[0], 2)
        self.assertEqual(self.main("--verify", "--last", "--category", "security")[0], 1)   # nothing written yet
        for a in (["--repo", self.repo, "--category", "quality"], ["--verify", "--last", "--category", "quality"],
                  ["--repo", self.repo, "--category", "security", "--only", "ruff"]):
            self.assertEqual(self.main(*a)[0], 2, a)
        rc, out = self.main("--repo", self.repo)          # ⚠no category: never a silent pass, nothing written
        self.assertEqual((rc, out.strip()), (1, "arch_checks: --category security required"))
        self.assertEqual(self.main("--verify", "--last")[0], 1)
        self.assertFalse(os.path.exists(self.fp()))


class LoadTest(Tmp):
    def setUp(self):
        super().setUp()
        self.rdir = os.path.join(self.tmp, "store", AV.repo_key(self.repo))
        self.mdir = os.path.join(self.rdir, C1)
        os.makedirs(self.mdir)
        self.m = {"modules": [{"id": "web", "name": "web", "path": "web", "kind": "module"},
                              {"id": "core", "name": "core", "path": "core", "kind": "module"},
                              {"id": "db", "name": "DB", "path": "", "kind": "external"}]}

    def put(self, commit, files, items, name=None, **kw):
        d = os.path.join(self.rdir, commit)
        os.makedirs(d, exist_ok=True)
        j = {"v": 1, "repo": self.repo, "commit": commit, "dirty": False, "src_changed": False, "at": 123.0,
             "tools": [{"id": "bandit", "rules": "default", "status": "ok", "ms": 3, "files": 5, "n": {"error": 1, "warning": 2}},
                       {"id": "nope", "rules": "x", "status": "ok", "ms": 0, "n": {}}],
             "files": files, "items": items}
        j.update(kw)
        with open(os.path.join(d, name or SC.SEC_FILE), "w") as f:
            json.dump(j, f)

    def test_none_without_security(self):
        self.assertIsNone(AC.load_checks(self.repo, self.mdir, self.m, C1))
        self.put(C1, {}, [], name="checks.json")        # a leftover lint result is never read
        self.assertIsNone(AC.load_checks(self.repo, self.mdir, self.m, C1))

    def test_aggregate_and_sanitise(self):
        with open(os.path.join(self.mdir, "plan.json"), "w") as f:
            json.dump({"modules": [{"id": "core", "globs": ["lib/*"]}]}, f)
        files = {"web/a.py": {"error": 1, "warning": 0}, "lib/b.py": {"error": 0, "warning": 2},
                 "tools/c.py": {"error": 0, "warning": 1}, "../x.py": {"error": 9, "warning": 9}}
        items = [{"tool": "bandit", "file": "web/a.py", "line": 3, "rule": "B105", "sev": "error"},
                 {"tool": "bandit", "file": "lib/b.py", "line": 1, "rule": "bad rule!", "sev": "warning"},
                 {"tool": "bandit", "file": "../x.py", "line": 1, "rule": "B1", "sev": "warning"},
                 {"tool": "bandit", "file": "lib/b.py", "line": 2, "rule": "B2", "sev": "warning", "msg": "secret"}]
        self.put(C1, files, items, rules={"bandit:B105": {"desc": "hardcoded password", "url": "https://bandit.readthedocs.io/b105"},
                                          "bandit:B2": {"desc": "x", "url": "http://insecure"}, "bandit:B9": {"desc": "unused"}})
        c = AC.load_checks(self.repo, self.mdir, self.m, C1)
        shell = {"commit": "", "at": None, "stale": False, "dirty": False, "src_changed": False, "tools": [], "mods": {},
                 "other": {"error": 0, "warning": 0}, "top": [], "rules": {}}
        self.assertEqual({k: v for k, v in c.items() if k != "security"}, shell)   # payload shape kept for the page
        s = c["security"]
        self.assertEqual(set(s), set(shell) | {"log"})
        self.assertEqual(s["mods"], {"web": {"error": 1, "warning": 0}, "core": {"error": 0, "warning": 2}})
        self.assertEqual(s["other"], {"error": 0, "warning": 1})
        self.assertEqual([(t["id"], t["files"]) for t in s["tools"]], [("bandit", 5)])
        self.assertEqual(s["top"], [{"tool": "bandit", "file": "web/a.py", "line": 3, "rule": "B105", "sev": "error", "mod": "web",
                                     "rk": "bandit:B105"},
                                    {"tool": "bandit", "file": "lib/b.py", "line": 2, "rule": "B2", "sev": "warning", "mod": "core",
                                     "rk": "bandit:B2"}])
        self.assertEqual(s["rules"], {"bandit:B105": {"desc": "hardcoded password", "url": "https://bandit.readthedocs.io/b105"},
                                      "bandit:B2": {"desc": "x", "url": ""}})      # insecure url dropped, unused B9 not sent
        self.assertNotIn("secret", json.dumps(c))
        self.assertFalse(s["stale"])

    def test_stale_and_foreign_repo(self):
        self.put(C2, {}, [])
        self.assertTrue(AC.load_checks(self.repo, self.mdir, self.m, C1)["security"]["stale"])
        self.put(C2, {}, [], repo="/elsewhere")
        self.assertIsNone(AC.load_checks(self.repo, self.mdir, self.m, C1))


class NoLintPipeline(unittest.TestCase):
    """The removed lint pipeline is named in no tracked text file (CHANGELOG keeps history). Reads `git ls-files` only."""
    OLD = "project" + "-checks"   # ⚠built from two halves so this file does not match itself

    def test_contents(self):
        import subprocess
        out = subprocess.run(["git", "-C", ROOT, "ls-files", "-z"], stdout=subprocess.PIPE, check=True).stdout
        bad = []
        for p in out.decode("utf-8", "surrogateescape").split("\0"):
            fp = os.path.join(ROOT, p)
            if not p or p == "CHANGELOG.md" or not os.path.isfile(fp) or os.path.islink(fp):
                continue
            with open(fp, "rb") as fh:
                data = fh.read()
            if b"\0" not in data and self.OLD.encode() in data:
                bad.append(p)
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
