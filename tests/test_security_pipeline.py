"""security-checks pipeline file: threat-model review stage contract (repo file, not live data); one Markdown report
per runner run with deps lines for this checkout only (git, tools and deps_audit stubbed)."""
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

D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".claude", "pipelines")


def _load(name):
    with open(os.path.join(D, name), encoding="utf-8") as f:
        return json.load(f)


class SecurityPipelineTest(unittest.TestCase):
    def setUp(self):
        self.d = _load("security-checks.json")
        self.st = self.d["stages"]

    def test_stage_fields(self):
        self.assertEqual([s["title"] for s in self.st], ["보안 검사", "위협 모델 리뷰"])
        s = self.st[1]
        self.assertEqual((s["agent"], s["model"]), ("general-purpose", "opus"))
        self.assertNotIn("gate", s)
        self.assertIn("gate", self.st[0])

    def test_task_contract(self):
        t = self.st[1]["task"]
        for w in ("<repo>/.oss-scanner/threat_model.md", "<repo>/threat_model.md",
                  "no threat model — copy <sidereus>/templates/oss-scanner/ to <repo>/.oss-scanner/",
                  "--log-show", "--mark <slug>@<file> resolved", "--log-review",
                  "Never quote", "unverified", "in-scope", "severity rubric", "no installs"):
            self.assertIn(w, t)
        self.assertLess(t.index("--log-show"), t.index("--mark"))
        self.assertLess(t.index("--mark"), t.index("--log-review"))

    def test_review_without_threat_model_and_project_agent(self):
        t = self.st[1]["task"]
        self.assertIn("[pl-agent:security-checks/%s=<agent>]" % self.st[1]["title"], t)
        self.assertLess(t.index("no threat model"), t.index("default lens"))   # hint, then review anyway
        for w in ("IDOR", "MyBatis `${}`", "SSRF", "deserialize"):
            self.assertIn(w, t)
        self.assertNotIn("log nothing", t)

    def test_never_marks_false_positive(self):
        t = self.st[1]["task"]
        self.assertIn("NEVER mark false-positive", t)
        self.assertNotIn("false-positive [", t)
        self.assertNotIn("--mark <slug>@<file> false-positive", t)

    def test_images_flag_only_on_request(self):
        t = self.st[0]["task"]
        self.assertIn("Add `--images` only when the request asks to include images.", t)
        self.assertNotIn("--images", self.st[0]["gate"])

    def test_rules_name_log(self):
        self.assertIn("security-log.jsonl", self.d["rules"])
        self.assertIn("--log-review", self.d["rules"])

    def test_monthly_alongside_deps_audit(self):
        d = _load("deps-audit.json")
        self.assertIn("security-checks", d["use"])
        self.assertIn("security-checks", d["rules"])

    def test_audit_stages_run_the_report(self):
        for name, dev in (("deps-audit.json", False), ("release.json", True)):
            t = _load(name)["stages"][0]["task"]
            self.assertIn("scripts/arch_checks.py --repo", t)
            self.assertEqual("--dev" in t, dev, name)
            self.assertIn("· report", t)

    def test_ci_stage_fails_reruns(self):
        st = [x for x in _load("release.json")["stages"] if x["title"] == "CI 확인"]
        self.assertEqual(len(st), 1)
        self.assertIn("attempt > 1 or that has a re-run job is reported as FAIL", st[0]["task"])
        self.assertIn("gh run view <id> --json attempt", st[0]["task"])


AV = sidereus("arch_verify")
SR = sidereus("sec_report")
BANDIT = {"results": [{"filename": "./a.py", "line_number": 1, "test_id": "B105", "issue_severity": "LOW",
                       "issue_text": "PLANTED-MESSAGE"}], "metrics": {"./a.py": {}, "_totals": {}}}


class ReportRun(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("arch_checks_cli_rep", os.path.join(ROOT, "scripts", "arch_checks.py"))
        self.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cli)
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-secrep-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo, self.store = os.path.join(self.tmp, "repo"), os.path.join(self.tmp, "store")
        os.makedirs(self.repo)
        with open(os.path.join(self.repo, "a.py"), "w", encoding="utf-8") as f:
            f.write("x = 1\n")
        self.deps_argv = []

        class Deps:
            @staticmethod
            def collect(argv):
                self.deps_argv.append(argv)
                return [("OK", "python imports", "stdlib only"), ("FAIL", "python (launchd: /x)", "EOL past"),
                        ("WARN", "online lookups", "skipped")]
        out = json.dumps(BANDIT)
        git = lambda repo, args: ("a" * 40 + "\n") if args[0] == "rev-parse" else ""
        for p in (mock.patch.object(AV, "ARCH_DIR", self.store), mock.patch.object(self.cli, "_git", git),
                  mock.patch.object(self.cli, "_which", lambda n: "/bin/" + n if n == "bandit" else None),
                  mock.patch.object(self.cli, "_exec", lambda p, t, tmp: {"rc": 1, "out": out, "err": "", "t0": 0, "ms": 5}),
                  mock.patch.object(self.cli, "_probe", lambda: False),
                  mock.patch.object(self.cli, "_export", lambda r, h, d, t: shutil.copytree(r, d, dirs_exist_ok=True) and True),
                  mock.patch.object(self.cli, "_load_deps", lambda: Deps),
                  mock.patch.object(self.cli.time, "time", lambda: 1760000000.0)):   # no clock: one fixed minute
            p.start()
            self.addCleanup(p.stop)

    def reports(self):
        kdir = os.path.join(self.store, AV.repo_key(self.repo))
        return kdir, [n for n in os.listdir(kdir) if SR.REPORT_RE.fullmatch(n)]

    def test_foreign_repo_one_report_deps_na(self):
        rc, line = self.cli.run(self.repo)
        kdir, names = self.reports()
        self.assertEqual((rc, len(names)), (0, 1))
        self.assertIn(" · report %s · deps n/a" % names[0], line)
        md = SR.read_text(kdir, names[0])
        self.assertIn("not applicable (covers the Sidereus checkout only)", md)
        self.assertIn("| bandit | ok |", md)
        self.assertIn("n/a — no earlier scan record", md)
        self.assertNotIn("PLANTED-MESSAGE", md)
        self.assertEqual(self.deps_argv, [])

    def test_images_reaches_trivy_argv(self):
        with open(os.path.join(self.repo, "Dockerfile"), "w", encoding="utf-8") as f:
            f.write("FROM alpine:3.19\n")
        seen = []
        ex = lambda p, t, tmp: seen.append(p["argv"]) or {"rc": 0, "out": '{"Results": []}', "err": "", "t0": 0, "ms": 1}
        with mock.patch.object(self.cli, "_which", lambda n: "/bin/" + n if n == "trivy" else None), \
                mock.patch.object(self.cli, "_exec", ex), mock.patch.object(self.cli, "_probe", lambda: True), \
                redirect_stdout(io.StringIO()):
            self.cli.main(["--repo", self.repo, "--category", "security"])
            self.assertFalse(any(a[1] == "image" for a in seen))
            self.cli.main(["--repo", self.repo, "--category", "security", "--images"])
        self.assertIn(["/bin/trivy", "image", "--scanners", "vuln", "--image-src", "docker,remote", "--format", "json",
                       "--quiet", "--", "alpine:3.19"], seen)

    def test_self_repo_deps_lines_and_delta(self):
        with mock.patch.object(self.cli, "SIDEREUS_ROOT", self.repo):
            self.cli.run(self.repo, dev=True, offline=True)
            rc, line = self.cli.run(self.repo)
        kdir, names = self.reports()
        self.assertEqual(len(names), 1)   # same minute: the second run replaced the first
        self.assertIn(" · deps 1 FAIL/1 WARN", line)
        self.assertEqual(self.deps_argv, [["--dev", "--offline"], []])
        md = SR.read_text(kdir, names[0])
        self.assertIn("- FAIL python (launchd: /x) — EOL past", md)
        self.assertIn("- new 0 · gone 0", md)


if __name__ == "__main__":
    unittest.main()
