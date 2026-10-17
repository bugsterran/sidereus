"""Windows paths of scripts/pl_eval.py and the pl_flow/pl_guard hooks, exercised by patching os.name (no real Windows)."""
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from tests._load import ROOT, sidereus   # noqa: F401  (sets MAILBOX_DIR to a tmp dir before any import)


def _mod(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


E = _mod("pl_eval_win_t", "scripts/pl_eval.py")
H = _mod("pl_flow_win_t", "hooks/pl_flow.py")


class Proc:
    pid = 4321

    def __init__(self):
        self.killed = 0

    def kill(self):
        self.killed += 1


class Rc:
    def __init__(self, rc):
        self.returncode = rc


class EvalWin(unittest.TestCase):
    def test_split_gate_keeps_backslashes_on_nt(self):
        with mock.patch.object(E.os, "name", "nt"):
            argv = E._split_gate(r'C:\Py\python.exe "C:\a b\arch_checks.py" --verify')
        self.assertEqual(argv, [r"C:\Py\python.exe", r"C:\a b\arch_checks.py", "--verify"])

    def test_split_gate_posix_unchanged(self):
        self.assertEqual(E._split_gate("scripts/check.sh 'a b' --fast"), ["scripts/check.sh", "a b", "--fast"])
        self.assertEqual(E._split_gate('x "unclosed'), [])

    def test_kill_tree_uses_taskkill_on_nt(self):
        p, calls = Proc(), []
        with mock.patch.object(E.os, "name", "nt"), \
                mock.patch.object(E.subprocess, "run", lambda argv, **k: calls.append(argv) or Rc(0)):
            E._kill_tree(p)
        self.assertEqual(calls, [["taskkill", "/F", "/T", "/PID", "4321"]])
        self.assertEqual(p.killed, 1)

    def test_kill_tree_without_killpg_still_kills_child(self):
        p = Proc()
        with mock.patch.object(E.os, "killpg", side_effect=AttributeError, create=True):
            E._kill_tree(p)
        self.assertEqual(p.killed, 1)

    def _winapi(self, **kw):
        return mock.patch.dict(sys.modules, {"_winapi": mock.Mock(**kw)})

    def test_link_dir_falls_back_to_junction_on_nt_without_shell(self):
        src, dst = r"C:\r\a&calc|x^%y\node_modules", r"C:\t\a&calc|x^%y\node_modules"
        no_shell = AssertionError("no subprocess")
        with mock.patch.object(E.os, "name", "nt"), mock.patch.object(E.os, "symlink", side_effect=OSError), \
                mock.patch.object(E.subprocess, "run", side_effect=no_shell), \
                mock.patch.object(E.subprocess, "Popen", side_effect=no_shell), self._winapi():
            self.assertTrue(E._link_dir(src, dst))
            sys.modules["_winapi"].CreateJunction.assert_called_once_with(src, dst)

    def test_link_dir_gives_up_without_raising(self):
        with mock.patch.object(E.os, "name", "nt"), mock.patch.object(E.os, "symlink", side_effect=OSError), \
                self._winapi(**{"CreateJunction.side_effect": OSError}):
            self.assertFalse(E._link_dir("a", "b"))
        with mock.patch.object(E.os, "symlink", side_effect=OSError), \
                self._winapi(**{"CreateJunction.side_effect": AssertionError("no junction off nt")}):
            self.assertFalse(E._link_dir("a", "b"))

    def test_unlinked_modules_turn_verdict_into_skip(self):
        with mock.patch.object(E, "_link_modules", return_value=["node_modules"]), \
                mock.patch.object(E, "_red_gate", return_value=("pass", "gate rc 1 on a broken repo")):
            v, why = E._red_in("p", ["x"], "fast", "r", "c", "s", "t", "h", 0)
        self.assertEqual(v, "skip")
        self.assertIn("node_modules", why)

    def test_rmtree_chmods_and_retries_never_raises(self):
        d = tempfile.mkdtemp()
        fp = os.path.join(d, "f")
        open(fp, "w", encoding="utf-8").close()

        def fake(path, onerror):
            onerror(os.remove, fp, None)
            raise OSError("still locked")
        with mock.patch.object(E.shutil, "rmtree", fake):
            E._rmtree(d)
        self.assertFalse(os.path.exists(fp))
        shutil.rmtree(d, ignore_errors=True)

    def test_gate_cwd_compares_case_blind(self):
        with mock.patch.object(E.os.path, "normcase", lambda s: s.lower()):
            got = E._gate_cwd("/Repo/.claude/pipelines/p.json", "/repo", "/clone")
        self.assertEqual(got, "/clone")


class HookWin(unittest.TestCase):
    def test_powershell_is_a_shell_tool(self):
        self.assertIn("PowerShell", H.SHELL)

    def test_commit_re_sees_windows_dash_c(self):
        m = H._COMMIT_RE.search(r'git -C "C:\work\repo" commit -m x')
        self.assertEqual(m.group(1), r'"C:\work\repo"')
        self.assertIsNotNone(H._COMMIT_RE.search(r"Set-Location C:\r; git commit -m x"))


if __name__ == "__main__":
    unittest.main()
