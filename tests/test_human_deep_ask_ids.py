"""parse._human_deep: an answer appended after the memo offset counts even when its ask sits before it.

Temp transcript only; no live file, clock or network.
"""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

parse = sidereus("parse")


def rec(ts, typ, content):
    return json.dumps({"type": typ, "timestamp": ts, "message": {"content": content}}) + "\n"


class HumanDeepAskIds(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d)
        self.fp = os.path.join(self.d, "t.jsonl")
        saved = dict(parse._HUMAN_SEEN)
        self.addCleanup(lambda: (parse._HUMAN_SEEN.clear(), parse._HUMAN_SEEN.update(saved)))
        parse._HUMAN_SEEN.pop(self.fp, None)

    def add(self, *lines):
        with open(self.fp, "a", encoding="utf-8") as f:
            f.write("".join(lines))

    def fresh(self):
        memo = parse._HUMAN_SEEN.pop(self.fp, None)
        try:
            return parse._human_deep(self.fp)
        finally:
            parse._HUMAN_SEEN[self.fp] = memo

    def test_answer_after_memo_matches_fresh_scan(self):
        self.add(rec("2026-01-01T00:00:00Z", "user", "hello"),
                 rec("2026-01-01T00:01:00Z", "assistant",
                     [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {}}]))
        asked = parse._human_deep(self.fp)
        self.assertEqual(parse._HUMAN_SEEN[self.fp][2], ("toolu_A",))
        self.add(rec("2026-01-01T00:05:00Z", "user", [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "x"}]))
        got = parse._human_deep(self.fp)
        self.assertGreater(got, asked)
        self.assertEqual(got, self.fresh())
        self.assertEqual(parse._HUMAN_SEEN[self.fp][2], ())          # answered: no longer carried

    def test_open_ids_capped(self):
        self.add(*[rec("2026-01-01T00:01:00Z", "assistant",
                       [{"type": "tool_use", "id": "toolu_%03d" % i, "name": "ExitPlanMode", "input": {}}])
                   for i in range(parse._ASK_OPEN_CAP + 10)])
        parse._human_deep(self.fp)
        self.assertEqual(len(parse._HUMAN_SEEN[self.fp][2]), parse._ASK_OPEN_CAP)


if __name__ == "__main__":
    unittest.main()
