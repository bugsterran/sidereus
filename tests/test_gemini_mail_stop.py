"""ext-hooks/gemini_mail_stop.py (Gemini AfterAgent): synthetic data dir only, never the live bus.

The Gemini session in a folder has its own mailbox id and must never surface the Claude session's mail
from the same folder.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "ext-hooks", "gemini_mail_stop.py")
_spec = importlib.util.spec_from_file_location("gemini_mail_stop", HOOK)
gms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gms)


class GeminiMailStop(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cwd = os.path.realpath(tempfile.mkdtemp())
        self.now = time.time_ns()
        self.n = 0
        self.ident({self.cwd: "claude-a", "gemini:" + self.cwd: "gem-a"})
        open(self.p("bus.jsonl"), "w", encoding="utf-8").close()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)
        shutil.rmtree(self.cwd, ignore_errors=True)

    def p(self, name):
        return os.path.join(self.d, name)

    def ident(self, data):
        with open(self.p("identity.json"), "w", encoding="utf-8") as f:
            json.dump(data, f)

    def post(self, to):
        self.n += 1
        with open(self.p("bus.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": f"m{self.n}", "t": self.now + self.n * 1000,
                                "from": "zed", "to": to, "body": "SECRET-BODY"}) + "\n")

    def decide(self, sid="g1"):
        gms.T0 = time.monotonic()
        return gms.decide({"session_id": sid, "cwd": self.cwd}, store=self.d, now_ns=self.now + 10 ** 9)

    def test_claude_mail_in_same_folder_is_not_taken(self):
        self.post("claude-a")
        self.assertIsNone(self.decide())
        self.assertFalse(os.path.exists(os.path.join(self.d, ".stop-hook")))  # nothing claimed

    def test_own_mail_blocks_once(self):
        self.post("claude-a")
        self.post("gem-a")
        r = self.decide()
        self.assertIn("`gem-a`", r)
        self.assertIn("1건", r)
        self.assertNotIn("SECRET-BODY", r)
        self.assertIsNone(self.decide())

    def test_unregistered_folder_uses_basename_gemini(self):
        self.ident({self.cwd: "claude-a"})
        self.post("claude-a")
        self.assertIsNone(self.decide())
        self.post(os.path.basename(self.cwd) + "-gemini")
        self.assertIsNotNone(self.decide())

    def test_login_under_a_claude_name_stays_silent(self):
        self.ident({self.cwd: "claude-a", "gemini:" + self.cwd: "claude-a"})
        self.post("claude-a")
        self.assertIsNone(self.decide())

    def test_process_contract(self):
        self.post("gem-a")
        env = dict(os.environ, MAILBOX_DIR=self.d)
        out = subprocess.run([sys.executable, HOOK], input=json.dumps({"session_id": "g2", "cwd": self.cwd}),
                             capture_output=True, text=True, env=env, timeout=10, encoding="utf-8")
        self.assertEqual(out.returncode, 0)
        self.assertEqual(json.loads(out.stdout)["decision"], "block")
        bad = subprocess.run([sys.executable, HOOK], input="not json", capture_output=True, text=True,
                             env=env, timeout=10, encoding="utf-8")
        self.assertEqual((bad.returncode, bad.stdout), (0, ""))


class GeminiMailWorker(GeminiMailStop):
    """Worker mode: opt-in, block with the wait instruction when idle, stop after K empty rounds."""

    def setUp(self):
        super().setUp()
        self._env = {k: os.environ.pop(k) for k in ("SIDEREUS_MAIL_WORKER", "SIDEREUS_MAIL_WORKER_MAX_IDLE")
                     if k in os.environ}

    def tearDown(self):
        os.environ.pop("SIDEREUS_MAIL_WORKER", None)
        os.environ.pop("SIDEREUS_MAIL_WORKER_MAX_IDLE", None)
        os.environ.update(self._env)
        super().tearDown()

    def mark(self):
        open(os.path.join(self.cwd, gms.WORKER_MARK), "w", encoding="utf-8").close()

    def chat(self, text):
        """Append a Gemini transcript "user" row (text "" = a tool response row)."""
        self.n += 1
        with open(self.p("chat.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": f"u{self.n}", "type": "user", "content": [{"text": text}]},
                               ensure_ascii=False) + "\n")

    def work(self, active=False, sid="g1", human=None):
        # active=False by default: what Gemini 0.61.0 really sends after a tool-response turn.
        if human:
            self.chat(human)
        out = gms.worker({"session_id": sid, "cwd": self.cwd, "stop_hook_active": active,
                          "transcript_path": self.p("chat.jsonl")}, store=self.d, now_ns=self.now)
        if out and out.get("decision") == "block":
            self.chat(out["reason"])
            self.chat("")                                   # the mailbox_wait tool response
        return out

    def run_hook(self, active=True):
        env = dict(os.environ, MAILBOX_DIR=self.d)
        env.pop("SIDEREUS_MAIL_WORKER", None)
        out = subprocess.run([sys.executable, HOOK], capture_output=True, text=True, env=env, timeout=10,
                             input=json.dumps({"session_id": "g9", "cwd": self.cwd, "stop_hook_active": active}), encoding="utf-8")
        self.assertEqual(out.returncode, 0)
        return out.stdout

    def test_worker_off_is_silent(self):
        self.assertIsNone(self.work())
        self.assertEqual(self.run_hook(), "")

    def test_worker_on_empty_blocks_with_wait(self):
        self.mark()
        out = json.loads(self.run_hook(active=False))
        self.assertEqual(out["decision"], "block")
        self.assertIn("mailbox_wait", out["reason"])
        self.assertIn("mailbox_send", out["reason"])

    def test_env_switch(self):
        os.environ["SIDEREUS_MAIL_WORKER"] = "1"
        self.assertEqual(self.work(human="hi")["decision"], "block")

    def test_k_limit_stops_blocking(self):
        self.mark()
        os.environ["SIDEREUS_MAIL_WORKER_MAX_IDLE"] = "2"
        self.assertEqual(self.work(human="hi")["decision"], "block")     # idle 0
        self.assertEqual(self.work()["decision"], "block")               # idle 1
        out = self.work()                                                # idle 2 -> stop
        self.assertNotIn("decision", out)
        self.assertIn("systemMessage", out)
        self.assertIsNotNone(self.work().get("systemMessage"))           # stays stopped
        self.assertEqual(self.work(human="go on")["decision"], "block")  # new human prompt resets

    def test_live_sequence_counts_up_despite_stop_hook_active_false(self):
        # Live 2026-09-24: every round ended after a tool response with stop_hook_active=false and
        # the counter stayed at «0/12». It must count up.
        self.mark()
        os.environ["SIDEREUS_MAIL_WORKER_MAX_IDLE"] = "12"
        r = [self.work(human="hi")["reason"]] + [self.work()["reason"] for _ in range(4)]
        self.assertIn("(빈 대기 0/12)", r[0])
        self.assertIn("(빈 대기 4/12)", r[4])

    def test_default_k_and_hour_wait(self):
        # One wait per hour (timeout_s=3540), so the default K is 3 (~3 h idle max), not 12 (~12 h).
        self.mark()
        r = self.work(human="hi")["reason"]
        self.assertIn("timeout_s=3540, round=1", r)
        self.assertIn("(빈 대기 0/3)", r)
        self.work()
        self.work()
        self.assertIn("systemMessage", self.work())                      # idle 3 -> stop

    def test_each_block_asks_for_a_new_round(self):
        # Gemini aborts after 5 identical mailbox_wait calls in one prompt_id; args must differ.
        self.mark()
        os.environ["SIDEREUS_MAIL_WORKER_MAX_IDLE"] = "12"
        r = [self.work(human="hi")["reason"]] + [self.work()["reason"] for _ in range(5)]
        rounds = [x.split("round=")[1].split()[0] for x in r]
        self.assertEqual(len(set(rounds)), 6)

    def test_machine_prompts_are_not_human(self):
        self.chat("hi")
        self.chat("System: Potential loop detected. Details: Repeated tool call")
        self.chat("[메일박스] `gem-a` 앞으로 새 메일")
        self.chat("")
        self.assertEqual(gms.human_key({"transcript_path": self.p("chat.jsonl")}), "u1")
        k = gms.human_key({"transcript_path": "", "prompt": "hi"})
        self.assertTrue(k.startswith("p:") and "hi" not in k[2:])       # hashed: no prompt text persisted
        self.assertEqual(k, gms.human_key({"transcript_path": "", "prompt": "hi"}))

    def test_cursor_move_resets_idle(self):
        self.mark()
        os.environ["SIDEREUS_MAIL_WORKER_MAX_IDLE"] = "2"
        self.work(human="hi")
        self.work()
        with open(self.p("read-gem-a.cursor"), "w", encoding="utf-8") as f:
            f.write(str(self.now))
        self.assertIn("(빈 대기 0/2)", self.work()["reason"])

    def test_pending_mail_uses_todays_path(self):
        self.mark()
        self.post("gem-a")
        out = json.loads(self.run_hook())
        self.assertEqual(out["decision"], "block")
        self.assertIn("새 메일 1건", out["reason"])
        self.assertNotIn("mailbox_wait", out["reason"])


class OtherPlatformMailStop(unittest.TestCase):
    """`--platform <key>` (Codex Stop, generic Stop): own id namespace, never the Claude id; example configs wired."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cwd = os.path.realpath(tempfile.mkdtemp())
        self.now = time.time_ns()
        with open(os.path.join(self.d, "identity.json"), "w", encoding="utf-8") as f:
            json.dump({self.cwd: "claude-a", "gemini:" + self.cwd: "gem-a"}, f)
        with open(os.path.join(self.d, "bus.jsonl"), "w", encoding="utf-8") as f:
            for i, to in enumerate(("claude-a", "gem-a", os.path.basename(self.cwd) + "-codex")):
                f.write(json.dumps({"id": f"m{i}", "t": self.now + i, "from": "zed", "to": to,
                                    "body": "SECRET-BODY"}) + "\n")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)
        shutil.rmtree(self.cwd, ignore_errors=True)

    def hook(self, *args):
        env = dict(os.environ, MAILBOX_DIR=self.d, SIDEREUS_MAIL_WORKER="1")
        out = subprocess.run([sys.executable, HOOK] + list(args), capture_output=True, text=True, env=env,
                             timeout=10, input=json.dumps({"session_id": "c1", "cwd": self.cwd}), encoding="utf-8")
        self.assertEqual(out.returncode, 0)
        return out.stdout

    def test_codex_takes_only_its_own_mail(self):
        out = json.loads(self.hook("--platform", "codex"))
        self.assertEqual(out["decision"], "block")
        self.assertIn("-codex`", out["reason"])
        self.assertIn("새 메일 1건", out["reason"])
        self.assertIn(" mailbox_inbox ", out["reason"])
        self.assertNotIn("mcp_mailbox_", out["reason"])
        self.assertNotIn("SECRET-BODY", out["reason"])
        again = json.loads(self.hook("--platform", "codex"))     # same mail never blocks twice -> worker block
        self.assertNotIn("새 메일", again["reason"])
        self.assertIn(" mailbox_wait ", again["reason"])
        self.assertNotIn("mcp_mailbox_", again["reason"])

    def test_worker_stays_off_on_unmeasured_platforms(self):
        self.hook("--platform", "cursor")                        # consumes the pending-mail block if any
        self.assertEqual(self.hook("--platform", "cursor"), "")

    def test_bad_or_claude_platform_is_silent(self):
        for args in (("--platform", "claude"), ("--platform", "../x"), ("--platform",)):
            self.assertEqual(self.hook(*args), "")

    def test_set_platform_rejects_claude(self):
        try:
            self.assertFalse(gms.set_platform("claude"))
            self.assertTrue(gms.set_platform("codex"))
            self.assertEqual((gms.KEY_PREFIX, gms.ID_SUFFIX, gms.TOOL_PREFIX), ("codex:", "-codex", ""))
        finally:
            gms.set_platform("gemini")

    def test_example_configs_wire_the_mail_hook(self):
        want = {"gemini-settings-example.json": ("AfterAgent", "gemini_mail_stop.py"),
                "codex-hooks-example.json": ("Stop", "gemini_mail_stop.py --platform codex"),
                "generic-hooks-example.json": ("Stop", "gemini_mail_stop.py --platform <PLATFORM>")}
        for name, (event, cmd) in want.items():
            with open(os.path.join(ROOT, "ext-hooks", name), encoding="utf-8") as f:
                hooks = json.load(f)["hooks"]
            cmds = [h.get("command", "") for g in hooks.get(event, []) for h in g.get("hooks", [])]
            self.assertTrue(any(c.endswith(cmd) for c in cmds), name)
            self.assertFalse(any("watch.sh" in c for c in cmds), name)


class CodexMailWorker(unittest.TestCase):
    """Worker mode on Codex: same opt-in as Gemini; human_key reads Codex rollout rows and skips injected ones."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cwd = os.path.realpath(tempfile.mkdtemp())
        self.now = time.time_ns()
        self.n = 0
        self.me = os.path.basename(self.cwd) + "-codex"
        with open(os.path.join(self.d, "identity.json"), "w", encoding="utf-8") as f:
            json.dump({self.cwd: "claude-a"}, f)
        open(os.path.join(self.d, "bus.jsonl"), "w", encoding="utf-8").close()
        self.tp = os.path.join(self.d, "rollout.jsonl")
        self._env = {k: os.environ.pop(k) for k in ("SIDEREUS_MAIL_WORKER", "SIDEREUS_MAIL_WORKER_MAX_IDLE")
                     if k in os.environ}
        gms.set_platform("codex")

    def tearDown(self):
        gms.set_platform("gemini")
        os.environ.pop("SIDEREUS_MAIL_WORKER", None)
        os.environ.pop("SIDEREUS_MAIL_WORKER_MAX_IDLE", None)
        os.environ.update(self._env)
        shutil.rmtree(self.d, ignore_errors=True)
        shutil.rmtree(self.cwd, ignore_errors=True)

    def row(self, text, kind="user.text", role="user"):
        """Append a row shaped like a Codex 0.163.0 rollout message (kind None = no passthrough metadata)."""
        self.n += 1
        p = {"type": "message", "role": role, "id": f"msg_{self.n}",
             "content": [{"type": "input_text", "text": text}]}
        if kind:
            p["internal_chat_message_metadata_passthrough"] = {"turn_id": "t1", "content_item_kinds": [kind]}
        with open(self.tp, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ordinal": self.n, "timestamp": "2026-10-20T00:00:00Z", "type": "response_item",
                                "payload": p}, ensure_ascii=False) + "\n")

    def work(self, human=None):
        if human:
            self.row(human)
        out = gms.worker({"session_id": "c1", "cwd": self.cwd, "transcript_path": self.tp},
                         store=self.d, now_ns=self.now)
        if out and out.get("decision") == "block":
            self.row('<hook_prompt hook_run_id="stop:1:hooks.json">' + out["reason"] + "</hook_prompt>",
                     kind="unknown")
        return out

    def test_worker_on_codex_marker_and_env(self):
        self.assertFalse(gms.worker_on(self.cwd))
        os.environ["SIDEREUS_MAIL_WORKER"] = "1"
        self.assertTrue(gms.worker_on(self.cwd))
        os.environ.pop("SIDEREUS_MAIL_WORKER")
        open(os.path.join(self.cwd, gms.WORKER_MARK), "w", encoding="utf-8").close()
        self.assertTrue(gms.worker_on(self.cwd))
        gms.set_platform("cursor")
        self.assertFalse(gms.worker_on(self.cwd))

    def test_codex_block_uses_bare_tool_names(self):
        os.environ["SIDEREUS_MAIL_WORKER"] = "1"
        r = self.work(human="hi")["reason"]
        self.assertIn(f"`{self.me}`", r)
        self.assertIn(" mailbox_wait 를 timeout_s=3540, round=1", r)
        self.assertNotIn("mcp_mailbox_", r)

    def test_human_key_skips_codex_injected_rows(self):
        self.row("<environment_context>  <cwd>/x</cwd></environment_context>",
                 kind="environments.environment_context")
        self.row("do the thing")
        self.row('<hook_prompt hook_run_id="stop:1:hooks.json">[메일 일꾼] wait</hook_prompt>', kind="unknown")
        self.row("# AGENTS.md instructions for /x", kind=None)
        self.row("<environment_context></environment_context>", kind=None)
        self.row("assistant text", role="assistant")
        self.assertEqual(gms.human_key({"transcript_path": self.tp}), "msg_2")
        self.assertNotIn("do the thing", json.dumps(gms.human_key({"transcript_path": self.tp})))

    def test_new_human_prompt_resets_idle(self):
        os.environ["SIDEREUS_MAIL_WORKER"] = "1"
        os.environ["SIDEREUS_MAIL_WORKER_MAX_IDLE"] = "2"
        self.assertIn("(빈 대기 0/2)", self.work(human="hi")["reason"])
        self.assertIn("(빈 대기 1/2)", self.work()["reason"])   # injected hook_prompt row is not human
        self.assertIn("systemMessage", self.work())
        self.assertIn("(빈 대기 0/2)", self.work(human="go on")["reason"])


if __name__ == "__main__":
    unittest.main()
