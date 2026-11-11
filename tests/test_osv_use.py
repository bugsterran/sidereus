"""osv-scanner usage judgement (sidereus/osv_use.py): grep over tmp trees, item `use`, schema and sort (R1-R3)."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

OU = sidereus("osv_use")
AC = sidereus("arch_checks")
AV = sidereus("arch_verify")
SC = sidereus("sec_checks")
TP = sidereus("sec_testpaths")
C1 = "a" * 40
GA, GB, GC = "GHSA-aaaa-bbbb-cccc", "GHSA-dddd-eeee-ffff", "GHSA-gggg-hhhh-iiii"
SECRET_LINE = "class X { XsltViewResolver secretLineText; }"


def rule(name, ids, pats, globs=("*.java",)):
    return {"name": name, "ids": list(ids), "any": list(pats), "globs": list(globs),
            "src": "https://github.com/advisories/" + ids[0], "at": "2026-11-11"}


def item(rule_id, sev="high", cve=None):
    x = {"tool": "osv-scanner", "file": "pom.xml", "line": 1, "rule": rule_id, "sev": sev, "pkg": "org.x:y"}
    if cve:
        x["cve"] = cve
    return x


class Tree(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-osvuse-"))
        self.root = os.path.join(self.tmp, "src")
        os.makedirs(self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def w(self, rel, data):
        fp = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "wb") as f:
            f.write(data if isinstance(data, bytes) else data.encode("utf-8"))
        return fp


class Judge(Tree):
    def test_r1_no_hit_is_unused_with_rule_and_date(self):
        self.w("src/A.java", "class A {}\n")
        rs = [rule("xslt", [GA], ["XsltView"])]
        out = OU.annotate([item(GA)], rs, OU.grep(self.root, rs))
        self.assertEqual(out[0]["use"], {"s": "unused", "r": "xslt", "at": "2026-11-11"})

    def test_r2_hit_is_used_with_file_line_only(self):
        self.w("src/A.java", "package a;\n\n" + SECRET_LINE + "\n")
        rs = [rule("xslt", [GA], ["XsltView"])]
        out = OU.annotate([item(GA)], rs, OU.grep(self.root, rs))
        self.assertEqual(out[0]["use"], {"s": "used", "r": "xslt", "at": "2026-11-11", "hf": "src/A.java", "hl": 3})
        blob = json.dumps(out) + json.dumps(AC.build(self.root, C1, False, False, 1.0, [], out))
        self.assertNotIn("secretLineText", blob)   # R2: never the matched line text
        self.assertNotIn("XsltView", blob)   # nor the pattern

    def test_r3_no_rule_is_none(self):
        rs = [rule("xslt", [GA], ["XsltView"])]
        out = OU.annotate([item(GB), {"tool": "gitleaks", "file": "a", "line": 1, "rule": "r", "sev": "high"}],
                          rs, OU.grep(self.root, rs))
        self.assertEqual(out[0]["use"], {"s": "none"})
        self.assertNotIn("use", out[1])

    def test_cve_alias_matches_and_any_rule_hit_wins(self):
        self.w("B.java", "SseEmitter e;\n")
        rs = [rule("x", ["CVE-2024-1234"], ["XsltView"]), rule("s", ["CVE-2024-1234"], ["SseEmitter"])]
        out = OU.annotate([item(GC, cve=["CVE-2024-1234"])], rs, OU.grep(self.root, rs))
        self.assertEqual(out[0]["use"]["s"], "used")
        self.assertEqual(out[0]["use"]["r"], "s")

    def test_one_incomplete_rule_blocks_unused(self):
        hits = {"a": {"s": "unused"}, "b": {"s": "none"}}
        rs = [rule("a", [GA], ["Foo"]), rule("b", [GA], ["Bar"])]
        self.assertEqual(OU.judge(item(GA), rs, hits), {"s": "none"})

    def test_glob_scope(self):
        self.w("notes.txt", "XsltView\n")
        rs = [rule("xslt", [GA], ["XsltView"])]
        self.assertEqual(OU.grep(self.root, rs)["xslt"], {"s": "unused"})


class Limits(Tree):
    """⚠Every limit, skip or error leaves the rule none — never unused."""
    rs = [rule("xslt", [GA], ["XsltView"])]

    def s(self):
        return OU.grep(self.root, self.rs)["xslt"]["s"]

    def test_file_over_max(self):
        self.w("A.java", "x" * 64)
        with mock.patch.object(OU, "FILE_MAX", 32):
            self.assertEqual(self.s(), "none")

    def test_nul_in_head(self):
        self.w("A.java", b"X\x00s\x00l\x00t\x00")
        self.assertEqual(self.s(), "none")

    def test_symlinked_file(self):
        self.w("real.txt", "nothing")
        os.symlink(os.path.join(self.root, "real.txt"), os.path.join(self.root, "L.java"))
        self.assertEqual(self.s(), "none")

    def test_symlinked_dir_out_of_root(self):
        out = os.path.join(self.tmp, "outside")
        os.makedirs(out)
        os.symlink(out, os.path.join(self.root, "lib"))
        self.w("A.java", "class A {}")
        self.assertEqual(self.s(), "none")

    def test_total_and_count_caps(self):
        self.w("A.java", "a" * 10)
        self.w("B.java", "b" * 10)
        with mock.patch.object(OU, "TOTAL_MAX", 5):
            self.assertEqual(self.s(), "none")
        with mock.patch.object(OU, "FILES_MAX", 1):
            self.assertEqual(self.s(), "none")

    def test_time_budget(self):
        self.w("A.java", "a")
        self.w("B.java", "b")
        t = iter([0.0, 0.0, 100.0, 100.0])
        with mock.patch.object(OU, "_clock", lambda: next(t)):
            self.assertEqual(self.s(), "none")

    def test_hit_survives_a_later_stop(self):
        self.w("A.java", "XsltView")
        self.w("B.java", "b")
        with mock.patch.object(OU, "FILES_MAX", 1):
            self.assertEqual(self.s(), "used")

    def test_no_tests_root_excludes_test_hits(self):
        self.w("src/test/java/T.java", "XsltView")   # a test-dir hit only
        self.w("src/main/java/A.java", "class A {}")
        self.assertEqual(self.s(), "used")
        code = os.path.join(self.tmp, "code")
        os.makedirs(code)
        TP.prune_copy(self.root, code)
        self.assertEqual(OU.grep(code, self.rs)["xslt"], {"s": "unused"})


class Schema(unittest.TestCase):
    def base(self, its):
        return AC.build("/r", C1, False, False, 1.0, [{"id": "osv-scanner", "rules": "default", "status": "ok",
                                                       "ms": 1, "files": 1}], its)

    def test_build_counts_before_cap_and_passes_gate(self):
        its = [dict(item(GA), use={"s": "unused", "r": "x", "at": "2026-11-11"}) for _ in range(3)]
        its.append(dict(item(GB), use={"s": "none"}))
        with mock.patch.object(AC, "ITEMS_MAX", 2):
            j = self.base(its)
            self.assertEqual(AC.checks_errors(j, ids=SC.SEC_IDS), [])
        self.assertEqual(j["osv_use"], {"unused": 3, "used": 0, "none": 1})
        self.assertEqual(j["items"][0]["use"], {"s": "none"})   # unused sorts last, the cap keeps none

    def test_unused_sorts_last_even_when_more_severe(self):
        its = [dict(item(GA, "critical"), use={"s": "unused", "r": "x", "at": "2026-11-11"}),
               dict(item(GB, "low"), use={"s": "used", "r": "y", "at": "2026-11-11", "hf": "a/B.java", "hl": 2})]
        self.assertEqual([x["use"]["s"] for x in self.base(its)["items"]], ["used", "unused"])

    def test_old_file_without_use_has_no_annotation(self):
        j = self.base([item(GA)])
        self.assertNotIn("osv_use", j)
        self.assertNotIn("use", j["items"][0])
        self.assertEqual(AC.checks_errors(j, ids=SC.SEC_IDS), [])

    def test_gate_refuses_bad_use(self):
        bad = [{"s": "used", "r": "x", "at": "2026-11-11", "hf": "../etc/passwd", "hl": 1},
               {"s": "used", "r": "x", "at": "2026-11-11", "hf": "a.java", "hl": 0},
               {"s": "unused", "r": "x", "at": "2026-11-11", "line": "text"},
               {"s": "unused", "r": "x", "at": "2026-11-11", "hf": "a.java", "hl": 1},
               {"s": "none", "r": "x"}, {"s": "maybe"}, {"s": "unused", "r": "x", "at": "11/11/2026"}]
        for u in bad:
            j = self.base([item(GA)])
            j["items"][0]["use"] = u
            self.assertIn("items", AC.checks_errors(j, ids=SC.SEC_IDS), u)
        j = self.base([item(GA)])
        j["osv_use"] = {"unused": 1, "used": 0}
        self.assertIn("osv_use", AC.checks_errors(j, ids=SC.SEC_IDS))

    def test_use_on_another_tool_is_refused(self):
        x = {"tool": "gitleaks", "file": "a", "line": 1, "rule": "r", "sev": "high", "use": {"s": "none"}}
        self.assertIsNone(AC._clean_item(x, SC.SEC_IDS))

    def test_loader_keeps_use_and_counts(self):
        tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-osvuse-load-"))
        try:
            repo = os.path.join(tmp, "repo")
            os.makedirs(repo)
            with mock.patch.object(AV, "ARCH_DIR", os.path.join(tmp, "arch")):
                its = [dict(item(GA), use={"s": "used", "r": "y", "at": "2026-11-11", "hf": "a/B.java", "hl": 2})]
                j = AC.build(repo, C1, False, False, 1.0, [], its)
                d = AV.store_dir(repo, C1)
                os.makedirs(d)
                with open(os.path.join(d, SC.SEC_FILE), "w", encoding="utf-8") as f:
                    json.dump(j, f)
                s = AC.load_checks(repo, os.path.join(os.path.dirname(d), "m" * 40), {"modules": []})["security"]
            self.assertEqual(s["osv_use"], {"unused": 0, "used": 1, "none": 0})
            self.assertEqual(s["top"][0]["use"]["hf"], "a/B.java")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Rules(unittest.TestCase):
    def test_pack_file_passes_check_rule(self):
        rs, errs = OU.read_file(OU.pack_file(), missing_ok=False)
        self.assertEqual(errs, [])
        self.assertGreater(len(rs), 0)
        for r in rs:
            self.assertEqual(OU.check_rule(r), [], r["name"])

    def test_symlinked_rule_file_refused(self):
        tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-osvuse-rf-"))
        try:
            real = os.path.join(tmp, "real.json")
            with open(real, "w", encoding="utf-8") as f:
                json.dump({"v": 1, "rules": [rule("a", [GA], ["Foo"])]}, f)
            link = os.path.join(tmp, "osv-rules.json")
            os.symlink(real, link)
            rs, errs = OU.read_file(link)
            self.assertEqual(rs, [])
            self.assertTrue(errs)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
