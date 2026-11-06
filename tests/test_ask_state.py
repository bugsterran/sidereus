"""A pending AskUserQuestion/ExitPlanMode is the user's turn («질문 대기»), not «도구 실행 중»/«생각 중».

Synthetic transcript tails only — parse._tail_lines/_running_bg/_cwd_from_slug and every
file/git/otel reader of sessions._session_row are monkeypatched. No live file is read.
"""
import json
import unittest

from tests import _clock
from tests._clock import NOW
from tests._load import sidereus

parse = sidereus("parse")
notes = sidereus("notes")
sessions = sidereus("sessions")
att = sidereus("attention")

CWD = "/w/repo-s"
T0 = "2026-09-24T00:58:18.937Z"


def asst(*content):
    return json.dumps({"type": "assistant", "sessionId": "s1", "cwd": CWD, "timestamp": T0,
                       "message": {"content": list(content)}})


def asst_mid(mid, *content):
    return json.dumps({"type": "assistant", "sessionId": "s1", "cwd": CWD, "timestamp": T0,
                       "message": {"id": mid, "content": list(content)}})


def user(*content):
    return json.dumps({"type": "user", "sessionId": "s1", "cwd": CWD, "timestamp": T0,
                       "message": {"content": list(content)}})


def tu(name, i):
    return {"type": "tool_use", "id": i, "name": name, "input": {}}


def tr(i):
    return {"type": "tool_result", "tool_use_id": i, "content": "ok"}


class Patch(unittest.TestCase):
    def setUp(self):
        clk = _clock.frozen(parse, notes, sessions, att)   # row ages and otel freshness use _clock.NOW
        clk.__enter__()
        self.addCleanup(clk.__exit__, None, None, None)

    def patch(self, mod, name, val):
        old = getattr(mod, name)
        setattr(mod, name, val)
        self.addCleanup(setattr, mod, name, old)

    def parse(self, lines):
        self.patch(parse, "_tail_lines", lambda fp, nbytes=0, limit=0: list(lines))
        self.patch(parse, "_running_bg", lambda fp: ([], [], []))
        self.patch(parse, "_cwd_from_slug", lambda s: CWD)
        return parse._parse_transcript("/x/-w-repo-s/s1.jsonl")


class ParseAndState(Patch):
    LIVE = {CWD: 1}

    def st(self, p):
        return notes._sess_state(p["cwd"], p["shape"], self.LIVE, p["ask"], p["abort"], p["err"],
                                 sid=p["sid"], ask_tool=p["askTool"])

    def test_pending_ask_is_ask(self):
        p = self.parse([asst({"type": "thinking"}), asst({"type": "text", "text": "x"}),
                        asst(tu("AskUserQuestion", "a1"))])
        self.assertTrue(p["askTool"])
        self.assertEqual(self.st(p), "ask")

    def test_pending_exit_plan_is_ask(self):
        p = self.parse([asst(tu("ExitPlanMode", "a1"))])
        self.assertEqual(self.st(p), "ask")

    def test_answered_ask_is_not_ask(self):
        p = self.parse([asst(tu("AskUserQuestion", "a1")), user(tr("a1"))])
        self.assertFalse(p["askTool"])
        self.assertEqual(self.st(p), "think")

    def test_question_followed_by_status_line_is_ask(self):
        p = self.parse([asst({"type": "text", "text": "Done.\n\nShall I push it?\n\nTests: 31 OK"})])
        self.assertTrue(p["ask"])

    def test_bold_question_is_ask(self):
        p = self.parse([asst({"type": "text", "text": "Done.\n\n**Push e7f3 to develop?**\n\nNote a\n\nNote b"})])
        self.assertTrue(p["ask"])

    def test_question_far_up_is_not_ask(self):
        p = self.parse([asst({"type": "text", "text": "Push it?\nline a\nline b\nline c\nline d"})])
        self.assertFalse(p["ask"])

    def test_human_at_skips_notifications(self):
        def u(ts, text, **kw):
            return json.dumps(dict({"type": "user", "sessionId": "s1", "cwd": CWD, "timestamp": ts,
                                    "message": {"content": [{"type": "text", "text": text}]}}, **kw))
        p = self.parse([u("2026-09-24T00:50:00.000Z", "do it"),
                        u("2026-09-24T00:55:00.000Z", "<task-notification>x</task-notification>"),
                        u("2026-09-24T00:56:00.000Z", "skill body", isMeta=True)])
        self.assertEqual(p["humanAt"], int(parse._line_ts(json.loads(u("2026-09-24T00:50:00.000Z", "")), 0)))
        self.assertEqual(self.parse([asst({"type": "text", "text": "x"})])["humanAt"], 0)

    def test_answered_ask_tool_counts_as_reply(self):
        # The picker answer is a tool_result: it must clear the «ask» card like a typed prompt.
        def at(ts, kind, *content):
            return json.dumps({"type": kind, "sessionId": "s1", "cwd": CWD, "timestamp": ts, "message": {"content": list(content)}})
        ts = lambda s: int(parse._line_ts({"timestamp": s}, 0))
        p = self.parse([at("2026-09-24T00:50:00.000Z", "user", {"type": "text", "text": "go"}),
                        at("2026-09-24T00:51:00.000Z", "assistant", tu("AskUserQuestion", "q1")),
                        at("2026-09-24T00:51:05.000Z", "user", tr("q1")),
                        at("2026-09-24T00:52:00.000Z", "assistant", tu("Bash", "b1")),
                        at("2026-09-24T00:52:01.000Z", "user", tr("b1"))])
        self.assertEqual(p["humanAt"], ts("2026-09-24T00:51:05.000Z"))
        card = ts("2026-09-24T00:51:00.000Z")
        row = {"sid": "s1", "state": "think", "humanAt": p["humanAt"], "tailAt": p["tailAt"]}
        self.assertFalse(att._ask_open(row, {"sid": "s1"}, card))
        # an ordinary tool_result is not a reply: the card still holds
        p2 = self.parse([at("2026-09-24T00:50:00.000Z", "user", {"type": "text", "text": "go"}),
                         at("2026-09-24T00:51:00.000Z", "assistant", tu("AskUserQuestion", "q1")),
                         at("2026-09-24T00:52:00.000Z", "assistant", tu("Bash", "b1")),
                         at("2026-09-24T00:52:01.000Z", "user", tr("b1"))])
        self.assertEqual(p2["humanAt"], ts("2026-09-24T00:50:00.000Z"))
        self.assertTrue(att._ask_open(dict(row, humanAt=p2["humanAt"]), {"sid": "s1"}, card))

    def test_queued_prompt_mid_turn_counts_as_reply(self):
        # A prompt typed while the turn runs lands as a queued_command attachment with humanTurn true.
        def att_line(ts, **a):
            return json.dumps({"type": "attachment", "sessionId": "s1", "cwd": CWD, "timestamp": ts,
                               "attachment": dict({"type": "queued_command", "commandMode": "prompt", "prompt": "x"}, **a)})
        def at(ts, kind, *content):
            return json.dumps({"type": kind, "sessionId": "s1", "cwd": CWD, "timestamp": ts, "message": {"content": list(content)}})
        ts = lambda s: int(parse._line_ts({"timestamp": s}, 0))
        head = [at("2026-09-24T00:50:00.000Z", "user", {"type": "text", "text": "go"}),
                at("2026-09-24T00:51:00.000Z", "assistant", tu("Bash", "b1"))]
        p = self.parse(head + [att_line("2026-09-24T00:51:30.000Z", humanTurn=True)])
        self.assertEqual(p["humanAt"], ts("2026-09-24T00:51:30.000Z"))
        # a task notification or reminder uses the same attachment type without humanTurn: not a reply
        p2 = self.parse(head + [att_line("2026-09-24T00:51:30.000Z", commandMode="task-notification")])
        self.assertEqual(p2["humanAt"], ts("2026-09-24T00:50:00.000Z"))
        self.assertTrue(parse._USER_RE.search(att_line("2026-09-24T00:51:30.000Z", humanTurn=True).encode()))

    def test_human_line_beyond_tail_window(self):
        # A human reply >400 KB from the end falls outside the tail: the scan past the tail still finds it.
        import os, tempfile
        def rec(ts, typ, content):
            return json.dumps({"type": typ, "sessionId": "s1", "cwd": CWD, "timestamp": ts,
                               "message": {"content": content}})
        big = [{"type": "text", "text": "x" * 100_000}]
        lines = [rec("2026-09-24T00:50:00.000Z", "user", [{"type": "text", "text": "yes, go"}])]
        lines += [rec("2026-09-24T00:5%d:00.000Z" % (1 + i), "assistant", big) for i in range(6)]
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: (os.remove(fp), os.rmdir(d)))
        fp = os.path.join(d, "s1.jsonl")
        with open(fp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        self.patch(parse, "_running_bg", lambda fp: ([], [], []))
        self.patch(parse, "_cwd_from_slug", lambda s: CWD)
        p = parse._parse_transcript(fp)
        reply = int(parse._line_ts(json.loads(lines[0]), 0))
        self.assertEqual(p["humanAt"], reply)
        self.assertGreater(p["tailAt"], reply)
        row = {"sid": "s1", "state": "think", "humanAt": p["humanAt"], "tailAt": p["tailAt"]}
        self.assertFalse(att._ask_open(row, {"sid": "s1"}, reply - 30))          # replied after the question: clears
        self.assertTrue(att._ask_open(row, {"sid": "s1"}, reply + 30))           # asked after that line: holds
        # appended wake-ups (no human) keep the memoised answer; a new prompt past the cap is found again
        with open(fp, "a", encoding="utf-8") as f:
            f.write(rec("2026-09-24T01:00:00.000Z", "user", "<task-notification>x</task-notification>") + "\n")
        self.assertEqual(parse._parse_transcript(fp)["humanAt"], reply)
        self.patch(parse, "_HUMAN_SCAN", 1000)
        parse._HUMAN_SEEN.pop(fp, None)
        self.assertEqual(parse._parse_transcript(fp)["humanAt"], 0)              # beyond the cap: unknown, holds

    def test_question_text_beside_bash_stays_tool(self):
        # a '?' in text sets `ask`, but the pending tool is Bash — it is running, not waiting on the user
        p = self.parse([asst({"type": "text", "text": "run it?"}, tu("Bash", "b1"))])
        self.assertTrue(p["ask"])
        self.assertEqual(self.st(p), "tool")

    def test_ask_split_from_sibling_tool_line_is_ask(self):
        # one message (same id) written as two lines: AskUserQuestion, then Read — newest line is Read
        p = self.parse([asst_mid("m1", tu("AskUserQuestion", "a1")), asst_mid("m1", tu("Read", "r1"))])
        self.assertTrue(p["askTool"])
        self.assertEqual(self.st(p), "ask")

    def test_ask_in_older_message_is_not_sibling(self):
        p = self.parse([asst_mid("m0", tu("AskUserQuestion", "a0")), user(tr("a0")),
                        asst_mid("m1", tu("Read", "r1"))])
        self.assertFalse(p["askTool"])
        self.assertEqual(self.st(p), "tool")


class RowOtelOverride(Patch):
    """The `api_request` (-> think) of the response carrying AskUserQuestion must not override `ask`."""

    def row(self, p, otel):
        for n, v in {"_ctx_window": lambda *a: (1000000, "obs"), "_otel_state": lambda sid: otel,
                     "_bg_show": lambda *a: [], "_mon_rows": lambda *a: [], "_bg_age": lambda *a: 0,
                     "session_repos": lambda *a: [], "_wt_of": lambda *a: None, "mbox_of": lambda *a: ("", ""),
                     "_projcost_of": lambda *a: 0.0, "_git_state": lambda *a: "", "_model_win": lambda *a: (0, 0),
                     "_dead": lambda *a: False}.items():
            self.patch(sessions, n, v)
        now = NOW
        return sessions._session_row("/nonexistent/s1.jsonl", now - 30, now, {CWD: 1}, p)

    def test_otel_think_does_not_override_ask(self):
        p = self.parse([asst(tu("AskUserQuestion", "a1"))])
        r = self.row(p, {"state": "think", "ev": "api_request", "at": NOW})
        self.assertEqual(r["state"], "ask")
        self.assertEqual(r["blocked"], "")

    def test_otel_still_applies_to_running_tool(self):
        p = self.parse([asst(tu("Bash", "b1")), user(tr("b1"))])
        r = self.row(p, {"state": "tool", "ev": "tool_decision", "at": NOW, "tool": "Bash"})
        self.assertEqual(r["state"], "tool")


class AttentionRank(Patch):
    def test_ask_ranks_above_bgdone_and_is_red(self):
        rows = [{"sid": "a", "cwd": "/w/a", "project": "a", "state": "ask", "ageSec": 30},
                {"sid": "b", "cwd": "/w/b", "project": "b", "state": "wait", "ageSec": 200}]
        cf, att._conflicts = att._conflicts, (lambda rows, now: [])   # no live transcript scan
        self.addCleanup(setattr, att, "_conflicts", cf)
        out = att.attention(rows, [], read="", read_ids=[])["rows"]
        self.assertEqual(out[0]["sid"], "a")
        self.assertGreaterEqual(out[0]["score"], 90)     # 17-attention.js tone: >= 90 is 'err' (red)


if __name__ == "__main__":
    unittest.main()
