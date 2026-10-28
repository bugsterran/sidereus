"""backup.sh: a missing MCP checkout is skipped (not a 0-byte «success»), and a failed tar leaves no archive for the keep-10 prune."""
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backup.sh")


@unittest.skipUnless(shutil.which("bash") and shutil.which("tar"), "bash/tar not installed")
class BackupSh(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.code, self.data = os.path.join(self.tmp, "code"), os.path.join(self.tmp, "data")
        os.makedirs(os.path.join(self.code, "web", "js"))
        os.makedirs(self.data)
        shutil.copy(SRC, self.code)

    def run_backup(self):
        env = dict(os.environ, MAILBOX_DIR=self.data, MAILBOX_MCP_SRC=os.path.join(self.tmp, "no-such-mcp"))
        return subprocess.run(["bash", os.path.join(self.code, "backup.sh")], env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)

    def archives(self):
        d = os.path.join(self.data, "backup")
        return sorted(os.path.join(d, f) for f in os.listdir(d) if f.startswith("mailbox-"))

    def test_missing_mcp_source_still_backs_up_code(self):
        for p in ("a.py", "web/index.html", "web/js/00-x.js"):
            with open(os.path.join(self.code, p), "w", encoding="utf-8") as f:
                f.write("x\n")
        r = self.run_backup()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("(skip) MCP source not found", r.stdout)
        [a] = self.archives()
        self.assertGreater(os.path.getsize(a), 0)
        with tarfile.open(a) as t:
            names = t.getnames()
        self.assertIn("a.py", names)
        self.assertIn("web/js/00-x.js", names)                 # directories recurse, no «web/js:» junk names

    def test_failed_tar_leaves_no_archive_and_keeps_old_ones(self):
        os.makedirs(os.path.join(self.data, "backup"))
        old = [os.path.join(self.data, "backup", "mailbox-202601%02d-000000.tar.gz" % i) for i in range(1, 11)]
        for p in old:
            with open(p, "wb") as f:
                f.write(b"old")
        shutil.rmtree(os.path.join(self.code, "web"))
        r = self.run_backup()                                   # nothing to archive: tar fails
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(self.archives(), old)                  # no partial file, prune never ran


if __name__ == "__main__":
    unittest.main()
