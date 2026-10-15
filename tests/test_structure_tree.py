"""structure_tree: «소스» popup listing + file endpoint (temp dirs only; allow list, ~/.claude and git patched)."""
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

T = sidereus("structure_tree")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-tree-"))
        self.root = os.path.join(self.tmp, "proj")
        self.claude = os.path.join(self.tmp, "home", ".claude")
        os.makedirs(self.root)
        os.makedirs(self.claude)
        T._tree_cache.clear()
        T._st_cache.clear()
        self.allowed = {self.root}
        roots = lambda p: (os.path.realpath(p) if p and os.path.realpath(p) in self.allowed else "")
        self.p = [mock.patch.object(T, "_struct_src_root", roots),
                  mock.patch.object(T, "_claude_dirs", lambda: {self.claude})]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        T._tree_cache.clear()
        T._st_cache.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, rel, data=b"x\n", base=None):
        fp = os.path.join(base or self.root, rel)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "wb") as f:
            f.write(data if isinstance(data, bytes) else data.encode("utf-8"))
        return fp

    def file(self, rel, line=1):
        T._tree_cache.clear()
        return T.structure_file(self.root, rel, line)

    def paths(self):
        T._tree_cache.clear()
        return [e["p"] for e in T.structure_tree(self.root)["files"]]


class TreeTest(Base):
    def test_walk_skips_and_shape(self):
        self.put("a.py", b"print(1)\n")
        self.put("sub/b.js")
        self.put("node_modules/x.js")
        self.put(".hidden/y.py")
        self.put("__pycache__/z.pyc")
        self.put("bus.jsonl")
        self.put("deep/log.JSONL")
        self.put(".env", b"A=1\n")
        out = T.structure_tree(self.root)
        self.assertTrue(out["ok"])
        self.assertFalse(out["git"])
        self.assertEqual([e["p"] for e in out["files"]], [".env", "a.py", "sub/b.js"])
        self.assertEqual(out["files"][1], {"p": "a.py", "sz": 9})
        self.assertEqual(out["files"][0].get("sec"), 1)
        self.assertEqual(set(out), {"ok", "path", "git", "files", "n", "truncated", "warm"})
        self.assertTrue(T.structure_tree(self.root)["warm"])

    def test_outside_allow_list_and_claude_root(self):
        self.assertFalse(T.structure_tree(self.tmp)["ok"])
        self.allowed.add(self.claude)
        self.assertFalse(T.structure_tree(self.claude)["ok"])

    def test_cap(self):
        for i in range(5):
            self.put("f%d.py" % i)
        with mock.patch.object(T, "TREE_MAX", 3):
            out = T.structure_tree(self.root)
        self.assertEqual(out["n"], 3)
        self.assertTrue(out["truncated"])

    def test_git_listing_used(self):
        os.makedirs(os.path.join(self.root, ".git"))
        self.put("a.py")
        self.put("ignored.py")
        self.put("x.jsonl")
        with mock.patch.object(T, "_tree_git_ls", lambda r: ["a.py", "gone.py", "x.jsonl", "../up.py"]):
            out = T.structure_tree(self.root)
        self.assertTrue(out["git"])
        self.assertEqual([e["p"] for e in out["files"]], ["a.py"])

    def test_git_parse_nul_and_failure(self):
        class R:
            returncode, stdout = 0, b"a.py\x00b/c.js\x00bad\xff\x00"
        with mock.patch.object(T.subprocess, "run", lambda *a, **k: R()):
            self.assertEqual(T._tree_git_ls(self.root), ["a.py", "b/c.js", ""])
        R.returncode = 128
        with mock.patch.object(T.subprocess, "run", lambda *a, **k: R()):
            self.assertIsNone(T._tree_git_ls(self.root))


class FileTest(Base):
    def test_ok_shape_and_redaction(self):
        self.put("app.py", "a = 1\npassword=hunter22\nb = 2\n")
        out = self.file("app.py", 2)
        self.assertTrue(out["ok"])
        self.assertNotIn("hunter22", out["code"])
        self.assertEqual(out["masked"], 1)
        self.assertEqual((out["file"], out["line"], out["n"], out["enc"], out["truncated"]), ("app.py", 2, 4, "utf-8", False))
        self.assertEqual(set(out), {"ok", "path", "file", "line", "n", "code", "truncated", "bytes", "enc", "masked", "note"})

    def test_refusals(self):
        self.put("a.py")
        outside = self.put("secret_out.py", base=self.tmp)
        for bad in ("../proj/a.py", "/etc/passwd", self.root + "/a.py", "a.py\x00", "sub\\a.py", "", "..", "missing.py"):
            out = self.file(bad)
            self.assertFalse(out["ok"], bad)
            self.assertNotIn("code", out)
        os.symlink(outside, os.path.join(self.root, "link.py"))
        self.assertIn("link.py", self.paths())
        self.assertFalse(self.file("link.py")["ok"])

    def test_claude_symlink_and_jsonl(self):
        self.put("t.py", base=self.claude)
        os.symlink(self.claude, os.path.join(self.root, "cl"))
        os.symlink(os.path.join(self.claude, "t.py"), os.path.join(self.root, "c.py"))
        self.assertFalse(self.file("c.py")["ok"])
        self.assertFalse(self.file("cl/t.py")["ok"])
        self.put("bus.jsonl", b'{"body":"x"}\n')
        self.assertFalse(self.file("bus.jsonl")["ok"])
        os.symlink(os.path.join(self.root, "bus.jsonl"), os.path.join(self.root, "b.txt"))
        self.assertFalse(self.file("b.txt")["ok"])

    def test_not_in_listing(self):
        self.put("node_modules/x.js")
        self.put(".git/config")
        with mock.patch.object(T, "_tree_git_ls", lambda r: None):
            self.assertFalse(self.file("node_modules/x.js")["ok"])
            self.assertFalse(self.file(".git/config")["ok"])

    def test_secret_names_locked(self):
        for name in (".env.local", "k.PEM", "id_rsa.pub", "aws_credentials", "my-secret.txt", ".npmrc",
                     "prod.tfstate.backup", "kubeconfig", "config.local.json"):
            self.put(name)
            out = self.file(name)
            self.assertEqual((out["ok"], out.get("locked")), (False, True), name)
            self.assertNotIn("code", out)

    def test_private_key_body(self):
        self.put("k.txt", "x\n-----BEGIN RSA PRIVATE KEY-----\nMIIE\n")
        out = self.file("k.txt")
        self.assertEqual((out["ok"], out.get("locked")), (False, True))

    def test_binary(self):
        self.put("img.dat", b"\x89PNG\x00\x01\x02")
        out = self.file("img.dat")
        self.assertEqual((out["ok"], out.get("bin")), (False, True))

    def test_byte_cap(self):
        self.put("big.py", ("가" * 30 + "\n") * 100)
        with mock.patch.object(T, "FILE_MAX_BYTES", 1000):
            out = self.file("big.py")
        self.assertTrue(out["truncated"])
        self.assertEqual(out["enc"], "utf-8")
        self.assertGreater(out["bytes"], 1000)
        self.assertNotIn("�", out["code"])

    def test_line_cap(self):
        self.put("many.py", "x\n" * 50)
        with mock.patch.object(T, "FILE_MAX_LINES", 10):
            out = self.file("many.py", 99)
        self.assertEqual((out["n"], out["truncated"], out["line"]), (10, True, 10))

    def test_cp949_and_replace(self):
        self.put("k.txt", "한글 주석\n".encode("cp949"))
        out = self.file("k.txt")
        self.assertEqual((out["enc"], out["code"].split("\n")[0]), ("cp949", "한글 주석"))
        self.put("bad.txt", b"ok \xff\xfe\xfd end\n")
        out = self.file("bad.txt")
        self.assertEqual(out["enc"], "replace")
        self.assertTrue(out["note"])

    def test_outside_root_refused(self):
        self.put("a.py")
        self.assertFalse(T.structure_file(self.tmp, "proj/a.py")["ok"])


class GitStatusTest(Base):
    def git(self, *args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                        "-C", self.root] + list(args), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def repo(self):
        self.git("init", "-q")
        for f in ("clean.py", "mod.py", "staged.py", "gone.py", "moved.py", ".env"):
            self.put(f, ("v1 %s\n" % f).encode())    # distinct bodies: identical ones pair renames arbitrarily
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "init")
        self.put("mod.py", b"v2\n")
        self.put("staged.py", b"v2\n")
        self.git("add", "staged.py")
        os.remove(os.path.join(self.root, "gone.py"))
        self.git("mv", "moved.py", "renamed.py")
        self.put("new.py")
        self.put("newdir/a.py")
        self.put("added.py")
        self.git("add", "added.py")
        self.git("rm", "-q", ".env")

    def tree(self):
        T._tree_cache.clear()
        T._st_cache.clear()
        return T.structure_tree(self.root)

    def test_mapping(self):
        self.repo()
        out = self.tree()
        st = {e["p"]: e.get("st") for e in out["files"]}
        self.assertEqual(st, {"clean.py": None, "mod.py": "M", "staged.py": "M", "gone.py": "D", "renamed.py": "R",
                              "new.py": "A", "newdir/a.py": "A", "added.py": "A", ".env": "D"})
        self.assertEqual(out["stn"], {"A": 4, "M": 2, "D": 2})
        self.assertEqual(out["n"], len(out["files"]))
        env = [e for e in out["files"] if e["p"] == ".env"][0]
        self.assertEqual((env["sec"], env["sz"]), (1, 0))

    def test_deleted_refused(self):
        self.repo()
        self.tree()
        out = T.structure_file(self.root, "gone.py")
        self.assertEqual(out, {"ok": False, "msg": "This file was deleted.", "gone": True})
        self.assertTrue(T.structure_file(self.root, "mod.py")["ok"])

    def test_deleted_after_listing_cached(self):
        self.repo()
        self.tree()
        os.remove(os.path.join(self.root, "clean.py"))
        T._st_cache.clear()
        self.assertTrue(T.structure_file(self.root, "clean.py").get("gone"))

    def test_status_ttl(self):
        calls = []
        os.makedirs(os.path.join(self.root, ".git"))
        self.put("a.py")
        fake = lambda r: calls.append(r) or ({"a.py": "M"}, ())
        now = [1000.0]
        with mock.patch.object(T, "_tree_git_ls", lambda r: ["a.py"]), \
                mock.patch.object(T, "_tree_git_status", fake), \
                mock.patch.object(T.time, "time", lambda: now[0]):
            self.assertEqual(T.structure_tree(self.root)["files"][0]["st"], "M")
            now[0] += T.TREE_ST_TTL - 1
            T.structure_tree(self.root)
            self.assertEqual(len(calls), 1)
            now[0] += 2
            T.structure_tree(self.root)
            self.assertEqual(len(calls), 2)

    def test_status_failure_and_non_git(self):
        os.makedirs(os.path.join(self.root, ".git"))
        self.put("a.py")
        with mock.patch.object(T, "_tree_git_ls", lambda r: ["a.py"]), \
                mock.patch.object(T, "_tree_git_status", lambda r: None):
            out = self.tree()
        self.assertNotIn("stn", out)
        self.assertNotIn("st", out["files"][0])
        shutil.rmtree(os.path.join(self.root, ".git"))
        with mock.patch.object(T, "_tree_git_status", lambda r: self.fail("status on non-git")):
            out = self.tree()
            self.assertNotIn("stn", out)
            self.assertTrue(self.file("a.py")["ok"])

    def test_parse_rename_and_nul(self):
        class R:
            returncode = 0
            stdout = b"R  new.py\x00old.py\x00 M m.py\x00?? d/\x00?? ../x\x00 D bus.jsonl\x00?? bad\xff\x00"
        with mock.patch.object(T.subprocess, "run", lambda *a, **k: R()):
            self.assertEqual(T._tree_git_status(self.root), ({"new.py": "R", "m.py": "M"}, ("d/",)))


if __name__ == "__main__":
    unittest.main()
