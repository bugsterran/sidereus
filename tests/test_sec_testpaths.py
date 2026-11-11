"""Test-code paths for `--no-tests` scans: matching, the pruned copy, and the log / report rule that such a scan
never resolves a finding in test code (tmp fixtures only)."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

TP = sidereus("sec_testpaths")
SC = sidereus("sec_checks")
SR = sidereus("sec_report")
C1, C2 = "a" * 40, "b" * 40


class IsTest(unittest.TestCase):
    def test_patterns(self):
        for rel in ("tests/a.py", "test/a.go", "src/__tests__/a.js", "spec/a.rb", "x/fixtures/key.pem", "x/mocks/m.ts",
                    "a_test.go", "src/a.test.js", "src/a.spec.ts", "test_a.py", "pkg/tests/deep/b.txt"):
            self.assertTrue(TP.is_test(rel), rel)

    def test_rejects(self):
        for rel in ("contest.py", "src/testing/x.py", "latest/a.py", "tests", "a.py", "testx/a.py", "Test_a.py", "", None):
            self.assertFalse(TP.is_test(rel), rel)


class PruneCopy(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-testpaths-"))
        self.src, self.dst = os.path.join(self.tmp, "src"), os.path.join(self.tmp, "dst")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def w(self, rel):
        fp = os.path.join(self.src, rel)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w", encoding="utf-8") as f:
            f.write("x")

    def files(self, root):
        return sorted(os.path.relpath(os.path.join(dp, f), root).replace(os.sep, "/")
                      for dp, dns, fns in os.walk(root) for f in fns + [d for d in dns if os.path.islink(os.path.join(dp, d))])

    def test_count_and_copy(self):
        rels = ["a.py", "src/b.js", "src/b.test.js", "tests/fixtures/mock_secret", "tests/c.py", "pkg/mocks/m.ts",
                "test_d.py", "contest.py", ".git/config"]
        for r in rels:
            self.w(r)
        n = TP.prune_copy(self.src, self.dst)
        self.assertEqual(n, 5)
        self.assertEqual(self.files(self.dst), sorted(r for r in rels if not TP.is_test(r) and not r.startswith(".git/")))

    @unittest.skipUnless(hasattr(os, "symlink") and os.name == "posix", "symlinks")
    def test_symlink_not_followed(self):
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(outside)
        for i in range(3):
            with open(os.path.join(outside, "f%d" % i), "w", encoding="utf-8") as f:
                f.write("x")
        self.w("a.py")
        os.symlink(outside, os.path.join(self.src, "tests"))    # a linked test folder counts as one entry
        os.symlink(outside, os.path.join(self.src, "lib"))      # a linked non-test folder is copied as a link
        n = TP.prune_copy(self.src, self.dst)
        self.assertEqual(n, 1)
        self.assertTrue(os.path.islink(os.path.join(self.dst, "lib")))
        self.assertFalse(os.path.lexists(os.path.join(self.dst, "tests")))


class NoTestsLog(unittest.TestCase):
    """A --no-tests scan keeps an earlier test finding open; a non-test finding missing from it resolves."""
    def setUp(self):
        self.k = tempfile.mkdtemp(prefix="sidereus-testpaths-log-")

    def tearDown(self):
        shutil.rmtree(self.k, ignore_errors=True)

    def items(self, *files):
        return [{"tool": "gitleaks", "file": f, "line": 1, "rule": "generic-api-key", "sev": "high"} for f in files]

    def test_stale_resolve(self):
        full = SC.scan_record(C1, 1.0, ["gitleaks"], self.items("tests/fixtures/mock_secret", "src/a.py"))
        nt = SC.scan_record(C2, 2.0, ["gitleaks"], [], notests=True)
        self.assertNotIn("notests", full)
        self.assertTrue(nt["notests"])
        for r in (full, nt):
            self.assertTrue(SC.log_append(self.k, r))
        v = SC.log_view(self.k)
        self.assertEqual([x["file"] for x in v["open"]], ["tests/fixtures/mock_secret"])
        self.assertEqual([x["file"] for x in v["resolved"]], ["src/a.py"])
        recs = SC.log_read(self.k)
        self.assertTrue(recs[-1]["notests"])
        prev, cur = SR.scan_pair(recs, 2.0)
        self.assertEqual(([x["file"] for x in prev], cur), (["src/a.py"], []))   # the test finding is not «gone»
        SC.log_append(self.k, SC.scan_record(C2, 3.0, ["gitleaks"], self.items("tests/fixtures/mock_secret", "src/b.py")))
        prev, cur = SR.scan_pair(SC.log_read(self.k), 3.0)   # prev notests, cur full: the test finding is not «new»
        self.assertEqual(([x["file"] for x in prev], [x["file"] for x in cur]), ([], ["src/b.py"]))
        SC.log_append(self.k, SC.scan_record(C2, 4.0, ["gitleaks"], []))   # a full scan does resolve it
        self.assertEqual(SC.log_view(self.k)["open"], [])

    def test_report_line(self):
        j = {"repo": "/r", "commit": C1, "at": 1.0, "tools": [], "items": []}
        self.assertNotIn("Test code excluded", SR.render(j, None, None, None, None))
        j["tests_excluded"] = {"n": 7, "patterns": list(TP.PATTERNS)}
        self.assertIn("- Test code excluded: 7 files", SR.render(j, None, None, None, None))
        self.assertNotIn("mock_secret", json.dumps(j))


if __name__ == "__main__":
    unittest.main()
