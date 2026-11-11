"""scripts/osv_rules.py (R5 writer side): --append validation and atomic write, --unjudged, --check (tmp files only)."""
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tests._load import ROOT, sidereus

OU = sidereus("osv_use")
AC = sidereus("arch_checks")
AV = sidereus("arch_verify")
SC = sidereus("sec_checks")
C1 = "c" * 40
GA, GB = "GHSA-aaaa-bbbb-cccc", "GHSA-dddd-eeee-ffff"


def cli():
    spec = importlib.util.spec_from_file_location("osv_rules_cli", os.path.join(ROOT, "scripts", "osv_rules.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def rule(name="xslt", **kw):
    r = {"name": name, "ids": [GA], "any": ["XsltView"], "globs": ["*.java"],
         "src": "https://github.com/advisories/" + GA, "at": "2026-11-11"}
    r.update(kw)
    return r


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-osvrules-"))
        self.arch = os.path.join(self.tmp, "arch")
        self.pack = os.path.join(self.tmp, "pack.json")
        with open(self.pack, "w", encoding="utf-8") as f:
            json.dump({"v": 1, "rules": [rule("packed", ids=[GB])]}, f)
        self.p = [mock.patch.object(AV, "ARCH_DIR", self.arch), mock.patch.object(OU, "USER_FILE", None),
                  mock.patch.object(OU, "PACK_FILE", self.pack)]
        for p in self.p:
            p.start()
        self.c = cli()

    def tearDown(self):
        for p in self.p:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.c.main(list(argv))
        return rc, buf.getvalue()

    def user(self):
        with open(os.path.join(self.arch, "osv-rules.json"), "rb") as f:
            return f.read()


class Append(Base):
    def test_r5_append_writes_user_file(self):
        rc, out = self.run_cli("--append", json.dumps(rule()))
        self.assertEqual(rc, 0, out)
        self.assertEqual(json.loads(self.user())["rules"], [rule()])
        self.assertEqual(self.run_cli("--check")[0], 0)

    def test_r5_append_refuses_bad_shapes(self):
        bad = [rule(src="http://example.com/a"), rule(src="javascript:alert(1)"), rule(at="2026-13-01"),
               rule(at="11/11/2026"), rule(any=["ab"]), rule(any=["x" * 81]), rule(any=["tab\there"]),
               rule(any=["p%d" % i + "xx" for i in range(21)]), rule(globs=["src/*.java"]), rule(ids=["PYSEC-1"]),
               rule(name="Bad Name"), dict(rule(), extra=1), [rule()]]
        for r in bad:
            rc, out = self.run_cli("--append", json.dumps(r))
            self.assertEqual(rc, 1, r)
        self.assertFalse(os.path.exists(os.path.join(self.arch, "osv-rules.json")))
        self.assertEqual(self.run_cli("--append", "{not json")[0], 1)

    def test_r5_duplicate_and_bad_entry_leave_file_unchanged(self):
        self.assertEqual(self.run_cli("--append", json.dumps(rule()))[0], 0)
        before = self.user()
        self.assertEqual(self.run_cli("--append", json.dumps(rule()))[0], 1)            # duplicate user name
        self.assertEqual(self.run_cli("--append", json.dumps(rule("packed")))[0], 1)    # duplicate pack name
        self.assertEqual(self.run_cli("--append", json.dumps(rule("y", any=["a"])))[0], 1)
        self.assertEqual(self.user(), before)
        self.assertEqual([n for n in os.listdir(self.arch) if n != "osv-rules.json"], [])   # no temp file left

    def test_r5_corrupt_user_file_is_not_rewritten(self):
        os.makedirs(self.arch)
        fp = os.path.join(self.arch, "osv-rules.json")
        with open(fp, "w", encoding="utf-8") as f:
            f.write(json.dumps({"v": 1, "rules": [rule("ok"), {"name": "broken"}]}))
        with open(fp, "rb") as f:
            before = f.read()
        self.assertEqual(self.run_cli("--append", json.dumps(rule("new")))[0], 1)
        self.assertEqual(self.user(), before)
        self.assertEqual(self.run_cli("--check")[0], 1)

    def test_r5_failed_write_leaves_file_unchanged(self):
        self.assertEqual(self.run_cli("--append", json.dumps(rule()))[0], 0)
        before = self.user()
        with mock.patch.object(self.c, "_atomic_write", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.run_cli("--append", json.dumps(rule("other")))
        self.assertEqual(self.user(), before)


class Unjudged(Base):
    def write_result(self, items, judged=True):
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(repo, exist_ok=True)
        j = AC.build(os.path.realpath(repo), C1, False, False, 1.0,
                     [{"id": "osv-scanner", "rules": "default", "status": "ok", "ms": 1, "files": 1}], items)
        if not judged:
            j.pop("osv_use", None)
        d = AV.store_dir(repo, C1)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, SC.SEC_FILE), "w", encoding="utf-8") as f:
            json.dump(j, f)
        return repo

    def it(self, rid, use, pkg):
        return {"tool": "osv-scanner", "file": "pom.xml", "line": 1, "rule": rid, "sev": "high", "pkg": pkg, "use": use}

    def test_r5_lists_only_none_ids(self):
        repo = self.write_result([self.it(GA, {"s": "none"}, "org.a:a"),
                                  self.it(GB, {"s": "unused", "r": "x", "at": "2026-11-11"}, "org.b:b"),
                                  self.it("GHSA-zzzz-zzzz-zzzz", {"s": "used", "r": "y", "at": "2026-11-11",
                                                                  "hf": "A.java", "hl": 1}, "org.c:c")])
        rc, out = self.run_cli("--unjudged", "--repo", repo)
        self.assertEqual(rc, 0)
        self.assertEqual(out.splitlines(), [GA + "\torg.a:a\t-"])

    def test_unjudged_without_result_or_annotation_is_unknown(self):
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(repo)
        self.assertEqual(self.run_cli("--unjudged", "--repo", repo)[0], 1)
        no_use = {"tool": "osv-scanner", "file": "pom.xml", "line": 1, "rule": GA, "sev": "high"}
        self.write_result([no_use])
        rc, out = self.run_cli("--unjudged", "--repo", repo)
        self.assertEqual(rc, 1)
        self.assertIn("not judged", out)

    def test_usage_error(self):
        self.assertEqual(self.run_cli("--unjudged")[0], 2)
        self.assertEqual(self.run_cli()[0], 2)


if __name__ == "__main__":
    unittest.main()
