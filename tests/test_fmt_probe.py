"""scripts/fmt_probe.py: real parsers over fixture records — good shapes pass, a renamed upstream key fails loudly."""
import importlib.util
import json
import os
import tempfile
import unittest

from tests._load import sidereus

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("fmt_probe", os.path.join(os.path.dirname(HERE), "scripts", "fmt_probe.py"))
fp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fp)

TS = "2026-10-01T10:00:00.000Z"
SID = "aa11aa11-0000-4000-8000-000000000000"


def _claude(usage_key="usage"):
    u = {"input_tokens": 3, "output_tokens": 5, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 10}
    return [{"type": "user", "sessionId": SID, "cwd": "/w/p", "timestamp": TS, "message": {"role": "user", "content": "x"}},
            {"type": "assistant", "sessionId": SID, "cwd": "/w/p", "timestamp": TS,
             "message": {"role": "assistant", "model": "claude-opus-5-5", usage_key: u,
                         "content": [{"type": "text", "text": "y"}]}}]


def _codex(usage_key="last_token_usage"):
    u = {"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 7, "reasoning_output_tokens": 2}
    return [{"type": "session_meta", "timestamp": TS, "payload": {"id": SID, "cwd": "/w/p", "timestamp": TS}},
            {"type": "turn_context", "timestamp": TS, "payload": {"model": "gpt-5"}},
            {"type": "event_msg", "timestamp": TS,
             "payload": {"type": "token_count", "info": {usage_key: u, "total_token_usage": u}}}]


def _gemini(tok_key="tokens"):
    return [{"sessionId": SID, "projectHash": "ab" * 32, "startTime": TS, "kind": "main"},
            {"id": "m1", "type": "gemini", "timestamp": TS, "model": "gemini-3-pro",
             tok_key: {"input": 50, "output": 5, "cached": 10, "thoughts": 1, "tool": 0}}]


def _write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(r) for r in rows) + "\n")


class FmtProbe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.mods = (sidereus("parse"), sidereus("plat_codex"), sidereus("plat_gemini"))

    def tearDown(self):
        self.tmp.cleanup()

    def probe(self, claude=None, codex=None, gemini=None):
        parse, cx, gm = self.mods
        r = {}
        if claude is not None:
            _write(os.path.join(self.d, "cc", "-w-p", SID + ".jsonl"), claude)
        if codex is not None:
            _write(os.path.join(self.d, "cx", "sessions", "2026", "10", "01", "rollout-x.jsonl"), codex)
        if gemini is not None:
            _write(os.path.join(self.d, "gm", "tmp", "p", "chats", "session-x.jsonl"), gemini)
        r["claude"] = fp.check_claude(os.path.join(self.d, "cc"), 4, parse)
        r["codex"] = fp.check_codex(os.path.join(self.d, "cx"), 4, cx)
        r["gemini"] = fp.check_gemini(os.path.join(self.d, "gm"), 4, gm)
        return r

    def test_good_shapes_pass(self):
        r = self.probe(_claude(), _codex(), _gemini())
        for k in ("claude", "codex", "gemini"):
            self.assertEqual((r[k]["status"], r[k]["missing"]), ("ok", []), k)

    def test_renamed_keys_fail_by_name(self):
        r = self.probe(_claude("usage_v2"), _codex("last_usage"), _gemini("tokenCounts"))
        self.assertIn("usage", r["claude"]["missing"])
        self.assertIn("token_count.last_token_usage", r["codex"]["missing"])
        self.assertIn("messages.tokens", r["gemini"]["missing"])
        self.assertTrue(all(r[k]["status"] == "fail" for k in r))

    def test_no_files_is_skip(self):
        r = self.probe()
        self.assertTrue(all(r[k]["status"] == "skip" for k in r))


if __name__ == "__main__":
    unittest.main()
