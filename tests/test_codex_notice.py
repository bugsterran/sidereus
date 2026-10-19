"""hooks/invite_notice.py and hooks/pipelines_brief.py with `--platform codex`: no Claude-only wording; no flag = unchanged. Tmp dirs only."""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    spec = importlib.util.spec_from_file_location(name + "_cx", os.path.join(ROOT, "hooks", name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


inv = _load("invite_notice")
pb = _load("pipelines_brief")

# Frozen pre-change Claude wording: a no-flag run must keep these bytes.
WAKE_EN_CC = ("New mail wakes this session via the Stop hook (mailbox_wake) — do not start Monitor or watch.sh."
              " When woken, read it with mailbox_inbox.")
HOW_CC = ("Default = run the pipeline directly: follow .claude/pipelines/<name>.json yourself with the Agent tool "
          "(stage order, agent, model, skill, gate, onFail; a stage skill means its prompt says Follow the <skill> skill.); "
          "start each stage's Agent description with [pl:<name>/<stage title>] and pass its agent/model as "
          "subagent_type/model. Skip a stage only after a Bash described [pl-skip:<name>/<stage title>] <reason>; "
          "another model: [pl-model:<name>/<stage title>=<model>]. In a run, SendMessage summaries start with the "
          "stage tag or [pl:-]. A stage whose agent is not installed runs as general-purpose with the same task.")
CLAUDE_ONLY = ("mailbox_wake", "Monitor", "Agent tool", "subagent_type", "SendMessage", "AskUserQuestion")


class InviteCodex(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.proj = os.path.join(self.d, "proj")
        os.makedirs(self.proj)
        self.proj = os.path.realpath(self.proj)
        vals = {"STORE": self.d, "ROOMS": os.path.join(self.d, "rooms.json"),
                "IDENTITY": os.path.join(self.d, "identity.json"), "SKIP": os.path.join(self.d, "skip.json"),
                "SEEN": os.path.join(self.d, "seen.json"), "CONFIG": os.path.join(self.d, "config.local.json"),
                "CLAUDE_JSON": os.path.join(self.d, "claude.json"), "ACCT_DIR": os.path.join(self.d, "acct"),
                "SESSPID_DIR": os.path.join(self.d, "sesspid"), "CLEAR_FILE": os.path.join(self.d, "clears.jsonl"),
                "_claude_pid": lambda: 4242, "_lang": lambda: "en", "PLATFORM": "cc"}
        for k, v in vals.items():
            p = mock.patch.object(inv, k, v)
            p.start()
            self.addCleanup(p.stop)
        self._w("claude.json", {"mcpServers": {"mailbox": {"command": "uv"}}})
        self._w("identity.json", {self.proj: "proj-bot"})

    def _w(self, name, data):
        with open(os.path.join(self.d, name), "w", encoding="utf-8") as f:
            json.dump(data, f)

    def run_hook(self, argv, event="SessionStart"):
        payload = json.dumps({"hook_event_name": event, "cwd": self.proj, "session_id": "sess-0001", "source": "startup"})
        out = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(payload)), contextlib.redirect_stdout(out):
            inv.main(argv)
        return out.getvalue()

    def test_no_flag_unchanged(self):
        self.assertEqual(self.run_hook([]), "[mailbox] id `proj-bot` · " + WAKE_EN_CC + "\n")
        self.assertTrue(os.path.isfile(os.path.join(self.d, "acct", "sess-0001")))

    def test_codex_wake_line(self):
        out = self.run_hook(["--platform", "codex"])
        self.assertEqual(out, "[mailbox] id `proj-codex` · " + inv.WAKE_EN_CODEX + "\n")
        for w in CLAUDE_ONLY:
            self.assertNotIn(w, out)
        self.assertFalse(os.path.exists(os.path.join(self.d, "acct")))   # Claude-only records skipped
        inv._lang = lambda: "ko"
        self.assertNotIn("mailbox_wake", self.run_hook(["--platform", "codex"]))

    def test_codex_identity_key_and_invites(self):
        self._w("identity.json", {self.proj: "proj-bot", "codex:" + self.proj: "cx"})
        self._w("rooms.json", {"r1": {"invited": ["cx"], "members": ["a"]}})
        out = self.run_hook(["--platform", "codex"])
        self.assertIn("id `cx`", out)
        self.assertIn("**r1**", out)

    def test_codex_id_colliding_with_claude_is_silent(self):
        self._w("identity.json", {self.proj: "proj-codex"})
        self.assertEqual(self.run_hook(["--platform", "codex"]), "")

    def test_unknown_platform_silent(self):
        self.assertEqual(self.run_hook(["--platform", "gemini"]), "")


class BriefCodex(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        d = os.path.join(self.tmp, ".claude", "pipelines")
        os.makedirs(d)
        with open(os.path.join(d, "change.json"), "w", encoding="utf-8") as f:
            json.dump({"v": 1, "name": "change", "title": "Change", "rules": "secret-rules",
                       "stages": [{"title": "Build", "agent": "general-purpose", "task": "secret-task"}]}, f)
        for k, v in (("CLAUDE_DIR", os.path.join(self.tmp, "home")), ("CONFIG_PATH", os.path.join(self.tmp, "cfg.json")),
                     ("BRIEF_DIR", os.path.join(self.tmp, "plbrief"))):
            p = mock.patch.object(pb, k, v)
            p.start()
            self.addCleanup(p.stop)

    def run_hook(self, argv):
        out = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"cwd": self.tmp}))), mock.patch.object(sys, "stdout", out):
            self.assertEqual(pb.main(argv), 0)
        return json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"] if out.getvalue() else ""

    def test_no_flag_unchanged(self):
        t = self.run_hook([])
        self.assertEqual(pb.HOW, HOW_CC)
        self.assertEqual(t, "Pipelines in this project (.claude/pipelines/):\n- change — Change · stages: Build\n" + HOW_CC)

    def test_codex_wording(self):
        t = self.run_hook(["--platform", "codex"])
        self.assertTrue(t.endswith(pb.HOW_CODEX))
        self.assertIn('echo "[pl:<name>/<stage title>]"', t)
        self.assertNotIn("secret", t)
        for w in CLAUDE_ONLY:
            self.assertNotIn(w, t)
        with open(pb.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"pipeline_apply": {"mode": "ask"}}, f)
        t = pb.brief(self.tmp, plat="codex")
        self.assertTrue(t.endswith(pb.HOW_ASK_CODEX))
        for w in CLAUDE_ONLY:
            self.assertNotIn(w, t)

    def test_unknown_platform_silent(self):
        self.assertEqual(self.run_hook(["--platform", "gemini"]), "")


if __name__ == "__main__":
    unittest.main()
