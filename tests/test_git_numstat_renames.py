"""Diff window + Branches commit detail: full numstat list survives a cut patch; renames are one row in both (temp repo)."""
import os
import shutil
import subprocess
import tempfile
import unittest

from tests._fs import rmtree_force
from tests._load import sidereus

gv = sidereus("git_view")


class NumstatRenames(unittest.TestCase):
    def setUp(self):
        self.d = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(rmtree_force, self.d)
        for name, val in (("sessions_rows", lambda **k: [{"cwd": self.d, "repos": []}]),
                          ("_branch_ok", lambda cwd: True)):
            self.addCleanup(setattr, gv, name, getattr(gv, name))
            setattr(gv, name, val)
        self.git("init", "-q", "-b", "main")
        os.makedirs(os.path.join(self.d, "client"))
        with open(os.path.join(self.d, "client", "m.ts"), "w", encoding="utf-8") as fh:
            fh.write("".join("line %d\n" % i for i in range(9)))
        self.git("add", "-A")
        self.git("commit", "-qm", "init")
        os.makedirs(os.path.join(self.d, "shared"))
        self.git("mv", "client/m.ts", "shared/m.ts")
        with open(os.path.join(self.d, "shared", "m.ts"), "a", encoding="utf-8") as fh:
            fh.write("a\nb\nc\nd\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "move")
        self.ren = self.git("rev-parse", "HEAD").strip()

    def git(self, *a):
        return subprocess.run(["git", "-C", self.d, "-c", "user.name=t", "-c", "user.email=t@t",
                               "-c", "commit.gpgsign=false"] + list(a),
                              check=True, capture_output=True, text=True, encoding="utf-8").stdout

    def test_parser_rename_and_binary(self):
        rows = gv._numstat("3\t1\ta.txt\0" "4\t0\t\0old/x\0new/x\0" "-\t-\tb.bin\0")
        self.assertEqual([(r["path"], r["from"], r["add"], r["del"], r["bin"]) for r in rows],
                         [("a.txt", "", 3, 1, False), ("new/x", "old/x", 4, 0, False), ("b.bin", "", 0, 0, True)])

    def test_commit_detail_rename_is_one_row(self):
        code, r = gv.git_commit(self.d, self.ren)
        self.assertEqual(code, 200)
        self.assertEqual(r["nfiles"], 1)
        f = r["files"][0]
        self.assertEqual((f["path"], f["from"], f["add"], f["del"]), ("shared/m.ts", "client/m.ts", 4, 0))
        code, p = gv.git_commit(self.d, self.ren, "shared/m.ts")
        self.assertEqual(code, 200)
        self.assertIn("rename from client/m.ts", p["diff"])

    def test_diff_window_rename_matches_detail(self):
        r = gv.git_diff(self.d, "c:" + self.ren)
        self.assertTrue(r["ok"])
        self.assertEqual([(f["path"], f["add"], f["del"]) for f in r["numstat"]], [("shared/m.ts", 4, 0)])

    def test_cut_patch_keeps_full_file_list(self):
        for i in range(30):
            with open(os.path.join(self.d, "f%02d.txt" % i), "w", encoding="utf-8") as fh:
                fh.write("x" * 80 + "\n" + "".join("row %d\n" % k for k in range(20)))
        self.git("add", "-A")
        self.git("commit", "-qm", "big")
        sha = self.git("rev-parse", "HEAD").strip()
        old = gv.DIFF_MAX
        gv.DIFF_MAX = 2000
        self.addCleanup(setattr, gv, "DIFF_MAX", old)
        r = gv.git_diff(self.d, "c:" + sha)
        self.assertTrue(r["ok"])
        self.assertGreater(r["cutBytes"], 2000)
        self.assertLess(r["diff"].count("diff --git "), 30)        # the patch alone undercounts
        self.assertEqual(r["numstatN"], 30)
        self.assertTrue(all(f["add"] == 21 for f in r["numstat"]))


if __name__ == "__main__":
    unittest.main()
