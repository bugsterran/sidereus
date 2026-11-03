"""R1-R3: a human response in the session clears «Question waiting» / «Done · waiting for input» /
«Background done» / «Background idle» without a click; an unanswered question stays (metadata only, no live data)."""
import unittest

from tests._clock import NOW
from tests.test_attention_replay_r4 import (Base, T, ask_turn, att, bang, bang_out, call, card, notify, prompt,
                                           result, row_of, say, scan, turn_end)


class Response(Base):
    def test_r1_bang_after_ask_clears_row_and_card(self):
        lines = ask_turn(T) + [bang(T + 300), bang_out(T + 301)]
        t = scan(lines)
        self.assertFalse(t["shp"]["ask"])
        self.assertEqual(t["humanAt"], T + 300)
        self.assertEqual(t["task"], "x")            # the command text never becomes the label
        r = row_of(lines)
        self.assertEqual(r["state"], "wait")
        self.assertEqual(self.kinds(r, [card("ask", T + 21)]), [])

    def test_r1_bang_stdout_alone_not_human(self):
        t = scan(ask_turn(T) + [bang_out(T + 300)])
        self.assertTrue(t["shp"]["ask"])
        self.assertEqual(t["humanAt"], T)
        self.assertIn("ask", self.kinds(row_of(ask_turn(T) + [bang_out(T + 300)])))

    def test_r1_bang_keeps_open_picker(self):
        # an AskUserQuestion picker is answered only by its tool_result: a `!` line beside it leaves it open
        lines = [prompt(T), call(T + 20, "AskUserQuestion", "toolu_q"), bang(T + 300)]
        self.assertEqual(row_of(lines)["state"], "ask")

    def test_r1_picker_answer_clears(self):
        lines = [prompt(T), call(T + 20, "AskUserQuestion", "toolu_q"), result(T + 300, "toolu_q")]
        r = row_of(lines)
        self.assertEqual(r["humanAt"], T + 300)
        self.assertEqual(self.kinds(r, [card("ask", T + 20)]), [])

    def test_r1_permission_allow_and_deny_clear_blocked(self):
        before = [prompt(T), call(T + 20, "Bash", "toolu_b")]
        self.assertIn("blocked", self.kinds(row_of(before, marker=T + 21)))
        for err in (False, True):
            with self.subTest(deny=err):
                r = row_of(before + [result(T + 300, "toolu_b", err=err)], marker=T + 21)   # marker < actAt
                self.assertNotIn("blocked", r)
                self.assertNotIn("blocked", self.kinds(r))

    def test_r3_done_cleared_by_bang(self):
        done = [prompt(T), say(T + 20), turn_end(T + 21)]
        self.assertEqual(self.kinds(row_of(done)), ["done"])
        r = row_of(done + [bang(T + 300), bang_out(T + 301)])
        self.assertEqual(r["state"], "wait")         # a `!` line is not activity: the row stays `wait` with an old t0
        self.assertEqual(self.kinds(r), [])

    def test_r3_bgdone_cleared_by_prompt_within_grace(self):
        c = card("bgdone", int(NOW) - 30)
        r = {"sid": c["sid"], "cwd": c["cwd"], "project": "p", "state": "think", "ageSec": 20}
        self.assertEqual(self.kinds(r, [c]), ["bgdone"])                       # inside the grace, no reply: holds
        self.assertEqual(self.kinds(dict(r, humanAt=int(NOW) - 20), [c]), [])  # typed after the completion
        self.assertEqual(self.kinds(dict(r, humanAt=int(NOW) - 40), [c]), ["bgdone"])   # typed before it

    def test_r3_bgidle_cleared_by_later_human(self):
        # one shell: last output NOW-1800, idle from NOW-900 (mtime + BG_IDLE_S)
        bi = {"n": 1, "idle": 1, "max": 1800, "at": int(NOW) - 1800, "last": int(NOW) - 1800}
        r = {"sid": "a", "cwd": "/w/p", "state": "tool", "ageSec": 30, "bgIdle": bi}
        self.assertEqual(self.kinds(r), ["bgidle"])
        self.assertEqual(self.kinds(dict(r, humanAt=int(NOW) - 1000)), ["bgidle"])   # before the idle onset: shows
        self.assertEqual(self.kinds(dict(r, humanAt=int(NOW) - 60)), [])             # after the onset: hidden
        # two shells: B idles from NOW-300, after the prompt at NOW-600 -> shows; a prompt after B's onset hides it
        two = dict(bi, n=2, idle=2, at=int(NOW) - 2000, last=int(NOW) - 1200)
        self.assertEqual(self.kinds(dict(r, bgIdle=two, humanAt=int(NOW) - 600)), ["bgidle"])
        self.assertEqual(self.kinds(dict(r, bgIdle=two, humanAt=int(NOW) - 60)), [])
        # an old snapshot without `last` falls back to `at`
        old = {"n": 1, "idle": 1, "max": 1800, "at": int(NOW) - 1800}
        self.assertEqual(self.kinds(dict(r, bgIdle=old, humanAt=int(NOW) - 1000)), ["bgidle"])
        self.assertEqual(self.kinds(dict(r, bgIdle=old, humanAt=int(NOW) - 60)), [])

    def test_r2_ask_stays_without_reply(self):
        lines = ask_turn(T) + [notify(T + 200)]
        for extra in ({}, {"sub": [{"idle": 0}]}, {"bgs": [{}]}, {"sub": [{"idle": 0}], "bgs": [{}]}):
            with self.subTest(**{k: True for k in extra}):
                self.assertIn("ask", self.kinds(row_of(lines, **extra), [card("ask", T + 21)]))
        # humanAt 0/missing is unknown, never a reply
        for ha in (0, None, True):
            r = {"sid": "a", "cwd": "/w/p", "state": "wait", "ageSec": 100, "humanAt": ha}
            self.assertEqual(self.kinds(r), ["done"])
            self.assertFalse(att._human_after(r, 0))


if __name__ == "__main__":
    unittest.main()
