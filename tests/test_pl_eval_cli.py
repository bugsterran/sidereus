"""scripts/pl_eval.py: seeds / score / redcheck against temp git repos (fake producer via patched _run, fake which)."""
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tests._load import ROOT, sidereus

PE = sidereus("pl_eval")
AV = sidereus("arch_verify")
NOW = 1_800_000_000.0
SGATE = "/usr/bin/python3 scripts/arch_checks.py --verify --last --category security"


def cli():
    spec = importlib.util.spec_from_file_location("pl_eval_cli", os.path.join(ROOT, "scripts", "pl_eval.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m._now = lambda: NOW
    return m


def rd(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def git(repo, *args):
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "core.hooksPath=/dev/null",
                           "-C", repo] + list(args), check=True, capture_output=True, text=True, env=env, encoding="utf-8").stdout


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-plevalcli-"))
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        self.ev = os.path.join(self.tmp, "ev.jsonl")
        for mod, k, v in ((PE, "EVAL_DIR", os.path.join(self.tmp, "eval")), (AV, "ARCH_DIR", os.path.join(self.tmp, "arch"))):
            p = mock.patch.object(mod, k, v)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.dict(os.environ, {"SIDEREUS_EVIDENCE": self.ev})
        p.start()
        self.addCleanup(p.stop)
        self.cli = cli()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def w(self, rel, text):
        fp = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(text)
        return fp

    def commit(self, stages):
        self.w(".claude/pipelines/p.json", json.dumps({"v": 1, "name": "p", "stages": stages}))
        git(self.repo, "init", "-q")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "c")
        return git(self.repo, "rev-parse", "HEAD").strip()

    def main(self, *a):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.cli.main(list(a))
        return rc, buf.getvalue()

    def rows(self):
        if not os.path.exists(self.ev):
            return []
        with open(self.ev, encoding="utf-8") as f:
            return [json.loads(x) for x in f]

    def pfile(self):
        return os.path.join(self.repo, ".claude", "pipelines", "p.json")


class SeedsScore(Base):
    def test_seeds_and_score(self):
        head = self.commit([{"title": "검사 실행", "agent": "x", "gate": SGATE}, {"title": "리뷰", "agent": "x"}])
        sf = os.path.join(self.tmp, "seeds.json")
        with open(sf, "w", encoding="utf-8") as f:
            json.dump({"v": 1, "seeds": [
                {"id": "pub-a", "kind": "secret", "file": "src/a.cfg", "line": 5, "rule": "generic-api-key", "expectStage": "검사 실행"},
                {"id": "pub-b", "kind": "logic", "file": "src/a.ts", "line": 9, "expectStage": "리뷰"},
                {"id": "hidden-holdout-x", "kind": "secret", "file": "src/a.cfg", "line": 20, "expectStage": "검사 실행",
                 "holdout": True}]}, f)
        rc, out = self.main("seeds", "--repo", self.repo, "--set", sf)
        self.assertEqual((rc, out.strip()), (0, "seeds: 3 (public 2 · holdout 1)"))
        self.assertEqual(self.main("seeds", "--repo", self.repo, "--check")[0], 0)
        d = os.path.join(AV.ARCH_DIR, AV.repo_key(self.repo), head)
        os.makedirs(d)
        with open(os.path.join(d, "checks-security.json"), "w", encoding="utf-8") as f:
            json.dump({"items": [{"tool": "gitleaks", "file": "src/a.cfg", "line": 6, "rule": "generic-api-key", "sev": "error"},
                                 {"tool": "gitleaks", "file": "src/a.cfg", "line": 21, "rule": "x", "sev": "error"}]}, f)
        rc, out = self.main("score", "--repo", self.repo, "--pipeline", self.pfile())
        self.assertEqual((rc, out.strip()), (1, "caught 1/2 · holdout 1/1"))
        ff = os.path.join(self.tmp, "f.json")
        with open(ff, "w", encoding="utf-8") as f:
            json.dump([{"file": "src/a.ts", "line": 10}], f)
        rc, out = self.main("score", "--repo", self.repo, "--pipeline", self.pfile(), "--findings", ff)
        self.assertEqual((rc, out.strip()), (0, "caught 2/2 · holdout 1/1"))
        raw = json.dumps(self.rows()) + out + rd(PE.EVAL_DIR, AV.repo_key(self.repo), head, "eval.json")
        self.assertNotIn("hidden-holdout-x", raw)
        self.assertEqual([(r["kind"], r["mode"], r["rc"]) for r in self.rows()], [("eval", "eval-catch", 1), ("eval", "eval-catch", 0)])
        self.assertEqual(self.main("seeds", "--repo", self.repo)[0], 2)   # usage

    def test_bad_seeds_print_no_ids(self):
        sf = os.path.join(self.tmp, "seeds.json")
        with open(sf, "w", encoding="utf-8") as f:
            json.dump({"v": 1, "seeds": [{"id": "ok-1", "kind": "secret", "file": "../x", "expectStage": "s", "holdout": True}]}, f)
        rc, out = self.main("seeds", "--repo", self.repo, "--set", sf)
        self.assertEqual(rc, 1)
        self.assertNotIn("ok-1", out)
        self.assertEqual(self.main("seeds", "--repo", self.repo, "--check")[0], 1)

    def test_auto_scores_once_per_commit(self):
        head = self.commit([{"title": "리뷰", "agent": "x"}])
        self.cli._sleep = lambda s: None
        self.assertEqual(self.main("score", "--repo", self.repo, "--pipeline", self.pfile(), "--auto")[0], 2)   # no seeds yet
        PE.save_seeds(self.repo, {"v": 1, "seeds": [{"id": "a", "kind": "logic", "file": "a.py", "expectStage": "리뷰"}]})
        rc, out = self.main("score", "--repo", self.repo, "--pipeline", self.pfile(), "--auto")
        self.assertEqual((rc, out.strip()), (1, "caught 0/1 · holdout 0/0"))
        rc, out = self.main("score", "--repo", self.repo, "--pipeline", self.pfile(), "--auto")
        self.assertEqual((rc, out.strip()), (0, "score: already scored at this commit"))
        self.assertEqual(len(self.rows()), 1)
        self.assertTrue(os.path.isfile(os.path.join(PE.EVAL_DIR, AV.repo_key(self.repo), head, "auto-p")))
        self.assertEqual(self.main("score", "--repo", self.repo, "--pipeline", self.pfile())[0], 1)   # manual score is never deduped
        cf = os.path.join(PE.EVAL_DIR, AV.repo_key(self.repo), head, "auto-p")
        self.assertEqual(rd(cf), "done")
        with open(cf, "w", encoding="utf-8") as f:
            f.write("run")   # crashed earlier run: retaken only once stale
        self.assertIn("already", self.main("score", "--repo", self.repo, "--pipeline", self.pfile(), "--auto")[1])
        os.utime(cf, (1, 1))
        self.assertEqual(self.main("score", "--repo", self.repo, "--pipeline", self.pfile(), "--auto")[0], 1)
        self.assertEqual(rd(cf), "done")

    def test_auto_since_needs_a_landed_commit(self):
        head = self.commit([{"title": "리뷰", "agent": "x"}])
        self.cli._sleep = lambda s: None
        PE.save_seeds(self.repo, {"v": 1, "seeds": [{"id": "a", "kind": "logic", "file": "a.py", "expectStage": "리뷰"}]})
        ct = int(git(self.repo, "log", "-1", "--format=%ct").strip())
        rc, out = self.main("score", "--repo", self.repo, "--pipeline", self.pfile(), "--auto", "--since", str(ct + 60))
        self.assertEqual((rc, out.strip()), (0, "score: the commit did not land"))   # denied/cancelled commit: old HEAD
        self.assertFalse(os.path.exists(os.path.join(PE.EVAL_DIR, AV.repo_key(self.repo), head, "auto-p")))
        self.assertEqual(self.main("score", "--repo", self.repo, "--pipeline", self.pfile(), "--auto", "--since", str(ct))[0], 1)


class Red(Base):
    def red(self, title="검증"):
        before = git(self.repo, "status", "--porcelain")
        rc, out = self.main("redcheck", "--pipeline", self.pfile(), "--stage", title, "--repo", self.repo, "--timeout", "60")
        return rc, out.strip(), before

    def entry(self, gate):
        with open(os.path.join(PE.EVAL_DIR, "redcheck.json"), encoding="utf-8") as f:
            return json.load(f)["gates"][PE.gate_key(gate)]

    def test_fast_pass_fail_and_target_changed(self):
        self.w("mod.py", "x = 1\n")
        self.w("check.sh", 'for f in *.py; do /usr/bin/python3 -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" "$f" || exit 1; done\n')
        self.commit([{"title": "검증", "agent": "x", "gate": "bash check.sh --fast"}])
        rc, out, before = self.red()
        self.assertEqual((rc, out), (0, "redcheck: pass — gate rc 1 on a broken repo"))
        self.assertEqual(git(self.repo, "status", "--porcelain"), before)   # the target never saw the break
        e = self.entry("bash check.sh --fast")
        self.assertEqual((e["verdict"], e["mode"], e["stage"], e["pipeline"], e["key"]), ("pass", "fast", "검증", "p", AV.repo_key(self.repo)))
        self.assertEqual([(r["kind"], r["mode"], r["rc"], r["steps"][0]["name"]) for r in self.rows()], [("red", "redcheck", 0, "fast")])
        with mock.patch.object(self.cli, "_which", lambda n: None):
            self.assertEqual(self.red()[:2], (2, "redcheck: skip — tool missing: bash"))

    def test_fast_never_red(self):
        self.w("mod.py", "x = 1\n")
        self.w("check.sh", "exit 0\n")
        self.commit([{"title": "검증", "agent": "x", "gate": "bash check.sh --fast"}])
        self.assertEqual(self.red()[:2], (1, "redcheck: fail — gate passed on a broken repo"))

    def test_target_changed(self):
        self.w("mod.py", "x = 1\n")
        self.w("check.sh", "echo x > %s/stray.txt\nexit 1\n" % self.repo)
        self.commit([{"title": "검증", "agent": "x", "gate": "bash check.sh --fast"}])
        self.assertEqual(self.red()[:2], (1, "redcheck: fail — target changed"))

    def fake_run(self, status="ok", report=True):
        def run(argv, cwd, env, timeout):
            if "--repo" in argv:   # producer: write the temp store's checks-security.json like scripts/arch_checks.py would
                clone = argv[argv.index("--repo") + 1]
                head = git(clone, "rev-parse", "HEAD").strip()
                self.assertTrue(rd(clone, "sidereus-redcheck.cfg").startswith('api_key = "'))
                d = os.path.join(env["MAILBOX_DIR"], "arch", AV.repo_key(clone), head)
                os.makedirs(d)
                items = [{"tool": "gitleaks", "file": "sidereus-redcheck.cfg", "line": 1, "rule": "generic-api-key",
                          "sev": "error"}] if report else []
                with open(os.path.join(d, "checks-security.json"), "w", encoding="utf-8") as f:
                    json.dump({"tools": [{"id": "gitleaks", "status": status}], "items": items}, f)
            self.assertTrue(env["SIDEREUS_EVIDENCE"].startswith(env["MAILBOX_DIR"].rsplit("/", 1)[0]))
            return 0, False
        return run

    def test_checks_security(self):
        self.commit([{"title": "검사 실행", "agent": "x", "gate": SGATE}])
        for kw, want in (({}, (0, "redcheck: pass — injected item reported")),
                         ({"report": False}, (1, "redcheck: fail — injected break not reported")),
                         ({"status": "missing"}, (2, "redcheck: skip — tool missing: gitleaks"))):
            with mock.patch.object(self.cli, "_run", self.fake_run(**kw)):
                self.assertEqual(self.red("검사 실행")[:2], want)
            self.assertEqual(self.entry(SGATE)["verdict"], ("pass", "fail", "skip")[want[0]])
        self.assertEqual([r["rc"] for r in self.rows()], [0, 1, 2])
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_inject_security_and_no_source(self):
        self.commit([{"title": "s", "agent": "x"}])
        exp, why = self.cli.inject("checks-security", self.repo)
        self.assertEqual(exp, [{"kind": "secret", "file": "sidereus-redcheck.cfg", "line": 1}])
        self.assertTrue(rd(self.repo, "sidereus-redcheck.cfg").startswith('api_key = "'))
        self.assertEqual(self.cli.inject("fast", self.repo), (None, "no .py file to break"))
        self.assertEqual(self.main("redcheck", "--pipeline", self.pfile(), "--stage", "s", "--repo", self.repo)[0], 2)


if __name__ == "__main__":
    unittest.main()
