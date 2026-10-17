"""History title/branch: picked up by the usage-index pass from Claude Code's own records (synthetic lines only)."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

us = sidereus("usage_index")
hi = sidereus("history")


def _line(**kw):
    return json.dumps(kw, separators=(",", ":")) + "\n"


def _usage(branch, ts="2026-09-20T01:00:00Z"):
    return _line(type="assistant", gitBranch=branch, timestamp=ts, requestId="r" + branch,
                 message={"id": "m" + branch, "model": "claude-opus-5",
                          "usage": {"input_tokens": 1, "output_tokens": 2}})


class HistTitle(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _scan(self, lines, name="s.jsonl", ent=None):
        fp = os.path.join(self.d, name)
        with open(fp, "a", encoding="utf-8") as f:
            f.write("".join(lines))
        ent = ent if ent is not None else {"sl": "x", "off": 0, "sz": -1, "mt": 0.0, "h": {}}
        us._uidx_scan(fp, ent)
        return fp, ent

    def test_custom_beats_ai_and_latest_wins(self):
        _, e = self._scan([_line(type="ai-title", aiTitle="first auto", sessionId="s"),
                           _usage("main"),
                           _line(type="custom-title", customTitle="renamed", sessionId="s"),
                           _line(type="ai-title", aiTitle="later auto", sessionId="s"),
                           _usage("feature/x")])
        self.assertEqual(hi._title_branch(e), ("renamed", "feature/x"))
        self.assertEqual(e["ti"], "later auto")
        self._scan([_line(type="custom-title", customTitle="renamed again", sessionId="s")], ent=e)
        self.assertEqual(hi._title_branch(e)[0], "renamed again")

    def test_missing_is_empty(self):
        _, e = self._scan([_usage("")])
        self.assertEqual(hi._title_branch(e), ("", ""))

    def test_title_text_in_conversation_is_ignored(self):
        _, e = self._scan([_line(type="user", message={"content": 'say "ai-title" and "custom-title"'})])
        self.assertEqual(hi._title_branch(e), ("", ""))

    def test_old_cache_probe(self):
        fp, e = self._scan([_line(type="ai-title", aiTitle="t", sessionId="s"), _usage("dev")])
        for k in ("ti", "br", "tv"):
            e.pop(k)
        us._uidx_meta_probe(fp, e)
        self.assertEqual(hi._title_branch(e), ("t", "dev"))
        self.assertEqual(e["tv"], us.UIDX_META_V)

    def test_subagent_files_skip_meta(self):
        os.makedirs(os.path.join(self.d, "subagents"))
        _, e = self._scan([_line(type="ai-title", aiTitle="t", sessionId="s")], name="subagents/a.jsonl")
        self.assertNotIn("ti", e)


if __name__ == "__main__":
    unittest.main()
