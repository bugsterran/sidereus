"""hooks/pl_flow.py refused-dispatch take-back: a dispatch Pre that never gets a Post (auto-mode classifier, permission
deny) is taken back from st[stage].n and inflight at the next dispatch Pre or Post once its tool_result is in the
session transcript. Tmp dirs only, fixed clock."""
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


class Pend(_Base):
    def setUp(self):
        super().setUp()
        self.tp = os.path.join(self.tmp, "projects", "p", SID + ".jsonl")
        os.makedirs(os.path.dirname(self.tp))
        open(self.tp, "w", encoding="utf-8").close()

    def result(self, tid):
        """The transcript line Claude Code writes for a finished or refused tool call (body is never read)."""
        rec = {"type": "user", "message": {"role": "user", "content": [
            {"tool_use_id": tid, "type": "tool_result", "content": "secret refusal text", "is_error": True}]}}
        with open(self.tp, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, separators=(",", ":")) + "\n")

    def ev(self, event, stage, tid, tool="Agent", tp=True):
        s = [x for x in F.PIPE["stages"] if x["title"] == stage][0]
        ti = {"description": "[pl:%s/%s] task" % (N, stage), "subagent_type": s["agent"]}
        if s.get("model"):
            ti["model"] = s["model"]
        ev = {"hook_event_name": event, "tool_name": tool, "session_id": SID, "cwd": self.proj, "tool_input": ti,
              "tool_use_id": tid}
        if tp:
            ev["transcript_path"] = self.tp
        if event == "PostToolUse":
            ev["tool_response"] = {"content": [{"type": "text", "text": "ok"}]}
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", out):
            H.main()
        v = out.getvalue()
        return json.loads(v)["hookSpecificOutput"] if v else None

    def test_refused_then_resent_counts_once_and_hands_off(self):
        """Refused Pre + re-sent Pre + one Post → n 1, nothing left in flight, the Post hands off to the next stage."""
        self.assertIsNone(self.ev("PreToolUse", "설계", "toolu_A1"))
        self.result("toolu_A1")                       # the refusal reaches the transcript, no Post
        self.t += 1
        self.assertIsNone(self.ev("PreToolUse", "설계", "toolu_A2"))
        o = self.ev("PostToolUse", "설계", "toolu_A2")
        self.assertIn("PASS → next", (o or {}).get("additionalContext", ""))
        r = self.run_()
        self.assertEqual((r["st"]["설계"]["n"], r["inflight"]["설계"], r["pend"]), (1, 0, []))

    def test_running_sibling_is_kept(self):
        """Two parallel dispatches with no result yet: the first Post waits for the second, n stays 2."""
        self.assertIsNone(self.ev("PreToolUse", "설계", "toolu_B1"))
        self.assertIsNone(self.ev("PreToolUse", "설계", "toolu_B2"))
        self.assertIsNone(self.ev("PostToolUse", "설계", "toolu_B1"))
        r = self.run_()
        self.assertEqual((r["st"]["설계"]["n"], r["inflight"]["설계"], r["pend"]), (2, 1, [["toolu_B2", "설계"]]))
        o = self.ev("PostToolUse", "설계", "toolu_B2")
        self.assertIn("PASS → next", (o or {}).get("additionalContext", ""))

    def test_refused_sibling_taken_back_at_post(self):
        """Batch of two, B refused (result, no Post) and last: A's Post hands off without waiting for a later Pre."""
        self.assertIsNone(self.ev("PreToolUse", "설계", "toolu_G1"))
        self.assertIsNone(self.ev("PreToolUse", "설계", "toolu_G2"))
        self.result("toolu_G2")
        o = self.ev("PostToolUse", "설계", "toolu_G1")
        self.assertIn("PASS → next", (o or {}).get("additionalContext", ""))
        r = self.run_()
        self.assertEqual((r["st"]["설계"]["n"], r["inflight"]["설계"], r["pend"]), (1, 0, []))

    def test_posted_sibling_not_taken_back_at_post(self):
        """B ran (own Post, then its result): A's Post must not take B back a second time."""
        self.assertIsNone(self.ev("PreToolUse", "설계", "toolu_H1"))
        self.assertIsNone(self.ev("PreToolUse", "설계", "toolu_H2"))
        self.assertIsNone(self.ev("PostToolUse", "설계", "toolu_H2"))
        self.result("toolu_H2")
        o = self.ev("PostToolUse", "설계", "toolu_H1")
        self.assertIn("PASS → next", (o or {}).get("additionalContext", ""))
        r = self.run_()
        self.assertEqual((r["st"]["설계"]["n"], r["inflight"]["설계"], r["pend"]), (2, 0, []))

    def test_refused_in_earlier_stage_taken_back_at_next_stage(self):
        """The last dispatch of a stage refused and the run moved on: the next stage's Pre corrects the old n."""
        self.assertIsNone(self.ev("PreToolUse", "설계", "toolu_C1"))
        self.ev("PostToolUse", "설계", "toolu_C1")
        self.t += 1
        self.assertIsNone(self.ev("PreToolUse", "구현", "toolu_C2"))
        self.result("toolu_C2")
        self.t += 1
        self.assertIsNone(self.ev("PreToolUse", "구현", "toolu_C3"))
        r = self.run_()
        self.assertEqual((r["st"]["설계"]["n"], r["st"]["구현"]["n"], r["inflight"]["구현"]), (1, 1, 1))

    def test_refused_last_dispatch_taken_back_in_ledger_row(self):
        """A run closed by a new request right after a refused dispatch: its ledger row does not count the refusal."""
        import glob
        os.makedirs(os.path.join(self.proj, ".git"))   # the ledger is written for git repos only
        self.assertIsNone(self.ev("PreToolUse", "설계", "toolu_F1"))
        self.ev("PostToolUse", "설계", "toolu_F1")
        self.t += 1
        self.assertIsNone(self.ev("PreToolUse", "구현", "toolu_F2"))
        self.result("toolu_F2")                       # refused; no re-send, the next tag is a new request
        self.t += 1
        self.ev("PreToolUse", "설계", "toolu_F3")
        rows = [json.loads(x) for p in glob.glob(os.path.join(self.tmp, "eval", "*", "runs.jsonl"))
                for x in open(p, encoding="utf-8")]
        self.assertEqual([(x["ss"]["설계"]["n"], x["ss"]["구현"]["n"]) for x in rows], [(1, 0)])

    def test_unreadable_transcript_keeps_counting(self):
        """No transcript path: nothing is taken back (the count stays as before)."""
        self.assertIsNone(self.ev("PreToolUse", "설계", "toolu_D1", tp=False))
        self.t += 1
        self.assertIsNone(self.ev("PreToolUse", "설계", "toolu_D2", tp=False))
        self.assertEqual(self.run_()["st"]["설계"]["n"], 2)

    def test_only_ids_stored(self):
        self.assertIsNone(self.ev("PreToolUse", "설계", "toolu_E1"))
        self.result("toolu_E1")
        self.t += 1
        self.ev("PreToolUse", "설계", "toolu_E2")
        with open(os.path.join(self.marks, SID + ".runs.json"), encoding="utf-8") as f:
            raw = f.read()
        self.assertNotIn("secret", raw)
        self.assertEqual(self.run_()["pend"], [["toolu_E2", "설계"]])

    def test_bad_id_not_recorded(self):
        self.assertIsNone(self.ev("PreToolUse", "설계", "../x y"))
        self.assertNotIn("pend", self.run_())

    def _hold_lock(self, secs):
        """A live holder: a fresh lockfile (younger than LOCK_STALE_S) removed by a thread after `secs`."""
        import threading
        os.makedirs(self.marks, exist_ok=True)
        lp = os.path.join(self.marks, SID + ".runs.json.lock")
        open(lp, "w", encoding="utf-8").close()
        th = threading.Timer(secs, os.remove, (lp,))
        th.start()
        self.addCleanup(th.join)
        return th

    def test_post_outwaits_a_live_lock_holder(self):
        """A dispatch Post blocked past LOCK_WAIT_S by a live holder still records vp n and clears pend."""
        self.assertIsNone(self.ev("PreToolUse", "설계", "toolu_L1"))
        with mock.patch.object(H, "LOCK_WAIT_S", 0.2), mock.patch.object(H, "POST_LOCK_WAIT_S", 0.9), \
                mock.patch.object(H, "LOCK_STALE_S", 5.0):
            self._hold_lock(0.5)
            o = self.ev("PostToolUse", "설계", "toolu_L1")
        self.assertIn("PASS → next", (o or {}).get("additionalContext", ""))
        r = self.run_()
        self.assertEqual((r["vp"]["설계"]["n"], r["inflight"]["설계"], r["pend"]), (1, 0, []))

    def test_pre_still_gives_up_after_lock_wait(self):
        """Pre keeps LOCK_WAIT_S: with the lock held it records nothing and returns before the holder lets go."""
        import time
        with mock.patch.object(H, "LOCK_WAIT_S", 0.2), mock.patch.object(H, "POST_LOCK_WAIT_S", 0.9), \
                mock.patch.object(H, "LOCK_STALE_S", 5.0):
            self._hold_lock(0.5)
            t0 = time.monotonic()
            self.assertIsNone(self.ev("PreToolUse", "설계", "toolu_L2"))
            took = time.monotonic() - t0
        self.assertLess(took, 0.45)
        self.assertNotIn(N, H._load(os.path.join(self.marks, SID + ".runs.json"))["runs"])   # nothing recorded

    def test_results_reads_ids_only_from_tool_result_lines(self):
        with open(self.tp, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "progress", "tool_use_id": "toolu_P"}) + "\n")
        self.result("toolu_Q")
        self.assertEqual(H._results(self.tp), {"toolu_Q"})
        self.assertIsNone(H._results(os.path.join(self.tmp, "missing.jsonl")))


if __name__ == "__main__":
    unittest.main()
