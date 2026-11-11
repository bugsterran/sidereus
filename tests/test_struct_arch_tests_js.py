"""«Include test code» in the security run window (web/js/84l4-structure-arch-tests.js + 84l): unchecked by default → body and
terminal command carry --no-tests; checked removes it; «Test code excluded · N files» only with a valid tests_excluded."""
import json
import os
import re
import shutil
import unittest

from tests.test_struct_arch_checks_js import run

_I18N = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "js", "06-i18n-zs-arch-checks.js")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchTests(unittest.TestCase):
    def test_no_tests_flag(self):
        sess = [{"sid": "a1", "cwd": "/x/shop", "mbox": "a", "mboxSrc": "identity", "state": "idle", "ageSec": 1}]
        r = run("const d = {ok: true, sidereus: '/sid', checks: null}, c = archChkFixCands(" + json.dumps(sess) + ", '/x/shop');"
                "const off = {sel: {}, req: null, run: {sid: 'a1', busy: false}, runSent: null}, on = {sel: {}, req: null, run: {sid: 'a1', busy: false, tests: true}, runSent: null};"
                "const non = {sel: {}, req: null, run: {sid: '', busy: false}, runSent: null};"
                "console.log(JSON.stringify([archChkRunBody('/x/shop', '/sid/'), archChkRunBody('/x/shop', '/sid/', false, false, true), archChkRunCmds('/x/shop', '/sid'), archChkRunCmds('/x/shop', '/sid', false, true),"
                "archChkRunHtml('/x/shop', d, off, c), archChkRunHtml('/x/shop', d, on, c), archChkRunHtml('/x/shop', d, non, []), archChkTestBox(null)]));")
        self.assertIn("Skip test code: pass --no-tests to the scanner run (gitleaks, semgrep, bandit).", r[0])
        self.assertNotIn("--no-tests", r[1])
        self.assertTrue(r[2]["sh"].endswith(" --no-tests") and r[2]["win"].endswith(" --no-tests"))
        self.assertNotIn("--no-tests", r[3]["sh"] + r[3]["win"])
        self.assertIn("<input type=checkbox data-cktests> 테스트 코드도 검사", r[4])   # unchecked by default
        self.assertIn("pass --no-tests", r[4])                                       # preview shows what will be sent
        self.assertIn("data-cktests checked", r[5])
        self.assertNotIn("--no-tests", r[5])
        self.assertIn("data-cktests>", r[6])                                         # terminal branch has the box too
        self.assertIn("--no-tests</code>", r[6])
        self.assertNotIn("checked", r[7])
        self.assertNotIn("테스트", r[0])                                              # wire text stays English

    def test_badge(self):
        r = run("console.log(JSON.stringify([archChkTestBadge({tests_excluded: {n: 12}}), archChkTestBadge({tests_excluded: {n: 0}}), archChkTestBadge({}), archChkTestBadge(null),"
                "archChkTestBadge({tests_excluded: {n: -1}}), archChkTestBadge({tests_excluded: {n: 1.5}}), archChkTestBadge({tests_excluded: {n: '<b>'}}), archChkTestBadge({tests_excluded: [3]}),"
                "archChkTestBadge({tests_excluded: {}})]));")
        self.assertEqual(r[0], '<div class="archckst cktestx">테스트 코드 제외됨 · 12개 파일</div>')
        self.assertIn("0개 파일", r[1])
        self.assertEqual(r[2:], [""] * 7)                                             # missing / bad n = unknown, nothing shown
        e = run("console.log(JSON.stringify(archChkTestBadge({tests_excluded: {n: 3}})));", lang="en")
        self.assertIn("Test code excluded · 3 files", e)

    def test_badge_in_window(self):
        sec = {"commit": "abc", "at": 1700000000, "top": [], "tools": [{"id": "gitleaks", "status": "ok", "n": {}}], "tests_excluded": {"n": 4}}
        r = run("const d = {ok: true, sidereus: '/sid', checks: {security: " + json.dumps(sec) + "}}, S = {sel: {}, req: null, run: null, runSent: null};"
                "const d2 = {ok: true, sidereus: '/sid', checks: {security: " + json.dumps(dict(sec, tests_excluded=None)) + "}};"
                "console.log(JSON.stringify([archChkWinHtml('/x/shop', d, S, []), archChkWinHtml('/x/shop', d2, S, [])]));", lang="en")
        self.assertIn("Test code excluded · 4 files", r[0])
        self.assertNotIn("Test code excluded", r[1])

    def test_ko_entries(self):
        with open(_I18N, encoding="utf-8") as fh:
            src = fh.read()
        self.assertTrue(re.search(r"'Include test code': '테스트 코드도 검사'", src))
        self.assertTrue(re.search(r"'Test code excluded · \{n\} files': '테스트 코드 제외됨 · \{n\}개 파일'", src))


if __name__ == "__main__":
    unittest.main()
