"""sidereus_cli.py setup-claude --write: confirm, backup, idempotent hook merge, plugin skip, symlink refusal, MCP argv."""
import contextlib
import glob
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("sidereus_cli_setup_write_t", os.path.join(ROOT, "sidereus_cli.py"))
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)

PY = "/x/python3"


class SetupWrite(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.path = os.path.join(self.home, "settings.json")
        self.calls = []
        self.registered = False

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def fake_run(self, argv, **k):
        self.calls.append(list(argv))
        rc = 0 if argv[1:3] != ["mcp", "get"] or self.registered else 1
        return subprocess.CompletedProcess(argv, rc)

    def run_write(self, yes=True, tty=False, answer="n", claude="/bin/claude"):
        out = io.StringIO()
        with mock.patch.object(cli, "claude_home", lambda: self.home), \
                mock.patch.object(cli, "_which", lambda n: claude), \
                mock.patch.object(cli, "_sub_run", self.fake_run), \
                mock.patch.object(cli, "_isatty", lambda: tty), \
                mock.patch.object(cli, "_input", lambda p: answer), \
                mock.patch.object(cli, "_now", lambda: 0), \
                mock.patch.dict(os.environ, {"LANG": "en_US.UTF-8"}), \
                contextlib.redirect_stdout(out):
            rc = cli.cmd_setup_write(PY, yes)
        return rc, out.getvalue()

    def put(self, text):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(text)

    def read(self):
        with open(self.path, encoding="utf-8") as f:
            return f.read()

    def baks(self):
        return glob.glob(self.path + ".bak-*")

    def adds(self):
        return [c for c in self.calls if c[1:3] == ["mcp", "add"]]

    def test_merge_backup_keeps_other_keys_and_is_idempotent(self):
        self.put('{\n    "model": "x",\n    "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "mine"}]}]},\n'
                 '    "zeta": [1, 2]\n}\n')
        rc, out = self.run_write()
        self.assertEqual(rc, 0, out)
        self.assertIn("+++", out)
        text = self.read()
        obj = json.loads(text)
        self.assertEqual(list(obj), ["model", "hooks", "zeta"])          # key order kept
        self.assertEqual((obj["model"], obj["zeta"]), ("x", [1, 2]))
        self.assertTrue(text.startswith('{\n    "model"'))               # file's indent kept
        self.assertEqual(obj["hooks"]["Stop"][0], {"hooks": [{"type": "command", "command": "mine"}]})
        want = cli.setup_hooks(PY)["hooks"]
        for ev, groups in want.items():
            cmds = [h["command"] for g in obj["hooks"][ev] for h in g["hooks"]]
            for g in groups:
                for h in g["hooks"]:
                    self.assertEqual(cmds.count(h["command"]), 1)
        self.assertEqual(len(self.baks()), 1)
        self.assertEqual(len(self.adds()), 1)
        # re-run: nothing changes, no new backup, MCP already registered
        self.registered = True
        self.calls = []
        rc, out = self.run_write()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.read(), text)
        self.assertEqual(len(self.baks()), 1)
        self.assertEqual(self.adds(), [])
        self.assertIn("Nothing to change", out)

    def test_plugin_installed_adds_no_hooks(self):
        ip = os.path.join(self.home, "plugins", "cache", "sidereus")
        os.makedirs(ip)
        with open(os.path.join(self.home, "plugins", "installed_plugins.json"), "w", encoding="utf-8") as f:
            json.dump({"plugins": {"sidereus@sidereus": [{"installPath": ip}]}}, f)
        self.put('{"a": 1}\n')
        rc, out = self.run_write()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.read(), '{"a": 1}\n')
        self.assertEqual(self.baks(), [])
        self.assertIn("plugin is installed", out)
        self.assertEqual(len(self.adds()), 1)

    def test_plugin_disabled_still_adds_hooks(self):
        ip = os.path.join(self.home, "plug")
        os.makedirs(ip)
        os.makedirs(os.path.join(self.home, "plugins"))
        with open(os.path.join(self.home, "plugins", "installed_plugins.json"), "w", encoding="utf-8") as f:
            json.dump({"plugins": {"sidereus@m": [{"installPath": ip}]}}, f)
        self.put('{"enabledPlugins": {"sidereus@m": false}}\n')
        self.assertFalse(cli.plugin_installed(self.home))

    def test_non_tty_without_yes_writes_nothing(self):
        self.put('{"a": 1}\n')
        rc, out = self.run_write(yes=False, tty=False)
        self.assertNotEqual(rc, 0)
        self.assertEqual(self.read(), '{"a": 1}\n')
        self.assertEqual(self.baks(), [])
        self.assertEqual(self.adds(), [])
        self.assertIn("--yes", out)

    def test_tty_answer_no_cancels(self):
        self.put('{"a": 1}\n')
        rc, _ = self.run_write(yes=False, tty=True, answer="n")
        self.assertNotEqual(rc, 0)
        self.assertEqual(self.read(), '{"a": 1}\n')
        self.assertEqual(self.adds(), [])
        rc, _ = self.run_write(yes=False, tty=True, answer="y")
        self.assertEqual(rc, 0)
        self.assertIn("hooks", json.loads(self.read()))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks")
    def test_symlink_refused(self):
        real = os.path.join(self.home, "real.json")
        with open(real, "w", encoding="utf-8") as f:
            f.write("{}\n")
        try:
            os.symlink(real, self.path)
        except OSError:
            self.skipTest("no symlink permission")
        rc, out = self.run_write()
        self.assertEqual(rc, 1)
        self.assertIn("symlink", out)
        with open(real, encoding="utf-8") as f:
            self.assertEqual(f.read(), "{}\n")
        self.assertEqual(self.calls, [])

    def test_invalid_json_refused(self):
        for bad in ('{"a": ', "[1, 2]\n"):
            self.put(bad)
            rc, out = self.run_write()
            self.assertEqual(rc, 1)
            self.assertIn("not a valid JSON object", out)
            self.assertEqual(self.read(), bad)
        self.assertEqual(self.calls, [])

    def test_missing_settings_created_without_backup(self):
        rc, _ = self.run_write()
        self.assertEqual(rc, 0)
        self.assertIn("hooks", json.loads(self.read()))
        self.assertEqual(self.baks(), [])

    def test_no_claude_on_path_prints_command(self):
        self.put('{"a": 1}\n')
        rc, out = self.run_write(claude=None)
        self.assertEqual(rc, 1)
        self.assertIn("not on PATH", out)
        line = out.split("not on PATH", 1)[1].splitlines()[1].strip()
        # Windows quotes every arg ("claude" "mcp" ...); compare unquoted tokens so both OSes check the same argv
        self.assertEqual([a.strip("\"'") for a in line.split()][:6], ["claude", "mcp", "add", "--scope", "user", "sidereus"])
        self.assertEqual(line, cli._argv_text(cli.mcp_add_argv("claude", PY)))
        self.assertEqual(self.calls, [])
        self.assertIn("hooks", json.loads(self.read()))      # hooks still written

    def test_mcp_argv(self):
        mcp = os.path.join(cli.CODE_DIR, "mcp", "sidereus_mcp.py")
        self.assertEqual(cli.mcp_add_argv("claude", PY, win=False),
                         ["claude", "mcp", "add", "--scope", "user", "sidereus", "--", PY, mcp])
        w = cli.mcp_add_argv("claude", PY, win=True)
        self.assertEqual(w[5], "sidereus")                    # name before the variadic -e
        self.assertEqual(w[6:10], ["-e", "PYTHONUTF8=1", "-e", "PYTHONIOENCODING=utf-8"])
        self.assertEqual(w[-3:], ["--", PY, mcp])

    def test_main_routes_write(self):
        with mock.patch.object(cli, "cmd_setup_write", lambda py, yes: 7 if yes else 8):
            self.assertEqual(cli.main(["setup-claude", "--write", "--yes"]), 7)
            self.assertEqual(cli.main(["setup-claude", "--write"]), 8)


if __name__ == "__main__":
    unittest.main()
