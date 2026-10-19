"""sidereus_cli.py doctor: one OK/FAIL line per check, fix on FAIL, exit code, Windows-only lines, Korean output."""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("sidereus_cli_doctor_t", os.path.join(ROOT, "sidereus_cli.py"))
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)

PY = "/x/python3"
EN = {"LANG": "en_US.UTF-8", "LC_ALL": "", "LC_MESSAGES": ""}
KO = {"LANG": "ko_KR.UTF-8", "LC_ALL": "", "LC_MESSAGES": ""}


class Doctor(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.pyexe = os.path.join(self.home, "python.exe")
        open(self.pyexe, "w", encoding="utf-8").close()

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def run_doctor(self, tools=("git", "claude"), code=200, plugin=False, win=False, env=None, lang=EN, py3=None):
        def which(n):
            if n == "python3":
                return py3
            return "/bin/" + n if n in tools else None
        out = io.StringIO()
        with mock.patch.object(cli, "claude_home", lambda: self.home), \
                mock.patch.object(cli, "_which", which), \
                mock.patch.object(cli, "answering", lambda p: code), \
                mock.patch.object(cli, "plugin_installed", lambda h: plugin), \
                mock.patch.object(cli, "configured_port", lambda: 8799), \
                mock.patch.object(cli, "setup_python", lambda: PY), \
                mock.patch.object(cli, "IS_WIN", win), \
                mock.patch.dict(os.environ, dict(lang, **(env or {})), clear=True), \
                contextlib.redirect_stdout(out):
            rc = cli.main(["doctor"])
        return rc, out.getvalue().splitlines()

    def test_all_ok(self):
        rc, lines = self.run_doctor(plugin=True)
        self.assertEqual(rc, 0)
        self.assertEqual(len(lines), 5)
        self.assertTrue(all(ln.startswith("OK ") for ln in lines), lines)
        self.assertNotIn("fix:", "\n".join(lines))

    def test_failures_carry_fix_and_exit_1(self):
        rc, lines = self.run_doctor(tools=("git",), code=0)
        self.assertEqual(rc, 1)
        self.assertEqual(len(lines), 5)
        bad = [ln for ln in lines if ln.startswith("FAIL")]
        self.assertEqual(len(bad), 3, lines)    # claude, hooks, viewer
        self.assertTrue(all(" — fix: " in ln for ln in bad))
        self.assertIn("python3 -m sidereus start", lines[4])
        self.assertIn("setup-claude --write", lines[3])

    def test_manual_hooks_count(self):
        hooks = cli.setup_hooks(PY)["hooks"]
        with open(os.path.join(self.home, "settings.json"), "w", encoding="utf-8") as f:
            json.dump({"hooks": hooks}, f)
        rc, lines = self.run_doctor()
        self.assertEqual(rc, 0)
        self.assertTrue(lines[3].startswith("OK"), lines[3])

    def test_hooks_elsewhere_count_by_basename(self):
        hooks = cli.setup_hooks(PY)["hooks"]
        moved = {ev: [dict(g, hooks=[dict(h, command="python3 ~/.claude/hooks/" + h["command"].rsplit("/", 1)[-1])
                                     for h in g["hooks"]]) for g in gs] for ev, gs in hooks.items()}
        self.assertIn("python3 ~/.claude/hooks/pl_mark.py", [h["command"] for gs in moved.values()
                                                              for g in gs for h in g["hooks"]])
        with open(os.path.join(self.home, "settings.json"), "w", encoding="utf-8") as f:
            json.dump({"hooks": moved}, f)
        self.assertTrue(self.run_doctor()[1][3].startswith("OK"))
        for gs in moved.values():     # drop one script everywhere -> FAIL naming it
            for g in gs:
                g["hooks"] = [h for h in g["hooks"] if not h["command"].endswith("/pl_mark.py")]
        with open(os.path.join(self.home, "settings.json"), "w", encoding="utf-8") as f:
            json.dump({"hooks": moved}, f)
        line = self.run_doctor()[1][3]
        self.assertTrue(line.startswith("FAIL") and "(pl_mark.py)" in line, line)

    def test_foreign_server_fails_busy_passes(self):
        self.assertTrue(self.run_doctor(plugin=True, code=404)[1][4].startswith("FAIL"))
        self.assertTrue(self.run_doctor(plugin=True, code=cli.BUSY)[1][4].startswith("OK"))

    def test_windows_lines_only_on_windows(self):
        rc, lines = self.run_doctor(plugin=True, win=True, env={"SIDEREUS_PYTHON": self.pyexe},
                                    py3="C:\\Python39\\python3.exe")
        self.assertEqual((rc, len(lines)), (0, 7))
        rc, lines = self.run_doctor(plugin=True, win=True,
                                    py3="C:\\Users\\a\\AppData\\Local\\Microsoft\\WindowsApps\\python3.exe")
        self.assertEqual(rc, 1)
        self.assertTrue(lines[5].startswith("FAIL") and "setx SIDEREUS_PYTHON" in lines[5], lines[5])
        self.assertTrue(lines[6].startswith("FAIL") and "App execution aliases" in lines[6], lines[6])
        rc, lines = self.run_doctor(plugin=True, win=True, env={"SIDEREUS_PYTHON": self.pyexe + ".gone"})
        self.assertTrue(lines[5].startswith("FAIL"), lines[5])
        self.assertTrue(lines[6].startswith("OK"), lines[6])     # no python3 on PATH is not an alias

    def test_windows_command_name_and_alias_with_override(self):
        alias = "C:\\Users\\a\\AppData\\Local\\Microsoft\\WindowsApps\\python3.exe"
        rc, lines = self.run_doctor(tools=("git", "claude", "py"), plugin=True, win=True,
                                    env={"SIDEREUS_PYTHON": "py"}, py3=alias)
        self.assertEqual(rc, 0, lines)     # documented `setx SIDEREUS_PYTHON py`; alias unused when it is set
        self.assertIn("unused", lines[6])
        rc, lines = self.run_doctor(plugin=True, win=True, env={"SIDEREUS_PYTHON": "nopy"}, py3=alias)
        self.assertEqual(rc, 1)
        self.assertTrue(lines[5].startswith("FAIL") and lines[6].startswith("FAIL"), lines)

    def test_korean(self):
        rc, lines = self.run_doctor(tools=(), plugin=True, lang=KO)
        self.assertEqual(rc, 1)
        self.assertIn("훅 연결", lines[3])
        self.assertIn(" — 해결: ", lines[1])

    def test_writes_nothing(self):
        self.run_doctor(tools=(), code=0)
        self.assertEqual(sorted(os.listdir(self.home)), ["python.exe"])

    def test_usage_lists_doctor(self):
        self.assertIn("doctor", cli.MSG["usage"][1])


if __name__ == "__main__":
    unittest.main()
