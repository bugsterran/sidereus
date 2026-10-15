"""Project / security checks on native Windows: .cmd/.bat shims, process-tree kill, temp cleanup, install hints.
No real Windows: os.name / sys.platform / which() are patched on the owning modules."""
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus
from tests.test_archchecks import cli

AC = sidereus("arch_checks")
SC = sidereus("sec_checks")


class Tmp(unittest.TestCase):
    def setUp(self):
        self.repo = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-archwin-"))

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def w(self, rel, text=""):
        fp = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(text)
        return fp


def which(have):
    return lambda n: ("C:/bin/" + n) if n in have else None


class DetectNtTest(Tmp):
    def test_node_bin_cmd_shim(self):
        self.w("package.json", "{}")
        self.w(".eslintrc.json", "{}")
        self.w("tsconfig.json", "{}")
        self.w("node_modules/.bin/eslint")            # sh shim only: missing on Windows
        cmd = self.w("node_modules/.bin/tsc.cmd")
        with mock.patch.object(AC.os, "name", "nt"):
            ps = {p["id"]: p for p in AC.detect(self.repo, which(set()))}
        self.assertEqual(ps["tsc"]["argv"][0], cmd)
        self.assertEqual(ps["eslint"]["status"], "missing")
        self.assertEqual(AC.node_bin("/d", "eslint"), os.path.join("/d", "node_modules", ".bin", "eslint"))

    def test_gradlew_bat_and_mvnw_cmd(self):
        self.w("build.gradle", "plugins { id 'checkstyle' }\n")
        gw = self.w("gradlew", "#!/bin/sh\n")
        os.chmod(gw, 0o755)
        bat = self.w("gradlew.bat")
        with mock.patch.object(AC.os, "name", "nt"):
            cs = [p for p in AC.detect(self.repo, which(set())) if p["id"] == "checkstyle"][0]
        self.assertEqual(cs["argv"][0], bat)
        os.remove(bat)
        with mock.patch.object(AC.os, "name", "nt"):   # sh wrapper alone is not used: falls back to PATH gradle
            cs = [p for p in AC.detect(self.repo, which({"gradle"})) if p["id"] == "checkstyle"][0]
        self.assertEqual(cs["argv"][0], "C:/bin/gradle")
        os.remove(os.path.join(self.repo, "build.gradle"))
        self.w("pom.xml", "<artifactId>maven-pmd-plugin</artifactId>")
        mv = self.w("mvnw.cmd")
        with mock.patch.object(AC.os, "name", "nt"):
            pmd = [p for p in AC.detect(self.repo, which(set())) if p["id"] == "pmd"][0]
        self.assertEqual(pmd["argv"][0], mv)

    def test_mypy_cache_in_runner_tmp(self):
        self.w("mypy.ini", "[mypy]\n")
        with mock.patch.object(AC.os, "name", "nt"):
            mp = [p for p in AC.detect(self.repo, which({"mypy"})) if p["id"] == "mypy"][0]
        self.assertNotIn("--cache-dir", mp["argv"])
        self.assertEqual(mp["env"], {"MYPY_CACHE_DIR": AC.TMP_TOKEN})
        mp = [p for p in AC.detect(self.repo, which({"mypy"})) if p["id"] == "mypy"][0]
        self.assertIn(os.devnull, mp["argv"])
        self.assertNotIn("env", mp)


class HintTest(unittest.TestCase):
    def hint(self, tool, name, plat):
        with mock.patch.object(SC.os, "name", name), mock.patch.object(SC.sys, "platform", plat):
            return SC.install_hint(tool)

    def test_per_os(self):
        self.assertEqual(self.hint("gitleaks", "posix", "darwin"), "install: brew install gitleaks")
        self.assertIn("winget install Gitleaks.Gitleaks", self.hint("gitleaks", "nt", "win32"))
        self.assertIn("WSL", self.hint("semgrep", "nt", "win32"))
        self.assertNotIn("brew", self.hint("osv-scanner", "posix", "linux"))
        for t in SC.HINTS:
            for name, plat in (("posix", "darwin"), ("nt", "win32"), ("posix", "linux")):
                self.assertLessEqual(len(self.hint(t, name, plat)), AC.WHY_MAX)

    def test_detect_uses_os_hint(self):
        with mock.patch.object(SC.os, "name", "nt"):
            gl = [p for p in SC.detect(tempfile.gettempdir(), which(set())) if p["id"] == "gitleaks"][0]
        self.assertIn("winget", gl["why"])


class RunnerNtTest(unittest.TestCase):
    class P:
        pid = 4242

        def __init__(self):
            self.killed = False

        def kill(self):
            self.killed = True

    def test_kill_tree_taskkill(self):
        c, calls, p = cli(), [], self.P()
        with mock.patch.object(c.os, "name", "nt"), \
                mock.patch.object(c.subprocess, "run", lambda argv, **k: calls.append(argv)):
            c._kill_tree(p)
        self.assertEqual(calls, [["taskkill", "/F", "/T", "/PID", "4242"]])
        self.assertTrue(p.killed)

    def test_kill_tree_no_killpg(self):
        c, p = cli(), self.P()
        with mock.patch.object(c.os, "killpg", mock.Mock(side_effect=AttributeError)):
            c._kill_tree(p)                           # ⚠AttributeError must not escape
        self.assertTrue(p.killed)
        with mock.patch.object(c.os, "name", "nt"), \
                mock.patch.object(c.subprocess, "run", mock.Mock(side_effect=subprocess.TimeoutExpired("t", 30))):
            c._kill_tree(self.P())

    def test_rmtree_read_only(self):
        c = cli()
        d = tempfile.mkdtemp(prefix="sidereus-archwin-rm-")
        fp = os.path.join(d, "ro")
        with open(fp, "w") as f:
            f.write("x")
        os.chmod(fp, stat.S_IREAD)
        real = os.unlink
        state = {"n": 0}

        def flaky(path, *a, **k):                     # first delete refused, as Windows does for read-only files
            state["n"] += 1
            if state["n"] == 1:
                raise PermissionError(path)
            return real(path, *a, **k)
        with mock.patch.object(c.shutil.os, "unlink", flaky):
            c._rmtree(d)
        self.assertFalse(os.path.exists(d))
        c._rmtree(d)                                  # missing dir: never raises


if __name__ == "__main__":
    unittest.main()
