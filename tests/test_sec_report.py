"""sidereus/sec_report.py: Markdown content, metadata-only, prune and read guards — tmp dirs only."""
import importlib
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
SR = importlib.import_module("sidereus.sec_report")

SECRET, DESC, MSG = "AKIAPLANTEDSECRET0001", "model wrote this sentence", "tool said something private"
AT = 1760000000.0


def _j(tools, items):
    return {"v": 2, "repo": "/r", "commit": "a" * 40, "dirty": True, "src_changed": False, "at": AT, "tools": tools,
            "items": items, "msg": MSG, "secret": SECRET}


T_ALL = [
    {"id": "gitleaks", "rules": "default", "status": "ok", "ms": 1200, "files": 12, "n": {"critical": 0, "high": 1, "medium": 0, "low": 0}},
    {"id": "osv-scanner", "rules": "default", "status": "skipped", "why": "offline (network unreachable or --offline)",
     "ms": 0, "files": 0, "n": {"critical": 0, "high": 0, "medium": 0, "low": 0}},
    {"id": "semgrep", "rules": "default", "status": "missing", "why": "install: brew install semgrep", "ms": 0, "files": 0,
     "n": {"critical": 0, "high": 0, "medium": 0, "low": 0}},
    {"id": "bandit", "rules": "default", "status": "fail", "why": "exit 2", "ms": 5, "files": 0, "n": {"critical": 0, "high": 0, "medium": 0, "low": 0}},
    {"id": "npm-audit", "rules": "default", "status": "timeout", "why": "over 300 s", "ms": 9, "files": 0,
     "n": {"critical": 0, "high": 0, "medium": 0, "low": 0}},
]
ITEMS = [{"tool": "gitleaks", "file": "conf.py", "line": 3, "rule": "aws-access-token", "sev": "high"},
         {"tool": "osv-scanner", "file": "package-lock.json", "line": 0, "rule": "GHSA-aaaa-bbbb-cccc", "sev": "medium",
          "pkg": "lodash@4.17.0", "cve": ["CVE-2020-8203"]}]
VIEW = {"open": [{"sev": "high", "file": "a.py", "line": 4, "key": "path-traversal", "desc": DESC, "ai": True},
                 {"sev": "high", "file": "conf.py", "line": 3, "key": "gitleaks:aws-access-token", "desc": "x", "ai": False}],
        "resolved": [{"sev": "low", "file": "b.py", "line": 1, "key": "old", "desc": DESC, "ai": True}],
        "fp": []}


class Render(unittest.TestCase):
    def test_sections(self):
        prev = [{"sev": "medium", "file": "old.py", "line": 1, "key": "gitleaks:gone-rule", "desc": "gone-rule"}]
        cur = [{"sev": "high", "file": "conf.py", "line": 3, "key": "gitleaks:aws-access-token", "desc": "aws-access-token"}]
        deps = [("OK", "python imports", "stdlib + first-party only"), ("FAIL", "python (launchd: /x)", "EOL past"),
                ("WARN", "online lookups", "skipped — offline")]
        md = SR.render(_j(T_ALL, ITEMS), VIEW, prev, cur, deps)
        for w in ("| gitleaks | ok | 12 | 0 | 1 | 0 | 0 | 1.2 s |", "| osv-scanner | skipped — offline |",
                  "| semgrep | missing — install: brew install semgrep |", "| bandit | failed — exit 2 |",
                  "| npm-audit | failed — timeout |", "## Findings (2)", "| high | gitleaks | aws-access-token | conf.py:3 |",
                  "| GHSA-aaaa-bbbb-cccc · CVE-2020-8203 | package-lock.json:0 | lodash@4.17.0 |", "open 2 (scan 1 · AI review 1) · resolved 1 · false-positive 0",
                  "| high | AI review | path-traversal | a.py:4 |", "- new 1 · gone 1",
                  "- new: gitleaks:aws-access-token · conf.py:3 · high", "- gone: gitleaks:gone-rule · old.py:1 · medium",
                  "- FAIL python (launchd: /x) — EOL past", "- WARN online lookups — skipped — offline",
                  "(uncommitted changes)"):
            self.assertIn(w, md)
        for leak in (SECRET, DESC, MSG):
            self.assertNotIn(leak, md)

    def test_no_tool_and_na(self):
        md = SR.render(_j(T_ALL[1:], []), {}, None, None, None)
        self.assertIn("No tool ran — this is not a clean result.", md)
        self.assertIn("n/a — no tool ran ok in this run", md)
        self.assertIn("not applicable (covers the Sidereus checkout only)", md)
        self.assertIn("n/a — no earlier scan record", SR.render(_j(T_ALL, []), {}, None, [], []))

    def test_scan_pair(self):
        a = {"src": "scan", "at": 1, "tools": ["gitleaks", "bandit"],
             "items": [{"key": "gitleaks:r", "file": "x"}, {"key": "bandit:B1", "file": "y"}]}
        b = {"src": "review", "at": 2, "items": []}
        c = {"src": "scan", "at": 3, "tools": ["gitleaks"], "items": []}
        self.assertEqual(SR.scan_pair([a, b, c], 3), ([{"key": "gitleaks:r", "file": "x"}], []))   # bandit did not run
        self.assertEqual(SR.scan_pair([a, b, c], 4), (None, None))
        self.assertEqual(SR.scan_pair([a], 1), (None, a["items"]))

    def test_caps_are_said(self):
        t = [dict(T_ALL[0], n={"critical": 0, "high": 0, "medium": 900, "low": 0})]
        cur = [{"sev": "medium", "file": "f%d" % i, "line": 1, "key": "bandit:B1"} for i in range(SR.LOG_ITEMS_MAX)]
        md = SR.render(_j(t, ITEMS[:1]), {}, cur, cur, [])
        self.assertIn("## Findings (900)", md)
        self.assertIn("Showing the first 1", md)
        self.assertIn("the log keeps %d findings per scan" % SR.LOG_ITEMS_MAX, md)

    def test_base_images(self):   # one line per image: fixable -> replace, unfixed -> waiting, failure -> its reason
        z = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        img = lambda **kw: dict({"id": "trivy-image", "rules": "default", "status": "ok", "ms": 1, "files": 1, "n": z}, **kw)
        t = [img(target="alpine:3.19", fixable=2, waiting=1), img(target="debian:12", fixable=0, waiting=3),
             img(target="ghcr.io/o/p:1", status="fail", why="docker login ghcr.io needed", files=0)]
        md = SR.render(_j(T_ALL[:1] + t, []), {}, None, None, None)
        for w in ("## Base images", "- `alpine:3.19`: fixable high/critical 2 — replace base image · waiting 1 (no fix yet)",
                  "- `debian:12`: fixable high/critical 0 · waiting 3 (no fix yet)",
                  "- `ghcr.io/o/p:1`: failed — docker login ghcr.io needed"):
            self.assertIn(w, md)
        self.assertIn("- (no image): skipped — add --images",
                      SR.render(_j([img(status="skipped", why="add --images")], []), {}, None, None, None))
        self.assertNotIn("## Base images", SR.render(_j(T_ALL, []), {}, None, None, None))

    def test_summary_header(self):   # R6: categories, severity totals, DB build time, fix lines; ver beside pkg
        s = {"cat": {"cve": 3, "sast": 1, "secret": 0, "config": 2}, "sev": {"critical": 1, "high": 2, "medium": 3, "low": 0},
             "db_built": "2026-11-10T04:12:30Z",
             "fixes": [{"pkg": "spring-web", "ver": "5.3.39", "to": "6.1.14", "n": 2, "sev": "critical"},
                       {"pkg": "a|b", "ver": "1", "to": "2", "n": 1, "sev": "low"},
                       {"pkg": "bad", "ver": "1", "to": "", "n": 1, "sev": "low"}], "fixes_more": 4}
        g = {"tool": "grype", "file": "pom.xml", "line": 0, "rule": "CVE-2024-38809", "sev": "critical",
             "pkg": "spring-web", "ver": "5.3.39", "fixv": "6.1.14"}
        md = SR.render(dict(_j(T_ALL[:1], [g]), summary=s), {}, None, None, None)
        for w in ("- Categories: CVE 3 · SAST 1 · Secret 0 · Config 2", "- Severity: critical 1 · high 2 · medium 3 · low 0",
                  "- Grype DB built: 2026-11-10T04:12:30Z", "- upgrade spring-web 5.3.39 to 6.1.14 resolves 2 (critical)",
                  "- upgrade a\\|b 1 to 2 resolves 1 (low)", "| pom.xml:0 | spring-web 5.3.39 |"):
            self.assertIn(w, md)
        self.assertNotIn("upgrade bad", md)
        self.assertLess(md.index("- Severity:"), md.index("## Tools"))
        self.assertLess(md.index("resolves 1 (low)"), md.index("- +4 more"))
        for bad in (0, True, -1, "4"):
            self.assertNotIn("more", SR.render(dict(_j(T_ALL[:1], []), summary=dict(s, fixes_more=bad)), {}, None, None, None))

    def test_summary_unknown_not_zero(self):   # R6: no summary or missing counters never read as zeros
        md = SR.render(_j(T_ALL[:1], []), {}, None, None, None)
        self.assertIn("- Summary: not recorded (older checks file)", md)
        self.assertNotIn("Categories:", md)
        md = SR.render(dict(_j(T_ALL[:1], []), summary={"cat": {"cve": True}, "sev": {"high": 1}, "db_built": 0}),
                       {}, None, None, None)
        self.assertIn("- Categories: CVE ? · SAST ? · Secret ? · Config ?", md)
        self.assertIn("- Severity: critical ? · high 1 · medium ? · low ?", md)
        self.assertNotIn("Grype DB built", md)
        nul = {"cat": {"cve": None, "sast": 2, "secret": None, "config": None}, "sev": {k: None for k in SR.SEVS}}
        md = SR.render(dict(_j(T_ALL[:1], []), summary=nul), {}, None, None, None)   # null = no ok tool covers it
        self.assertIn("- Categories: CVE ? · SAST 2 · Secret ? · Config ?", md)
        self.assertIn("- Severity: critical ? · high ? · medium ? · low ?", md)
        self.assertNotIn("Grype DB built", SR.render(dict(_j(T_ALL[:1], []), summary={"cat": {}, "sev": {}, "db_built": "1970"}),
                                                     {}, None, None, None))

    def test_pipes_escaped(self):
        md = SR.render(_j(T_ALL[:1], [dict(ITEMS[0], file="a|b`c.py")]), {}, None, None, None)
        self.assertIn("a\\|b'c.py:3", md)


class Files(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="sec-report-")
        self.addCleanup(shutil.rmtree, self.d)

    def test_write_prune_newest(self):
        other = os.path.join(self.d, "notes.md")
        with open(other, "w", encoding="utf-8") as f:
            f.write("keep")
        tgt = os.path.join(self.d, "target.txt")
        with open(tgt, "w", encoding="utf-8") as f:
            f.write("t")
        link = "security-report-19990101-0000.md"
        os.symlink(tgt, os.path.join(self.d, link))
        names = [SR.write(self.d, AT + 3600 * i, "r%d\n" % i) for i in range(12)]
        left = sorted(n for n in os.listdir(self.d) if SR.REPORT_RE.fullmatch(n) and n != link)
        self.assertEqual(left, sorted(names[2:]))
        self.assertTrue(os.path.exists(other) and os.path.islink(os.path.join(self.d, link)))
        self.assertEqual(SR.newest(self.d), names[-1])
        self.assertEqual(SR.read_text(self.d, names[-1]), "r11\n")
        self.assertEqual(SR.write(self.d, AT + 3600 * 11, "again\n"), names[-1])   # same minute: replaced
        self.assertEqual(SR.read_text(self.d, names[-1]), "again\n")
        self.assertEqual(SR.newest(os.path.join(self.d, "none")), "")

    def test_read_text_refuses(self):
        n = SR.write(self.d, AT, "ok\n")
        self.assertEqual(SR.read_text(self.d, n), "ok\n")
        tgt = os.path.join(self.d, "t.md")
        with open(tgt, "w", encoding="utf-8") as f:
            f.write("secret")
        os.symlink(tgt, os.path.join(self.d, "security-report-20000101-0000.md"))
        big = os.path.join(self.d, "security-report-20000101-0001.md")
        with open(big, "wb") as f:
            f.write(b"x" * (SR.MAX_BYTES + 1))
        for bad in ("../x", "../" + n, "t.md", "security-report-20000101-0000.md", "security-report-20000101-0001.md",
                    "security-report-2000-0001.md", None):
            self.assertIsNone(SR.read_text(self.d, bad), bad)


if __name__ == "__main__":
    unittest.main()
