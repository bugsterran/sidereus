"""Table tests for sidereus/steps.py write-target extraction (_wrote_files / _edit_target / _work_scan wiring).

No live data: repos are temp dirs with an empty `.git` dir; transcripts are synthetic JSON lines.
"""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus
from tests._node import node_e

st = sidereus("steps")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = os.path.join(self.tmp, "repo")
        self.other = os.path.join(self.tmp, "other")
        self.plain = os.path.join(self.tmp, "plain")          # exists, but no git anywhere up to /
        os.makedirs(os.path.join(self.repo, ".git"))
        os.makedirs(os.path.join(self.repo, "frontend", "src"))
        os.makedirs(os.path.join(self.other, ".git"))
        os.makedirs(self.plain)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class WroteFiles(Base):
    def test_table(self):
        R, O, P = self.repo, self.other, self.plain
        cases = [
            # (label, command, expected)
            ("no write signal", f"cd {R} && cat src/a.py", []),
            ("in-repo relative", f"cd {R} && sed -i s/a/b/ src/a.py", [{"cwd": R, "path": "src/a.py"}]),
            ("./ prefix", f"cd {R} && sed -i s/a/b/ ./src/a.py", [{"cwd": R, "path": "src/a.py"}]),
            ("url skipped", f"cd {R} && sed -i s/a/b/ src/a.py https://docs.example.com/x/create_index.html",
             [{"cwd": R, "path": "src/a.py"}]),
            ("cd into non-repo", f"cd {P} && sed -i s/a/b/ src/a.py", []),
            ("subdir prefix", f"cd {R}/frontend && sed -i s/a/b/ src/a.tsx",
             [{"cwd": R, "path": "frontend/src/a.tsx"}]),
            ("abs inside repo", f"cd {R} && sed -i s/a/b/ {R}/src/a.py", [{"cwd": R, "path": "src/a.py"}]),
            ("abs outside repo", f"cd {R} && sed -i s/a/b/ {O}/b.py", []),
            ("abs no cd, own repo", f"sed -i s/a/b/ {O}/lib/b.py", [{"cwd": O, "path": "lib/b.py"}]),
            ("abs no cd, no repo", f"sed -i s/a/b/ {P}/b.py", []),
            ("dotdot escapes repo", f"cd {R} && sed -i s/a/b/ ../other/b.py", []),
            ("dotdot stays in repo", f"cd {R}/frontend && sed -i s/a/b/ ../lib/c.py",
             [{"cwd": R, "path": "lib/c.py"}]),
            ("dotdot no cd", "sed -i s/a/b/ ../lib/c.py", []),
            ("relative no cd", "sed -i s/a/b/ src/a.py", [{"cwd": "", "path": "src/a.py"}]),
            ("build dirs", f"cd {R} && sed -i s/a/b/ build/a.js node_modules/x/y.js dist/z.js", []),
            ("bare filename", f"cd {R} && sed -i s/a/b/ a.py", []),
        ]
        for label, cmd, want in cases:
            with self.subTest(label):
                self.assertEqual(st._wrote_files(cmd), want)


class EditTarget(Base):
    def test_table(self):
        R = self.repo
        cases = [
            ("empty", "", None),
            ("relative", "src/a.py", None),
            ("inside", f"{R}/src/a.py", {"cwd": R, "path": "src/a.py"}),
            ("subdir", f"{R}/frontend/src/a.tsx", {"cwd": R, "path": "frontend/src/a.tsx"}),
            ("dotdot-named dir is in repo", f"{R}/..cfg/a.py", {"cwd": R, "path": "..cfg/a.py"}),
            ("no repo", f"{self.plain}/a.py", None),
            ("build dir", f"{R}/node_modules/x/a.js", None),
        ]
        for label, path, want in cases:
            with self.subTest(label):
                self.assertEqual(st._edit_target(path), want)

    def test_outside(self):
        self.assertTrue(st._outside(".."))
        self.assertTrue(st._outside("../x.py"))
        self.assertFalse(st._outside("..cfg/x.py"))
        self.assertFalse(st._outside("src/x.py"))


class WorkScanWiring(Base):
    """Callers read `wrote` from _work_scan: in-repo paths keep their old shape; Bash without cd gets the session cwd."""

    def line(self, name, inp):
        return json.dumps({"type": "assistant", "timestamp": "2026-09-25T00:00:00.000Z",
                           "message": {"content": [{"type": "tool_use", "name": name, "id": "t1", "input": inp}]}})

    def test_wrote(self):
        R = self.repo
        src = [
            self.line("Bash", {"command": "sed -i s/a/b/ src/a.py"}),
            self.line("Bash", {"command": f"cd {R} && sed -i s/a/b/ {self.other}/b.py"}),
            self.line("Edit", {"file_path": f"{R}/src/c.py", "old_string": "x", "new_string": "y"}),
        ]
        res, err = st._work_scan(src, cwd=R)
        self.assertIsNone(err)
        steps = res[0]
        self.assertEqual(steps[0]["wrote"], [{"cwd": R, "path": "src/a.py"}])
        self.assertNotIn("wrote", steps[1])
        self.assertEqual(steps[2]["wrote"], [{"cwd": R, "path": "src/c.py"}])


class EditCutCount(unittest.TestCase):
    """Steps whose edit bodies were cut (editCut) still count as «파일 고친 스텝» in the popup header (35-worklog.js)."""

    def test_cut_steps_counted(self):
        import re
        import shutil as sh
        import subprocess
        from tests._load import js_all
        steps = [{"tool": "Edit", "edit": {"old": "x" * 10, "new": "y" * 10}} for _ in range(4)]
        self.assertEqual(st._cap_edit_bodies(steps, budget=25), 3)
        self.assertEqual([bool(s.get("editCut")) for s in steps], [True, True, True, False])
        if not sh.which("node"):
            self.skipTest("node not installed")
        m = re.search(r"const nWrote = \(d\.steps\|\|\[\]\)\.filter\((.+?)\)\.length;", js_all())
        r = subprocess.run(node_e("process.stdout.write(String(" + json.dumps(steps)
                            + ".filter(" + m.group(1) + ").length))"), capture_output=True, text=True, timeout=20)
        self.assertEqual(r.stdout, "4", r.stderr)


if __name__ == "__main__":
    unittest.main()
