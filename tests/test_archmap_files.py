"""arch_map.files: /api/arch/files body from a temp store (allow list, store dir and _ls patched; no git, clock or network)."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

AM = sidereus("arch_map")
AV = sidereus("arch_verify")
C1 = "c" * 40
TREE = ["README.md", "sidereus/a.py", "sidereus/sub/b.py", "sidereus2/x", "web/app.js"]


class FilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-archfiles-"))
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        self.store = os.path.join(self.tmp, "store")
        self.tree, self.calls, self.raise_ = list(TREE), [], None
        roots = lambda p: (os.path.realpath(p) if p and os.path.realpath(p) == self.repo else "")

        def ls(root, commit):
            self.calls.append((root, commit))
            if self.raise_:
                raise self.raise_
            return sorted(self.tree), False

        self.p = [mock.patch.object(AM, "ARCH_DIR", self.store), mock.patch.object(AM, "_struct_src_root", roots),
                  mock.patch.object(AM, "_ls", ls), mock.patch.dict(AM._TREE_CACHE, clear=True)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, path="sidereus", kind="module"):
        d = os.path.join(self.store, AV.repo_key(self.repo), C1)
        os.makedirs(d, exist_ok=True)
        m = {"v": 1, "repo": self.repo, "commit": C1,
             "modules": [{"id": "s", "name": "S", "path": path, "kind": kind},
                         {"id": "db", "name": "DB", "path": "", "kind": "external", "ext": "db"},
                         {"id": "e", "name": "E", "path": "", "kind": "module"}],
             "edges": []}
        for name, data in (("map.json", json.dumps(m)), ("verify.json", json.dumps({"commit": C1, "edges": []}))):
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.write(data)

    def test_r1_prefix_lists_only_its_files(self):
        self.put("sidereus/")
        out = AM.files(self.repo, "s")
        self.assertTrue(out["ok"])
        self.assertEqual((out["files"], out["total"], out["why"], out["commit"]),
                         (["sidereus/a.py", "sidereus/sub/b.py"], 2, "", C1))
        self.assertNotIn("sidereus2/x", out["files"])

    def test_r1_single_file_and_root(self):
        self.put("./web/app.js")
        self.assertEqual(AM.files(self.repo, "s")["files"], ["web/app.js"])
        self.put(".")
        self.assertEqual(AM.files(self.repo, "s")["total"], len(TREE))

    def test_r2_cap_keeps_real_total(self):
        self.tree = ["sidereus/f%03d.py" % i for i in range(250)]
        self.put()
        out = AM.files(self.repo, "s")
        self.assertEqual((len(out["files"]), out["total"]), (AM.FILES_MAX, 250))

    def test_r2_cut_flag(self):
        self.put()
        with mock.patch.object(AM, "_ls", lambda r, c: (["sidereus/a.py"], True)):
            self.assertTrue(AM.files(self.repo, "s")["cut"])

    def test_r3_reasons(self):
        self.assertEqual(AM.files(self.repo, "s")["why"], "nomap")
        self.put("gone/dir")
        self.assertEqual(AM.files(self.repo, "s")["why"], "gone")
        self.assertEqual(AM.files(self.repo, "db")["why"], "ext")
        self.assertEqual(AM.files(self.repo, "e")["why"], "nopath")
        self.assertEqual(AM.files(self.repo, "nope")["why"], "bad")
        self.assertFalse(AM.files(os.path.join(self.tmp, "other"), "s")["ok"])

    def test_guards_skip_git(self):
        for bad in ("../etc", "a/../b", "-x", ":x"):
            # schema may refuse some first (-> nomap); either way git must not run
            self.put(bad)
            self.assertIn(AM.files(self.repo, "s")["why"], ("bad", "nomap"), bad)
        self.assertEqual(AM.files(self.repo, "s/../x")["why"], "bad")
        self.assertEqual(self.calls, [])

    def test_prefix_guard_direct(self):
        for bad in ("../etc", "a/../b", "/abs", "-x", ":x", "a\\b", "a\0b", "./-x", "x" * (AM.PATH_MAX + 1)):
            self.assertIsNone(AM._mod_prefix(bad), repr(bad))
        self.assertEqual(AM._mod_prefix("./a/b/"), "a/b")
        self.assertEqual(AM._mod_prefix("."), "")

    def test_git_error(self):
        self.put()
        self.raise_ = subprocess.TimeoutExpired("git", 10)
        self.assertEqual(AM.files(self.repo, "s")["why"], "git")


class LsTest(unittest.TestCase):
    def test_argv_has_no_path_and_cache_hits(self):
        seen = []

        def run(cwd, args, timeout, cap):
            seen.append(list(args))
            return "b/x\0a/y\0", 8

        with mock.patch.object(AM, "_git_run_capped", run), mock.patch.dict(AM._TREE_CACHE, clear=True):
            self.assertEqual(AM._ls("/r", C1), (["a/y", "b/x"], False))
            self.assertEqual(AM._ls("/r", C1), (["a/y", "b/x"], False))
            for i in range(5):
                AM._ls("/r%d" % i, C1)
            self.assertLessEqual(len(AM._TREE_CACHE), 4)
        self.assertEqual(seen[0], ["ls-tree", "-r", "--name-only", "-z", C1])
        self.assertEqual(len(seen), 6)


if __name__ == "__main__":
    unittest.main()
