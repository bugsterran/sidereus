"""hooks/ev_hook.py: Bash test/build runs -> evidence rows (tmp DATA_DIR and git fixtures, clock and git patched)."""
import contextlib
import importlib.util
import inspect
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ev = _load("ev_hook_t", "hooks/ev_hook.py")
rec = _load("evidence_rec_t", "scripts/evidence_rec.py")
SHA = "0123456789abcdef0123456789abcdef01234567"


class _FakeMsvcrt(object):
    LK_UNLCK, LK_NBLCK = 0, 2

    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def locking(self, fd, mode, n):
        self.calls.append((mode, n, os.lseek(fd, 0, os.SEEK_CUR)))
        if self.fail and mode == self.LK_NBLCK:
            raise OSError(36, "lock violation")


class WinLock(unittest.TestCase):
    """Windows (simulated: fcntl None + fake msvcrt): rows are appended under a `.lock` sidecar byte-0 lock."""

    def setUp(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        self.p = os.path.join(d, "sub", "evidence.jsonl")

    def _with(self, m, ms):
        st = contextlib.ExitStack()
        st.enter_context(mock.patch.object(m, "fcntl", None))
        st.enter_context(mock.patch.object(m, "msvcrt", ms))
        st.enter_context(mock.patch.object(m.time, "sleep", lambda s: None))
        return st

    def test_row_written_and_lock_released(self):
        for m in (ev, rec):
            ms = _FakeMsvcrt()
            with self._with(m, ms):
                self.assertTrue(m.append(self.p, '{"a":1}\n'))
            self.assertEqual(ms.calls, [(ms.LK_NBLCK, 1, 0), (ms.LK_UNLCK, 1, 0)], m.__name__)
        with open(self.p, "rb") as f:
            self.assertEqual(f.read(), b'{"a":1}\n{"a":1}\n')
        self.assertTrue(os.path.exists(self.p + ".lock"))

    def test_lock_miss_writes_nothing(self):
        for m in (ev, rec):
            ms = _FakeMsvcrt(fail=True)
            with self._with(m, ms):
                self.assertFalse(m.append(self.p, "{}\n"))
            self.assertEqual(len(ms.calls), m.WIN_LOCK_TRIES)
            self.assertNotIn(ms.LK_UNLCK, [c[0] for c in ms.calls])
        self.assertFalse(os.path.exists(self.p))

    def test_rotation_keeps_lf(self):
        ms = _FakeMsvcrt()
        with self._with(rec, ms):
            for i in range(rec.EV_CAP + 1):
                rec.append(self.p, '{"i":%d}\n' % i)
        with open(self.p, "rb") as f:
            lines = f.read().splitlines(True)
        self.assertEqual(len(lines), rec.EV_KEEP)
        self.assertEqual((lines[-1], b"\r" in b"".join(lines)), (b'{"i":%d}\n' % rec.EV_CAP, False))

    def test_no_lock_at_all_writes_nothing(self):
        for m in (ev, rec):
            with mock.patch.object(m, "fcntl", None), mock.patch.object(m, "msvcrt", None):
                self.assertFalse(m.append(self.p, "{}\n"))
        self.assertFalse(os.path.exists(self.p))


class EvHook(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.data = os.path.join(self.d, "data")
        self.repo = os.path.join(self.d, "repo")
        os.makedirs(os.path.join(self.repo, ".git", "refs", "heads"))
        os.makedirs(os.path.join(self.repo, "sub"))
        with open(os.path.join(self.repo, ".git", "HEAD"), "w", encoding="utf-8") as f:
            f.write("ref: refs/heads/main\n")
        with open(os.path.join(self.repo, ".git", "refs", "heads", "main"), "w", encoding="utf-8") as f:
            f.write(SHA + "\n")
        self.clock = [1000.0]
        self.git = mock.Mock(return_value="")
        for k, v in (("DATA_DIR", self.data), ("EV_FILE", os.path.join(self.data, "evidence.jsonl")),
                     ("START_DIR", os.path.join(self.data, "evstart")), ("NOW", lambda: self.clock[0]),
                     ("git_status", self.git)):
            p = mock.patch.object(ev, k, v)
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        shutil.rmtree(self.d)

    def rows(self):
        try:
            with open(ev.EV_FILE, encoding="utf-8") as f:
                return [json.loads(x) for x in f]
        except OSError:
            return []

    def evt(self, name, cmd, tuid="toolu_01", cwd=None, **extra):
        e = {"hook_event_name": name, "tool_name": "Bash", "tool_use_id": tuid, "cwd": cwd or self.repo,
             "tool_input": {"command": cmd, "description": "run"}}
        e.update(extra)
        return ev.handle(e)

    def test_pattern_table(self):
        hits = {"./gradlew test": "test", "gradle build --info": "build", "./gradlew check": "check",
                "mvn test": "test", "CI=1 npm test": "test", 'FOO="a b" ./gradlew test': "test", "mvn verify -q": "check", "npm test": "test", "npm run build": "build",
                "pnpm lint": "lint", "yarn run test": "test", "pytest -q tests": "test",
                "python -m pytest": "test", "python3 -m pytest -x": "test", "go test ./...": "test",
                "cargo test": "test", "cargo build --release": "build", "cd sub && npm test": "test",
                "npm test 2>&1": "test"}
        self.assertIsNone(ev.classify("npm test\nls", self.repo))   # multi-line: rc would be the last line's
        for cmd, kind in hits.items():
            got = ev.classify(cmd, self.repo)
            self.assertEqual(got and got[:2], ("hook-" + kind, kind), cmd)
        skips = ("npm test | tail", "npm test; echo", "npm test || true", "npm test &", "npm test && npm run build",
                 "npm test --watch", "npm test --watchAll", "gradle test --continuous", "gradle test -t",
                 "scripts/check.sh --fast", "cd x && bash scripts/check.sh", "echo npm test", "ls",
                 "git status", "npm install", "cargo run", "go build", "mvn package")
        for cmd in skips:
            self.assertIsNone(ev.classify(cmd, self.repo), cmd)

    def test_ci_classify(self):
        for cmd in ("gh run watch 123 --exit-status", "gh run view 123 --exit-status", "gh run view --exit-status 123",
                    "gh run watch --exit-status 9 -i 5"):
            self.assertEqual(ev.classify(cmd, self.repo), ("ci", None, os.path.realpath(self.repo)), cmd)
        for cmd in ("gh run watch 123", "gh run view 123", "gh run watch 1 --exit-status=1", "gh run watch 1 --exit-status -R o/r",
                    "gh run watch 1 --exit-status --repo o/r", "gh run watch 1 --exit-status --repo=o/r",
                    "gh run watch 1 --exit-status | tail", "gh run watch 1 --exit-status && git push",
                    "gh run watch 1 --exit-status &", "gh run list --exit-status", "echo gh run watch 1 --exit-status",
                    "gh run watch --exit-status", "gh run watch --exit-status -i 5", "gh run watch --exit-status --interval=5",
                    "gh run watch 1 --exit-status\nnpm test"):
            self.assertIsNone(ev.classify(cmd, self.repo), cmd)
        other = os.path.join(self.d, "other")
        os.makedirs(os.path.join(other, ".git", "x"))
        got = ev.classify("cd %s && gh run watch 7 --exit-status" % os.path.join(other, ".git", "x"), self.repo)
        self.assertEqual(got, ("ci", None, os.path.realpath(other)))

    def test_ci_row(self):
        self.assertIsNone(self.evt("PreToolUse", "gh run watch 1 --exit-status"))
        self.assertFalse(os.path.exists(ev.START_DIR))   # no duration for CI
        self.clock[0] = 1050.7
        row = self.evt("PostToolUse", "gh run watch 1 --exit-status", tool_response={"stdout": "SECRET_LOG"})
        self.assertEqual(row, {"v": 1, "kind": "ci", "ts": 1050, "repo": os.path.realpath(self.repo), "head": SHA[:7], "rc": 0})
        row = self.evt("PostToolUseFailure", "gh run view 1 --exit-status", error="Exit code 1\nX build failed")
        self.assertEqual(sorted(row), ["head", "kind", "rc", "repo", "ts", "v"])
        self.assertEqual(row["rc"], 1)
        self.assertEqual(self.rows(), [{"v": 1, "kind": "ci", "ts": 1050, "repo": os.path.realpath(self.repo), "head": SHA[:7], "rc": 0}, row])
        self.git.assert_not_called()
        self.assertIsNone(self.evt("PostToolUse", "gh run watch 1"))
        self.assertIsNone(self.evt("PostToolUseFailure", "gh run watch 1 --exit-status", error="Command timed out after 2m"))
        self.assertEqual(len(self.rows()), 2)   # unknown result: no false red

    def test_plugin_copy_identical(self):
        with open(os.path.join(ROOT, "hooks", "ev_hook.py"), "rb") as a, open(os.path.join(ROOT, "plugin", "hooks", "ev_hook.py"), "rb") as b:
            self.assertEqual(a.read(), b.read())

    def test_cd_target_sets_repo(self):
        other = os.path.join(self.d, "other")
        os.makedirs(os.path.join(other, ".git"))
        self.assertEqual(ev.classify("cd %s && cargo test" % other, self.repo)[2], os.path.realpath(other))
        self.assertEqual(ev.classify("npm test", os.path.join(self.repo, "sub"))[2], os.path.realpath(self.repo))

    def test_post_success_row(self):
        self.evt("PreToolUse", "npm test")
        self.clock[0] = 1012.5
        row = self.evt("PostToolUse", "npm test", tool_response={"stdout": "ok", "interrupted": False})
        self.assertEqual(self.rows(), [row])
        self.assertEqual(row, {"v": 1, "kind": "check", "ts": 1012, "mode": "hook-test",
                               "repo": os.path.realpath(self.repo), "head": SHA[:7], "dirty": False, "rc": 0,
                               "steps": [{"name": "test", "rc": 0, "n": 0, "failed": 0, "secs": 12.5}]})
        self.assertEqual(os.listdir(ev.START_DIR), [])   # start file consumed

    def test_failure_exit_code(self):
        self.git.return_value = " M a.py\n"
        row = self.evt("PostToolUseFailure", "./gradlew test", error="Exit code 2\nFAILED: 3 tests")
        self.assertEqual((row["rc"], row["steps"][0]["rc"], row["steps"][0]["secs"], row["dirty"]), (2, 2, 0, True))
        row = self.evt("PostToolUseFailure", "./gradlew test", error="Command timed out")
        self.assertEqual(row["rc"], 1)

    def test_interrupted_and_background_write_nothing(self):
        self.evt("PostToolUseFailure", "npm test", error="Exit code 130", is_interrupt=True)
        self.evt("PostToolUse", "npm test", tool_response={"interrupted": True})
        e = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_use_id": "t2", "cwd": self.repo,
             "tool_input": {"command": "npm test", "run_in_background": True}}
        ev.handle(e)
        ev.handle(dict(e, hook_event_name="PostToolUse"))
        self.assertEqual(self.rows(), [])
        self.assertFalse(os.path.exists(ev.START_DIR))

    def test_unmatched_touches_nothing(self):
        self.evt("PreToolUse", "ls -la")
        self.evt("PostToolUse", "ls -la")
        self.git.assert_not_called()
        self.assertFalse(os.path.exists(self.data))

    def test_pipeline_gate(self):
        pd = os.path.join(self.repo, ".claude", "pipelines")
        os.makedirs(pd)
        with open(os.path.join(pd, "p.json"), "w", encoding="utf-8") as f:
            json.dump({"stages": [{"title": "a", "gate": "make  test"}, {"title": "b", "gate": "./verify.sh"},
                                  {"title": "c", "gate": "scripts/check.sh --fast"}]}, f)
        self.assertEqual(self.evt("PostToolUse", "make test")["mode"], "gate-test")
        row = self.evt("PostToolUse", "./verify.sh")
        self.assertEqual((row["mode"], row["steps"][0]["name"]), ("gate-check", "gate"))
        self.assertIsNone(self.evt("PostToolUse", "scripts/check.sh --fast"))
        self.assertIsNone(self.evt("PostToolUse", "./other.sh"))

    def test_no_secret_in_row(self):
        self.evt("PostToolUseFailure", "pytest -k SECRET_TOKEN_abc", error="Exit code 1\nAPI_KEY=sk-live-xyz",
                 tool_response={"stdout": "password=hunter2"})
        with open(ev.EV_FILE, encoding="utf-8") as f:
            raw = f.read()
        for s in ("SECRET_TOKEN", "sk-live", "hunter2", "pytest", "API_KEY"):
            self.assertNotIn(s, raw)

    def test_malformed_stdin(self):
        for raw in ("", "{", "[1,2]", '{"tool_name":"Bash","hook_event_name":"PostToolUse","tool_input":7}'):
            out = io.StringIO()
            with mock.patch("sys.stdin", io.StringIO(raw)), contextlib.redirect_stdout(out):
                self.assertEqual(ev.main(), 0)
            self.assertEqual(out.getvalue(), "")
        self.assertEqual(self.rows(), [])

    def test_sweep_old_starts(self):
        os.makedirs(ev.START_DIR)
        old = os.path.join(ev.START_DIR, "old")
        open(old, "w", encoding="utf-8").close()
        os.utime(old, (0, 0))
        self.clock[0] = 10000.0
        self.evt("PreToolUse", "npm test", tuid="new")
        self.assertEqual(os.listdir(ev.START_DIR), ["new"])

    def test_git_safe_opts_match_gitinfo(self):
        with open(os.path.join(ROOT, "sidereus", "gitinfo.py"), encoding="utf-8") as f:
            src = f.read().replace('"', "'")
        self.assertIn("GIT_SAFE_OPTS = %r" % ev.GIT_SAFE_OPTS, src)

    def test_append_matches_evidence_rec(self):
        # The plugin ships hooks/ only, so the flock/rotate append is duplicated: keep it identical.
        self.assertEqual(inspect.getsource(ev.append), inspect.getsource(rec.append))
        self.assertEqual(inspect.getsource(ev._win_append), inspect.getsource(rec._win_append))
        self.assertEqual((ev.WIN_LOCK_TRIES, ev.WIN_LOCK_STEP), (rec.WIN_LOCK_TRIES, rec.WIN_LOCK_STEP))
        self.assertEqual((ev.EV_CAP, ev.EV_KEEP), (rec.EV_CAP, rec.EV_KEEP))


if __name__ == "__main__":
    unittest.main()
