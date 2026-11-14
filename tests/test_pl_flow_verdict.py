"""hooks/pl_flow.py review-verdict guard: an onFail loop-back is denied only when every agent of the review pass
returned a passing VERDICT (R1); any BLOCKING/FAIL or unknown verdict keeps it allowed (R2); only ids and a count are
stored (R3); a later round decides on its own verdicts (R4). Tmp dirs only, fixed clock."""
import io
import json
import os
import unittest
from unittest import mock

from tests import test_pl_flow as F   # ⚠not `from … import Flow`: its tests would run again here
from tests._load import sidereus  # noqa: F401  (package bootstrap)

H = F.H
N, SID = F.N, F.SID
_Base = type("_Base", (F.Flow,), {k: None for k in dir(F.Flow) if k.startswith("test")})   # helpers only
BODY = "secret report body line"


def _handback(verdict_text):
    return [{"type": "assistant", "message": {"role": "assistant", "content": [{"type": "thinking", "thinking": "t"}]}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "tu1", "name": "SubagentHandback",
                 "input": {"message": "%s\n%s" % (BODY, verdict_text)}}]}},
            {"type": "attachment", "attachment": {"type": "hook_success"}},
            {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu1"}]}},
            {"type": "attachment", "attachment": {"type": "hook_success"}}]


def _running():
    return [{"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "tu2", "name": "Bash", "input": {"command": "ls"}}]}}]


def _prompt():
    return [{"type": "user", "message": {"role": "user", "content": "next round prompt"}}]


class Verdict(_Base):
    def setUp(self):
        super().setUp()
        self.sess = os.path.join(self.tmp, "projects", "p", SID)
        self.subs = os.path.join(self.sess, "subagents")
        os.makedirs(self.subs)
        self.tp = self.sess + ".jsonl"

    def agent(self, aid, recs, append=False):
        with open(os.path.join(self.subs, "agent-%s.jsonl" % aid), "a" if append else "w", encoding="utf-8") as f:
            f.writelines(json.dumps(x) + "\n" for x in recs)

    def ev(self, event, stage, tool="Agent", bg=False, to=None, resp=None):
        key = "summary" if tool == "SendMessage" else "description"
        ti = {key: "[pl:%s/%s] task" % (N, stage)}
        if tool == "Agent":
            s = [x for x in F.PIPE["stages"] if x["title"] == stage][0]
            ti["subagent_type"] = s["agent"]
            if s.get("model"):
                ti["model"] = s["model"]
        if bg:
            ti["run_in_background"] = True
        if to:
            ti["to"] = to
        ev = {"hook_event_name": event, "tool_name": tool, "session_id": SID, "cwd": self.proj, "tool_input": ti,
              "transcript_path": self.tp}
        if event == "PostToolUse":
            ev["tool_response"] = resp if resp is not None else {"content": [{"type": "text", "text": "ok"}]}
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", out):
            H.main()
        v = out.getvalue()
        return json.loads(v)["hookSpecificOutput"] if v else None

    def review(self, ids, bg=True, title="리뷰"):
        """Dispatch one reviewer per id (None = a dispatch whose Post carries no agent id)."""
        for aid in ids:
            self.t += 1
            self.assertIsNone(self.ev("PreToolUse", title, bg=bg))
        for aid in ids:
            self.ev("PostToolUse", title, bg=bg, resp={"agentId": aid} if aid else None)

    def goto(self):
        self.t += 1
        return self.ev("PreToolUse", "구현", tool="SendMessage", to="impl1")

    def denied(self, o):
        return bool(o) and o.get("permissionDecision") == "deny"

    def test_r1_all_passing_background_reviewers_deny_loop_back(self):
        """R1: CLEAN + PASS handbacks → goto Pre denied, run state unchanged except the jump deny count."""
        self.to_review()
        self.agent("a1", _handback("VERDICT: CLEAN"))
        self.agent("a2", _handback("VERDICT: PASS"))
        self.review(["a1", "a2"])
        before = self.run_()
        o = self.goto()
        self.assertTrue(self.denied(o))
        why = o["permissionDecisionReason"]
        self.assertIn("confirmed Important", why)
        self.assertIn("quick-fix", why)
        self.assertTrue(why.startswith("리뷰:"))
        r = self.run_()
        for k in ("lb", "loops", "ret", "cur", "st", "vp", "skipok"):
            self.assertEqual(r.get(k), before.get(k), k)
        self.assertEqual((r["deny"], r["dl"][-1]["c"]), (int(before.get("deny") or 0) + 1, "jump"))

    def test_r1_foreground_reviewers_ids_from_post(self):
        """R1: foreground Agent Posts carry the id too; they never enter `ag` (commit matching stays bg-only)."""
        self.to_review()
        self.agent("a1", _handback("VERDICT: CLEAN"))
        self.agent("a2", _handback("VERDICT: CLEAN"))
        self.review(["a1", "a2"], bg=False)
        r = self.run_()
        self.assertEqual(r["vp"]["리뷰"], {"a": ["a1", "a2"], "n": 2})
        self.assertNotIn("ag", r["st"]["리뷰"])
        self.assertTrue(self.denied(self.goto()))

    def test_r1_text_only_final_record(self):
        self.to_review()
        self.agent("a1", [{"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "VERDICT: BLOCKING (draft)\n%s\nVERDICT: PASS" % BODY}]}}])
        self.review(["a1"])
        self.assertTrue(self.denied(self.goto()))   # the last verdict line decides

    def test_r2_one_blocking_allows(self):
        self.to_review()
        self.agent("a1", _handback("VERDICT: CLEAN"))
        self.agent("a2", _handback("VERDICT: BLOCKING"))
        self.review(["a1", "a2"])
        self.assertIsNone(self.goto())
        r = self.run_()
        self.assertEqual((r["cur"], r["ret"], r["loops"].get("리뷰")), ("구현", "재검증", 1))

    def test_r2_unknown_verdicts_allow(self):
        """R2: an unknown verdict is never a pass."""
        cases = {
            "missing transcript": lambda: None,
            "format mismatch": lambda: self.agent("a1", _handback("**Verdict** clean")),
            "still running": lambda: self.agent("a1", _handback("VERDICT: CLEAN") + _running()),
            "unanswered continuation": lambda: self.agent("a1", _handback("VERDICT: CLEAN") + _prompt()),
        }
        for name, setup in cases.items():
            with self.subTest(name):
                for fn in os.listdir(self.subs):
                    os.remove(os.path.join(self.subs, fn))
                os.remove(os.path.join(self.marks, SID + ".runs.json")) if os.path.exists(self.marks) else None
                self.to_review()
                setup()
                self.review(["a1"])
                self.assertIsNone(self.goto())
                self.assertEqual(self.run_()["cur"], "구현")

    def test_r2_dispatch_without_id_allows(self):
        """R2: two returned dispatches, one Post without an agentId: n=2 with one id is unknown."""
        self.to_review()
        self.agent("a1", _handback("VERDICT: CLEAN"))
        self.review(["a1", None])
        self.assertEqual(self.run_()["vp"]["리뷰"], {"a": ["a1"], "n": 2})
        self.assertIsNone(self.goto())

    def test_r2_no_transcript_path_allows(self):
        self.to_review()
        self.agent("a1", _handback("VERDICT: CLEAN"))
        self.review(["a1"])
        self.tp = "relative.jsonl"   # rejected by _main → no transcript → unknown
        self.assertIsNone(self.goto())

    def test_r3_only_ids_and_count_stored(self):
        self.to_review()
        self.agent("a1", _handback("VERDICT: CLEAN"))
        self.agent("a2", _handback("VERDICT: PASS"))
        self.review(["a1", "a2"])
        self.goto()
        with open(os.path.join(self.marks, SID + ".runs.json"), encoding="utf-8") as f:
            raw = f.read()
        for s in (BODY, "VERDICT", "CLEAN", "PASS"):
            self.assertNotIn(s, raw)
        self.assertEqual(self.run_()["vp"]["리뷰"], {"a": ["a1", "a2"], "n": 2})

    def _round2(self):
        """Round 1 loop-back allowed, the fix and re-verify run; the run sits on 재검증 for round 2 of 리뷰."""
        self.assertIsNone(self.goto())
        self.ev("PostToolUse", "구현", tool="SendMessage", to="impl1")
        self.t += 1
        self.assertIsNone(self.ev("PreToolUse", "재검증"))
        self.ev("PostToolUse", "재검증")

    def test_r4_round2_continuation_decides_alone(self):
        """R4: round 1 BLOCKING allows; round 2 by SendMessage to the same id ending CLEAN is denied."""
        self.to_review()
        self.agent("a1", _handback("VERDICT: BLOCKING"))
        self.review(["a1"])
        self._round2()
        self.t += 1
        self.assertIsNone(self.ev("PreToolUse", "리뷰", tool="SendMessage", to="a1"))
        self.assertNotIn("리뷰", self.run_()["vp"])   # the new round dropped round 1; nothing counts before its Post
        self.ev("PostToolUse", "리뷰", tool="SendMessage", to="a1")
        self.assertEqual(self.run_()["vp"]["리뷰"], {"a": ["a1"], "n": 1})
        self.agent("a1", _prompt() + _handback("VERDICT: CLEAN"), append=True)
        self.assertTrue(self.denied(self.goto()))

    def test_r4_stale_round1_cleared(self):
        """R4: round 1 CLEAN + BLOCKING; round 2 is a new agent: its own verdict decides, the old ids are gone."""
        self.to_review()
        self.agent("a1", _handback("VERDICT: CLEAN"))
        self.agent("a2", _handback("VERDICT: BLOCKING"))
        self.review(["a1", "a2"])
        self._round2()
        self.agent("a3", _handback("VERDICT: CLEAN"))
        self.review(["a3"])
        self.assertEqual(self.run_()["vp"]["리뷰"], {"a": ["a3"], "n": 1})
        self.assertTrue(self.denied(self.goto()))   # a2's old BLOCKING no longer counts

    def test_r4_stale_clean_new_blocking_allows(self):
        self.to_review()
        self.agent("a1", _handback("VERDICT: CLEAN"))
        self.agent("a2", _handback("VERDICT: BLOCKING"))
        self.review(["a1", "a2"])
        self._round2()
        self.t += 1
        self.assertIsNone(self.ev("PreToolUse", "리뷰", tool="SendMessage", to="a1"))
        self.ev("PostToolUse", "리뷰", tool="SendMessage", to="a1")
        self.assertEqual(self.run_()["vp"]["리뷰"], {"a": ["a1"], "n": 1})
        self.agent("a1", _prompt() + _handback("VERDICT: BLOCKING"), append=True)
        self.assertIsNone(self.goto())

    def test_r1_refused_dispatch_never_counts(self):
        """R1: a dispatch refused before it ran (classifier, permission) gets Pre but no Post; it must not block."""
        self.to_review()
        self.agent("a1", _handback("VERDICT: CLEAN"))
        self.t += 1
        self.assertIsNone(self.ev("PreToolUse", "리뷰", bg=True))   # refused attempt: no Post follows
        self.review(["a1"])                                          # the re-sent dispatch
        self.assertEqual(self.run_()["vp"]["리뷰"], {"a": ["a1"], "n": 1})
        self.assertTrue(self.denied(self.goto()))

    def test_r1_refused_sendmessage_never_counts(self):
        self.to_review()
        self.agent("x9", _handback("VERDICT: PASS"))
        for _ in range(2):   # the first one is refused before it runs
            self.t += 1
            self.assertIsNone(self.ev("PreToolUse", "리뷰", tool="SendMessage", to="x9"))
        self.ev("PostToolUse", "리뷰", tool="SendMessage", to="x9")
        self.assertTrue(self.denied(self.goto()))

    def test_sequential_redispatch_keeps_first_verdict(self):
        """A second reviewer after the first one finished (same round) adds to the pass, never replaces it."""
        self.to_review()
        self.agent("a1", _handback("VERDICT: BLOCKING"))
        self.agent("a2", _handback("VERDICT: CLEAN"))
        self.review(["a1"], bg=False)
        self.review(["a2"], bg=False)
        self.assertEqual(self.run_()["vp"]["리뷰"], {"a": ["a1", "a2"], "n": 2})
        self.assertIsNone(self.goto())

    def test_sendmessage_continuation_id_counts(self):
        """An agent of another stage continued into the review stage by SendMessage counts as that pass's agent."""
        self.to_review()
        self.agent("x9", _handback("VERDICT: PASS"))
        self.t += 1
        self.assertIsNone(self.ev("PreToolUse", "리뷰", tool="SendMessage", to="x9"))
        self.ev("PostToolUse", "리뷰", tool="SendMessage", to="x9")
        self.assertTrue(self.denied(self.goto()))

    def test_agent_verdict_unit(self):
        fp = os.path.join(self.subs, "agent-u.jsonl")
        self.assertRaises(OSError, H._agent_verdict, fp)
        self.agent("u", _handback("VERDICT: FAIL"))
        self.assertEqual(H._agent_verdict(fp), "FAIL")
        self.agent("u", [{"type": "api-request-blob", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "VERDICT: PASS"}]}}])
        self.assertIsNone(H._agent_verdict(fp))   # not an assistant record
        with mock.patch.object(H, "VERDICT_TAIL", 64):
            self.agent("u", _handback("VERDICT: PASS"))
            self.assertIsNone(H._agent_verdict(fp))   # the handback record is cut by the tail window → unknown

    def test_verdict_pass_never_raises(self):
        self.assertFalse(H._verdict_pass({"vp": {"리뷰": {"a": ["../x"], "n": 1}}}, "리뷰"))
        self.assertFalse(H._verdict_pass({"vp": "bad"}, "리뷰"))
        self.assertFalse(H._verdict_pass(None, "리뷰"))


if __name__ == "__main__":
    unittest.main()
