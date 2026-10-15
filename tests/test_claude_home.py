"""Claude Code config root follows CLAUDE_CONFIG_DIR (else ~/.claude) for every sidereus reader."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from tests._load import ROOT, sidereus

cfg = sidereus("config")


class ClaudeHomeTest(unittest.TestCase):
    def test_env_set(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": td}):
            self.assertEqual(cfg.claude_home(), td)
            self.assertEqual(cfg.claude_json(), os.path.join(td, ".claude.json"))

    def test_env_unset(self):
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(cfg.claude_home(), os.path.expanduser("~/.claude"))
            self.assertEqual(cfg.claude_json(), os.path.expanduser("~/.claude.json"))

    def test_readers_follow_env(self):
        # Fresh interpreter: the path constants are computed at import, so only a new process sees the env.
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as data:
            env = dict(os.environ, CLAUDE_CONFIG_DIR=td, MAILBOX_DIR=data, SIDEREUS_HOOK_NO_PID="1",
                       CODEX_HOME=os.path.join(os.devnull, "no-codex-home"))
            with open(os.path.join(data, "config.local.json"), "w") as f:
                f.write("{}\n")
            code = ("import json, sidereus.transcript as t, sidereus.ctxsrc as c, sidereus.burn_scan as b, sidereus.quota as q;"
                    "print(json.dumps([t.CLAUDE_PROJECTS, c.CLAUDE_DIR, c.CLAUDE_JSON, b.CLAUDE_SETTINGS,"
                    " q.CLAUDE_CONF, q.OMC_CACHE]))")
            out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True,
                                 text=True, timeout=60)
            self.assertEqual(out.returncode, 0, out.stderr[-2000:])
            got = json.loads(out.stdout.strip().splitlines()[-1])
            self.assertEqual(got, [os.path.join(td, "projects"), td, os.path.join(td, ".claude.json"),
                                   os.path.join(td, "settings.json"), os.path.join(td, ".claude.json"),
                                   os.path.join(td, "plugins", "oh-my-claudecode", ".usage-cache.json")])

    def test_hooks_follow_env(self):
        # Standalone hooks inline the same rule; load fresh copies under each env.
        import importlib.util

        def load(name):
            spec = importlib.util.spec_from_file_location("ch_" + name, os.path.join(ROOT, "hooks", name + ".py"))
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": td}):
            self.assertEqual(load("invite_notice").CLAUDE_JSON, os.path.join(td, ".claude.json"))
            self.assertEqual(load("pipelines_brief").CLAUDE_DIR, td)
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(load("invite_notice").CLAUDE_JSON, os.path.expanduser("~/.claude.json"))
            self.assertEqual(load("pipelines_brief").CLAUDE_DIR, os.path.expanduser("~/.claude"))


if __name__ == "__main__":
    unittest.main()
