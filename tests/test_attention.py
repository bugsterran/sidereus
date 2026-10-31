"""Deterministic tests for sidereus/attention.py and sidereus/parse.py:_tail_rep.

No live data is read: `read`/`read_ids` are always passed so cards_read() never touches disk, and
failures._FAIL_EV/_FAIL_LOCK are swapped for private objects per test.
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
parse = sidereus("parse")
cards = sidereus("cards")

ROW_KEYS = {"sid", "cwd", "project", "branch", "score", "why", "since", "sigs"}
SIG_KEYS = {"k", "why", "pts", "since"}


def iso(ts):
    return datetime.fromtimestamp(ts).isoformat()


def sess(sid, cwd="/w/p", state="run", age=10, **kw):
    r = {"sid": sid, "cwd": cwd, "project": "p", "branch": "main", "state": state, "ageSec": age}
    r.update(kw)
    return r


class Base(unittest.TestCase):
    def setUp(self):
        # Private failure store; restored after each test. Reset the 30s toolfail cache.
        self._ev, self._lk, self._wa = fl._FAIL_EV, fl._FAIL_LOCK, fl._WRECK_AT
        fl._FAIL_EV, fl._FAIL_LOCK, fl._WRECK_AT = {}, threading.Lock(), {}
        att._TF.update(at=0.0, idx={})
        self._cf, att._conflicts = att._conflicts, (lambda rows, now: [])   # no live transcript scan
        self._clk = _clock.frozen(att, fl, cards)   # card windows and ages are computed against _clock.NOW
        self._clk.__enter__()

    def tearDown(self):
        self._clk.__exit__(None, None, None)
        fl._FAIL_EV, fl._FAIL_LOCK, fl._WRECK_AT = self._ev, self._lk, self._wa
        att._conflicts = self._cf
        att._TF.update(at=0.0, idx={})

    def run_att(self, sessions, cards=()):
        att._TF.update(at=0.0, idx={})
        return att.attention(sessions, list(cards), read="", read_ids=[])["rows"]

    def one(self, r, cards=()):
        rows = self.run_att([r], cards)
        return rows[0] if rows else None

    def kinds(self, r, cards=()):
        row = self.one(r, cards)
        return [s["k"] for s in row["sigs"]] if row else []

    def tool_ev(self, cwd, sig, ats, tp="/t/x.jsonl"):
        fl._FAIL_EV.setdefault(tp, []).extend(
            {"at": a, "kind": "tool", "cwd": cwd, "sig": sig} for a in sorted(ats))


class TestPoints(Base):
    def test_point_table(self):
        self.assertEqual(att.ATT_PTS, {"blocked": 100, "ask": 90, "conflict": 85, "mailidle": 75, "abort": 70, "ctx95": 65, "fail": 60,
                                       "wreck": 60, "stall": 55, "loop": 50, "toolfail": 45, "bgidle": 30,
                                       "ctx85": 25, "done": 20, "bgdone": 15})

    def test_thresholds(self):
        self.assertEqual((att.ATT_FAIL_CARD_S, att.ATT_STALL_S, att.ATT_LOOP_N, att.ATT_TOOLFAIL_N,
                          att.ATT_TOOLFAIL_S, att.ATT_TOOLFAIL_RECENT_S, att.ATT_DONE_S),
                         (1800, 1800, 8, 4, 600, 180, (15, 7200)))

    def test_ranking_across_sessions(self):
        rows = [
            sess("bg", state="run", age=5),
            sess("done", cwd="/w/done", state="wait", age=600),
            sess("ctx85", cwd="/w/c85", ctx=86, win=100),
            sess("loop", cwd="/w/loop", rep={"n": 9, "tool": "Bash"}),
            sess("stall", cwd="/w/st", state="tool", age=400, sub=[{"idle": 2000}]),
            sess("wreck", cwd="/w/wr", wreck=2),
            sess("ctx95", cwd="/w/c95", ctx=96, win=100),
            sess("abort", cwd="/w/ab", state="abort"),
            sess("ask", cwd="/w/ask", state="ask"),
            sess("blocked", cwd="/w/bl", blocked="권한 대기"),
        ]
        cards = [{"kind": "bgdone", "cwd": "/w/p", "at": iso(NOW - 60), "project": "p"}]
        out = self.run_att(rows, cards)
        self.assertEqual([r["sid"] for r in out],
                         ["blocked", "ask", "abort", "ctx95", "wreck", "stall", "loop", "ctx85", "done", "bg"])
        self.assertEqual([r["score"] for r in out], [100, 90, 70, 65, 60, 55, 50, 25, 20, 15])

    def test_extra_signal_adds_five(self):
        row = self.one(sess("a", state="ask", ctx=96, win=100, wreck=1))
        self.assertEqual(row["score"], 90 + 5 * 2)
        self.assertEqual(row["sigs"][0]["k"], "ask")
        self.assertTrue(row["why"].endswith(" 외 2"))

    def test_no_signal_no_row(self):
        self.assertEqual(self.run_att([sess("a")]), [])

    def test_ties_oldest_since_first(self):
        out = self.run_att([sess("new", cwd="/a", state="ask", age=30),
                            sess("old", cwd="/b", state="ask", age=900)])
        self.assertEqual([r["sid"] for r in out], ["old", "new"])
        self.assertLess(out[0]["since"], out[1]["since"])

    def test_non_dict_rows_ignored(self):
        self.assertEqual(len(self.run_att([None, "x", sess("a", state="ask")])), 1)


class TestCtx(Base):
    def test_win_zero_no_signal(self):
        self.assertEqual(self.kinds(sess("a", ctx=999999, win=0)), [])

    def test_ctx_bands(self):
        self.assertEqual(self.kinds(sess("a", ctx=84, win=100)), [])
        self.assertEqual(self.kinds(sess("a", ctx=85, win=100)), ["ctx85"])
        self.assertEqual(self.kinds(sess("a", ctx=95, win=100)), ["ctx95"])

    def test_ctx_ignored_when_done(self):
        self.assertEqual(self.kinds(sess("a", state="done", ctx=99, win=100)), [])


class TestDone(Base):
    def test_window_bounds(self):
        self.assertEqual(self.kinds(sess("a", state="wait", age=10)), [])
        self.assertEqual(self.kinds(sess("a", state="wait", age=14)), [])
        self.assertEqual(self.kinds(sess("a", state="wait", age=15)), ["done"])
        self.assertEqual(self.kinds(sess("a", state="wait", age=20)), ["done"])
        self.assertEqual(self.kinds(sess("a", state="wait", age=7200)), ["done"])
        self.assertEqual(self.kinds(sess("a", state="wait", age=7201)), [])

    def test_not_while_working(self):
        for st in ("think", "tool"):
            self.assertNotIn("done", self.kinds(sess("a", state=st, age=600)))

    def test_label_under_a_minute(self):
        why = self.one(sess("a", state="wait", age=20))["sigs"][0]["why"]
        self.assertNotIn("0분", why)
        self.assertIn("20초", why)
        self.assertIn("2분", self.one(sess("a", state="wait", age=150))["sigs"][0]["why"])

    def test_not_with_sub_or_bgs(self):
        self.assertNotIn("done", self.kinds(sess("a", state="wait", age=600, sub=[{"idle": 1}])))
        self.assertEqual(self.kinds(sess("a", state="wait", age=600, bgs=[{"id": "b"}])), [])


class TestMailIdle(Base):
    def test_R3_mailidle_sig_pts(self):
        row = self.one(sess("a", state="wait", age=10, mailIdle={"n": 3, "age": 720}))  # under the done floor: mailidle alone
        sg = [s for s in row["sigs"] if s["k"] == "mailidle"][0]
        self.assertEqual((sg["pts"], row["score"]), (75, 75))
        self.assertEqual(sg["why"], "메일 3통 대기 · 세션 쉼 12분")
        self.assertEqual(set(sg), SIG_KEYS)
        self.assertEqual(self.kinds(sess("a", state="tool", age=30, mailIdle={"n": 3, "age": 720})), [])


class TestBgIdle(Base):
    def test_R2_bgidle_sig(self):
        bi = {"n": 3, "idle": 2, "max": 1500}
        row = self.one(sess("a", state="tool", age=30, bgs=[{}, {}, {}], bgIdle=bi))
        sg = [s for s in row["sigs"] if s["k"] == "bgidle"][0]
        self.assertEqual((sg["pts"], sg["why"], sg["since"]), (30, "백그라운드 셸 3개 · 무출력 2개 · 최장 25분", int(NOW) - 1500))
        self.assertEqual(set(sg), SIG_KEYS)
        for st in ("gone", "done"):
            self.assertNotIn("bgidle", self.kinds(sess("a", state=st, age=30, bgIdle=bi)))
        self.assertNotIn("bgidle", self.kinds(sess("a", state="tool", age=30, bgIdle={"n": 2, "idle": 0, "max": 0})))

    def test_R4_old_shell_still_counts(self):
        row = self.one(sess("a", state="wait", age=10, bgIdle={"n": 1, "idle": 1, "max": 3 * 3600}))
        self.assertIn("최장 180분", [s for s in row["sigs"] if s["k"] == "bgidle"][0]["why"])


class TestStall(Base):
    def test_needs_parent_waiting_5min(self):
        sub = [{"idle": 1800}]
        self.assertEqual(self.kinds(sess("a", state="tool", age=299, sub=sub)), [])
        row = self.one(sess("a", state="tool", age=300, sub=sub))
        self.assertEqual([s["k"] for s in row["sigs"]], ["stall"])
        self.assertIn("30분", row["why"])

    def test_sub_idle_below_threshold(self):
        self.assertEqual(self.kinds(sess("a", state="tool", age=900, sub=[{"idle": 1799}])), [])

    def test_parent_running_no_stall(self):
        self.assertEqual(self.kinds(sess("a", state="run", age=900, sub=[{"idle": 5000}])), [])


class TestCards(Base):
    def test_fail_card_by_cwd_prefix(self):
        now = NOW
        c = {"kind": "fcheck", "cwd": "/w/p/sub/dir", "at": iso(now - 60)}
        row = self.one(sess("a", cwd="/w/p"), [c])
        self.assertEqual(row["sigs"][0]["k"], "fail")
        self.assertEqual(row["why"], "원인 확인 필요")

    def test_prefix_is_path_boundary(self):
        c = {"kind": "fcheck", "cwd": "/w/pother", "at": iso(NOW - 60)}
        self.assertIsNone(self.one(sess("a", cwd="/w/p"), [c]))

    def test_fail_card_expires_after_30min(self):
        c = {"kind": "flimit", "cwd": "/w/p", "at": iso(NOW - 1900)}
        self.assertIsNone(self.one(sess("a", cwd="/w/p"), [c]))

    def test_fail_attached_to_most_recent_session(self):
        c = {"kind": "fcut", "cwd": "/w/p", "at": iso(NOW - 60)}
        out = self.run_att([sess("old", cwd="/w/p", age=500), sess("new", cwd="/w/p", age=20)], [c])
        self.assertEqual([r["sid"] for r in out], ["new"])

    def test_same_kind_cards_fold(self):
        now = NOW
        cards = [{"kind": k, "cwd": "/w/p", "at": iso(now - s)} for k, s in
                 (("fcheck", 300), ("fcut", 200), ("fwreck", 100))]
        row = self.one(sess("a", age=400), cards)     # last activity before every card
        self.assertEqual([s["k"] for s in row["sigs"]], ["fail"])
        self.assertEqual(row["score"], 60)
        self.assertEqual(row["why"], "반쯤 고친 파일 등 3건")
        self.assertEqual(row["since"], int(datetime.fromisoformat(iso(now - 300)).timestamp()))

    def test_bgdone_fold_and_read_filter(self):
        now = NOW
        a1, a2 = iso(now - 100), iso(now - 50)
        cards = [{"kind": "agent", "cwd": "/w/p", "at": a1, "project": "p"},
                 {"kind": "bgdone", "cwd": "/w/p", "at": a2, "project": "p"}]
        row = self.one(sess("a", age=200), cards)
        self.assertEqual([s["k"] for s in row["sigs"]], ["bgdone"])
        self.assertEqual(row["why"], "백그라운드·서브에이전트 완료 2건 미확인")
        # read watermark hides both; read_ids hides one
        rows = att.attention([sess("a", age=200)], cards, read=a2, read_ids=[])["rows"]
        self.assertEqual(rows, [])
        rows = att.attention([sess("a", age=200)], cards, read="", read_ids=["%s|agent|p" % a1])["rows"]
        self.assertIn("1건", rows[0]["why"])

    def test_bgdone_keys_round_trip_through_mark_cards_read(self):
        # The row's «Seen» posts sig.keys to /api/cards/read -> mark_cards_read; the next attention() has no bgdone.
        import os, tempfile
        cards_mod = sidereus("cards")
        now = NOW
        a1, a2 = iso(now - 100), iso(now - 50)
        cards = [{"kind": "agent", "cwd": "/w/p", "at": a1, "project": "p"},
                 {"kind": "agent", "cwd": "/w/p", "at": a2, "project": "p"}]
        row = self.one(sess("a", age=200), cards)
        keys = row["sigs"][0]["keys"]
        self.assertEqual(sorted(keys), ["%s|agent|p" % a1, "%s|agent|p" % a2])
        d = tempfile.mkdtemp()
        old = cards_mod.READ_IDS, cards_mod.READ_MARK
        cards_mod.READ_IDS, cards_mod.READ_MARK = os.path.join(d, "cards-read-ids.txt"), os.path.join(d, "cards-read.txt")
        try:
            cards_mod.mark_cards_read(keys)
            rows = att.attention([sess("a", age=200)], cards, read="", read_ids=cards_mod.cards_read_ids())["rows"]
        finally:
            cards_mod.READ_IDS, cards_mod.READ_MARK = old
        self.assertEqual(rows, [])


class TestBgdoneResume(Base):
    """bgdone cards clear once the owning session carries on past the completion (as the failure family)."""

    def card(self, ago, kind="agent", **kw):
        c = {"kind": kind, "cwd": "/w/p", "at": iso(NOW - ago), "project": "p"}
        c.update(kw)
        return c

    def test_R1_later_activity_clears(self):
        self.assertIsNone(self.one(sess("a", age=100), [self.card(600), self.card(500, "bgdone", sid="a")]))

    def test_R1_only_resumed_cards_dropped(self):
        row = self.one(sess("a", age=300), [self.card(600), self.card(250, "bgdone")])
        self.assertEqual(row["sigs"][0]["why"], "백그라운드 완료 1건 미확인")

    def test_R2_no_later_activity_stays(self):
        self.assertEqual(self.kinds(sess("a", age=900), [self.card(600)]), ["bgdone"])
        self.assertEqual(self.kinds(sess("a", age=100), [self.card(150)]), ["bgdone"])   # within grace

    def test_R3_other_sid_not_cleared(self):
        self.assertEqual(self.kinds(sess("a", age=5), [self.card(600, sid="zz")]), ["bgdone"])


class TestResume(Base):
    """★2026-09-28: failure-card signals clear once the same session carries on past the failure."""

    def card(self, ago, **kw):
        c = {"kind": "fcut", "cwd": "/w/p", "at": iso(NOW - ago)}
        c.update(kw)
        return c

    def test_later_activity_clears(self):
        self.assertIsNone(self.one(sess("a", age=100), [self.card(600)]))

    def test_no_later_activity_stays_until_cap(self):
        self.assertEqual(self.kinds(sess("a", age=1700), [self.card(1600)]), ["fail"])
        self.assertIsNone(self.one(sess("a", age=1900), [self.card(1850)]))

    def test_activity_before_card_stays(self):
        self.assertEqual(self.kinds(sess("a", age=900), [self.card(600)]), ["fail"])

    def test_within_grace_stays(self):
        self.assertEqual(self.kinds(sess("a", age=100), [self.card(150)]), ["fail"])

    def test_sleep_gap_then_resume_clears(self):
        # failure 3000s ago, Mac asleep, card stamped on wake 300s ago; session worked 1000s ago (pre-sleep) and again now
        now = NOW
        fl._FAIL_EV["/t/p.jsonl"] = [{"at": now - 3000, "kind": "agent", "tid": "t1", "cwd": "/w/p"}]
        self.assertEqual(self.kinds(sess("a", age=1000), [self.card(300, tid="t1")]), [])
        self.assertIsNone(self.one(sess("a", age=5), [self.card(300, tid="t1")]))

    def test_sleep_gap_no_resume_stays(self):
        now = NOW
        fl._FAIL_EV["/t/p.jsonl"] = [{"at": now - 3000, "kind": "agent", "tid": "t1", "cwd": "/w/p"}]
        self.assertEqual(self.kinds(sess("a", age=4000), [self.card(300, tid="t1")]), ["fail"])

    def test_other_session_card_not_cleared(self):
        self.assertEqual(self.kinds(sess("a", age=5), [self.card(600, sid="zz")]), ["fail"])

    def test_wreck_clears_after_activity(self):
        now = NOW
        fl._WRECK_AT["/w/p"] = now - 600
        self.assertEqual(self.kinds(sess("a", age=900, wreck=2)), ["wreck"])
        self.assertEqual(self.kinds(sess("a", age=100, wreck=2)), [])
        fl._WRECK_AT.clear()                  # unknown time -> old behavior (stays while dirty)
        self.assertEqual(self.kinds(sess("a", age=100, wreck=2)), ["wreck"])

    def test_blocked_ask_unaffected(self):
        cards = [self.card(600)]
        self.assertEqual(self.kinds(sess("a", age=5, blocked="권한 대기"), cards), ["blocked"])
        self.assertEqual(self.kinds(sess("a", state="ask", age=5), cards), ["ask"])


class TestToolfail(Base):
    def test_benign_list(self):
        for p in ("Exit code", "File does not exist", "String to replace not found", "Cancelled"):
            self.assertIn(p, att._TF_BENIGN)

    def test_five_distinct_benign_none(self):
        now = NOW
        for i, sg in enumerate(("Exit code 1", "File does not exist.", "EISDIR: x", "Cancelled", "Blocked: sleep")):
            self.tool_ev("/w/p", sg, [now - 10 - i])
        self.assertEqual(att._toolfail_idx(now), {})

    def test_many_identical_benign_none(self):
        now = NOW
        self.tool_ev("/w/p", "Exit code 1", [now - i for i in range(10)])
        self.assertEqual(att._toolfail_idx(now), {})

    def test_four_identical_signal(self):
        now = NOW
        self.tool_ev("/w/p", "InputValidationError: Grep failed due to x", [now - 500, now - 300, now - 100, now - 30])
        idx = att._toolfail_idx(now)
        self.assertEqual(idx["/w/p"][0][:2], (4, "Grep"))
        row = self.one(sess("a"))
        self.assertEqual(row["sigs"][0]["k"], "toolfail")
        self.assertEqual(row["why"], "같은 오류 4회 반복 · Grep")
        self.assertEqual(row["score"], 45)

    def test_three_identical_none(self):
        now = NOW
        self.tool_ev("/w/p", "### Error: boom", [now - 100, now - 50, now - 10])
        self.assertEqual(att._toolfail_idx(now), {})

    def test_last_older_than_3min_none(self):
        now = NOW
        self.tool_ev("/w/p", "### Error: boom", [now - 500, now - 400, now - 300, now - 200])
        self.assertEqual(att._toolfail_idx(now), {})

    def test_outside_10min_not_counted(self):
        now = NOW
        self.tool_ev("/w/p", "### Error: boom", [now - 700, now - 100, now - 50, now - 10])
        self.assertEqual(att._toolfail_idx(now), {})

    def test_mcp_tool_name_and_done_session_skipped(self):
        now = NOW
        self.tool_ev("/w/p", "### Error: boom", [now - 40, now - 30, now - 20, now - 10])
        self.assertEqual(att._toolfail_idx(now)["/w/p"][0][1], "MCP")
        self.assertIsNone(self.one(sess("a", state="done")))


class TestTailRep(unittest.TestCase):
    @staticmethod
    def line(name, inp, tid):
        return json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": tid, "name": name, "input": inp}]}})

    def test_consecutive_identical(self):
        rows = [self.line("Grep", {"p": "x"}, "g0")] + \
               [self.line("Bash", {"command": "ls"}, "b%d" % i) for i in range(9)]
        self.assertEqual(parse._tail_rep(rows), {"n": 9, "tool": "Bash"})

    def test_read_offsets_differ(self):
        rows = [self.line("Read", {"file_path": "/a", "offset": i * 100}, "r%d" % i) for i in range(10)]
        self.assertEqual(parse._tail_rep(rows)["n"], 1)

    def test_duplicate_ids_and_noise(self):
        ln = self.line("Bash", {"command": "ls"}, "same")
        rows = [ln, ln, ln, '{"type":"user","x":"tool_use"}', "not json"]
        self.assertEqual(parse._tail_rep(rows), {"n": 1, "tool": "Bash"})
        self.assertEqual(parse._tail_rep([]), {"n": 0, "tool": ""})

    @staticmethod
    def result(tid):
        return json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": tid, "content": "out " + tid}]}})

    def test_cron_turns_do_not_count(self):
        rows = []
        for i in range(9):
            rows.append(json.dumps({"type": "user", "isMeta": True, "message": {"content": "tick"}}))
            rows += [self.line("Bash", {"command": "check"}, "b%d" % i), self.result("b%d" % i)]
        self.assertEqual(parse._tail_rep(rows), {"n": 1, "tool": "Bash"})
        rows[0::3] = [json.dumps({"type": "user", "message": {"content": "go"}})] * 9
        self.assertEqual(parse._tail_rep(rows)["n"], 1)

    def test_one_turn_with_results_counts(self):
        rows = [json.dumps({"type": "user", "message": {"content": "go"}})]
        for i in range(9):
            rows += [self.line("Bash", {"command": "check"}, "b%d" % i), self.result("b%d" % i)]
        self.assertEqual(parse._tail_rep(rows), {"n": 9, "tool": "Bash"})

    def test_queue_operation_breaks_run(self):
        rows = [self.line("Bash", {"command": "check"}, "b%d" % i) for i in range(5)]
        rows.insert(3, json.dumps({"type": "queue-operation", "operation": "enqueue"}))
        self.assertEqual(parse._tail_rep(rows)["n"], 2)

    def test_loop_signal_threshold(self):
        base = Base("run")
        base.setUp()
        try:
            self.assertEqual(base.kinds(sess("a", rep={"n": 7, "tool": "Bash"})), [])
            row = base.one(sess("a", rep={"n": 8, "tool": "Bash"}))
            self.assertEqual(row["why"], "Bash 같은 호출 8회 반복")
            self.assertEqual(base.kinds(sess("a", state="done", rep={"n": 20, "tool": "Bash"})), [])
        finally:
            base.tearDown()


class TestMetadataOnly(Base):
    SECRET = "ZZSECRET_42"

    def test_no_text_leaks_and_allowed_keys(self):
        now = NOW
        s = sess("a", state="ask", ctx=96, win=100, wreck=1, rep={"n": 9, "tool": "Bash"},
                 task="task " + self.SECRET, reply="reply " + self.SECRET, last=self.SECRET,
                 title=self.SECRET, targ=self.SECRET)
        cards = [{"kind": "fcheck", "cwd": "/w/p", "at": iso(now - 30), "text": self.SECRET,
                  "title": self.SECRET, "body": self.SECRET, "project": "p"},
                 {"kind": "agent", "cwd": "/w/p", "at": iso(now - 20), "text": self.SECRET,
                  "title": self.SECRET, "project": "p"}]
        self.tool_ev("/w/p", "### Error: " + self.SECRET, [now - 40, now - 30, now - 20, now - 10])
        rows = self.run_att([s], cards)
        self.assertEqual(len(rows), 1)
        blob = json.dumps(rows, ensure_ascii=False)
        self.assertNotIn(self.SECRET, blob)
        for r in rows:
            self.assertLessEqual(set(r), ROW_KEYS)
            for sg in r["sigs"]:
                self.assertEqual(set(sg), SIG_KEYS | ({"until"} if sg["k"] == "fail" else {"keys"} if sg["k"] == "bgdone" else set()))
        self.assertEqual({s["k"] for s in rows[0]["sigs"]},
                         {"ask", "ctx95", "wreck", "loop", "fail", "bgdone", "toolfail"})


class TestExtAskCap(Base):
    """A pending external-CLI request never ages out of attention; only a dead pid (gone) removes it."""
    NOW = NOW

    def setUp(self):
        super().setUp()
        ext = self.ext = sidereus("ext")
        names = ("_ext", "ext_gone_check", "_ext_prune_locked", "ext_tok_refresh", "ext_tok")
        self._saved = {n: getattr(ext, n) for n in names}
        self._eclk = _clock.frozen(ext)
        self._eclk.__enter__()
        ext._ext = {}
        ext.ext_gone_check = lambda now: None
        ext._ext_prune_locked = lambda now: None
        ext.ext_tok_refresh = lambda plat, sid, tp: None
        ext.ext_tok = lambda plat, sid: {}

    def tearDown(self):
        self._eclk.__exit__(None, None, None)
        for n, v in self._saved.items():
            setattr(self.ext, n, v)
        super().tearDown()

    def ext_row(self, ago, **kw):
        t = self.NOW - ago
        self.ext._ext[("gemini", "s-ask")] = dict({"cwd": "/w/p", "state": "ask", "blocked": True,
                                                  "lastSeen": t, "firstSeen": t}, **kw)
        rows = self.ext.ext_rows()
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_fresh_ask_ranks_first(self):
        r = self.ext_row(60)
        self.assertEqual(r["state"], "ask")
        rows = self.run_att([sess("c", state="run", age=5, ctx=96, win=100), r])
        self.assertEqual(rows[0]["sid"], "s-ask")
        self.assertEqual({s["k"] for s in rows[0]["sigs"]}, {"blocked", "ask"})

    def test_aged_ask_keeps_signal(self):
        # unknown liveness (no pid): age changes nothing, the request stays at its rank
        for ago in (31 * 60, 2 * 3600, 24 * 3600):
            r = self.ext_row(ago)
            self.assertEqual(r["state"], "ask", ago)
            rows = self.run_att([sess("c", state="run", age=5, ctx=96, win=100), r])
            self.assertEqual(rows[0]["sid"], "s-ask", ago)
            self.assertEqual({s["k"] for s in rows[0]["sigs"]}, {"blocked", "ask"}, ago)

    def test_gone_row_leaves_attention_requests(self):
        # ext_gone_check turned a dead-pid row into gone (blocked cleared): only the low «gone» signal remains
        r = self.ext_row(31 * 60, state="gone", blocked=False, goneWhy="pid", gone=self.NOW, pid=4242)
        self.assertEqual(self.kinds(r), ["gone"])


class TestClaudePendingAge(Base):
    """Claude rows: ask / plan approval (state ask) and approval (blocked) keep their rank at any age."""
    AGES = (31 * 60, 2 * 3600, 24 * 3600)

    def test_ask_and_plan_any_age(self):
        for ago in self.AGES:
            rows = self.run_att([sess("c", state="run", age=5, ctx=96, win=100), sess("a", state="ask", age=ago)])
            self.assertEqual((rows[0]["sid"], rows[0]["sigs"][0]["k"]), ("a", "ask"), ago)

    def test_blocked_any_age(self):
        for ago in self.AGES:
            r = sess("b", state="tool", age=ago, blocked="Edit waiting for approval", blockedAt=int(NOW - ago))
            rows = self.run_att([sess("c", state="ask", age=5), r])
            self.assertEqual((rows[0]["sid"], rows[0]["sigs"][0]["k"]), ("b", "blocked"), ago)

    def test_done_row_has_no_request(self):
        # process gone -> row state done: nothing left to answer
        self.assertEqual(self.kinds(sess("d", state="done", age=60)), [])

    def test_unknown_liveness_keeps_ask(self):
        notes = sidereus("notes")
        self.assertEqual(notes._sess_state("/w/p", "text", None, asking=True), "ask")
        self.assertEqual(notes._sess_state("/w/p", "tool", None, ask_tool=True), "ask")
        self.assertEqual(notes._sess_state("/w/p", "text", None), "unknown")
        self.assertEqual(notes._sess_state("/w/p", "text", None, asking=True, aborted=True), "unknown")
        saved = (notes.sid_alive, notes.sid_alive_stale)
        try:
            notes.sid_alive, notes.sid_alive_stale = (lambda s: False), (lambda s: True)
            self.assertEqual(notes._sess_state("/w/p", "tool", set(), sid="s1", ask_tool=True), "ask")
            notes.sid_alive_stale = lambda s: False
            self.assertEqual(notes._sess_state("/w/p", "tool", set(), sid="s1", ask_tool=True), "done")
        finally:
            notes.sid_alive, notes.sid_alive_stale = saved


class TestBlockedAt(Base):
    def test_marker_time_is_since_and_ep(self):
        row = self.one(sess("a", state="tool", age=40, blocked="Edit waiting for approval", blockedAt=1_700_000_123))
        g = next(s for s in row["sigs"] if s["k"] == "blocked")
        self.assertEqual((g["since"], g["ep"], row["since"]), (1_700_000_123, 1_700_000_123, 1_700_000_123))

    def test_marker_wins_regardless_of_state(self):
        # R2: a main-turn permission marker surfaces whatever the row state reads
        for st in ("think", "tool", "wait"):
            row = self.one(sess("a", state=st, age=40, blocked="Edit waiting for approval", blockedAt=1_700_000_123))
            self.assertIn("blocked", [s["k"] for s in row["sigs"]], st)

    def test_transcript_blocked_has_no_ep(self):
        row = self.one(sess("a", state="tool", age=40, blocked="Edit waiting for approval"))
        self.assertNotIn("ep", next(s for s in row["sigs"] if s["k"] == "blocked"))


class TestFrozenRestores(unittest.TestCase):
    def test_time_restored_on_exit(self):
        import time as real
        with _clock.frozen(att):
            self.assertEqual(att.time.time(), NOW)
        self.assertIs(att.time, real)


if __name__ == "__main__":
    unittest.main()
