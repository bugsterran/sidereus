"""Attention wire contract: every signal carries a nested `v` (numbers, tool names, sid8, agent types) and an English
`why` equal to the MCP text agent_brief produced before `v` existed (expected strings recorded from that version).

No live data: read/read_ids are passed, failures stores and the conflict seam are private per test.
"""
import json
import threading
import unittest
from datetime import datetime

from tests import _clock
from tests._clock import NOW
from tests._load import sidereus

att = sidereus("attention")
fl = sidereus("failures")
cards_m = sidereus("cards")
ab = sidereus("agent_brief")


def iso(ts):
    return datetime.fromtimestamp(ts).isoformat()


def sess(sid="a", cwd="/w/p", state="run", age=10, **kw):
    r = {"sid": sid, "cwd": cwd, "project": "p", "branch": "main", "state": state, "ageSec": age}
    r.update(kw)
    return r


class Base(unittest.TestCase):
    def setUp(self):
        self._ev, self._lk, self._wa = fl._FAIL_EV, fl._FAIL_LOCK, fl._WRECK_AT
        fl._FAIL_EV, fl._FAIL_LOCK, fl._WRECK_AT = {}, threading.Lock(), {}
        att._TF.update(at=0.0, idx={})
        self._cf, att._conflicts = att._conflicts, (lambda rows, now: [])
        self._clk = _clock.frozen(att, fl, cards_m)
        self._clk.__enter__()

    def tearDown(self):
        self._clk.__exit__(None, None, None)
        fl._FAIL_EV, fl._FAIL_LOCK, fl._WRECK_AT = self._ev, self._lk, self._wa
        att._conflicts = self._cf
        att._TF.update(at=0.0, idx={})

    def rows(self, sessions, cards=()):
        att._TF.update(at=0.0, idx={})
        return att.attention(sessions, list(cards), read="", read_ids=[])["rows"]

    def sig(self, k, r, cards=()):
        out = [s for x in self.rows([r] if isinstance(r, dict) else r, cards) for s in x["sigs"] if s["k"] == k]
        self.assertEqual(len(out), 1, k)
        return out[0]

    def check(self, k, r, v, why, cards=()):
        s = self.sig(k, r, cards)
        self.assertEqual(s["v"], v)
        self.assertEqual(s["why"], why)
        self.assertEqual(ab._why_en(s), why)   # MCP reads the same text
        return s

    def tool_ev(self, sig, n=4):
        fl._FAIL_EV.setdefault("/t/x.jsonl", []).extend(
            {"at": NOW - 10 * (n - i), "kind": "tool", "cwd": "/w/p", "sig": sig} for i in range(n))


class TestRowSignals(Base):
    def test_gone(self):
        self.check("gone", sess(state="gone", goneWhy="silent"), {"q": True}, "Disconnected?")
        self.check("gone", sess(state="gone"), {"q": False}, "Disconnected")

    def test_ask_abort(self):
        self.check("ask", sess(state="ask"), {"kept": False}, "Asked a question")
        self.check("abort", sess(state="abort"), {}, "Interrupted — needs a new instruction")

    def test_ctx(self):
        self.check("ctx95", sess(ctx=96, win=100), {"pct": 96}, "Context 96% — auto-compact soon")
        self.check("ctx85", sess(ctx=88, win=100), {"pct": 88}, "Context 88%")

    def test_wreck_stall(self):
        self.check("wreck", sess(wreck=2), {"n": 2}, "Leftover edits in 2 files")
        self.check("stall", sess(state="tool", age=300, sub=[{"idle": 1830}]), {"m": 30},
                   "Subagent silent 30 min · parent waiting")

    def test_loop_tool_known_and_unknown(self):
        self.check("loop", sess(rep={"n": 8, "tool": "Bash"}), {"n": 8, "tool": "Bash"}, "Same call repeated 8× · Bash")
        self.check("loop", sess(rep={"n": 9}), {"n": 9, "tool": None}, "Same call repeated 9×")

    def test_mailidle(self):
        self.check("mailidle", sess(state="wait", mailIdle={"n": 3, "age": 720}), {"n": 3, "m": 12},
                   "Mail waiting · session idle · 3 message(s) · 12 min")

    def test_bglong(self):
        bl = {"n": 2, "long": 1, "max": 31 * 60, "at": int(NOW) - 31 * 60, "last": int(NOW) - 31 * 60}
        bi = {"n": 2, "idle": 1, "max": 1500, "at": int(NOW) - 1500, "last": int(NOW) - 1500}
        self.check("bglong", sess(state="tool", age=30, bgLong=bl), {"n": 1, "m": 31, "idle": 0},
                   "Long background 1 · longest 31 min")
        self.check("bglong", sess(state="tool", age=30, bgLong=bl, bgIdle=bi), {"n": 1, "m": 31, "idle": 1},
                   "Long background 1 · longest 31 min · 1 idle")

    def test_bgidle(self):
        self.check("bgidle", sess(state="tool", age=30, bgIdle={"n": 3, "idle": 2, "max": 1500}),
                   {"n": 3, "idle": 2, "m": 25}, "3 background shell(s) · 2 idle · longest 25 min")

    def test_done_seconds_and_minutes(self):
        self.check("done", sess(state="wait", age=20), {"s": 20}, "Done · waiting for input 20 s")
        self.check("done", sess(state="wait", age=150), {"s": 150}, "Done · waiting for input 2 min")

    def test_credit(self):
        self.check("credit", sess(credit={"lastAt": int(NOW) - 45}), {"s": 45}, "Spending credits · 45s ago")

    def test_blocked_unchanged(self):
        s = self.sig("blocked", sess(blocked="Bash waiting for approval"))
        self.assertEqual(s["why"], "Bash waiting for approval")
        self.assertNotIn("v", s)
        self.assertEqual(ab._why_en(s), "Waiting for permission")

    def test_row_tail_english(self):
        r = self.rows([sess(state="ask", ctx=96, win=100, wreck=1)])[0]
        self.assertEqual(r["why"], "Asked a question +2 more")


class TestCardSignals(Base):
    def test_ask_card_kept(self):
        c = {"kind": "ask", "cwd": "/w/p", "sid": "a", "project": "p", "at": iso(NOW - 120)}
        self.check("ask", sess(state="think", age=5, humanAt=int(NOW - 600)), {"kept": True},
                   "Asked a question · kept working since", [c])

    def test_fail_kind_and_count(self):
        one = [{"kind": "fcheck", "cwd": "/w/p", "at": iso(NOW - 60)}]
        self.check("fail", sess(age=400), {"kind": "fcheck", "n": 1}, "Cause needs a look", one)   # one alert names its kind
        three = [{"kind": k, "cwd": "/w/p", "at": iso(NOW - s)} for k, s in (("fcheck", 300), ("fcut", 200), ("fwreck", 100))]
        self.check("fail", sess(age=400), {"kind": "fwreck", "n": 3}, "Failure alert (3)", three)
        for k, want, why in (("fail", "fail", "Failure alert"), ("flimit", "flimit", "Stopped by limit"), ("fzzz", "fail", "Failure alert")):
            self.check("fail", sess(age=400), {"kind": want, "n": 1}, why,
                       [{"kind": k, "cwd": "/w/p", "at": iso(NOW - 60)}])

    def test_bgdone_sources(self):
        cs = [{"kind": "agent", "cwd": "/w/p", "at": iso(NOW - 100), "project": "p"},
              {"kind": "bgdone", "cwd": "/w/p", "at": iso(NOW - 50), "project": "p"}]
        self.check("bgdone", sess(age=200), {"n": 2, "src": ["bg", "agent"]}, "2 agent completion(s) unread", cs)
        self.check("bgdone", sess(age=200), {"n": 1, "src": ["agent"]}, "1 agent completion(s) unread", cs[:1])

    def test_toolfail_known_and_unknown_tool(self):
        self.tool_ev("InputValidationError: Grep failed due to x")
        self.check("toolfail", sess(), {"n": 4, "tool": "Grep"}, "Same error repeated 4× · Grep")
        fl._FAIL_EV.clear()
        self.tool_ev("Something odd happened")
        self.check("toolfail", sess(), {"n": 4, "tool": None}, "Same error repeated 4×")


class TestTieBreaks(Base):
    """Equal keys keep the pick made when tool/kind were Korean strings (codepoint order)."""

    def test_toolfail_tie_none_vs_named(self):
        self.tool_ev("InputValidationError: Grep failed due to x")
        fl._FAIL_EV.setdefault("/t/y.jsonl", []).extend(
            {"at": NOW - 10 * (4 - i), "kind": "tool", "cwd": "/w/p", "sig": "Something odd happened"} for i in range(4))
        att._TF.update(at=0.0, idx={})
        self.assertEqual(sorted(x[1] or "" for x in att._toolfail_idx(NOW)["/w/p"]), ["", "Grep"])
        self.check("toolfail", sess(), {"n": 4, "tool": None}, "Same error repeated 4×")   # unknown sorted above names
        self.assertEqual(att.attention([sess()], [], read="", read_ids=[])["rows"][0]["sigs"][0]["k"], "toolfail")

    def test_fail_same_at_picks_former_title_order(self):
        at = iso(NOW - 60)
        for ks, want in ((("flimit", "fcut"), "flimit"), (("fcheck", "fwreck", "fzzz"), "fcheck"), (("fail", "fwreck"), "fail")):
            cs = [{"kind": k, "cwd": "/w/p", "at": at} for k in ks]
            self.assertEqual(self.sig("fail", sess(age=400), cs)["v"], {"kind": want, "n": len(ks)})

    def test_bgdone_same_at_keys_bg_first(self):
        at = iso(NOW - 50)
        cs = [{"kind": "agent", "cwd": "/w/p", "at": at, "project": "p"},
              {"kind": "bgdone", "cwd": "/w/p", "at": at, "project": "p"}]
        self.assertEqual(self.sig("bgdone", sess(age=200), cs)["keys"], ["%s|bgdone|p" % at, "%s|agent|p" % at])

    def test_attention_source_has_no_hangul(self):
        # English-source module: Korean lives only in I18N.ko, so even a sort key must not be a Korean literal.
        import re
        with open(att.__file__, encoding="utf-8") as f:
            self.assertEqual(re.findall(r"[가-힣]+", f.read()), [])


class TestConflict(Base):
    def go(self, g, sids):
        att._conflicts = lambda rows, now: [g]
        return self.rows([sess(s, state="tool") for s in sids])

    def test_sessions(self):
        g = {"sids": ["aaaaaaaa-1", "bbbbbbbb-2"], "files": ["/r/a", "/r/b"], "since": NOW - 60, "last": NOW - 5,
             "by": "bbbbbbbb-2"}
        s = [x for x in self.go(g, ["aaaaaaaa-1", "bbbbbbbb-2"])[0]["sigs"] if x["k"] == "conflict"][0]
        self.assertEqual(s["v"], {"files": 2, "sids": ["aaaaaaaa", "bbbbbbbb"]})
        self.assertEqual(s["why"], "Conflict risk · 2 file(s) · sessions aaaaaaaa, bbbbbbbb")

    def test_subagents_main_is_null(self):
        g = {"sids": ["aaaaaaaa-1"], "labs": [None, "Explore"], "files": ["/r/a"], "since": NOW - 60, "last": NOW - 5,
             "by": "aaaaaaaa-1"}
        s = [x for x in self.go(g, ["aaaaaaaa-1"])[0]["sigs"] if x["k"] == "conflict"][0]
        self.assertEqual(s["v"], {"files": 1, "labs": [None, "Explore"]})
        self.assertEqual(s["why"], "Conflict risk · 1 file(s) · subagents main, Explore")
        self.assertEqual(ab._why_en(s), s["why"])


class TestMetadataOnly(Base):
    SECRET = "TOPSECRET-task-text"

    def test_v_holds_no_text_and_no_hangul(self):
        r = sess(state="ask", ctx=96, win=100, wreck=1, rep={"n": 9}, task=self.SECRET, title=self.SECRET)
        cs = [{"kind": "fcheck", "cwd": "/w/p", "at": iso(NOW - 30), "text": self.SECRET, "project": "p"},
              {"kind": "agent", "cwd": "/w/p", "at": iso(NOW - 20), "text": self.SECRET, "project": "p"}]
        self.tool_ev("### Error: " + self.SECRET)
        blob = json.dumps(self.rows([r], cs), ensure_ascii=False)
        self.assertNotIn(self.SECRET, blob)
        self.assertFalse(any("가" <= ch <= "힣" for ch in blob), blob)


if __name__ == "__main__":
    unittest.main()
