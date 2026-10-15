"""Security category of project checks: plans, parsers (secrets never kept), network gating, runner + gate, loader, UI."""
import io
import json
import os
import shutil
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tests._i18n_js import i18n_prelude
from tests._load import sidereus, js_fn
from tests.test_archchecks import C1, Tmp, cli
from tests._node import node_e

AC = sidereus("arch_checks")
AV = sidereus("arch_verify")
SC = sidereus("sec_checks")
SECRET, MATCH, LINE = "AKIAREALLOOKING7Q2Z9XK", "aws_key = AKIAREALLOOKING7Q2Z9XK", "    aws_key = 'AKIAREALLOOKING7Q2Z9XK'"
NPM = {"auditReportVersion": 2, "vulnerabilities": {
    "lodash": {"name": "lodash", "severity": "high", "via": [
        {"source": 1094, "name": "lodash", "title": "Prototype pollution", "url": "https://github.com/advisories/GHSA-p6mc-m468-83gw",
         "severity": "critical"}]},
    "minimist": {"name": "minimist", "severity": "moderate", "via": [
        {"source": 1179, "name": "minimist", "url": "https://npmjs.com/advisories/1179", "severity": "moderate"}, "lodash"]}},
    "metadata": {"dependencies": {"prod": 3, "total": 3}}}


class Plans(Tmp):
    def w(self, rel, text=""):
        fp = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w") as f:
            f.write(text)

    def test_missing_and_network_gating(self):
        self.w("a.py", "x = 1\n")
        self.w("web/package-lock.json", "{}")
        ids = lambda ps: [(p["id"], p.get("status"), p.get("why")) for p in ps]
        none = SC.detect(self.repo, lambda n: None)
        self.assertEqual(ids(none), [("gitleaks", "missing", SC.install_hint("gitleaks")),
                                     ("npm-audit", "skipped", SC.WHY_NET), ("osv-scanner", "skipped", SC.WHY_NET),
                                     ("semgrep", "missing", SC.install_hint("semgrep")),
                                     ("bandit", "missing", "install: pip install bandit")])
        allx = SC.detect(self.repo, lambda n: "/bin/" + n, net=True)
        npm = next(p for p in allx if p["id"] == "npm-audit")
        self.assertEqual((npm["argv"], npm["cwd"], npm["net"]), (["/bin/npm", "audit", "--json"], os.path.join(self.repo, "web"), True))
        self.assertEqual(next(p for p in allx if p["id"] == "semgrep")["status"], "skipped")   # no local rules
        gl = next(p for p in allx if p["id"] == "gitleaks")
        self.assertIn("--redact", gl["argv"])
        b = SC.bind(gl, "/t")
        self.assertEqual((b["argv"][-2:], b["report"]), (["--report-path", "/t/gitleaks-report.json"], "/t/gitleaks-report.json"))

    def test_npm_audit_parse(self):
        its = SC.parse_npm_audit(json.dumps(NPM))
        self.assertEqual([(x["rule"], x["pkg"], x["sev"], x["file"], x["line"]) for x in its],
                         [("GHSA-p6mc-m468-83gw", "lodash", "error", "package-lock.json", 1),
                          ("1179", "minimist", "warning", "package-lock.json", 1)])
        self.assertEqual(SC.files({"id": "npm-audit"}, {"out": json.dumps(NPM)}, self.repo), 1)

    def test_offline_is_skipped(self):
        self.w("package-lock.json", "{}")
        p = {"id": "npm-audit", "rules": "default", "argv": ["npm"], "cwd": self.repo, "src": "stdout", "ok_rc": (0, 1), "net": True}
        out = json.dumps({"error": {"code": "ENOTFOUND", "summary": "request to https://registry.npmjs.org failed"}})
        self.assertEqual(AC.judge(p, {"rc": 1, "out": out, "err": ""}, self.repo), ("skipped", "needs network", [], 0))
        self.assertEqual(AC.judge(p, {"rc": 1, "out": "", "err": "npm ERR! code EAI_AGAIN"}, self.repo)[0], "skipped")
        st, _w, its, n = AC.judge(p, {"rc": 1, "out": json.dumps(NPM), "err": ""}, self.repo)
        self.assertEqual((st, [x["pkg"] for x in its], n), ("ok", ["lodash", "minimist"], 1))

    def test_bandit_never_reads_code(self):
        rep = {"results": [{"filename": "./a.py", "line_number": 3, "test_id": "B105", "test_name": "hardcoded_password_string",
                            "issue_severity": "LOW", "issue_text": "Possible " + SECRET, "code": LINE,
                            "more_info": "https://bandit.readthedocs.io/en/latest/plugins/b105.html"}],
               "metrics": {"_totals": {}, "./a.py": {}}}
        its = SC.parse_bandit(json.dumps(rep))
        self.assertNotIn(SECRET, json.dumps(its))
        self.assertEqual((its[0]["rule"], its[0]["sev"], its[0]["help"]["desc"]), ("B105", "warning", "hardcoded password string"))
        self.assertEqual(SC.files({"id": "bandit"}, {"out": json.dumps(rep)}, self.repo), 1)


class Runner(Tmp):
    def setUp(self):
        super().setUp()
        self.store = os.path.join(self.tmp, "store")
        self.cli = cli()
        with open(os.path.join(self.repo, "conf.py"), "w") as f:
            f.write("x = 1\n")
        self.err = "INF scanned ~2048 bytes (2.05 KB) in 9ms"
        self.reports = []

        def ex(p, t, tmp):
            self.reports.append(p["report"])
            with open(p["report"], "w") as f:
                json.dump([{"RuleID": "aws-access-token", "File": os.path.join(self.repo, "conf.py"), "StartLine": 1,
                            "Secret": SECRET, "Match": MATCH, "Line": LINE, "Description": "AWS " + SECRET}], f)
            return {"rc": 1, "out": "", "err": self.err, "t0": 0, "ms": 4}
        git = lambda repo, args: (C1 + "\n") if args[0] == "rev-parse" else ""
        self.p = [mock.patch.object(AV, "ARCH_DIR", self.store), mock.patch.object(self.cli, "_git", git),
                  mock.patch.object(self.cli, "_which", lambda n: "/bin/gitleaks" if n == "gitleaks" else None),
                  mock.patch.object(self.cli, "_exec", ex)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        super().tearDown()

    def main(self, *a):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = self.cli.main(list(a))
        return rc, out.getvalue()

    def test_secrets_never_stored_and_report_removed(self):
        rc, line = self.main("--repo", self.repo, "--category", "security")
        self.assertEqual(rc, 0, line)
        self.assertTrue(line.startswith("arch_checks: security · 1 tools · 1 errors · 0 warnings"), line)
        fp = os.path.join(self.store, AV.repo_key(self.repo), C1, SC.SEC_FILE)
        with open(fp) as f:
            raw = f.read()
        for leak in (SECRET, MATCH, LINE.strip(), "AWS "):
            self.assertNotIn(leak, raw + line)
        j = json.loads(raw)
        self.assertEqual(j["items"], [{"tool": "gitleaks", "file": "conf.py", "line": 1, "rule": "aws-access-token", "sev": "error"}])
        self.assertEqual([os.path.exists(r) for r in self.reports], [False])
        self.assertFalse(os.path.exists(os.path.join(self.store, AV.repo_key(self.repo), C1, AC.CHECKS_FILE)))   # quality untouched
        self.assertEqual(self.main("--verify", "--last", "--category", "security")[0], 0)
        self.assertEqual(self.main("--verify", "--last")[0], 1)          # quality pointer was never written
        c = AC.load_checks(self.repo, os.path.join(self.store, AV.repo_key(self.repo), C1), {"modules": []}, C1)
        self.assertEqual((c["commit"], c["tools"], c["security"]["top"][0]["rule"]), ("", [], "aws-access-token"))
        self.assertNotIn(SECRET, json.dumps(c))

    def test_verify_records_evidence(self):
        ev = os.path.join(self.tmp, "ev.jsonl")
        self.cli._record = self.cli._verify_record   # cli() stubs it out for every other test
        self.main("--repo", self.repo, "--category", "security")
        made, real = [], self.cli.tempfile.mkstemp

        def mkstemp(**kw):
            made.append(real(**kw))
            return made[-1]
        with mock.patch.dict(os.environ, {"SIDEREUS_EVIDENCE": ev}), mock.patch.object(self.cli.tempfile, "mkstemp", mkstemp):
            self.assertEqual(self.main("--verify", "--last", "--category", "security")[0], 0)
            with mock.patch.object(self.cli, "_EV_PY", "/nonexistent/python"):   # recording failure keeps the rc
                self.assertEqual(self.main("--verify", "--last", "--category", "security")[0], 0)
        with open(ev) as f:
            rows = [json.loads(x) for x in f]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["mode"], rows[0]["rc"], rows[0]["repo"]), ("checks-security", 0, self.repo))
        self.assertEqual(json.dumps(rows[0]).count("gitleaks"), 1)
        self.assertNotIn(SECRET, json.dumps(rows))
        self.assertEqual([os.path.exists(m[1]) for m in made], [False, False])   # steps.tsv removed both times

    def test_verify_empty(self):
        self.err = "INF scanned ~0 bytes"
        self.assertEqual(self.main("--repo", self.repo, "--category", "security")[0], 0)
        rc, out = self.main("--verify", "--last", "--category", "security")
        self.assertEqual(rc, 1)
        self.assertIn("EMPTY: gitleaks examined 0 files", out)
        self.assertEqual(self.main("--repo", self.repo, "--category", "security", "--only", "semgrep")[0], 0)
        rc, out = self.main("--verify", "--last", "--category", "security")
        self.assertEqual(rc, 1)
        self.assertIn("EMPTY: no tool ran (missing: semgrep (%s))" % SC.install_hint("semgrep"), out)
        self.assertIn("[pl-skip:security-checks/", out)

    def test_pkg_schema_and_usage(self):
        j = AC.build(self.repo, C1, False, False, 1.0, [{"id": "npm-audit", "rules": "default", "status": "ok", "files": 1}],
                     [{"tool": "npm-audit", "file": "package-lock.json", "line": 1, "rule": "GHSA-p6mc-m468-83gw", "sev": "error",
                       "pkg": "@scope/x"}])
        self.assertEqual(j["items"][0]["pkg"], "@scope/x")
        self.assertEqual(AC.checks_errors(j, ids=SC.SEC_IDS), [])
        self.assertEqual(AC.checks_errors(j), ["tools[0]", "items"])     # quality ids refuse security tools
        bad = dict(j, items=[dict(j["items"][0], pkg="x y")])
        self.assertEqual(AC.checks_errors(bad, ids=SC.SEC_IDS), ["items"])
        for a in (["--repo", self.repo, "--category", "bogus"], ["--repo", self.repo, "--only", "gitleaks"],
                  ["--verify", "--last", "--net"], ["--repo"], ["--last", "--repo", self.repo]):
            self.assertEqual(self.main(*a)[0], 2, a)


SECJ = {"commit": "c" * 40, "tools": [{"id": "gitleaks", "rules": "default", "status": "ok", "n": {"error": 1, "warning": 0}},
                                      {"id": "semgrep", "rules": "project", "status": "missing", "why": "install: <b>", "n": {}}],
        "top": [{"tool": "npm-audit", "file": "package-lock.json", "line": 1, "rule": "GHSA-p6mc-m468-83gw", "sev": "error",
                 "pkg": "<lodash>", "rk": "npm-audit:GHSA-p6mc-m468-83gw"}],
        "rules": {"npm-audit:GHSA-p6mc-m468-83gw": {"desc": "", "url": "https://github.com/advisories/GHSA-p6mc-m468-83gw"}}}
QJ = {"commit": "abcdef123", "tools": [{"id": "ruff", "rules": "project", "status": "ok", "n": {"error": 0, "warning": 1}}],
      "top": [{"tool": "ruff", "file": "a.py", "line": 2, "rule": "F401", "sev": "warning"}]}
FNS = ["strHdBadge", "hhmm", "archBase", "archChkN", "archChkTools", "archChkSum", "archChkStat", "archChkTop", "archChkTopBtn",
       "archChkBadge", "archChkHelp", "archChkKey", "archChkSel", "archChkCandLabel", "archChkFixBody", "archHome", "archDmBody", "archChkReqKey", "archChkGoLabel", "archChkSentHtml", "archChkLogHtml", "archChkWinHtml"]


def run_js(body):
    pre = "\n".join(["let LANG = 'ko';", i18n_prelude("LANG", ("T", "KE", "U", "TV")), "function sid8(s){ return String(s).slice(0, 8); }", "function agoAt(s){ return '@' + s; }", "const ARCH_PL = 'arch-map';",
                     "const esc = s => String(s).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));"])
    js = pre + "\n" + "\n".join(js_fn(n) for n in FNS) + "\n" + body
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class Ui(unittest.TestCase):
    def test_badge_tabs_and_fix_body(self):
        c = dict(QJ, security=SECJ)
        r = run_js("const d = {checks: " + json.dumps(c) + "}, S = {sel: {}, req: null, cat: 's'}; S.sel[archChkKey(d.checks.top[0])] = 1;"
                   "S.sel[archChkKey(d.checks.security.top[0])] = 1;"
                   "console.log(JSON.stringify([archChkTopBtn(d), archChkWinHtml('/r', d, S, []), archChkFixBody('/r', d.checks, archChkSel(d, S.sel)),"
                   "archChkWinHtml('/r', {checks: " + json.dumps(QJ) + "}, {sel: {}, req: null, cat: 's'}, []), archChkBadge({checks: {commit: '', tools: [], top: [], security: d.checks.security}})]));")
        btn, win, body, plain, only = r
        self.assertIn("품질 1 · 보안 1", btn)
        self.assertNotIn("archckiw", btn)                     # security error -> red
        self.assertIn("install: &lt;b&gt;", btn)              # tool why escaped in the tooltip
        self.assertIn('data-ckcat=s aria-selected=true', win)
        self.assertIn("GHSA-p6mc-m468-83gw · &lt;lodash&gt;", win)
        self.assertNotIn("<lodash>", win)
        self.assertNotIn("F401", win)                          # quality rows are on the other tab
        self.assertEqual(body.splitlines()[2:4], [   # line 2 = target repository
                         "- warning · F401 · a.py:2",
                                                  "- error · GHSA-p6mc-m468-83gw · <lodash> · package-lock.json:1 (https://github.com/advisories/GHSA-p6mc-m468-83gw)"])
        self.assertIn("<div class=archckst>점검한 적 없음", win)   # security tab ends with the (empty) history section
        self.assertNotIn("data-ckcat", plain)                  # no security results -> no tabs
        self.assertTrue(only.startswith("<button") and "보안 1" in only)   # security only: no empty quality badge


if __name__ == "__main__":
    unittest.main()
