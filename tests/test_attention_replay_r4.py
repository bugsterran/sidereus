"""R4: replay of transcript shapes (metadata only) through parse._scan_tail -> row -> attention().

Each case is a synthetic JSONL tail shaped like a real Claude Code transcript (uuid session ids, `x`/`?`
placeholder text, empty tool inputs/results). No live files, clock or network: the clock is frozen, timestamps
are parsed TZ-independently, conflicts and permission markers are patched on their owning modules.
"""
import calendar
import json
import threading
import time
import unittest
from unittest import mock

from tests import _clock
from tests._clock import NOW
from tests._load import sidereus

att = sidereus("attention")
parse = sidereus("parse")
notes = sidereus("notes")
pm = sidereus("perm_marks")
fl = sidereus("failures")
cards_mod = sidereus("cards")

SID = "0b8a7c52-3f1e-4d2a-9c61-5e7f0a1b2c3d"
CWD = "/w/p"
T = int(NOW) - 600            # base time of every case


def ts(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))


def _ts_utc(d, fallback):
    """TZ-independent stand-in for transcript._line_ts (same contract: the line's own time or fallback)."""
    s = d.get("timestamp")
    try:
        return calendar.timegm(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S"))
    except (TypeError, ValueError):
        return fallback


def _ln(kind, t, content=None, **kw):
    d = {"type": kind, "sessionId": SID, "cwd": CWD, "timestamp": ts(t)}
    if content is not None:
        d["message"] = {"role": "user" if kind == "user" else "assistant", "content": content}
    d.update(kw)
    return d


def prompt(t):
    return _ln("user", t, "x")


def bang(t):
    return _ln("user", t, "<bash-input></bash-input>")


def bang_out(t):
    return _ln("user", t, "<bash-stdout></bash-stdout><bash-stderr></bash-stderr>")


def notify(t):
    return _ln("user", t, "<task-notification></task-notification>")


def say(t, text="x"):
    d = _ln("assistant", t, [{"type": "text", "text": text}])
    d["message"].update(id="msg_%d" % t, model="m", stop_reason="end_turn",
                        usage={"input_tokens": 1, "cache_read_input_tokens": 1, "cache_creation_input_tokens": 1})
    return d


def turn_end(t):
    return {"type": "system", "subtype": "turn_duration", "sessionId": SID, "cwd": CWD, "timestamp": ts(t)}


def call(t, name, tid):
    d = _ln("assistant", t, [{"type": "tool_use", "id": tid, "name": name, "input": {}}])
    d["message"].update(id="msg_%d" % t, model="m", stop_reason="tool_use")
    return d


def result(t, tid, err=False):
    b = {"type": "tool_result", "tool_use_id": tid, "content": ""}
    if err:
        b["is_error"] = True
    return _ln("user", t, [b])


def ask_turn(t):
    """A typed prompt, then a turn that ends with a question."""
    return [prompt(t), say(t + 20, "?"), turn_end(t + 21)]


def scan(lines):
    """parse._scan_tail on the JSONL rows (TZ-independent timestamps)."""
    rows = [json.dumps(d) for d in lines]
    with mock.patch.object(parse, "_line_ts", _ts_utc):
        t = parse._scan_tail(rows)
    t["askTool"] = parse._ask_pending(rows, t["shp"])
    return t


def row_of(lines, marker=None, **extra):
    """Session row as sessions.py assembles it (state · ageSec · humanAt · tailAt · blocked)."""
    t = scan(lines)
    shp = t["shp"]
    st = notes._sess_state(CWD, shp["shape"], {CWD}, shp["ask"], shp["abort"], shp["err"], SID, t["askTool"])
    r = {"sid": SID, "cwd": CWD, "project": "p", "branch": "main", "state": st,
         "ageSec": int(NOW - t["actAt"]), "humanAt": int(t["humanAt"]), "tailAt": int(t["tailAt"])}
    if marker is not None:
        with mock.patch.object(pm, "_read", lambda name: {"sid": SID, "t": marker}):
            mt = pm._mark_t(SID, t["actAt"], NOW)
        if mt:
            r.update(blocked="Bash", blockedAt=int(mt))
    r.update(extra)
    return r


def card(kind, t):
    return {"kind": kind, "sid": SID, "cwd": CWD, "project": "p", "at": ts(t)}


class Base(unittest.TestCase):
    def setUp(self):
        self._ev, self._lk, self._wa = fl._FAIL_EV, fl._FAIL_LOCK, fl._WRECK_AT
        fl._FAIL_EV, fl._FAIL_LOCK, fl._WRECK_AT = {}, threading.Lock(), {}
        att._TF.update(at=0.0, idx={})
        p = mock.patch.object(att, "_conflicts", lambda rows, now: [])   # no live transcript scan
        p.start()
        self.addCleanup(p.stop)
        self._clk = _clock.frozen(att, fl, cards_mod, pm)
        self._clk.__enter__()

    def tearDown(self):
        self._clk.__exit__(None, None, None)
        fl._FAIL_EV, fl._FAIL_LOCK, fl._WRECK_AT = self._ev, self._lk, self._wa
        att._TF.update(at=0.0, idx={})

    def kinds(self, r, cards=()):
        att._TF.update(at=0.0, idx={})
        rows = att.attention([r], list(cards), read="", read_ids=[])["rows"]
        return [s["k"] for s in rows[0]["sigs"]] if rows else []


class Replay(Base):
    def test_r4_typed_prompt_clears_question(self):
        before = ask_turn(T)
        self.assertIn("ask", self.kinds(row_of(before), [card("ask", T + 21)]))
        self.assertEqual(self.kinds(row_of(before + [prompt(T + 300)]), [card("ask", T + 21)]), [])

    def test_r4_bang_command_clears_question(self):
        lines = ask_turn(T) + [bang(T + 300), bang_out(T + 301)]
        self.assertEqual(self.kinds(row_of(lines), [card("ask", T + 21)]), [])

    def test_r4_picker_answer_clears_question(self):
        before = [prompt(T), call(T + 20, "AskUserQuestion", "toolu_q")]
        self.assertIn("ask", self.kinds(row_of(before)))
        after = before + [result(T + 300, "toolu_q")]
        self.assertEqual(self.kinds(row_of(after), [card("ask", T + 20)]), [])

    def test_r4_permission_allow_clears_blocked(self):
        before = [prompt(T), call(T + 20, "Bash", "toolu_b")]
        self.assertIn("blocked", self.kinds(row_of(before, marker=T + 21)))
        self.assertEqual(self.kinds(row_of(before + [result(T + 300, "toolu_b")], marker=T + 21)), [])

    def test_r4_permission_deny_clears_blocked(self):
        before = [prompt(T), call(T + 20, "Bash", "toolu_b")]
        after = before + [result(T + 300, "toolu_b", err=True)]
        self.assertNotIn("blocked", self.kinds(row_of(after, marker=T + 21)))

    def test_r4_done_then_typed_clears_done(self):
        done = [prompt(T), say(T + 20), turn_end(T + 21)]
        self.assertEqual(self.kinds(row_of(done)), ["done"])
        self.assertEqual(self.kinds(row_of(done + [prompt(T + 400)])), [])

    def test_r4_bgdone_then_typed_clears_card(self):
        # typed 10 s after the completion, polled 20 s later: inside the 60 s resume grace
        lines = [prompt(T), call(T + 20, "Bash", "toolu_b"), result(T + 21, "toolu_b"), prompt(int(NOW) - 20)]
        self.assertEqual(self.kinds(row_of(lines), [card("bgdone", int(NOW) - 30)]), [])

    def test_r4_bgidle_then_typed_clears(self):
        # shell output last at T-1500 -> idle from T-600; prompts at T-700 (before) and T (after the onset)
        bi = {"n": 1, "idle": 1, "max": 2100, "at": T - 1500, "last": T - 1500}
        before = [prompt(T - 700), call(T + 400, "Bash", "toolu_b")]
        self.assertEqual(self.kinds(row_of(before, bgIdle=bi, bgs=[{}])), ["bgidle"])
        after = [prompt(T - 700), prompt(T), call(T + 400, "Bash", "toolu_b")]
        self.assertEqual(self.kinds(row_of(after, bgIdle=bi, bgs=[{}])), [])

    def test_r4_question_holds_without_reply(self):
        # end-of-turn question while a background job and a subagent run; later lines are harness echoes only
        lines = ask_turn(T) + [notify(T + 200), bang_out(T + 210)]
        self.assertIn("ask", self.kinds(row_of(lines, sub=[{"idle": 0}], bgs=[{}])))
        # a hand-back wakes the session (row leaves `ask`): the card still holds
        woke = ask_turn(T) + [notify(T + 200), call(T + 210, "Read", "toolu_r")]
        self.assertIn("ask", self.kinds(row_of(woke, bgs=[{}]), [card("ask", T + 21)]))

    def test_r4_question_holds_when_pushed_out_of_tail(self):
        # only wake-ups after the question: the question and every human line left the tail (humanAt 0, tailAt > card)
        self.assertEqual(sorted(self.kinds(row_of([say(T + 200), turn_end(T + 201)]), [card("ask", T + 21)])),
                         ["ask", "done"])


def _placeholder_only(obj):
    """Rule-1 guard (as tests/test_state_replay.py): text only "" / x / ?, empty shell tags, tool input {}, results empty."""
    msg = obj.get("message") if isinstance(obj, dict) else None
    c = (msg or {}).get("content")
    if isinstance(c, str):
        return c in ("", "x", "<bash-input></bash-input>", "<bash-stdout></bash-stdout><bash-stderr></bash-stderr>",
                     "<task-notification></task-notification>")
    for b in c or []:
        if not isinstance(b, dict):
            return False
        t = b.get("type")
        if t == "text" and b.get("text") not in ("", "x", "?"):
            return False
        if t == "thinking" and b.get("thinking"):
            return False
        if t == "tool_use" and b.get("input") != {}:
            return False
        if t == "tool_result" and b.get("content") not in (None, "", []):
            return False
    return True


class Fixtures(unittest.TestCase):
    def test_replay_fixtures_metadata_only(self):
        lines = ask_turn(T) + [bang(T), bang_out(T), notify(T), say(T), turn_end(T), call(T, "AskUserQuestion", "q"),
                               result(T, "q"), result(T, "q", err=True)]
        for d in lines:
            self.assertTrue(_placeholder_only(d), d)
        self.assertFalse(_placeholder_only(_ln("user", T, "<bash-input>rm</bash-input>")))


if __name__ == "__main__":
    unittest.main()
