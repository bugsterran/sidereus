"""Security category of project checks: plans, parsers (secrets never kept), network gating, runner + gate, loader, UI."""
import importlib.util
import io
import json
import os
import shutil
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tests._i18n_js import i18n_prelude
from tests._load import sidereus, js_fn, ROOT
from tests.test_archchecks import C1, Tmp, cli
from tests._node import node_e

AC = sidereus("arch_checks")
ACP = sidereus("arch_checks_parse")
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
        with open(fp, "w", encoding="utf-8") as f:
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
        sg = next(p for p in allx if p["id"] == "semgrep")   # no local rules + net: registry packs, metrics off
        self.assertEqual((sg["rules"], sg["net"], sg["argv"][:3]), ("default", True, ["/bin/semgrep", "scan", "--config"]))
        self.assertIn("--metrics=off", sg["argv"])
        self.assertNotIn("auto", sg["argv"])
        offl = next(p for p in SC.detect(self.repo, lambda n: "/bin/" + n) if p["id"] == "semgrep")
        self.assertEqual(offl["status"], "skipped")
        self.assertTrue(SC.net_fail(sg, {"rc": 2, "err": "HTTPSConnectionPool: Max retries exceeded", "out": ""}))
        gl =next(p for p in allx if p["id"] == "gitleaks")
        self.assertIn("--redact", gl["argv"])
        b = SC.bind(gl, "/t")
        rp = os.path.join("/t", "gitleaks-report.json")   # native join: `\` on Windows
        self.assertEqual((b["argv"][-2:], b["report"]), (["--report-path", rp], rp))

    def osv(self, net=False):
        return next(p for p in SC.detect(self.repo, lambda n: "/bin/" + n, net=net) if p["id"] == "osv-scanner")

    def test_osv_row_without_lockfile(self):   # a vanished osv row read as «dependencies clean»
        self.w("README.md", "x\n")
        self.assertEqual((self.osv(True)["status"], self.osv(True)["why"]), ("skipped", SC.WHY_NO_DEPS))
        self.w("admin/build.gradle.kts", "plugins {}\n")
        self.w("admin/src/A.java", "class A {}\n")
        p = self.osv(True)
        self.assertEqual((p["status"], p["why"]), ("skipped", SC.WHY_GRADLE))
        self.assertLessEqual(len(SC.WHY_GRADLE), AC.WHY_MAX)
        SR = sidereus("sec_report")
        self.assertIsNone(SR._NET.search(SC.WHY_GRADLE))
        md = SR.render({"repo": "/r", "commit": "a" * 40, "at": 0, "tools": [dict(p, ms=0, files=0)], "items": []},
                       {}, None, None, None)
        self.assertIn("| osv-scanner | skipped — %s |" % SC.WHY_GRADLE, md)
        self.assertIn("No tool ran", md)

    def test_osv_java_manifests_planned(self):
        for rel in ("pom.xml", "gradle/verification-metadata.xml", "gradle/libs.versions.toml"):
            shutil.rmtree(self.repo)
            os.makedirs(self.repo)
            self.w("build.gradle", "")
            self.w(rel, "<x/>")
            p = self.osv(True)
            self.assertEqual((p.get("argv"), p.get("net")), (["/bin/osv-scanner", "--format", "json", "-r", "."], True), rel)
            self.assertEqual(self.osv()["why"], SC.WHY_NET, rel)   # a real manifest offline keeps the network reason
        shutil.rmtree(self.repo)
        os.makedirs(self.repo)
        self.w("docs/verification-metadata.xml", "<x/>")   # outside gradle/: not a manifest osv-scanner reads
        self.assertEqual(self.osv(True)["why"], SC.WHY_NO_DEPS)

    def test_npm_audit_parse(self):
        its = SC.parse_npm_audit(json.dumps(NPM))
        self.assertEqual([(x["rule"], x["pkg"], x["sev"], x["file"], x["line"]) for x in its],
                         [("GHSA-p6mc-m468-83gw", "lodash", "critical", "package-lock.json", 1),
                          ("1179", "minimist", "medium", "package-lock.json", 1)])
        self.assertEqual(SC.files({"id": "npm-audit"}, {"out": json.dumps(NPM)}, self.repo), 1)

    def test_cve_aliases_kept_beside_key(self):   # rule (finding key) stays GHSA-first; CVE ids ride in a separate field
        osv = {"results": [{"source": {"path": "web/package-lock.json"}, "packages": [{"package": {"name": "lodash"}, "groups": [],
               "vulnerabilities": [{"id": "GHSA-p6mc-m468-83gw", "aliases": ["CVE-2020-8203", "CVE-2020-8203", "CVE-x", "CVE-2020-8203; rm",
                                                                              "CVE-2021-1"]},
                                   {"id": "PYSEC-2024-1", "aliases": ["GHSA-aaaa-bbbb-cccc", "CVE-2024-0001", "CVE-2023-12345", "CVE-2022-9999",
                                                                       "CVE-2021-1111"]},
                                   {"id": "GO-2024-1"}]}]}]}
        its = SC.parse_osv(json.dumps(osv))
        self.assertEqual([(x["rule"], x.get("cve")) for x in its],
                         [("GHSA-p6mc-m468-83gw", ["CVE-2020-8203"]),
                          ("GHSA-aaaa-bbbb-cccc", ["CVE-2021-1111", "CVE-2022-9999", "CVE-2023-12345"]), ("GO-2024-1", None)])
        npm6 = {"advisories": {"1": {"id": 1, "module_name": "minimist", "severity": "high", "cves": ["CVE-2021-44906", "junk"],
                                     "url": "https://github.com/advisories/GHSA-xvch-5gv4-984h"}}}
        self.assertEqual([(x["rule"], x["cve"]) for x in SC.parse_npm_audit(json.dumps(npm6))], [("GHSA-xvch-5gv4-984h", ["CVE-2021-44906"])])
        self.assertTrue(all("cve" not in x for x in SC.parse_npm_audit(json.dumps(NPM))))   # npm 7 `via` carries no CVE
        it = {k: v for k, v in dict(its[0], tool="osv-scanner").items() if k != "help"}   # help is stored per rule, not per item
        self.assertEqual(AC._clean_item(it, SC.SEC_IDS), it)
        for bad in (["CVE-x"], [], "CVE-2020-8203", ["CVE-2020-8203", "CVE-2020-8203"]):
            self.assertIsNone(AC._clean_item(dict(it, cve=bad), SC.SEC_IDS))

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
        self.assertEqual((its[0]["rule"], its[0]["sev"], its[0]["help"]["desc"]), ("B105", "low", "hardcoded password string"))
        self.assertEqual(SC.files({"id": "bandit"}, {"out": json.dumps(rep)}, self.repo), 1)

    def test_levels_per_tool(self):   # R1: each tool's own severity field -> critical/high/medium/low
        def osv(score, label=None):
            v = {"id": "GHSA-aaaa-bbbb-cccc"}
            if label:
                v["database_specific"] = {"severity": label}
            g = [{"ids": [v["id"]], "max_severity": score}] if score is not None else []
            j = {"results": [{"source": {"path": "go.sum"}, "packages": [{"package": {"name": "x"}, "groups": g,
                                                                           "vulnerabilities": [v]}]}]}
            return SC.parse_osv(json.dumps(j))[0]["sev"]
        self.assertEqual([osv("9.8"), osv("7.0"), osv("4.0"), osv("3.9"), osv(None, "MODERATE"), osv(None, "CRITICAL"),
                          osv(None)], ["critical", "high", "medium", "low", "medium", "critical", "medium"])
        self.assertEqual(osv("3.9", "CRITICAL"), "low")   # a CVSS score wins over the advisory label
        bd = lambda s: SC.parse_bandit(json.dumps({"results": [{"filename": "a.py", "line_number": 1, "test_id": "B1",
                                                                "issue_severity": s}]}))[0]["sev"]
        self.assertEqual([bd(s) for s in ("HIGH", "MEDIUM", "LOW", "UNDEFINED")], ["high", "medium", "low", "medium"])
        sg = lambda s: SC.parse_semgrep(json.dumps({"results": [{"path": "a.py", "start": {"line": 1}, "check_id": "r",
                                                                 "extra": {"severity": s}}]}))[0]["sev"]
        self.assertEqual([sg(s) for s in ("CRITICAL", "ERROR", "WARNING", "INFO", "HIGH", "LOW")],
                         ["critical", "high", "medium", "low", "high", "low"])
        self.assertEqual(SC.parse_gitleaks(json.dumps([{"RuleID": "k", "File": "a", "StartLine": 1}]))[0]["sev"], "high")
        npm = lambda s: SC.parse_npm_audit(json.dumps({"advisories": {"1": {"id": 1, "module_name": "m", "severity": s}}}))[0]["sev"]
        self.assertEqual([npm(s) for s in ("critical", "high", "moderate", "low", "info")],
                         ["critical", "high", "medium", "low", "low"])
        self.assertEqual(SC.SEVS, ("critical", "high", "medium", "low"))

    def test_severity_table(self):   # one table: CVSS bands (boundaries inclusive), GHSA words, v1 legacy names
        for raw, want in ((("10.0", None), "critical"), (("9.0", None), "critical"), (("8.99", None), "high"),
                          (("7.0", None), "high"), (("6.99", None), "medium"), (("4.0", None), "medium"),
                          (("3.99", None), "low"), (("0.1", None), "low"),
                          ((None, "CRITICAL"), "critical"), ((None, "HIGH"), "high"), ((None, "MODERATE"), "medium"),
                          ((None, "LOW"), "low"), (("0", "HIGH"), "high"), (("n/a", "LOW"), "low"), ((None, None), "medium"),
                          (("9.0", "LOW"), "critical")):   # a CVSS score wins over the advisory word
            self.assertEqual(SC._lv("osv-scanner", raw), want, raw)
        for raw, want in (("error", "high"), ("warning", "medium"), ("critical", "critical"), ("low", "low"),
                          ("bogus", None), (None, None), (1, None)):
            self.assertEqual(ACP.level(raw), want, raw)
        self.assertEqual((ACP.SEVS, ACP.LEGACY), (("critical", "high", "medium", "low"), {"error": "high", "warning": "medium"}))
        j = AC.build("/r", "a" * 40, False, False, 1.0, [{"id": "bandit", "rules": "default", "status": "ok", "files": 1}],
                     [{"tool": "bandit", "file": "a.py", "line": 1, "rule": "B1", "sev": s} for s in ("low", "critical")])
        self.assertEqual(([x["sev"] for x in j["items"]], j["v"]), (["critical", "low"], 2))   # most severe first
        self.assertEqual(AC.checks_errors(j, ids=SC.SEC_IDS), [])
        self.assertIn("v must be 2", AC.checks_errors(dict(j, v=1), ids=SC.SEC_IDS))   # gate: v2 only
        bad = dict(j, items=[dict(j["items"][0], sev="error")])
        self.assertEqual(AC.checks_errors(bad, ids=SC.SEC_IDS), ["items"])             # never error/warning in a v2 file


class Runner(Tmp):
    def setUp(self):
        super().setUp()
        self.store = os.path.join(self.tmp, "store")
        self.cli = cli()
        with open(os.path.join(self.repo, "conf.py"), "w", encoding="utf-8") as f:
            f.write("x = 1\n")
        self.err = "INF scanned ~2048 bytes (2.05 KB) in 9ms"
        self.reports = []

        def ex(p, t, tmp):
            self.reports.append(p["report"])
            with open(p["report"], "w", encoding="utf-8") as f:
                json.dump([{"RuleID": "aws-access-token", "File": os.path.join(p["cwd"], "conf.py"), "StartLine": 1,
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
        self.assertTrue(line.startswith("arch_checks: security · 1 tools · 0 critical · 1 high · 0 medium · 0 low"), line)
        fp = os.path.join(self.store, AV.repo_key(self.repo), C1, SC.SEC_FILE)
        with open(fp, encoding="utf-8") as f:
            raw = f.read()
        for leak in (SECRET, MATCH, LINE.strip(), "AWS "):
            self.assertNotIn(leak, raw + line)
        j = json.loads(raw)
        self.assertEqual(j["items"], [{"tool": "gitleaks", "file": "conf.py", "line": 1, "rule": "aws-access-token", "sev": "high"}])
        self.assertEqual([os.path.exists(r) for r in self.reports], [False])
        self.assertFalse(os.path.exists(os.path.join(self.store, AV.repo_key(self.repo), C1, "checks.json")))   # quality untouched
        self.assertEqual(self.main("--verify", "--last", "--category", "security")[0], 0)
        self.assertEqual(self.main("--verify", "--last")[0], 1)          # quality pointer was never written
        c = AC.load_checks(self.repo, os.path.join(self.store, AV.repo_key(self.repo), C1), {"modules": []}, C1)
        self.assertEqual((c["commit"], c["tools"], c["security"]["top"][0]["rule"]), ("", [], "aws-access-token"))
        self.assertNotIn(SECRET, json.dumps(c))

    @unittest.skipUnless(shutil.which("git"), "needs git")
    def test_scans_head_export_not_worktree(self):   # results are stored under HEAD, so only HEAD's files are scanned
        g = lambda *a: subprocess.run(["git", "-C", self.repo, "-c", "user.name=t", "-c", "user.email=t@t", "-c",
                                       "commit.gpgsign=false"] + list(a), capture_output=True, text=True, encoding="utf-8",
                                      check=True).stdout
        self.w(".gitignore", ".env\n")
        g("init", "-q")
        g("add", "-A")
        g("commit", "-qm", "c")
        head = g("rev-parse", "HEAD").strip()
        self.w("conf.py", "edited = 1\n")   # uncommitted edit
        self.w("new.py", "x = 2\n")         # untracked
        self.w(".env", "K=1\n")             # gitignored
        por, seen = g("status", "--porcelain"), []

        def ex(p, t, tmp):
            src = p["cwd"]
            with open(os.path.join(src, "conf.py"), encoding="utf-8") as f:
                seen.append((src, sorted(os.listdir(src)), f.read()))
            with open(p["report"], "w", encoding="utf-8") as f:
                json.dump([{"RuleID": "r", "File": os.path.join(src, "conf.py"), "StartLine": 1}], f)
            return {"rc": 1, "out": "", "err": self.err, "t0": 0, "ms": 4}
        spec = importlib.util.spec_from_file_location("arch_checks_cli_export", os.path.join(ROOT, "scripts", "arch_checks.py"))
        c = importlib.util.module_from_spec(spec)   # fresh module: real _git and _export (cli() stubs both)
        spec.loader.exec_module(c)
        c._record = lambda *a: False
        with mock.patch.object(c, "_exec", ex), \
                mock.patch.object(c, "_which", lambda n: "/bin/gitleaks" if n == "gitleaks" else None):
            rc, line = c.run(self.repo)
        self.assertEqual(rc, 0, line)
        src, names, text = seen[0]
        self.assertNotEqual(src, self.repo)
        self.assertEqual((names, text), ([".gitignore", "conf.py"], "x = 1\n"))
        self.assertFalse(os.path.exists(src))   # export dir removed
        j = AV.read_json(os.path.join(self.store, AV.repo_key(self.repo), head, SC.SEC_FILE))
        self.assertEqual(([x["file"] for x in j["items"]], j["dirty"], j["src_changed"]), (["conf.py"], True, False))
        self.assertTrue(os.path.isfile(os.path.join(self.repo, j["items"][0]["file"])))
        self.assertEqual(g("status", "--porcelain"), por)   # repo untouched

    @unittest.skipUnless(shutil.which("git"), "needs git")
    def test_export_includes_export_ignore(self):   # export-ignore must not hide tracked files from the scan
        g = lambda *a: subprocess.run(["git", "-C", self.repo, "-c", "user.name=t", "-c", "user.email=t@t", "-c",
                                       "commit.gpgsign=false"] + list(a), capture_output=True, text=True, encoding="utf-8",
                                      check=True).stdout
        self.w(".gitattributes", "secret/** export-ignore\n")
        self.w("secret/key.txt", "k = 1\n")
        g("init", "-q")
        g("add", "-A")
        g("commit", "-qm", "c")
        head = g("rev-parse", "HEAD").strip()
        self.w("conf.py", "edited = 1\n")   # uncommitted edit
        self.w("secret/new.txt", "u\n")     # untracked
        gitdir = os.path.join(self.repo, ".git")
        snap = lambda: sorted(os.path.join(dp, f) for dp, _, fs in os.walk(gitdir) for f in fs)
        before = snap()
        spec = importlib.util.spec_from_file_location("arch_checks_cli_export2", os.path.join(ROOT, "scripts", "arch_checks.py"))
        c = importlib.util.module_from_spec(spec)   # fresh module: real _git (cli() stubs it)
        spec.loader.exec_module(c)
        dest, tmp = os.path.join(self.tmp, "dest"), os.path.join(self.tmp, "work")
        os.makedirs(dest)
        os.makedirs(tmp)
        self.assertTrue(c._export(self.repo, head, dest, tmp))
        got = sorted(os.path.relpath(os.path.join(dp, f), dest).replace(os.sep, "/") for dp, _, fs in os.walk(dest) for f in fs)
        self.assertEqual(got, [".gitattributes", "conf.py", "secret/key.txt"])
        with open(os.path.join(dest, "conf.py"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "x = 1\n")
        self.assertEqual(os.listdir(tmp), [])   # scratch git dir and tar removed
        self.assertEqual(snap(), before)        # real .git gained no files

    def test_export_drops_unsafe_members(self):
        import tarfile
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            for name, kind, link in (("ok.txt", tarfile.REGTYPE, ""), ("../up.txt", tarfile.REGTYPE, ""),
                                     ("/abs.txt", tarfile.REGTYPE, ""), ("in", tarfile.SYMTYPE, "ok.txt"),
                                     ("out", tarfile.SYMTYPE, "../../etc/passwd"), ("abs", tarfile.SYMTYPE, "/etc"),
                                     ("dev", tarfile.CHRTYPE, "")):
                ti = tarfile.TarInfo(name)
                ti.type, ti.linkname = kind, link
                tf.addfile(ti, io.BytesIO(b"") if kind == tarfile.REGTYPE else None)
        buf.seek(0)
        with tarfile.open(fileobj=buf) as tf:
            self.assertEqual([m.name for m in self.cli._safe_members(tf, self.repo)], ["ok.txt", "in"])

    @unittest.skipIf(os.name == "nt", "evidence_rec.py writes no row without fcntl (documented: no evidence rows on Windows)")
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
        with open(ev, encoding="utf-8") as f:
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
                     [{"tool": "npm-audit", "file": "package-lock.json", "line": 1, "rule": "GHSA-p6mc-m468-83gw", "sev": "critical",
                       "pkg": "@scope/x"}])
        self.assertEqual(j["items"][0]["pkg"], "@scope/x")
        self.assertEqual(AC.checks_errors(j, ids=SC.SEC_IDS), [])
        self.assertEqual(AC.checks_errors(j), ["tools[0]", "items"])     # quality ids refuse security tools
        bad = dict(j, items=[dict(j["items"][0], pkg="x y")])
        self.assertEqual(AC.checks_errors(bad, ids=SC.SEC_IDS), ["items"])
        for a in (["--repo", self.repo, "--category", "bogus"], ["--repo", self.repo, "--only", "gitleaks"],
                  ["--verify", "--last", "--net"], ["--verify", "--last", "--offline"], ["--repo"],
                  ["--last", "--repo", self.repo]):
            self.assertEqual(self.main(*a)[0], 2, a)

    def test_online_by_default_with_probe(self):
        self.w("requirements.txt", "x==1\n")
        fp = os.path.join(self.store, AV.repo_key(self.repo), C1, SC.SEC_FILE)
        probes, ran = [], []
        osv = lambda p, t, tmp: ran.append(p["id"]) or {"rc": 0, "out": '{"results": []}', "err": "", "ms": 1}

        def go(up, *extra):
            del probes[:], ran[:]
            with mock.patch.object(self.cli, "_which", lambda n: "/bin/" + n if n == "osv-scanner" else None), \
                    mock.patch.object(self.cli, "_exec", osv), \
                    mock.patch.object(self.cli, "_probe", lambda: probes.append(1) or up):
                self.assertEqual(self.main("--repo", self.repo, "--category", "security", "--only", "osv-scanner",
                                           *extra)[0], 0)
            with open(fp, encoding="utf-8") as f:
                return json.load(f)["tools"][0]
        self.assertEqual((go(True)["status"], probes, ran), ("ok", [1], ["osv-scanner"]))
        t = go(False)   # unreachable: skipped, never «0 issues»
        self.assertEqual((t["status"], t["why"], ran), ("skipped", SC.WHY_NET, []))
        t = go(True, "--offline")   # opt-out: no probe at all
        self.assertEqual((t["status"], probes, ran), ("skipped", [], []))
        self.assertEqual(go(True, "--net")["status"], "ok")   # --net stays accepted (no-op)


SECJ = {"commit": "c" * 40, "tools": [{"id": "gitleaks", "rules": "default", "status": "ok",
                                       "n": {"critical": 0, "high": 1, "medium": 0, "low": 0}},
                                      {"id": "semgrep", "rules": "project", "status": "missing", "why": "install: <b>", "n": {}}],
        "top": [{"tool": "npm-audit", "file": "package-lock.json", "line": 1, "rule": "GHSA-p6mc-m468-83gw", "sev": "high",
                 "pkg": "<lodash>", "rk": "npm-audit:GHSA-p6mc-m468-83gw"}],
        "rules": {"npm-audit:GHSA-p6mc-m468-83gw": {"desc": "", "url": "https://github.com/advisories/GHSA-p6mc-m468-83gw"}}}
QJ = {"commit": "abcdef123", "tools": [{"id": "ruff", "rules": "project", "status": "ok", "n": {"critical": 0, "high": 0, "medium": 1, "low": 0}}],
      "top": [{"tool": "ruff", "file": "a.py", "line": 2, "rule": "F401", "sev": "medium"}]}
FNS = ["strHdBadge", "hhmm", "archBase", "archNoHome", "archChkLv", "archChkLvLbl", "archChkSevF", "archChkN", "archChkTools", "archChkSum", "archChkStat", "archChkSec", "archChkTop", "archChkTopBtn",
       "archChkHelp", "archChkRule", "archChkKey", "archChkSel", "archChkCandLabel", "archChkFixBody", "archChkRunBody", "archHome", "archDmBody", "archChkReqKey", "archChkGoLabel", "archChkSentHtml", "archChkLogHtml", "archChkRunHtml", "archChkWinHtml",
       "archChkRk", "archChkHidSet", "archChkHidPref", "archChkHidden", "archChkView"]   # hidden-rule view helpers (archChkTopBtn / archChkWinHtml call them)
FNS += ["ago", "archRunOf", "archRunEl", "archRunHtml", "archChkProgHtml"]   # run progress line (archChkRunHtml calls it)
FNS += ["archChkScanAt", "archChkLast", "archChkLastHtml", "archChkFixRecHtml"]   # last-check line (badge tooltip, window header)


def run_js(body):
    pre = "\n".join(["let LANG = 'ko';", i18n_prelude("LANG", ("T", "KE", "U", "TV", "AGO")), "function sid8(s){ return String(s).slice(0, 8); }", "function agoAt(s){ return '@' + s; }", "const ARCH_PL = 'arch-map', ARCH_SEC_PL = 'security-checks'; let ARCHRUN = {}, SECRUN = {};",
                     "const esc = s => String(s).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));"])
    js = pre + "\n" + "\n".join(js_fn(n) for n in FNS) + "\n" + body
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class Ui(unittest.TestCase):
    def test_badge_window_and_fix_body(self):   # security only: quality fields beside it are ignored
        c = dict(QJ, security=SECJ)
        r = run_js("const d = {checks: " + json.dumps(c) + "}, S = {sel: {}, req: null}; S.sel[archChkKey(d.checks.top[0])] = 1;"
                   "S.sel[archChkKey(d.checks.security.top[0])] = 1;"
                   "console.log(JSON.stringify([archChkTopBtn(d), archChkWinHtml('/r', d, S, []), archChkFixBody('/r', d.checks, archChkSel(d, S.sel)),"
                   "archChkWinHtml('/r', {checks: " + json.dumps(QJ) + "}, {sel: {}, req: null}, []), archChkTopBtn({checks: {commit: '', tools: [], top: [], security: d.checks.security}})]));")
        btn, win, body, plain, only = r
        self.assertIn(">보안 문제 1</button>", btn)
        self.assertNotIn("품질", btn)
        self.assertNotIn("archckiw", btn)                     # security error -> red
        self.assertIn("install: &lt;b&gt;", btn)              # tool why escaped in the tooltip
        self.assertNotIn("tablist", win)
        self.assertNotIn("data-ckcat", win)
        self.assertIn("GHSA-p6mc-m468-83gw · &lt;lodash&gt;", win)
        self.assertNotIn("<lodash>", win)
        self.assertNotIn("F401", win)                          # quality rows are not listed
        self.assertEqual(body.splitlines()[2:4], [   # line 2 = target repository; quality item dropped
                         "- high · GHSA-p6mc-m468-83gw · <lodash> · package-lock.json:1 (https://github.com/advisories/GHSA-p6mc-m468-83gw)",
                         "Fix the cause, keep behaviour, run the project's tests."])
        self.assertIn("<div class=archckst>점검한 적 없음", win)   # window ends with the (empty) history section
        self.assertNotIn("a.py", plain)                        # no security results -> nothing listed
        self.assertNotIn("<div class=archckst>점검한 적 없음", plain)   # no history section
        self.assertIn('<span class="ckwlast">점검한 적 없음</span>', plain)   # header last-check line
        r2 = run_js("console.log(JSON.stringify([archChkRule({rule: 'GHSA-1', cve: ['CVE-2020-8203', '<b>'], pkg: 'lodash'}), archChkRule({rule: 'B105'})]));")
        self.assertEqual(r2, ["GHSA-1 · CVE-2020-8203 · lodash", "B105"])
        self.assertTrue(only.startswith("<button") and only.endswith("</button>") and "보안 문제 1" in only)

if __name__ == "__main__":
    unittest.main()
