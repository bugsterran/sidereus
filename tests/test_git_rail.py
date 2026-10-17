"""Timeline git rail: git_diff(view="rail") parses numstat/raw/status v2 without a patch body."""
import os
import tempfile
import unittest
from types import SimpleNamespace

from tests._load import sidereus

gv = sidereus("git_view")
gr = sidereus("git_rail")   # rail internals live here (split 2026-09-25)

RAW = ("\0".join([":100644 100644 aaa bbb M", "web/js/a.js",
                  ":000000 100644 000 ccc A", "web/css/new.css",
                  ":100644 000000 ddd 000 D", "old.txt",
                  ":100644 100644 eee fff R087", "sidereus/x.py", "sidereus/y.py",
                  ":100644 100644 111 222 M", "img.png",
                  "3\t1\tweb/js/a.js", "10\t0\tweb/css/new.css", "0\t7\told.txt",
                  "2\t2\t", "sidereus/x.py", "sidereus/y.py", "-\t-\timg.png"]) + "\0")
STATUS = ("# branch.oid 1234\n# branch.head feat/rail\n# branch.upstream origin/feat/rail\n"
          "# branch.ab +2 -1\n1 .M N... 100644 100644 100644 aaa bbb web/js/a.js\n")
LOG = "abc1234\t1790000000\tFirst subject\ndef5678\t1789990000\tSecond\n"


class Rail(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.cwd = tempfile.mkdtemp()
        self.addCleanup(os.rmdir, self.cwd)

        def fake(cwd, args, timeout, wait=None):
            self.calls.append(args)
            out = {"status": STATUS, "diff": RAW, "log": LOG}.get(args[0], "")
            return SimpleNamespace(stdout=out, returncode=0)
        self._run, self._sess = gv._git_run, gv.sessions_rows
        gv._git_run = fake
        gv.sessions_rows = lambda **k: [{"cwd": self.cwd, "repos": []}]

    def tearDown(self):
        gv._git_run, gv.sessions_rows = self._run, self._sess

    def test_rail_shape(self):
        d = gv.git_diff(self.cwd, view="rail")
        self.assertTrue(d["ok"])
        self.assertEqual((d["branch"], d["upstream"], d["ahead"], d["behind"], d["hasUp"]),
                         ("feat/rail", "origin/feat/rail", 2, 1, True))
        f = {x["path"]: x for x in d["files"]}
        self.assertEqual([x["path"] for x in d["files"]],
                         ["web/js/a.js", "web/css/new.css", "old.txt", "sidereus/y.py", "img.png"])
        self.assertEqual((f["web/js/a.js"]["st"], f["web/js/a.js"]["add"], f["web/js/a.js"]["del"]), ("M", 3, 1))
        self.assertEqual(f["web/css/new.css"]["st"], "A")
        self.assertEqual((f["old.txt"]["st"], f["old.txt"]["del"]), ("D", 7))
        self.assertEqual((f["sidereus/y.py"]["st"], f["sidereus/y.py"]["old"], f["sidereus/y.py"]["add"]), ("R", "sidereus/x.py", 2))
        self.assertTrue(f["img.png"]["bin"])
        self.assertEqual((d["n"], d["add"], d["del"]), (5, 15, 10))
        self.assertEqual(d["commits"][0], {"sha": "abc1234", "at": 1790000000, "msg": "First subject"})
        self.assertNotIn("diff", d)                            # no patch body on the polling path
        self.assertEqual(sum(1 for a in self.calls if a[0] == "diff"), 1)

    def test_rail_guard(self):
        d = gv.git_diff("/elsewhere", view="rail")
        self.assertFalse(d["ok"])
        self.assertEqual(self.calls, [])

    def test_default_view_unchanged(self):
        d = gv.git_diff(self.cwd, scope="work")
        self.assertIn("diff", d)
        self.assertNotIn("files", d)

    def test_untracked(self):
        with open(os.path.join(self.cwd, "new.txt"), "w", encoding="utf-8") as fh:
            fh.write("a\nb\nc")                                 # 3 lines, no trailing newline
        with open(os.path.join(self.cwd, "blob.bin"), "wb") as fh:
            fh.write(b"\x00\x01\x02")
        self.addCleanup(lambda: [os.remove(os.path.join(self.cwd, x)) for x in ("new.txt", "blob.bin")])
        many = ["? gen/f%d.txt" % i for i in range(gr.RAIL_UNTRACKED_MAX + 5)]  # missing on disk -> no count
        st = "\0".join(["# branch.oid 1", "# branch.head main", "? new.txt", "? blob.bin",
                        "2 R. N... 100644 100644 100644 a b R100 z.py", "? tricky"] + many) + "\0"
        run = lambda a: {"status": st, "diff": RAW, "log": LOG}.get(a[0], "")
        d = gr._git_rail(self.cwd, run)
        f = {x["path"]: x for x in d["files"]}
        self.assertEqual((f["new.txt"]["st"], f["new.txt"]["add"], f["new.txt"]["del"], f["new.txt"]["bin"]),
                         ("A", 3, 0, False))
        self.assertTrue(f["blob.bin"]["bin"])
        self.assertNotIn("tricky", f)                          # rename orig-path token, not an untracked entry
        self.assertEqual(d["untracked"], gr.RAIL_UNTRACKED_MAX + 7)
        self.assertEqual(sum(1 for x in d["files"] if x.get("new")), gr.RAIL_UNTRACKED_MAX)
        self.assertEqual((d["n"], d["add"], d["del"]), (5 + gr.RAIL_UNTRACKED_MAX + 7, 15 + 3, 10))
        self.assertEqual(d["branch"], "main")

    def test_detached_no_upstream(self):
        b = gr._status_branch("# branch.oid 1\n# branch.head (detached)\n")
        self.assertEqual(b, {"branch": "", "upstream": "", "ahead": 0, "behind": 0})


class UntrackedPatch(unittest.TestCase):
    """Rail click on an untracked file: all-added patch, guarded to untracked-not-ignored paths inside the root."""
    def setUp(self):
        import shutil
        self.root = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        os.mkdir(os.path.join(self.root, ".git"))
        os.mkdir(os.path.join(self.root, "sub"))
        self.out = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.out)
        for p, b in (("sub/n.js", b"a\nb"), ("blob", b"\x00x"), (os.path.join(self.out, "secret"), b"s\n")):
            with open(os.path.join(self.root, p), "wb") as fh:
                fh.write(b)
        os.symlink(os.path.join(self.out, "secret"), os.path.join(self.root, "link"))
        self.listed = "sub/n.js\0blob\0link\0"                 # what `ls-files --others --exclude-standard` says
        self.calls = []

        def fake(cwd, args, timeout, wait=None):
            self.calls.append((cwd, args))
            if args[0] == "ls-files" and "--others" in args:
                return SimpleNamespace(stdout=self.listed, returncode=0)
            if args[0] == "ls-files":
                return SimpleNamespace(stdout="", returncode=1)   # --error-unmatch: not tracked
            return SimpleNamespace(stdout="", returncode=0)
        self._run, self._sess = gv._git_run, gv.sessions_rows
        gv._git_run = fake
        gv.sessions_rows = lambda **k: [{"cwd": os.path.join(self.root, "sub"), "repos": []}]

    def tearDown(self):
        gv._git_run, gv.sessions_rows = self._run, self._sess

    def test_text_patch(self):
        p = gv._untracked_patch(os.path.join(self.root, "sub"), "sub/n.js")
        self.assertIn("new file mode", p)
        self.assertIn("@@ -0,0 +1,2 @@\n+a\n+b\n\\ No newline at end of file\n", p)
        self.assertEqual(self.calls[0][0], self.root)            # pathspec resolved from the repo root

    def test_binary(self):
        self.assertIn("Binary files /dev/null and b/blob differ", gv._untracked_patch(self.root, "blob"))

    def test_guard(self):
        for bad in ("../" + os.path.basename(self.out) + "/secret", os.path.join(self.out, "secret"), "link", ""):
            self.assertEqual(gv._untracked_patch(self.root, bad), "", bad)
        self.listed = ""                                        # ignored (or tracked): git does not list it
        self.assertEqual(gv._untracked_patch(self.root, "sub/n.js"), "")

    def test_wired(self):
        cwd = os.path.join(self.root, "sub")
        d = gv.git_diff(cwd, scope="work", new="sub/n.js")
        self.assertIn("+++ b/sub/n.js", d["diff"])
        self.assertNotIn("n.js", gv.git_diff(cwd, scope="work")["diff"])  # no blanket untracked in the window
        f = gv.git_file_diff(cwd, "sub/n.js", "work")
        self.assertTrue(f["ok"])
        self.assertIn("+a", f["diff"])
        self.assertFalse(gv.git_file_diff(cwd, "sub/n.js", "all")["ok"])


class RealRepo(unittest.TestCase):
    """Real git in temp dirs: non-repo, unborn repo, `rm --cached` dedupe."""
    def setUp(self):
        import shutil
        import subprocess
        self.sp = subprocess
        self.d = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d)
        self._sess = gv.sessions_rows
        gv.sessions_rows = lambda **k: [{"cwd": self.d, "repos": []}]
        self.addCleanup(setattr, gv, "sessions_rows", self._sess)

    def git(self, *a):
        self.sp.run(["git", "-C", self.d, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
                    + list(a), check=True, capture_output=True)

    def put(self, p, b):
        with open(os.path.join(self.d, p), "w", encoding="utf-8") as fh:
            fh.write(b)

    def test_not_a_repo(self):
        d = gv.git_diff(self.d, view="rail")
        self.assertEqual(d, {"ok": False, "msg": "Not a git repository."})

    def test_unborn_staged(self):
        self.git("init", "-q", "-b", "fresh")
        self.put("a.txt", "x\ny\n")
        self.git("add", "a.txt")
        d = gv.git_diff(self.d, view="rail")
        self.assertTrue(d["ok"])
        f = {x["path"]: x for x in d["files"]}
        self.assertEqual((f["a.txt"]["st"], f["a.txt"]["add"]), ("A", 2))
        self.assertNotIn("new", f["a.txt"])                    # from the diff, not the untracked list
        self.assertEqual((d["branch"], d["commits"]), ("fresh", []))

    def test_rm_cached_dedupe(self):
        self.git("init", "-q")
        self.put("x.txt", "1\n2\n3\n")
        self.git("add", "x.txt")
        self.git("commit", "-qm", "c")
        self.git("rm", "-q", "--cached", "x.txt")
        d = gv.git_diff(self.d, view="rail")
        self.assertEqual([x["path"] for x in d["files"]], ["x.txt"])
        self.assertEqual((d["files"][0]["st"], d["n"], d["del"], d["add"], d["untracked"]), ("D", 1, 3, 0, 0))


class ReadSmall(unittest.TestCase):
    def setUp(self):
        import shutil
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d)
        gr._rail_lc.clear()

    def test_fifo_and_symlink_refused(self):
        f = os.path.join(self.d, "pipe")
        os.mkfifo(f)
        self.assertIsNone(gv._read_small(f))                   # returns, does not block on open/read
        with open(os.path.join(self.d, "real"), "w", encoding="utf-8") as fh:
            fh.write("a\n")
        os.symlink(os.path.join(self.d, "real"), os.path.join(self.d, "ln"))
        self.assertIsNone(gv._read_small(os.path.join(self.d, "ln")))
        self.assertEqual(gv._read_small(os.path.join(self.d, "real")), b"a\n")
        self.assertEqual(gr._untracked_rec(self.d, "pipe")["add"], 0)

    def test_line_count_cache(self):
        p = os.path.join(self.d, "t.txt")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("1\n2\n")
        opens = []
        real = os.open
        gv.os.open = lambda *a, **k: (opens.append(a[0]), real(*a, **k))[1]
        self.addCleanup(setattr, gv.os, "open", real)
        self.assertEqual(gr._untracked_rec(self.d, "t.txt")["add"], 2)
        self.assertEqual(gr._untracked_rec(self.d, "t.txt")["add"], 2)
        self.assertEqual(len(opens), 1)                        # second poll served from the cache
        with open(p, "a", encoding="utf-8") as fh:
            fh.write("3\n4\n5\n")                              # size changes -> re-read
        self.assertEqual(gr._untracked_rec(self.d, "t.txt")["add"], 5)
        self.assertEqual(len(opens), 2)


if __name__ == "__main__":
    unittest.main()
