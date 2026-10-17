"""sidereus/pl_scorecard.py: R1 per-check verdicts, R2 na outside m, R4 ids/verdicts/counts only. No live files, no git spawn."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

BASE = ["LICENSE", "SECURITY.md", "package.json", "package-lock.json", ".github/dependabot.yml", "src/a.py"]
SEC = ["python3 scripts/arch_checks.py --verify --last --category security"]


def _v(r):
    return {c["id"]: c["v"] for c in r["checks"]}


class Score(unittest.TestCase):
    def setUp(self):
        self.m = sidereus("pl_scorecard")

    def check(self, cid, files, gates, want):
        self.assertEqual(_v(self.m.score(files, gates))[cid], want, (cid, files, gates))

    def test_order_and_all_pass(self):   # R1
        r = self.m.score(BASE, SEC)
        self.assertEqual([c["id"] for c in r["checks"]], list(self.m.SC_IDS))
        self.assertEqual((r["n"], r["m"]), (8, 8))

    def test_security_policy(self):   # R1
        for f in ("SECURITY.md", ".github/SECURITY.md", "docs/security.md"):
            self.check("security-policy", [f], None, "pass")
        self.check("security-policy", ["src/SECURITY.md", "README.md"], None, "fail")

    def test_license(self):   # R1
        self.check("license", ["LICENSE.txt"], None, "pass")
        self.check("license", ["COPYING"], None, "pass")
        self.check("license", ["vendor/LICENSE"], None, "fail")

    def test_pinned_deps(self):   # R1
        self.check("pinned-deps", ["README.md"], None, "na")
        self.check("pinned-deps", ["web/package.json", "web/yarn.lock", "go.mod", "go.sum"], None, "pass")
        self.check("pinned-deps", ["pyproject.toml", "requirements-dev.txt"], None, "pass")
        self.check("pinned-deps", ["Cargo.toml", "Cargo.lock", "crates/a/Cargo.toml"], None, "pass")   # workspace member
        self.check("pinned-deps", ["web/package.json", "package-lock.json"], None, "pass")             # ancestor lockfile
        self.check("pinned-deps", ["package.json", "Gemfile", "Gemfile.lock"], None, "fail")
        self.check("pinned-deps", ["web/package.json", "web/Cargo.lock"], None, "fail")
        self.check("pinned-deps", ["node_modules/x/package.json", "vendor/y/composer.json"], None, "na")

    def test_dep_update_tool(self):   # R1
        for f in (".github/dependabot.yaml", "renovate.json", ".renovaterc.json", ".github/renovate.json"):
            self.check("dep-update-tool", [f], None, "pass")
        self.check("dep-update-tool", ["dependabot.yml", "docs/renovate.json"], None, "fail")

    def test_binary_artifacts(self):   # R1
        self.check("binary-artifacts", ["a.py", "b.so.txt"], None, "pass")
        for f in ("lib/x.JAR", "a/__pycache__/m.cpython-39.pyc", "bin/tool.exe"):
            self.check("binary-artifacts", [f], None, "fail")

    def test_gates(self):   # R1
        for cid in ("secret-gate", "sast-gate", "dep-audit-gate"):
            self.check(cid, [], SEC, "pass")
            self.check(cid, [], ["scripts/check.sh --fast"], "fail")
            self.check(cid, [], [], "fail")
            self.check(cid, [], None, "na")
        self.check("secret-gate", [], ["gitleaks detect --no-git"], "pass")
        self.check("sast-gate", [], ["make lint && /usr/local/bin/semgrep --config auto"], "pass")
        self.check("dep-audit-gate", [], ["npm audit --audit-level high"], "pass")
        self.check("dep-audit-gate", [], ["pip-audit -r requirements.txt"], "pass")
        self.check("dep-audit-gate", [], ["npm test"], "fail")

    def test_gate_only_filter(self):   # R1
        g = [SEC[0] + " --only gitleaks,bandit"]
        self.assertEqual([_v(self.m.score([], g))[c] for c in ("secret-gate", "sast-gate", "dep-audit-gate")],
                         ["pass", "pass", "fail"])
        self.assertEqual(_v(self.m.score([], [SEC[0] + " --only=osv-scanner"]))["dep-audit-gate"], "pass")
        self.assertEqual(_v(self.m.score([], ["arch_checks.py --verify --last --only gitleaks"]))["secret-gate"], "fail")   # no security category

    def test_counts_skip_na(self):   # R2: 8 checks, 1 na, 5 pass -> n=5 m=7
        files = ["LICENSE", "SECURITY.md", "README.md", "renovate.json", "x.dll"]
        r = self.m.score(files, [SEC[0] + " --only gitleaks,semgrep"])
        self.assertEqual([v for v in _v(r).values()].count("na"), 1)
        self.assertEqual((r["n"], r["m"]), (5, 7))

    def test_unbalanced_quote(self):
        self.assertEqual(self.m.gate_tools("gitleaks detect 'oops"), {"gitleaks"})


class Scorecard(unittest.TestCase):
    def setUp(self):
        self.m = sidereus("pl_scorecard")
        self.proj = tempfile.mkdtemp(prefix="pl-sc-")
        d = os.path.join(self.proj, ".claude", "pipelines")
        os.makedirs(d)
        with open(os.path.join(d, "flow.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "flow", "stages": [{"title": "t", "gate": SEC[0]}]}, f)
        self.calls = []
        self._saved = [(self.m, "_tracked", self.m._tracked), (self.m, "SC_CACHE", self.m.SC_CACHE)]
        self.m.SC_CACHE = {}

        def tracked(p):
            self.calls.append(p)
            return ["/abs/secret/path/LICENSE", "SECURITY.md", "keys/id_rsa.jar"]
        self.m._tracked = tracked

    def tearDown(self):
        for mod, k, val in self._saved:
            setattr(mod, k, val)
        shutil.rmtree(self.proj, ignore_errors=True)

    def test_cache_head(self):
        a = self.m.scorecard(self.proj, "a" * 40)
        self.assertIs(self.m.scorecard(self.proj, "a" * 40), a)
        self.assertEqual(len(self.calls), 1)
        self.m.scorecard(self.proj, "b" * 40)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(_v(a)["secret-gate"], "pass")   # gate strings come from the project's pipeline files
        self.assertIsNone(self.m.scorecard(self.proj, ""))

    def test_not_git(self):
        self.m._tracked = lambda p: None
        self.assertIsNone(self.m.scorecard(self.proj, "c" * 40))

    def test_no_contents(self):   # R4: only id/v/n/m, never a path
        r = self.m.scorecard(self.proj, "a" * 40)
        self.assertEqual(set(r), {"n", "m", "checks"})
        self.assertTrue(all(set(c) == {"id", "v"} for c in r["checks"]))
        s = json.dumps(r)
        for bad in ("secret", "keys", "id_rsa", "SECURITY.md", "arch_checks", self.proj):
            self.assertNotIn(bad, s.replace("secret-gate", ""))


if __name__ == "__main__":
    unittest.main()
