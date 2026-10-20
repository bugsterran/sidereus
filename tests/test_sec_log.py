"""Security log (sidereus/sec_checks.py log_*, scripts/arch_checks.py --log-review / --log-show / --mark): status
computed on read, scan/review isolation, caps, metadata only."""
import io
import json
import os
import shutil
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tests._i18n_js import i18n_prelude
from tests._load import js_fn, sidereus
from tests._node import node_e
from tests.test_archchecks import C1, Tmp, cli

AC = sidereus("arch_checks")
AV = sidereus("arch_verify")
SC = sidereus("sec_checks")
C2, C3 = "b" * 40, "c" * 40
SECRET = "AKIAREALLOOKING7Q2Z9XK"


def scan(at, commit, tools, items):
    return SC.scan_record(commit, at, tools, [dict({"line": 1, "sev": "error"}, **x) for x in items])


def rev(at, commit, items):
    return SC.review_record(commit, at, [dict({"line": 3, "sev": "high", "desc": "d"}, **x) for x in items])


class Log(Tmp):
    def setUp(self):
        super().setUp()
        self.k = os.path.join(self.tmp, "arch", "key")

    def add(self, *recs):
        for r in recs:
            self.assertTrue(SC.log_append(self.k, r))

    def ids(self, v, s):
        return [(x["src"], x["key"], x["file"]) for x in v[s]]

    def test_round_trip_and_empty(self):
        self.assertEqual(SC.log_view(self.k), {"at_scan": None, "at_review": None, "open": [], "resolved": [], "fp": []})
        self.add(scan(10, C1, ["gitleaks"], [{"tool": "gitleaks", "file": "a.py", "rule": "aws-token"}]))
        v = SC.log_view(self.k)
        self.assertEqual(v["at_scan"], 10)
        self.assertEqual(v["open"], [{"sev": "error", "file": "a.py", "line": 1, "key": "gitleaks:aws-token", "desc": "aws-token",
                                      "src": "scan", "ai": False, "status": "open", "at": 10, "commit": C1}])

    def test_scan_resolution_reopen_and_partial_run(self):
        g = {"tool": "gitleaks", "file": "a.py", "rule": "aws-token"}
        b = {"tool": "bandit", "file": "b.py", "rule": "B105", "sev": "warning"}
        self.add(scan(10, C1, ["gitleaks", "bandit"], [g, b]),
                 scan(20, C2, ["bandit"], [b]))          # gitleaks did not run ok: its finding stays open
        self.assertEqual(len(SC.log_view(self.k)["open"]), 2)
        self.add(scan(30, C3, ["gitleaks", "bandit"], [b]))
        v = SC.log_view(self.k)
        self.assertEqual(self.ids(v, "resolved"), [("scan", "gitleaks:aws-token", "a.py")])
        self.assertEqual((v["resolved"][0]["at"], v["resolved"][0]["commit"]), (30, C3))
        self.add(scan(40, C3, ["gitleaks"], [dict(g, line=9)]))   # same identity on another line reopens it
        v = SC.log_view(self.k)
        self.assertEqual(self.ids(v, "open"), [("scan", "gitleaks:aws-token", "a.py"), ("scan", "bandit:B105", "b.py")])
        self.assertEqual((v["open"][0]["line"], v["open"][0]["at"], v["resolved"]), (9, 40, []))

    def test_review_not_resolved_by_absence_and_marks(self):
        self.add(rev(10, C1, [{"file": "x.py", "key": "sql-inj"}, {"file": "y.py", "key": "path-trav", "sev": "low"}]),
                 rev(20, C2, []),
                 scan(30, C2, ["gitleaks"], []))          # neither a later review nor a scan resolves review findings
        v = SC.log_view(self.k)
        self.assertEqual(self.ids(v, "open"), [("review", "sql-inj", "x.py"), ("review", "path-trav", "y.py")])
        self.assertTrue(all(x["ai"] for x in v["open"]))
        self.assertEqual(v["at_review"], 20)
        self.add(SC.mark_record(C3, 40, "sql-inj", "x.py", "resolved"), SC.mark_record(C3, 41, "path-trav", "y.py", "false-positive"))
        v = SC.log_view(self.k)
        self.assertEqual((self.ids(v, "resolved"), self.ids(v, "fp"), v["open"]),
                         ([("review", "sql-inj", "x.py")], [("review", "path-trav", "y.py")], []))
        self.assertEqual((v["resolved"][0]["at"], v["resolved"][0]["commit"]), (40, C3))
        self.add(SC.mark_record(C3, 50, "sql-inj", "x.py", "false-positive"))   # last mark wins
        self.assertEqual(len(SC.log_view(self.k)["fp"]), 2)

    def test_scan_and_review_isolated(self):
        self.add(scan(10, C1, ["gitleaks"], [{"tool": "gitleaks", "file": "a.py", "rule": "r1"}]),
                 rev(11, C1, [{"file": "a.py", "key": "r1"}]),
                 SC.mark_record(C1, 12, "r1", "a.py", "resolved"))   # mark hits the review finding only
        v = SC.log_view(self.k)
        self.assertEqual((self.ids(v, "open"), self.ids(v, "resolved")), ([("scan", "gitleaks:r1", "a.py")], [("review", "r1", "a.py")]))
        self.add(scan(13, C2, ["gitleaks"], []), rev(14, C2, [{"file": "a.py", "key": "r1"}]))   # reappears after resolve: reopened
        v = SC.log_view(self.k)
        self.assertEqual((self.ids(v, "open"), self.ids(v, "resolved")), ([("review", "r1", "a.py")], [("scan", "gitleaks:r1", "a.py")]))

    def test_caps_unsafe_paths_and_corrupt_lines(self):
        long = "x\x00\x1b[31m" + "y" * 400 + "\n"
        r = rev(10, C1, [{"file": "a.py", "key": "k1", "desc": long}, {"file": "../etc/passwd", "key": "k2"},
                         {"file": "/abs.py", "key": "k3"}, {"file": "a.py", "key": "bad slug"}, {"file": "a.py", "key": "k4", "sev": "urgent"}])
        self.assertEqual([x["key"] for x in r["items"]], ["k1"])
        self.assertEqual(r["items"][0]["desc"], "x[31m" + "y" * 155)
        self.assertEqual(len(rev(1, C1, [{"file": "f%d.py" % i, "key": "k"} for i in range(300)])["items"]), SC.LOG_ITEMS_MAX)
        self.add(r)
        with open(os.path.join(self.k, SC.LOG_FILE), "a", encoding="utf-8") as f:
            f.write("{not json\n" + json.dumps({"v": 1, "at": 1, "commit": "zz", "src": "review", "items": []}) + "\n")
        self.add(rev(20, C2, [{"file": "b.py", "key": "k5"}]))
        v = SC.log_view(self.k)
        self.assertEqual([x["key"] for x in v["open"]], ["k1", "k5"])

    def test_reads_only_newest_lines(self):
        self.add(rev(1, C1, [{"file": "old.py", "key": "k"}]))
        for i in range(SC.LOG_LINES):
            self.add(scan(2 + i, C1, ["gitleaks"], []))
        self.assertEqual(SC.log_view(self.k)["open"], [])

    def test_write_failure_returns_false(self):
        with open(os.path.join(self.tmp, "file"), "w", encoding="utf-8") as f:
            f.write("x")
        self.assertFalse(SC.log_append(os.path.join(self.tmp, "file", "sub"), rev(1, C1, [])))


class Cli(Tmp):
    def setUp(self):
        super().setUp()
        self.store = os.path.join(self.tmp, "store")
        self.cli = cli()
        with open(os.path.join(self.repo, "conf.py"), "w", encoding="utf-8") as f:
            f.write("x = 1\n")
        self.calls = 0

        def ex(p, t, tmp):
            self.calls += 1
            if "report" not in p:
                return {"rc": 0, "out": "[]", "err": "", "t0": 0, "ms": 1}
            with open(p["report"], "w", encoding="utf-8") as f:
                json.dump([{"RuleID": "aws-access-token", "File": os.path.join(p["cwd"], "conf.py"), "StartLine": 1,
                            "Secret": SECRET, "Match": "k = " + SECRET}], f)
            return {"rc": 1, "out": "", "err": "INF scanned ~2048 bytes", "t0": 0, "ms": 4}
        git = lambda repo, args: (C1 + "\n") if args[0] == "rev-parse" else ""
        self.p = [mock.patch.object(AV, "ARCH_DIR", self.store), mock.patch.object(self.cli, "_git", git),
                  mock.patch.object(self.cli, "_which", lambda n: "/bin/" + n if n in ("gitleaks", "ruff") else None),
                  mock.patch.object(self.cli, "_exec", ex)]
        for p in self.p:
            p.start()
        self.kdir = os.path.join(self.store, AV.repo_key(self.repo))
        self.log = os.path.join(self.kdir, SC.LOG_FILE)

    def tearDown(self):
        for p in self.p:
            p.stop()
        super().tearDown()

    def main(self, *a, stdin=""):
        out = io.StringIO()
        with redirect_stdout(out), mock.patch.object(self.cli.sys, "stdin", io.StringIO(stdin)):
            rc = self.cli.main(list(a))
        return rc, out.getvalue()

    def lines(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log, encoding="utf-8") as f:
            return [json.loads(x) for x in f]

    def test_security_run_logs_one_scan_quality_none(self):
        self.assertEqual(self.main("--repo", self.repo, "--category", "security")[0], 0)
        rows = self.lines()
        self.assertEqual([(r["src"], r["tools"], [x["key"] for x in r["items"]]) for r in rows],
                         [("scan", ["gitleaks"], ["gitleaks:aws-access-token"])])
        self.assertNotIn(SECRET, json.dumps(rows))
        with open(os.path.join(self.repo, "ruff.toml"), "w", encoding="utf-8") as f:
            f.write("")
        self.main("--repo", self.repo)                       # quality run: nothing logged
        self.assertEqual(len(self.lines()), 1)
        c = AC.load_checks(self.repo, os.path.join(self.kdir, C1), {"modules": []}, C1)
        self.assertEqual([x["key"] for x in c["security"]["log"]["open"]], ["gitleaks:aws-access-token"])
        self.assertNotIn(SECRET, json.dumps(c))

    def test_failed_run_not_logged_and_write_failure_keeps_rc(self):
        self.main("--repo", self.repo, "--category", "security", "--only", "semgrep")   # nothing ran ok
        self.assertEqual(self.lines(), [])
        os.makedirs(self.log)                                 # a dir where the log file would be: append fails
        self.assertEqual(self.main("--repo", self.repo, "--category", "security")[0], 0)

    def test_review_show_and_mark(self):
        tsv = "high\tconf.py:3\tsql-inj\tUnparameterised query\x07 built from input\nbogus line\nlow\t../x:1\tk\td\n"
        rc, out = self.main("--repo", self.repo, "--log-review", stdin=tsv)
        self.assertEqual((rc, out.strip()), (0, "arch_checks: review · 1 findings logged · 2 lines skipped"))
        self.assertEqual(self.lines()[0]["items"], [{"sev": "high", "file": "conf.py", "line": 3, "key": "sql-inj",
                                                     "desc": "Unparameterised query built from input"}])
        rc, out = self.main("--repo", self.repo, "--log-show")
        self.assertEqual(out.splitlines(), ["high\tconf.py:3\tsql-inj", "arch_checks: 1 open AI findings"])
        self.assertEqual(self.main("--repo", self.repo, "--mark", "sql-inj@conf.py", "resolved", "--commit", C2)[0], 0)
        self.assertEqual(self.lines()[-1], {"v": 1, "at": self.lines()[-1]["at"], "commit": C2, "src": "mark", "key": "sql-inj",
                                            "file": "conf.py", "status": "resolved", "by": "cli"})
        v = SC.log_view(self.kdir)
        self.assertEqual(([x["commit"] for x in v["resolved"]], v["open"]), ([C2], []))
        self.main("--repo", self.repo, "--mark", "sql-inj@conf.py", "false-positive")   # default commit = HEAD
        self.assertEqual(self.lines()[-1]["commit"], C1)

    def test_usage_errors(self):
        for a in (["--repo", self.repo, "--mark", "bad slug@conf.py", "resolved"],
                  ["--repo", self.repo, "--mark", "k@../x", "resolved"],
                  ["--repo", self.repo, "--mark", "k@a.py", "fixed"],
                  ["--repo", self.repo, "--mark", "k@a.py", "resolved", "--commit", "abc"],
                  ["--repo", self.repo, "--log-review", "--commit", C1],
                  ["--repo", self.repo, "--log-review", "--log-show"],
                  ["--log-show"], ["--repo", self.repo, "--commit", C1]):
            self.assertEqual(self.main(*a)[0], 2, a)


FNS = ["hhmm", "archChkLogHtml"]


def run_js(body, lang="ko"):
    pre = "\n".join(["process.env.TZ = 'UTC';", "let LANG = '%s';" % lang, i18n_prelude("LANG", ("T", "KE", "U", "TV")),
                     "function agoAt(s){ return '@' + s; }",   # clock-free stand-in
                     "const esc = s => String(s).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));"])
    r = subprocess.run(node_e(pre + "\n" + "\n".join(js_fn(n) for n in FNS) + "\n" + body), stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class Ui(unittest.TestCase):
    def test_age_rows_and_escaping(self):
        L = {"at_scan": 1700000000, "at_review": 1700000100,
             "open": [{"sev": "high", "file": "a/<x>.py", "line": 3, "key": "sql<inj>", "desc": "<b>bad</b>", "src": "review", "ai": True,
                       "status": "open", "at": 1, "commit": C1}],
             "resolved": [{"sev": "error", "file": "b.py", "line": 1, "key": "gitleaks:aws-token", "desc": "aws-token", "src": "scan",
                           "ai": False, "status": "resolved", "at": 1700000000, "commit": C2}],
             "fp": [{"sev": "low", "file": "c.py", "line": 2, "key": "k", "desc": "", "src": "review", "ai": True,
                     "status": "false-positive", "at": 1700000000, "commit": C3}]}
        ko, never = run_js("console.log(JSON.stringify([archChkLogHtml(%s), archChkLogHtml(null)]));" % json.dumps(L))
        en = run_js("console.log(JSON.stringify(archChkLogHtml(%s)));" % json.dumps(L), lang="en")
        self.assertIn("마지막 보안 점검 @1700000000", ko)
        self.assertIn("마지막 AI 리뷰 @1700000100", ko)
        self.assertIn("열림 1 · 해결 1 · 오탐 1", ko)
        self.assertIn("모델 생성 · 검증 안 됨", ko)
        self.assertIn("해결 · 11/14 22:13 · " + C2[:7], ko)
        self.assertIn("오탐 · 11/14 22:13 · " + C3[:7], ko)
        self.assertIn("a/<wbr>&lt;x&gt;.py", ko)
        self.assertIn("sql&lt;inj&gt;", ko)
        self.assertIn("&lt;b&gt;bad&lt;/b&gt;", ko)
        self.assertNotIn("<b>bad", ko)
        self.assertIn("Last security check @1700000000", en)
        self.assertIn("model-generated, unverified", en)
        self.assertTrue(never.startswith("<div class=archckst>점검한 적 없음"))
        self.assertNotIn("<ol", never)


if __name__ == "__main__":
    unittest.main()
