"""Viewer git spawns neutralise repo-local code-running config, and diff bodies are read with a memory cap.
Fakes replace subprocess.run/Popen; FilterDriver alone runs real git in a temp repo."""
import io
import subprocess
import threading
import unittest

from tests._load import sidereus

gi = sidereus("gitinfo")


class SafeArgv(unittest.TestCase):
    def setUp(self):
        self.seen = []
        self._run = gi.subprocess.run

        def fake(cmd, **kw):
            self.seen.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        gi.subprocess.run = fake

    def tearDown(self):
        gi.subprocess.run = self._run

    def test_config_overrides_before_subcommand(self):
        gi._git_run("/r", ["status", "--porcelain"], 1)
        cmd = self.seen[0]
        n = len(gi.GIT_SAFE_OPTS)
        self.assertEqual(cmd[:5], ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null"])
        self.assertEqual(cmd[1:n + 1], gi.GIT_SAFE_OPTS)
        self.assertEqual(cmd[n + 1:], ["-C", "/r", "status", "--porcelain"])

    def test_diff_show_log_get_no_ext_diff_no_textconv(self):
        for sub in ("diff", "show", "log"):
            gi._git_run("/r", [sub, "HEAD"], 1)
            cmd = self.seen[-1]
            i = cmd.index(sub)
            self.assertEqual(cmd[i:], [sub, "--no-ext-diff", "--no-textconv", "HEAD"])

    def test_other_subcommands_untouched(self):
        gi._git_run("/r", ["ls-files", "--", ":(literal)log"], 1)
        self.assertNotIn("--no-ext-diff", self.seen[0])


class FakeProc:
    def __init__(self, cmd, data):
        self.args = cmd
        self.stdout = io.StringIO(data)
        self.reads = 0
        self.killed = False
        real = self.stdout.read

        def read(n=-1):
            self.reads += 1
            return real(n)
        self.stdout.read = read

    def kill(self):
        self.killed = True

    def wait(self):
        return 0


class Capped(unittest.TestCase):
    def setUp(self):
        self._popen, self._cnt, self._sem = gi.subprocess.Popen, gi.GIT_COUNT_MAX, gi._GIT_SEM
        gi._GIT_SEM = threading.BoundedSemaphore(gi.GIT_MAX_PROCS)
        self.procs = []

    def tearDown(self):
        gi.subprocess.Popen, gi.GIT_COUNT_MAX, gi._GIT_SEM = self._popen, self._cnt, self._sem

    def _fake(self, data):
        def popen(cmd, **kw):
            p = FakeProc(cmd, data)
            self.procs.append(p)
            return p
        gi.subprocess.Popen = popen

    def test_small_output_whole(self):
        self._fake("abc\n")
        self.assertEqual(gi._git_run_capped("/r", ["diff"], 1, 100), ("abc\n", 4))
        self.assertIn("--no-textconv", self.procs[0].args)

    def test_cut_keeps_prefix_and_total(self):
        self._fake("x" * 300_000)
        text, total = gi._git_run_capped("/r", ["diff"], 1, 1000)
        self.assertEqual((len(text), total), (1001, 300_000))

    def test_stops_early_past_count_max(self):
        gi.GIT_COUNT_MAX = 200_000
        self._fake("x" * 10_000_000)
        text, total = gi._git_run_capped("/r", ["diff"], 1, 1000)
        p = self.procs[0]
        self.assertTrue(p.killed)
        self.assertLess(p.reads, 10)                 # 64K chunks: stopped long before 10M
        self.assertLessEqual(len(text), 1001)
        self.assertLess(total, 10_000_000)


class StructureSpawns(unittest.TestCase):
    """structure / structure_snap spawn git directly; they must use git_argv too."""
    def setUp(self):
        import tempfile, os
        self.td = tempfile.TemporaryDirectory()
        os.mkdir(os.path.join(self.td.name, ".git"))
        self.seen = []
        self._run = gi.subprocess.run

        def fake(cmd, **kw):
            self.seen.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        gi.subprocess.run = fake

    def tearDown(self):
        gi.subprocess.run = self._run
        self.td.cleanup()

    def test_log_and_show(self):
        sidereus("structure_snap")._struct_git(self.td.name)
        sidereus("structure")._struct_src_at(self.td.name, "a.py", "git", "abc1234", 0)
        log, show = self.seen[0], self.seen[1]
        n = len(gi.GIT_SAFE_OPTS) + 1
        self.assertEqual(log[1:n], gi.GIT_SAFE_OPTS)
        self.assertEqual(show[1:n], gi.GIT_SAFE_OPTS)
        self.assertEqual(show[show.index("show"):], ["show", "--no-ext-diff", "--no-textconv", "abc1234:a.py"])


class FileDiffCapped(unittest.TestCase):
    def setUp(self):
        self.gv = gv = sidereus("git_view")
        self._saved = (gv._git_run, gv._git_run_capped, gv.sessions_rows)
        gv.sessions_rows = lambda **k: [{"cwd": "/r", "repos": []}]
        gv._git_run = lambda cwd, args, timeout, wait=None: subprocess.CompletedProcess(args, 0, "", "")
        self.calls = []

        def capped(cwd, args, timeout, cap, wait=None):
            self.calls.append((args, cap))
            return "x" * (cap + 1), 900_000
        gv._git_run_capped = capped

    def tearDown(self):
        self.gv._git_run, self.gv._git_run_capped, self.gv.sessions_rows = self._saved

    def test_full_expand_uses_cap_and_reports_total(self):
        d = self.gv.git_file_diff("/r", "a.py", scope="work")
        self.assertEqual(self.calls[0][1], self.gv.FULL_MAX)
        self.assertEqual((len(d["diff"]), d["cutBytes"]), (self.gv.FULL_MAX, 900_000))


class AttrSource(unittest.TestCase):
    def test_version_gate(self):
        self.assertEqual(gi._attr_opts("git version 2.39.5 (Apple Git-154)"), [])
        self.assertEqual(gi._attr_opts("git version 2.40.0"), ["--attr-source=" + gi.EMPTY_TREE])
        self.assertEqual(gi._attr_opts("git version 3.1"), ["--attr-source=" + gi.EMPTY_TREE])
        self.assertEqual(gi._attr_opts(""), [])


class FilterDriver(unittest.TestCase):
    """Real git in a temp repo only: a `.gitattributes` filter=evil with a local filter.evil.clean must not run.
    Trade-off: with --attr-source=<empty tree>, LFS/eol attributes are ignored for display too."""
    def setUp(self):
        import os, tempfile
        if not any(a.startswith("--attr-source=") for a in gi.GIT_SAFE_OPTS):
            self.skipTest("git < 2.40: --attr-source unsupported")
        self.td = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.td.name, "r")
        self.marker = os.path.join(self.td.name, "MARKER")
        os.mkdir(self.repo)
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        self.env = env

        def git(*a):
            subprocess.run(["git", "-C", self.repo] + list(a), check=True, env=env, capture_output=True)
        git("init", "-q")
        with open(os.path.join(self.repo, "f.txt"), "w", encoding="utf-8") as f:
            f.write("a\n")
        git("add", "f.txt")
        git("commit", "-qm", "init")
        git("config", "filter.evil.clean", "touch '%s'; cat" % self.marker)
        with open(os.path.join(self.repo, ".gitattributes"), "w", encoding="utf-8") as f:
            f.write("* filter=evil\n")
        with open(os.path.join(self.repo, "f.txt"), "a", encoding="utf-8") as f:
            f.write("b\n")
        self._env = gi.git_env
        gi.git_env = lambda: dict(env, GIT_OPTIONAL_LOCKS="0")

    def tearDown(self):
        gi.git_env = self._env
        self.td.cleanup()

    def test_viewer_status_diff_do_not_run_filter(self):
        import os
        st = gi._git_run(self.repo, ["status", "--porcelain"], 10)
        self.assertIn("f.txt", st.stdout)
        text, _ = gi._git_run_capped(self.repo, ["diff"], 10, 100000)
        self.assertIn("+b", text)
        self.assertFalse(os.path.exists(self.marker))

    def test_control_plain_git_runs_filter(self):
        import os
        subprocess.run(["git", "-C", self.repo, "diff"], env=self.env, capture_output=True)
        self.assertTrue(os.path.exists(self.marker))


if __name__ == "__main__":
    unittest.main()
