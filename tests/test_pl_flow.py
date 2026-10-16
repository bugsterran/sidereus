"""Hook hooks/pl_flow.py: pipeline run state + Pre skip guard + Post hand-off text. Tmp dirs only, fixed clock."""
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

_P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks", "pl_flow.py")
_spec = importlib.util.spec_from_file_location("pl_flow_hook", _P)
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)

N = "sidereus-change"
SID = "sess-0001"
# Same stage shape as .claude/pipelines/sidereus-change.json (tasks trimmed).
PIPE = {"v": 1, "name": N, "after": ["restart", "commit"], "stages": [
    {"title": "설계", "agent": "sidereus-designer", "produces": "slices"},
    {"title": "구현", "agent": "sidereus-implementer", "fanout": "slices", "gate": "scripts/check.sh --fast",
     "onError": "continue"},
    {"title": "검증", "agent": "sidereus-verifier", "model": "sonnet", "gate": "scripts/check.sh --full",
     "onFail": {"goto": "구현", "max": 2}},
    {"title": "리뷰", "agent": "sidereus-reviewer", "onFail": {"goto": "구현", "max": 1, "then": "재검증"}},
    {"title": "재검증", "agent": "sidereus-verifier", "model": "sonnet", "gate": "scripts/check.sh --full",
     "onlyOnJump": True, "onFail": {"goto": "구현", "max": 1}},
    {"title": "라이브 검증", "skill": "sidereus-ship", "agent": "general-purpose"}]}


class Flow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(os.path.join(self.proj, ".claude", "pipelines"))
        self._pipe(PIPE)
        self.cfg = os.path.join(self.tmp, "config.local.json")
        self.marks = os.path.join(self.tmp, "plmark")
        self.t = 1000.0
        self.user = os.path.join(self.tmp, "user-claude")
        for k, v in (("MARK_DIR", self.marks), ("CONFIG_PATH", self.cfg), ("_now", lambda: self.t),
                     ("CLAUDE_DIR", self.user), ("HOME_DIR", self.tmp), ("DIRS_DIR", os.path.join(self.tmp, "plbrief")),
                     ("DATA_DIR", self.tmp), ("_spawn", lambda argv: None)):   # run-end auto scoring: no live eval store, no child
            p = mock.patch.object(H, k, v)
            p.start()
            self.addCleanup(p.stop)

    def _pipe(self, body):
        with open(os.path.join(self.proj, ".claude", "pipelines", N + ".json"), "w", encoding="utf-8") as f:
            f.write(body if isinstance(body, str) else json.dumps(body, ensure_ascii=False))

    def _ev(self, event, stage, tool="Agent", resp=None, bg=False, text=" secret task text", sub=None, model=None,
            raw=None):
        key = "summary" if tool == "SendMessage" else "description"
        ti = {key: raw if raw is not None else "[pl:%s/%s]%s" % (N, stage, text)}
        if tool in ("Agent", "Task"):   # default = the stage's own agent and model (the compliant call)
            s = [x for x in PIPE["stages"] if x["title"] == stage]
            sub = sub if sub is not None else (s[0]["agent"] if s else None)
            model = model if model is not None else (s[0].get("model") if s else None)
            if sub:
                ti["subagent_type"] = sub
            if model:
                ti["model"] = model
        if bg:
            ti["run_in_background"] = True
        ev = {"hook_event_name": event, "tool_name": tool, "session_id": SID, "cwd": self.proj, "tool_input": ti}
        if resp is not None:
            ev["tool_response"] = resp
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", out):
            H.main()
        v = out.getvalue()
        return json.loads(v)["hookSpecificOutput"] if v else None

    def pre(self, stage, tool="Agent", **kw):
        return self._ev("PreToolUse", stage, tool, **kw)

    def post(self, stage, tool="Agent", **kw):
        o = self._ev("PostToolUse", stage, tool, resp=kw.pop("resp", {"content": [{"type": "text", "text": "ok"}]}), **kw)
        return o["additionalContext"] if o else None

    def run_(self):
        with open(os.path.join(self.marks, SID + ".runs.json"), encoding="utf-8") as f:
            return json.load(f)["runs"][N]

    def to_review(self):
        self.pre("설계"), self.post("설계")
        self.pre("구현"), self.post("구현")
        self.pre("검증"), self.post("검증")

    def test_run_start_metadata_only(self):
        self.assertIsNone(self.pre("설계"))
        with open(os.path.join(self.marks, SID + ".runs.json"), encoding="utf-8") as f:
            raw = f.read()
        self.assertNotIn("secret", raw)
        r = self.run_()
        self.assertEqual((r["cur"], r["inflight"], r["end"]), ("설계", {"설계": 1}, 0))
        self.assertFalse(os.path.exists(os.path.join(self.marks, SID + ".json")))

    def _heads(self, seq):
        calls = []
        it = iter(seq)

        def f(proj):
            calls.append(proj)
            v = next(it)
            if isinstance(v, Exception):
                raise v
            return v
        p = mock.patch.object(H, "_head", f)
        p.start()
        self.addCleanup(p.stop)
        return calls

    def test_head_stamps_run_start_and_stage_change(self):
        calls = self._heads(["aaa1", "bbb2", "ccc3"])
        self.pre("설계")
        r = self.run_()
        self.assertEqual((r["h0"], r["h1"], calls), ("aaa1", "aaa1", [self.proj]))   # fresh run: h1 reuses h0
        self.post("설계"), self.pre("설계", tool="SendMessage")   # same-stage re-mark: no git call
        self.assertEqual(len(calls), 1)
        self.pre("구현")
        r = self.run_()
        self.assertEqual((r["h0"], r["h1"], len(calls)), ("aaa1", "bbb2", 2))

    def test_head_failure_never_blocks(self):
        def boom(proj):
            raise RuntimeError("git")
        with mock.patch.object(H.subprocess, "run", boom):
            self.assertEqual(H._head(self.proj), "")
        calls = self._heads(["", "", ""])
        self.assertIsNone(self.pre("설계"))
        t = self.post("설계")
        r = self.run_()
        self.assertNotIn("h0", r)
        self.assertNotIn("h1", r)
        self.assertIn("next: [pl:sidereus-change/구현]", t)
        self.assertEqual(len(calls), 2)   # h0 attempt + h1 attempt, each failing quietly

    def test_git_safe_opts_match_gitinfo(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(_P)), "sidereus", "gitinfo.py"), encoding="utf-8") as f:
            src = f.read().replace('"', "'")
        self.assertIn("GIT_SAFE_OPTS = %r" % H.GIT_SAFE_OPTS, src)

    def test_commit_close_does_not_stamp_head(self):
        self.pre("설계"), self.post("설계"), self.pre("구현")
        calls = self._heads([])
        self.assertEqual(self._cmd("git commit -m x"), "")
        self.assertEqual((self.run_()["end"] > 0, calls), (True, []))

    def test_design_hands_off_to_impl(self):
        self.pre("설계")
        t = self.post("설계")
        self.assertIn("PASS → next: [pl:sidereus-change/구현] · agent sidereus-implementer · gate scripts/check.sh --fast", t)
        self.assertNotIn("secret", t)
        self.assertNotIn("ok", t.split("agent")[0])

    def test_fanout_waits_for_last_slice(self):
        self.pre("설계"), self.post("설계")
        self.pre("구현"), self.pre("구현")
        self.assertIsNone(self.post("구현"))
        t = self.post("구현")
        self.assertIn("[pl:sidereus-change/검증] · agent sidereus-verifier · model sonnet", t)
        self.assertIn("do not block", t)

    def test_verify_fail_branch_and_loop_back(self):
        self.pre("설계"), self.post("설계"), self.pre("구현"), self.post("구현"), self.pre("검증")
        t = self.post("검증")
        self.assertIn("PASS → next: [pl:sidereus-change/리뷰]", t)
        self.assertIn("FAIL → SendMessage the 구현 agent tagged [pl:sidereus-change/구현] (round 1/2", t)
        self.assertIsNone(self.pre("구현", tool="SendMessage"))
        self.assertEqual((self.run_()["loops"], self.run_()["ret"]), ({"검증": 1}, "검증"))
        t = self.post("구현", tool="SendMessage")
        self.assertIn("PASS → next: [pl:sidereus-change/검증]", t)
        self.assertIsNone(self.pre("검증"))
        self.assertIn("round 2/2", self.post("검증"))

    def test_review_fail_then_final_verify(self):
        self.to_review()
        self.pre("리뷰")
        t = self.post("리뷰")
        self.assertIn("PASS → next: [pl:sidereus-change/라이브 검증] · agent general-purpose · skill sidereus-ship", t)
        self.assertNotIn("next: [pl:sidereus-change/재검증]", t)   # onlyOnJump is never the plain next
        self.assertIn("round 1/1; at max → [pl:sidereus-change/재검증]", t)
        self.pre("구현", tool="SendMessage")
        self.assertEqual(self.run_()["ret"], "재검증")
        self.assertIn("PASS → next: [pl:sidereus-change/재검증]", self.post("구현", tool="SendMessage"))
        self.assertIsNone(self.pre("재검증"))   # jump allowed via ret
        self.assertEqual(self.run_()["ret"], "")
        self.assertIn("next: [pl:sidereus-change/라이브 검증]", self.post("재검증"))

    def test_loopback_edges(self):
        self.pre("설계"), self.post("설계"), self.pre("구현"), self.post("구현")
        for _ in range(2):
            self.pre("검증"), self.post("검증")
            self.pre("구현", tool="SendMessage"), self.post("구현", tool="SendMessage")
        self.pre("검증"), self.post("검증"), self.pre("리뷰"), self.post("리뷰")
        self.pre("구현", tool="SendMessage"), self.post("구현", tool="SendMessage")
        self.pre("재검증"), self.post("재검증")
        self.pre("구현", tool="SendMessage")
        lb = [(e["f"], e["g"], e["n"]) for e in self.run_()["lb"]]
        self.assertEqual(lb, [("검증", "구현", 2), ("리뷰", "구현", 1), ("재검증", "구현", 1)])
        self.assertEqual(self.run_()["lb"][0]["t"], self.t)
        self.assertNotIn("secret", json.dumps(self.run_()["lb"], ensure_ascii=False))

    def test_undeclared_backward_move_marks_back(self):
        self.to_review()
        self.pre("리뷰"), self.post("리뷰"), self.pre("라이브 검증")   # its Post never came
        self.assertIsNone(self.pre("구현", tool="SendMessage"))   # 라이브 검증 has no onFail -> 구현
        r = self.run_()
        self.assertEqual((r["cur"], r["st"]["라이브 검증"]["s"]), ("구현", "back"))
        self.assertNotIn("라이브 검증", [e["f"] for e in r["lb"]])   # no loop was declared

    def test_pass_start_on_reentry(self):
        self.pre("설계"), self.post("설계"), self.pre("구현"), self.post("구현")
        self.t += 100
        self.pre("검증"), self.post("검증")
        self.assertNotIn("p0", self.run_()["st"]["검증"])   # first pass: t0 is the pass start
        self.t += 100
        self.pre("구현", tool="SendMessage")
        s = self.run_()["st"]["구현"]
        self.assertEqual((s["t0"], s["p0"], s["k"], s["s"]), (1000.0, 1200.0, 2, "run"))
        self.post("구현", tool="SendMessage")
        self.assertEqual((self.run_()["st"]["구현"]["p0"], self.run_()["st"]["구현"]["k"]), (1200.0, 2))   # kept by _mark

    def test_closed_passes_recorded(self):
        self.pre("설계"), self.post("설계"), self.pre("구현")
        self.t += 10
        self.post("구현")
        for a in (1100, 1200):   # 검증 sends 구현 back twice
            self.t = a - 50.0
            self.pre("검증"), self.post("검증")
            self.t = float(a)
            self.pre("구현", tool="SendMessage")
            self.t += 10
            self.post("구현", tool="SendMessage")
        s = self.run_()["st"]["구현"]
        self.assertEqual((s["t0"], s["p0"], s["k"]), (1000.0, 1200.0, 3))
        self.assertEqual(s["ps"], [{"a": 1000.0, "b": 1010.0, "s": "done"}, {"a": 1100.0, "b": 1110.0, "s": "done"}])
        self.assertEqual(self.run_()["st"]["검증"]["ps"], [{"a": 1050.0, "b": 1100.0, "s": "back"}])
        self.assertNotIn("ps", self.run_()["st"]["설계"])   # a single pass records nothing

    def test_mark_keeps_passes(self):
        ps = [{"a": 1.0, "b": 2.0, "s": "back"}]
        for s in ("done", "back", "fail", "run"):
            r = {"st": {"x": {"s": "run", "t0": 1.0, "t1": 3.0, "n": 1, "p0": 3.0, "k": 2, "ps": list(ps)}}}
            H._mark(r, "x", s, 9.0)
            self.assertEqual(r["st"]["x"]["ps"], ps)
        r = {"st": {"x": {"s": "done", "t0": 1.0, "t1": 3.0, "n": 1, "ps": list(ps)}}}
        H._mark(r, "x", "skip", 9.0)   # skip after a run keeps everything
        self.assertEqual(r["st"]["x"]["ps"], ps)

    def test_passes_capped(self):
        e = {}
        for i in range(8):
            H._ps(e, {"s": "back", "t0": 0.0, "p0": float(i), "t1": i + 0.5})
        self.assertEqual([x["a"] for x in e["ps"]], [2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        self.assertEqual(len(e["ps"]), H.PS_MAX)
        H._ps(e, {"s": "back", "t0": "bad"})   # malformed old pass: ignored, never raises
        H._ps(e, None)
        self.assertEqual(len(e["ps"]), 6)

    def _cmd(self, cmd, cwd=None, agent=None, desc="commit"):
        ev = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": SID, "cwd": cwd or self.proj,
              "tool_input": {"command": cmd, "description": desc}}
        if agent:
            ev["agent_id"] = agent
        out = io.StringIO()
        # untagged-Bash nudge muted: it is context only and covered by its own tests
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", out), \
                mock.patch.object(H, "_nudge", lambda *a: None):
            H.main()
        return out.getvalue()

    def test_outside_commit_keeps_run_open(self):
        """An unrelated `[pl:-]` commit mid-run (or one tagged for another pipeline) must not close the run, or the next
        stage is denied as skipping stages that ran."""
        self.pre("설계"), self.post("설계"), self.pre("구현"), self.post("구현")
        self.assertEqual(self._cmd("git commit -m x", desc="[pl:-] unrelated commit"), "")
        self.assertEqual(self._cmd("git commit -m x", desc="[pl:other-pipe/x] commit"), "")
        r = self.run_()
        self.assertEqual((r["end"], r["st"].get("cm")), (0, None))
        self.assertIsNone(self.pre("검증"))
        self.assertEqual(self._cmd("git commit -m x", desc="[pl:%s/검증] commit" % N), "")   # its own tag closes it
        self.assertNotEqual(self.run_()["end"], 0)

    def test_main_stage_bash_after_closed_run_counts(self):
        """Main's own first-stage Bash after a run closed on that same stage starts a new run, so the next dispatch passes."""
        pipe = dict(PIPE, stages=[{"title": "요구사항", "agent": "main"}] + PIPE["stages"])
        self._pipe(pipe)
        self.assertIsNone(self.pre("요구사항", tool="Bash"))
        self._cmd("git commit -m x")   # closes that run while cur is still 요구사항
        self.assertNotEqual(self.run_()["end"], 0)
        self.t += 60
        self.assertIsNone(self.pre("요구사항", tool="Bash"))
        r = self.run_()
        self.assertEqual((r["end"], r["t0"], r["cur"]), (0, 1060.0, "요구사항"))
        self.assertIsNone(self.pre("설계"))

    def test_commit_closes_open_run(self):
        self.pre("설계"), self.post("설계"), self.pre("구현")
        for cmd in ("git commit --dry-run -m x", "git commit-tree abc", "echo git", "git log"):
            self.assertEqual(self._cmd(cmd), "")
            self.assertEqual(self.run_()["end"], 0)
        self.assertEqual(self._cmd("git commit -m x", cwd=self.tmp), "")   # other folder: not this project
        self.assertEqual(self.run_()["end"], 0)
        self.t += 5
        self.assertEqual(self._cmd("cd x && git -C %s commit -m 'secret msg'" % self.proj, cwd=self.tmp), "")   # never denies
        r = self.run_()
        self.assertEqual((r["end"], r["st"]["구현"]["s"]), (1005.0, "done"))
        with open(os.path.join(self.marks, SID + ".runs.json"), encoding="utf-8") as f:
            self.assertNotIn("secret", f.read())
        self.t += 5
        self.pre("설계")   # the next tagged dispatch opens a fresh run
        self.assertEqual((self.run_()["t0"], self.run_()["end"]), (1010.0, 0))

    def test_subagent_commit_keeps_run_open(self):
        self.pre("설계"), self.post("설계"), self.pre("구현")
        self.assertEqual(self._cmd("git commit -m x", agent="a97015b8e84f092f4"), "")
        r = self.run_()
        self.assertEqual((r["end"], r["st"]["구현"]["s"]), (0, "run"))
        self.assertEqual(self._cmd("git commit -m x"), "")   # main's own commit still closes it
        self.assertNotEqual(self.run_()["end"], 0)

    def _sub_commit(self, aid, atype=None):
        ev = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": SID, "cwd": self.proj,
              "tool_input": {"command": "git commit -m x"}, "agent_id": aid}
        if atype:
            ev["agent_type"] = atype
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", io.StringIO()):
            H.main()

    def _cms(self):
        return {t: len(e.get("cm") or []) for t, e in self.run_()["st"].items() if e.get("cm")}

    def test_subagent_commit_stamps_stage_listing_its_id(self):
        self.pre("설계"), self.post("설계"), self.pre("구현"), self.post("구현")
        ev = {"hook_event_name": "PreToolUse", "tool_name": "SendMessage", "session_id": SID, "cwd": self.proj,
              "tool_input": {"summary": "[pl:%s/구현] fix" % N, "to": "a1111111"}}
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", io.StringIO()):
            H.main()
        self.post("구현", tool="SendMessage"), self.pre("검증")
        self.assertEqual(self.run_()["cur"], "검증")
        self._sub_commit("a1111111", "sidereus-verifier")   # id wins over agent_type
        self.assertEqual(self._cms(), {"구현": 1})
        self.assertEqual(self.run_()["end"], 0)

    def test_subagent_commit_matches_agent_type(self):
        self.pre("설계"), self.post("설계"), self.pre("구현"), self.post("구현"), self.pre("검증")
        self._sub_commit("a2222222", "sidereus-implementer")
        self.assertEqual(self._cms(), {"구현": 1})
        self._sub_commit("a2222222", "sidereus-verifier")   # two stages use it; only 검증 is running
        self.assertEqual(self._cms(), {"구현": 1, "검증": 1})

    def test_subagent_commit_without_match_stamps_cur(self):
        self.pre("설계"), self.post("설계"), self.pre("구현")
        self._sub_commit("a3333333")
        self._sub_commit("a3333333", "someone-else")
        self.assertEqual(self._cms(), {"구현": 2})
        self.assertEqual(self._cmd("git commit -m x"), "")   # main stamps cur and closes the run
        r = self.run_()
        self.assertEqual((self._cms(), r["st"]["구현"]["s"]), ({"구현": 3}, "done"))
        self.assertNotEqual(r["end"], 0)

    def test_bg_launch_records_agent_id(self):
        self.pre("설계"), self.post("설계"), self.pre("구현", bg=True)
        txt = "Async agent launched successfully.\nagentId: a4444444 (internal)\nsecret prompt"
        self.post("구현", bg=True, resp={"content": [{"type": "text", "text": txt}]})
        self.assertEqual(self.run_()["st"]["구현"]["ag"], ["a4444444"])
        self.post("구현", bg=True, resp={"status": "async_launched", "agentId": "a5555555"})
        self.assertEqual(self.run_()["st"]["구현"]["ag"], ["a4444444", "a5555555"])
        with open(os.path.join(self.marks, SID + ".runs.json"), encoding="utf-8") as f:
            self.assertNotIn("secret", f.read())

    def test_bg_aid_structured_first_and_boundary(self):
        f = lambda resp: H._bg_aid({"tool_response": resp})
        self.assertEqual(f({"agentId": "a6666666", "content": "agentId: a7777777"}), "a6666666")
        self.assertEqual(f({"agentId": "bad id!", "content": "agentId: a7777777"}), "a7777777")   # invalid key: fallback
        self.assertIsNone(f({"content": [{"type": "text", "text": "subagentId: a8888888"}]}))
        self.assertIsNone(f("x subagentId=a8888888"))
        self.assertEqual(f("launched\nagentId: a9999999"), "a9999999")   # JSON-dumped escape counts as a boundary
        self.assertEqual(f("agentId: a9999999"), "a9999999")

    def test_main_only_stage_flag(self):
        self.pre("설계"), self.post("설계"), self.pre("구현", tool="Bash")
        self.assertIs(self.run_()["st"]["구현"]["m"], True)   # only main's own Bash so far
        self.pre("구현")
        self.assertIs(self.run_()["st"]["구현"]["m"], False)  # a dispatch followed
        self.assertNotIn("m", self.run_()["st"]["설계"])        # dispatched first: never main-only

    def test_sendmessage_records_target_id(self):
        self.pre("설계"), self.post("설계"), self.pre("구현"), self.post("구현")
        ev = {"hook_event_name": "PreToolUse", "tool_name": "SendMessage", "session_id": SID, "cwd": self.proj,
              "tool_input": {"summary": "[pl:%s/검증] again" % N, "to": "a1234567", "message": "secret body"}}
        for to in ("a1234567", "bad id!", "a1234567"):
            ev["tool_input"]["to"] = to
            with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", io.StringIO()):
                H.main()
        st = self.run_()["st"]["검증"]
        self.assertEqual(st["ag"], ["a1234567"])   # deduped, invalid id dropped
        self.pre("리뷰")
        self.assertEqual(self.run_()["st"]["검증"]["ag"], ["a1234567"])   # _mark keeps ids
        with open(os.path.join(self.marks, SID + ".runs.json"), encoding="utf-8") as f:
            self.assertNotIn("secret", f.read())

    def test_loopback_denied_records_nothing(self):
        os.makedirs(os.path.join(self.proj, ".claude", "agents"))
        open(os.path.join(self.proj, ".claude", "agents", "sidereus-implementer.md"), "w").close()
        self.pre("설계"), self.post("설계"), self.pre("구현"), self.post("구현"), self.pre("검증"), self.post("검증")
        self.assertEqual(self.pre("구현", sub="Explore")["permissionDecision"], "deny")   # loop-back dispatch refused
        self.assertEqual((self.run_()["lb"], self.run_()["loops"]), ([], {}))

    def test_skip_denied_every_time(self):
        self.pre("설계"), self.post("설계")
        for _ in range(3):
            o = self.pre("검증")
            self.assertEqual(o["permissionDecision"], "deny")
            self.assertIn("You skipped 구현;", o["permissionDecisionReason"])
            self.assertIn("[pl-skip:sidereus-change/<stage>]", o["permissionDecisionReason"])
            self.assertNotIn("secret", o["permissionDecisionReason"])
        r = self.run_()
        self.assertEqual((r["cur"], r["skipok"]), ("설계", []))
        self.assertIsNone(self.pre("설계"))   # earlier stages never denied

    def bash(self, desc):
        return self._ev("PreToolUse", "", tool="Bash", raw=desc)

    def _past(self):
        with open(os.path.join(self.marks, SID + ".runs.json"), encoding="utf-8") as f:
            return json.load(f).get("past", {}).get(N, [])

    def _with_req(self):
        self._pipe(dict(PIPE, stages=[{"title": "요구사항", "agent": "main"}] + PIPE["stages"]))

    def test_first_stage_again_opens_new_run(self):
        self._with_req()
        self.pre("요구사항", tool="Bash")
        self.pre("요구사항", tool="Bash")   # main re-marks the first stage at cur: same run
        self.pre("설계"), self.post("설계"), self.pre("구현"), self.post("구현"), self.pre("검증"), self.post("검증")
        self.pre("구현", tool="SendMessage"), self.post("구현", tool="SendMessage")   # 검증 FAIL: declared loop-back
        self.pre("검증"), self.post("검증"), self.pre("리뷰"), self.post("리뷰")
        self.pre("구현", tool="SendMessage"), self.post("구현", tool="SendMessage")   # 리뷰 FAIL → then 재검증
        self.assertIsNone(self.pre("재검증")), self.post("재검증")
        self.assertIsNone(self.pre("라이브 검증", tool="Bash"))
        r = self.run_()
        self.assertEqual((r["t0"], r["end"], self._past()), (1000.0, 0, []))   # loop-backs stayed in one run
        self.assertEqual([(e["f"], e["g"]) for e in r["lb"]], [("검증", "구현"), ("리뷰", "구현")])
        self.t += 10
        self.assertIsNone(self.pre("요구사항", tool="Bash"))   # a new change starts
        r, past = self.run_(), self._past()
        self.assertEqual((r["t0"], set(r["st"]), r["end"]), (1010.0, {"요구사항"}, 0))
        self.assertEqual(len(past), 1)
        self.assertEqual((past[0]["end"], past[0]["st"]["라이브 검증"]["s"], len(past[0]["lb"])), (1010.0, "done", 2))
        self.assertEqual(set(past[0]), {"st", "lb", "cur", "end", "t0", "t1"})   # only what pl_runs reads (size cap)

    def test_first_stage_skip_past_it_opens_new_run(self):
        self._with_req()
        self.pre("요구사항", tool="Bash"), self.pre("설계"), self.post("설계")
        self.assertIsNone(self.bash("[pl-skip:%s/요구사항] r" % N))
        r = self.run_()
        self.assertEqual((r["st"], r["skipok"]), ({"요구사항": {"s": "skip", "t0": 1000.0, "t1": 1000.0, "n": 0}}, ["요구사항"]))
        self.assertEqual(self._past()[0]["st"]["설계"]["s"], "done")

    def test_past_runs_capped(self):
        self._with_req()
        for i in range(7):
            self.t = 1000.0 + i
            self.pre("요구사항", tool="Bash"), self.pre("설계")
        self.assertEqual([x["t0"] for x in self._past()], [1001.0, 1002.0, 1003.0, 1004.0, 1005.0])
        self.assertEqual(H.PAST_MAX, 5)

    def test_later_stage_after_last_stage_opens_new_run(self):
        self._with_req()
        self.pre("요구사항", tool="Bash"), self.pre("설계"), self.post("설계"), self.pre("구현"), self.post("구현")
        self.pre("검증"), self.post("검증"), self.pre("리뷰"), self.post("리뷰")
        self.assertIsNone(self.pre("라이브 검증", tool="Bash"))   # main's last stage: no Post, run stays open
        self.t += 10
        o = self.pre("설계")   # a new request starting at stage 2: old run closed, the new run wants 요구사항 declared
        self.assertEqual(o["permissionDecision"], "deny")
        self.assertIn("You skipped 요구사항;", o["permissionDecisionReason"])
        past = self._past()
        self.assertEqual((len(past), past[0]["end"], past[0]["st"]["라이브 검증"]["s"]), (1, 1010.0, "done"))
        self.assertIsNone(self.bash("[pl-skip:%s/요구사항] r" % N))
        self.assertIsNone(self.pre("설계"))
        r = self.run_()
        self.assertEqual((r["t0"], r["cur"], r["end"], len(self._past())), (1010.0, "설계", 0, 1))
        self.assertEqual({k: v["s"] for k, v in r["st"].items()}, {"요구사항": "skip", "설계": "run"})

    def test_loop_back_mid_run_keeps_run(self):
        self._with_req()
        self.pre("요구사항", tool="Bash"), self.to_review()
        self.assertIsNone(self.pre("구현", tool="SendMessage"))   # 검증 onFail goto 구현
        r = self.run_()
        self.assertEqual((r["t0"], r["cur"], r["st"]["검증"]["s"], self._past()), (1000.0, "구현", "back", []))

    def test_declared_skip_passes_and_records(self):
        self.pre("설계"), self.post("설계")
        self.assertIsNone(self.bash("[pl-skip:%s/구현] secret reason" % N))
        self.assertIsNone(self.pre("검증"))
        r = self.run_()
        self.assertEqual((r["cur"], r["skipok"]), ("검증", ["구현"]))
        self.assertEqual(r["st"]["구현"], {"s": "skip", "t0": 1000.0, "t1": 1000.0, "n": 0})
        self.assertEqual(r["st"]["설계"]["s"], "done")
        self.assertEqual((r["st"]["검증"]["s"], r["st"]["검증"]["n"]), ("run", 1))
        with open(os.path.join(self.marks, SID + ".runs.json"), encoding="utf-8") as f:
            self.assertNotIn("secret", f.read())

    def _main_first(self):
        self._pipe(dict(PIPE, stages=[{"title": "요구사항", "agent": "main"}] + PIPE["stages"]))

    def test_main_first_stage_opens_run_from_bash_mark(self):
        self._main_first()
        self.assertIsNone(self.bash("[pl:%s/요구사항] pin the request" % N))
        r = self.run_()
        self.assertEqual((r["cur"], r["st"]["요구사항"]["m"]), ("요구사항", True))
        self.assertIsNone(self.pre("설계"))
        r = self.run_()
        self.assertEqual((r["cur"], r["st"]["요구사항"]["s"]), ("설계", "done"))

    def test_main_first_stage_unmarked_denies_next(self):
        self._main_first()
        o = self.pre("설계")
        self.assertEqual(o["permissionDecision"], "deny")
        self.assertIn("You skipped 요구사항;", o["permissionDecisionReason"])

    def test_first_stage_skip_denied_on_new_run(self):
        o = self.pre("구현")
        self.assertEqual(o["permissionDecision"], "deny")
        self.assertIn("You skipped 설계;", o["permissionDecisionReason"])
        self.assertFalse(os.path.exists(os.path.join(self.marks, SID + ".runs.json")) and self.run_()["cur"])

    def test_declared_first_stage_skip_allows_jump(self):
        self.assertIsNone(self.bash("[pl-skip:%s/설계] reason" % N))
        self.assertIsNone(self.pre("구현"))
        r = self.run_()
        self.assertEqual((r["cur"], r["st"]["설계"]["s"]), ("구현", "skip"))

    def test_skip_decl_then_later_stage_denies_unrun_first(self):
        self.assertIsNone(self.bash("[pl-skip:%s/구현] reason" % N))   # opens the run with cur ""
        o = self.pre("검증")
        self.assertEqual(o["permissionDecision"], "deny")
        self.assertIn("You skipped 설계;", o["permissionDecisionReason"])
        self.assertEqual(self.run_()["cur"], "")

    def _commit(self, stage):
        ev = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": SID, "cwd": self.proj,
              "tool_input": {"command": "git commit -m x", "description": "[pl:%s/%s] commit" % (N, stage)}}
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", out):
            H.main()
        v = out.getvalue()
        return json.loads(v)["hookSpecificOutput"] if v else None

    def _rework_open(self):
        """Run passed 리뷰, then a resumed implementer put it back at 구현 (still open)."""
        self.to_review()
        self.pre("리뷰"), self.post("리뷰")
        self.pre("구현", tool="SendMessage")
        self.assertEqual(self.run_()["cur"], "구현")

    def test_denied_commit_keeps_run_and_skips_converge(self):
        self._rework_open()
        t0 = self.run_()["t0"]
        o = self._commit("라이브 검증")
        self.assertIn("You skipped 검증, 리뷰;", o["permissionDecisionReason"])
        self.assertEqual(self.run_()["end"], 0)   # the denied commit never ran: run stays open
        self.assertIsNone(self.bash("[pl-skip:%s/구현] r" % N))   # behind cur: no-op (the first stage would open a new run)
        self.assertEqual((self.run_()["t0"], self.run_()["skipok"]), (t0, []))
        self.assertEqual(self._commit("라이브 검증")["permissionDecision"], "deny")
        for s in ("검증", "리뷰"):
            self.assertIsNone(self.bash("[pl-skip:%s/%s] r" % (N, s)))
        self.t += 5
        self.assertIsNone(self._commit("라이브 검증"))
        r = self.run_()
        self.assertEqual((r["t0"], r["skipok"], r["end"]), (t0, ["검증", "리뷰"], 1005.0))
        self.assertEqual((r["st"]["설계"]["s"], r["st"]["리뷰"]["s"], r["st"]["라이브 검증"]["s"]), ("done", "back", "done"))   # 리뷰 ran: the skip keeps its outcome

    def test_skip_keeps_a_stage_that_already_ran(self):
        # A [pl-skip:] after a loop-back must not erase the earlier pass of 검증 / 리뷰 (state, t0, n).
        self._rework_open()
        before = {s: dict(self.run_()["st"][s]) for s in ("검증", "리뷰")}
        self.t += 50
        for s in ("검증", "리뷰"):
            self.assertIsNone(self.bash("[pl-skip:%s/%s] r" % (N, s)))
        r = self.run_()
        self.assertEqual(r["skipok"], ["검증", "리뷰"])   # the jump guard still lets the run move on
        self.assertEqual({s: r["st"][s] for s in ("검증", "리뷰")}, before)
        self.assertEqual((before["검증"]["s"], before["리뷰"]["s"], before["검증"]["n"]), ("done", "back", 1))

    def test_skip_ahead_attaches_to_open_run(self):
        self._rework_open()
        t0 = self.run_()["t0"]
        for s in ("검증", "리뷰"):
            self.assertIsNone(self.bash("[pl-skip:%s/%s] r" % (N, s)))
        self.assertEqual((self.run_()["t0"], self.run_()["cur"], self.run_()["skipok"]), (t0, "구현", ["검증", "리뷰"]))
        self.assertIsNone(self.pre("라이브 검증", tool="Bash"))

    def test_skipped_return_stage_starts_the_jump_check(self):
        # Review loop-back (then 재검증), skip 재검증: 검증/리뷰 already ran, so 라이브 검증 is the plain next.
        self.to_review()
        self.pre("리뷰"), self.post("리뷰")
        self.pre("구현", tool="SendMessage"), self.post("구현", tool="SendMessage")
        before = {s: dict(self.run_()["st"][s]) for s in ("검증", "리뷰")}
        self.assertIsNone(self.bash("[pl-skip:%s/재검증] r" % N))
        self.assertIsNone(self.pre("라이브 검증"))
        r = self.run_()
        self.assertEqual((r["deny"], r["cur"]), (0, "라이브 검증"))
        self.assertEqual({s: r["st"][s] for s in ("검증", "리뷰")}, before)

    def test_loop_back_clears_round_one_skip(self):
        # 리뷰 skipped in round 1, then 검증 FAIL → 구현: round 2 must run 리뷰 again or re-declare the skip.
        self.to_review()
        self.pre("검증")
        self.assertIsNone(self.bash("[pl-skip:%s/리뷰] r" % N))
        self.assertEqual(self.run_()["skipok"], ["리뷰"])
        self.pre("구현", tool="SendMessage"), self.post("구현", tool="SendMessage")
        self.assertEqual(self.run_()["skipok"], [])
        self.pre("검증"), self.post("검증")
        o = self.pre("라이브 검증")
        self.assertEqual(o["permissionDecision"], "deny")
        self.assertIn("You skipped 리뷰;", o["permissionDecisionReason"])

    def test_declared_goto_drops_skips_from_the_goto_stage(self):
        self.to_review()
        self.assertIsNone(self.bash("[pl-skip:%s/라이브 검증] r" % N))
        self.pre("리뷰")
        self.pre("구현", tool="SendMessage")   # 리뷰 onFail goto 구현, then 재검증
        r = self.run_()
        self.assertEqual((r["cur"], r["ret"]), ("구현", "재검증"))
        self.assertEqual([x for x in r["skipok"] if H._idx(PIPE["stages"], x) >= 1], [])

    def test_skipped_verify_without_then_still_denies(self):
        # 검증 FAIL loop-back has no `then`: skipping 검증 must not excuse 리뷰.
        self.pre("설계"), self.post("설계"), self.pre("구현"), self.post("구현")
        self.pre("검증"), self.post("검증")
        self.pre("구현", tool="SendMessage"), self.post("구현", tool="SendMessage")
        self.assertIsNone(self.bash("[pl-skip:%s/검증] r" % N))
        o = self.pre("라이브 검증")
        self.assertEqual(o["permissionDecision"], "deny")
        self.assertIn("You skipped 리뷰;", o["permissionDecisionReason"])   # 재검증 is onlyOnJump: never listed

    def test_skip_after_idle_opens_fresh_run(self):
        self.pre("설계"), self.post("설계")
        self.t += H.IDLE_S + 1
        self.assertIsNone(self.bash("[pl-skip:%s/설계] r" % N))
        r = self.run_()
        self.assertEqual((r["t0"], r["cur"], r["skipok"]), (self.t, "", ["설계"]))
        self.assertIn("You skipped 구현;", self.pre("검증")["permissionDecisionReason"])

    def test_skip_after_commit_opens_fresh_run(self):
        self.pre("설계"), self.post("설계"), self.pre("구현")
        self._cmd("git commit -m x")
        self.t += 5
        self.assertIsNone(self.bash("[pl-skip:%s/설계] r" % N))
        self.assertEqual((self.run_()["t0"], self.run_()["end"]), (1005.0, 0))
        self.assertIsNone(self.pre("구현"))

    def test_closed_last_stage_bash_extends_t1(self):
        self.to_review()
        self.pre("리뷰"), self.post("리뷰")
        self.pre("라이브 검증", tool="Bash")
        self.t += 30
        self.pre("라이브 검증", tool="Bash")
        r = self.run_()
        s = r["st"]["라이브 검증"]
        self.assertEqual((s["s"], s["t0"], s["t1"], r["end"], r["t0"], r["cur"]), ("run", 1000.0, 1030.0, 0, 1000.0, "라이브 검증"))
        self.t += 10
        self._cmd("git commit -m x")   # the commit closes it
        self.t += 10
        self.pre("라이브 검증", tool="Bash")   # Bash after the commit: never re-lit, no new run
        r = self.run_()
        self.assertEqual((r["st"]["라이브 검증"]["s"], r["end"], r["t0"]), ("done", 1040.0, 1000.0))

    def test_untagged_sendmessage_during_run(self):
        msg = lambda raw: self._ev("PreToolUse", "", tool="SendMessage", raw=raw)
        self.assertIsNone(msg("plain"))                      # no run
        self.pre("설계")
        o = msg("plain secret")
        self.assertEqual(o["permissionDecision"], "deny")
        self.assertIn("[pl:sidereus-change/<stage>]", o["permissionDecisionReason"])
        self.assertNotIn("secret", o["permissionDecisionReason"])
        self.assertIsNone(msg("[pl:-] side note"))
        self.assertIsNone(self.pre("설계", tool="SendMessage"))   # tagged passes
        self.t += H.LOST_S + 1
        self.assertIsNone(msg("plain"))                      # run untouched for 45 min
        self.assertIsNone(self._ev("PreToolUse", "", tool="Agent", raw="plain"))   # Agent left to pl_mark nudge

    def test_bash_last_stage_stays_open_until_commit(self):
        msg = lambda: self._ev("PreToolUse", "", tool="SendMessage", raw="plain")
        self.to_review()
        self.pre("리뷰"), self.post("리뷰")
        self.assertIsNone(self.pre("라이브 검증", tool="Bash"))
        r = self.run_()
        self.assertEqual((r["end"], r["cur"], r["st"]["라이브 검증"]["s"]), (0, "라이브 검증", "run"))
        self.assertIsNone(msg())                              # main-run tail: untagged SendMessage passes
        self.t += 5
        self.pre("라이브 검증", tool="Bash")                  # more Bash of that stage: same run
        self.assertEqual((self.run_()["t0"], self.run_()["end"]), (1000.0, 0))
        self.assertIsNone(self.pre("구현", tool="SendMessage"))   # a backward move still works on the same run
        self.assertEqual(self.run_()["cur"], "구현")
        self.assertIsNotNone(msg())                           # no longer the tail: untagged SendMessage denied

    def test_bash_end_marker_closes_run(self):
        self.pre("설계"), self.post("설계"), self.pre("구현")
        self.assertIsNotNone(self._ev("PreToolUse", "", tool="SendMessage", raw="plain"))
        self.assertIsNone(self.bash("[pl-end:%s/구현]" % N))
        r = self.run_()
        self.assertEqual((r["end"], r["st"]["구현"]["s"]), (1000.0, "done"))
        self.assertIsNone(self._ev("PreToolUse", "", tool="SendMessage", raw="plain"))

    def test_shell_end_marker_closes_last_stage(self):
        for t in ("설계", "구현", "검증", "리뷰"):
            self.stage(t)
        self.assertEqual(self.stage("라이브 검증")["additionalContext"], "Run complete: restart · commit")
        self.assertEqual(self.run_()["end"], 1000.0)

    def test_agent_mismatch_denied(self):
        os.makedirs(os.path.join(self.proj, ".claude", "agents"))
        open(os.path.join(self.proj, ".claude", "agents", "sidereus-designer.md"), "w").close()
        o = self.pre("설계", sub="general-purpose")
        self.assertEqual(o["permissionDecision"], "deny")
        self.assertIn("expects subagent_type sidereus-designer;", o["permissionDecisionReason"])
        self.assertFalse(os.path.exists(os.path.join(self.marks, SID + ".runs.json")))   # refused call not recorded
        self.assertIsNotNone(self.pre("설계", sub="Explore"))
        self.assertIsNone(self.pre("설계"))

    def test_missing_agent_accepts_general_purpose(self):
        self.assertIsNone(self.pre("설계", sub="general-purpose"))
        self.assertIsNone(self._ev("PreToolUse", "설계", sub="", raw="[pl:%s/설계] x" % N))   # omitted = general-purpose
        o = self.pre("설계", sub="Explore")
        self.assertIn("general-purpose also accepted", o["permissionDecisionReason"])
        os.makedirs(os.path.join(self.user, "agents"))
        open(os.path.join(self.user, "agents", "sidereus-designer.md"), "w").close()   # user-level install counts
        self.assertIsNotNone(self.pre("설계", sub="general-purpose"))

    def test_model_mismatch_and_override(self):
        self.pre("설계"), self.post("설계"), self.pre("구현"), self.post("구현")
        o = self.pre("검증", model="opus")
        self.assertIn("and model sonnet", o["permissionDecisionReason"])
        self.assertIn("model opus", o["permissionDecisionReason"])
        self.assertIsNotNone(self._ev("PreToolUse", "검증", raw="[pl:%s/검증] x" % N, model=""))   # omitted
        self.assertIsNone(self.bash("[pl-model:%s/검증=opus] secret" % N))
        self.assertEqual(self.run_()["models"], {"검증": "opus"})
        self.assertIsNotNone(self.pre("검증"))                # stage default no longer matches
        self.assertIsNone(self.pre("검증", model="opus"))
        self.assertIsNone(self.pre("구현", tool="SendMessage"))   # SendMessage: no agent/model check

    def test_denies_counted_on_open_run(self):
        self.assertEqual(self.pre("설계", sub="Explore", text=" secret-a")["permissionDecision"], "deny")   # no open run: nothing written
        self.assertFalse(os.path.exists(os.path.join(self.marks, SID + ".runs.json")))
        self.assertIsNone(self.pre("설계", text=" secret-b"))
        self.assertEqual((self.run_()["deny"], self.run_()["dl"]), (0, []))
        self.post("설계")
        self.assertEqual(self.pre("검증", text=" secret-c")["permissionDecision"], "deny")                  # jump
        self.assertEqual(self.pre("구현", sub="Explore", text=" secret-d")["permissionDecision"], "deny")   # agent
        self.assertEqual(self._ev("PreToolUse", "", tool="SendMessage", raw="secret-e")["permissionDecision"], "deny")
        self.assertEqual(self.pre("없는 단계secret", text=" secret-f")["permissionDecision"], "deny")
        self.assertEqual(self.bash("[pl-skip:%s/secret-g] secret-h" % N)["permissionDecision"], "deny")
        self.pre("구현"), self.post("구현")
        self.assertEqual(self.pre("검증", model="opus", text=" secret-i")["permissionDecision"], "deny")   # model
        r = self.run_()
        self.assertEqual(r["deny"], 6)
        self.assertEqual([(e["c"], e["title"]) for e in r["dl"]],
                         [("jump", "검증"), ("agent", "구현"), ("tag", "설계"), ("stage", ""), ("stage", ""), ("model", "검증")])
        self.assertTrue(all(sorted(e) == ["c", "t", "title"] for e in r["dl"]))
        self.assertEqual(r["cur"], "구현")   # a deny never moves the run
        with open(os.path.join(self.marks, SID + ".runs.json"), encoding="utf-8") as f:
            self.assertNotIn("secret", f.read())

    def test_deny_log_capped(self):
        self.pre("설계"), self.post("설계")
        for i in range(H.DL_MAX + 5):
            self.t += 1
            self.pre("검증")
        r = self.run_()
        self.assertEqual((r["deny"], len(r["dl"]), r["dl"][-1]["t"]), (H.DL_MAX + 5, H.DL_MAX, self.t))

    def test_unknown_title_denied(self):
        o = self.pre("없는 단계")
        self.assertEqual(o["permissionDecision"], "deny")
        self.assertIn("stages: 설계 → 구현 → 검증", o["permissionDecisionReason"])
        self.assertIsNotNone(self.bash("[pl-skip:%s/없는 단계] x" % N))
        self.assertIsNone(self.post("없는 단계"))
        self.assertIsNone(self._ev("PreToolUse", "", raw="[pl:other/설계] x"))   # no such pipeline: silent
        self.assertFalse(os.path.exists(self.marks))

    def test_onfail_loop_marks_back_then_done(self):
        self.to_review()
        self.pre("구현", tool="SendMessage")
        st = self.run_()["st"]
        self.assertEqual((st["검증"]["s"], st["구현"]["s"], st["구현"]["n"]), ("back", "run", 2))   # loop-back is not a failure
        self.assertEqual(sorted(set(k for v in st.values() for k in v)), ["n", "s", "t0", "t1"])
        self.post("구현", tool="SendMessage"), self.pre("검증"), self.post("검증")
        self.assertEqual(self.run_()["st"]["검증"]["s"], "done")

    def test_last_stage_ends_and_new_run_opens(self):
        self.to_review()
        self.pre("리뷰"), self.post("리뷰")
        self.pre("라이브 검증")
        t = self.post("라이브 검증")
        self.assertEqual(t, "Run complete: restart · commit")
        self.assertEqual(self.run_()["end"], 1000.0)
        self.t = 2000.0
        self.assertIsNone(self.pre("설계"))
        r = self.run_()
        self.assertEqual((r["t0"], r["cur"], r["end"], r["done"]), (2000.0, "설계", 0, []))

    def test_lost_slice_and_denied_pre_do_not_block(self):
        self.pre("설계"), self.post("설계")
        self.assertIsNotNone(self.pre("검증"))           # skip deny
        self.assertNotIn("검증", self.run_()["inflight"])  # denied call did not count
        self.pre("구현"), self.pre("구현"), self.pre("구현")   # one slice is refused and never gets a Post
        self.assertIsNone(self.post("구현"))
        self.t += H.LOST_S + 60
        self.assertIn("PASS → next: [pl:sidereus-change/검증]", self.post("구현"))

    def test_idle_run_restarts(self):
        self.pre("설계"), self.post("설계")
        self.t += H.IDLE_S + 1
        self.assertEqual(self.pre("라이브 검증")["permissionDecision"], "deny")   # new run mid-way: earlier stages unrun
        self.assertIsNone(self.pre("설계"))
        self.assertEqual(self.run_()["t0"], self.t)

    def test_background_keeps_inflight(self):
        self.pre("설계")
        t = self.post("설계", bg=True)
        self.assertTrue(t.startswith("When it finishes, next: [pl:sidereus-change/구현]"))
        self.assertEqual(self.run_()["inflight"], {"설계": 0})   # the bg Post is the only one it gets
        self.pre("구현")
        t = self.post("구현", resp={"status": "async_launched", "agentId": "a1"})
        self.assertTrue(t.startswith("When it finishes"))
        self.pre("구현", tool="SendMessage")
        t = self.post("구현", tool="SendMessage", resp={"success": True, "message": "Resuming agent a1"})
        self.assertTrue(t.startswith("When it finishes"))

    def test_bash_sets_cur_only(self):
        self.pre("설계", tool="Bash")
        r = self.run_()
        self.assertEqual((r["cur"], r["inflight"]), ("설계", {}))
        self.assertIsNone(self.post("설계", tool="Bash"))

    def test_apply_off_silent(self):
        with open(self.cfg, "w") as f:
            json.dump({"pipeline_apply": {"projects": {self.proj: "off"}}}, f)
        self.assertIsNone(self.pre("설계"))
        self.assertIsNone(self.post("설계"))
        self.assertFalse(os.path.exists(self.marks))

    def test_bad_pipeline_silent(self):
        self._pipe("{not json")
        self.assertIsNone(self.pre("설계"))
        self.assertIsNone(self.post("설계"))
        self.assertIsNone(self._ev("PreToolUse", "", tool="SendMessage", raw="plain"))
        self.assertFalse(os.path.exists(self.marks))

    def test_plm_of_ignores_runs_file(self):
        self.pre("설계")
        ag = sidereus("agents")
        with mock.patch.object(ag, "PLM_DIR", self.marks):
            self.assertIsNone(ag.plm_of(SID, 1000))

    def test_no_platform_bytes_identical(self):
        ev = json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Agent", "session_id": SID, "cwd": self.proj,
                         "tool_input": {"description": "[pl:%s/설계]" % N}})
        outs = []
        for argv in ([], ["--platform", "cc"]):
            self.pre("설계")
            out = io.StringIO()
            with mock.patch("sys.stdin", io.StringIO(ev)), mock.patch("sys.stdout", out):
                H.main(argv)
            outs.append(out.getvalue())
        want = json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext":
                           "PASS → next: [pl:sidereus-change/구현] · agent sidereus-implementer · gate scripts/check.sh --fast"}}, ensure_ascii=False)
        self.assertEqual(outs, [want, want])

    def sh(self, cmd, event, plat="gemini", tool="run_shell_command"):
        ev = {"hook_event_name": event, "tool_name": tool, "session_id": SID, "cwd": self.proj,
              "tool_input": {"command": cmd}}
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", out):
            H.main(["--platform", plat])
        return out.getvalue()

    def stage(self, title, fail=False, plat="gemini"):
        self.assertEqual(self.sh('echo "[pl:%s/%s] secret"' % (N, title), "BeforeTool", plat), "")
        v = self.sh("echo '[pl-end:%s/%s%s]'" % (N, title, "|fail" if fail else ""), "AfterTool", plat)
        return json.loads(v)["hookSpecificOutput"] if v else None

    def test_shell_pass_hand_off(self):
        o = self.stage("설계")
        self.assertEqual(o["hookEventName"], "PostToolUse")
        self.assertEqual(o["additionalContext"],
                         "PASS → next: [pl:sidereus-change/구현] · agent sidereus-implementer · gate scripts/check.sh --fast")
        self.stage("구현")
        t = self.stage("검증")["additionalContext"]
        self.assertIn("PASS → next: [pl:sidereus-change/리뷰]", t)
        self.assertNotIn("FAIL", t)                     # result is known: PASS only
        with open(os.path.join(self.marks, SID + ".runs.json"), encoding="utf-8") as f:
            self.assertNotIn("secret", f.read())

    def test_shell_fail_counts_round(self):
        self.stage("설계"), self.stage("구현")
        t = self.stage("검증", fail=True)["additionalContext"]
        self.assertEqual(t, "FAIL (round 1/2) → next: [pl:sidereus-change/구현] · agent sidereus-implementer · gate scripts/check.sh --fast")
        r = self.run_()
        self.assertEqual((r["loops"], r["ret"], r["cur"]), ({"검증": 1}, "검증", "구현"))
        self.assertEqual([(e["f"], e["g"], e["n"]) for e in r["lb"]], [("검증", "구현", 1)])   # end() fail path
        self.assertIn("PASS → next: [pl:sidereus-change/검증]", self.stage("구현")["additionalContext"])
        self.assertEqual(self.run_()["loops"], {"검증": 1})   # the loop-back start did not count again
        self.assertIn("round 2/2", self.stage("검증", fail=True)["additionalContext"])
        self.assertEqual(self.run_()["st"]["검증"]["s"], "fail")
        self.stage("구현")
        self.assertIn("round limit 2/2", self.stage("검증", fail=True)["additionalContext"])

    def test_shell_skip_still_starts(self):
        self.stage("설계")
        self.assertIn("PASS → next: [pl:sidereus-change/리뷰]", self.stage("검증")["additionalContext"])
        st = self.run_()["st"]
        self.assertEqual((st["설계"]["s"], st["구현"]["s"], st["검증"]["s"]), ("done", "skip", "done"))

    def test_shell_not_markers(self):
        self.assertEqual(self.sh('grep "[pl:%s/설계]" x' % N, "BeforeTool"), "")
        self.assertEqual(self.sh('echo "[pl:%s/설계]"' % N, "PreToolUse", plat="cc", tool="Bash"), "")
        self.assertFalse(os.path.exists(self.marks))
        self.sh('echo "[pl:%s/설계]"' % N, "BeforeTool")
        self.assertEqual(self.sh("echo [pl-end:%s/설계]" % N, "AfterTool", plat="nope"), "")
        self.assertEqual(self.run_()["done"], [])         # unknown platform: no effect
        self.assertEqual(self.sh("echo [pl-end:%s/설계]" % N, "PostToolUse", plat="cursor"), "")   # no hand-off
        self.assertEqual(self.run_()["done"], ["설계"])   # but the run advances

    def test_codex_shell(self):
        self.assertEqual(self.sh(": [pl:%s/설계]" % N, "PreToolUse", plat="codex", tool="Bash"), "")
        v = self.sh("echo [pl-end:%s/설계]" % N, "PostToolUse", plat="codex", tool="Bash")
        self.assertIn("PASS → next", json.loads(v)["hookSpecificOutput"]["additionalContext"])

    def _poke(self, **kv):
        p = os.path.join(self.marks, SID + ".runs.json")
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        d["runs"][N].update(kv)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)

    def test_bg_post_decrements_inflight(self):
        self.pre("설계"), self.pre("설계")
        self._poke(inflight={"설계": 2, "other": 3})
        self.post("설계")
        self.post("설계", bg=True)
        r = self.run_()
        self.assertEqual(r["inflight"], {"설계": 0, "other": 3})
        self.assertNotIn("설계", r["done"])   # a bg Post never marks done

    def test_dispatch_on_other_stage_counts_only_it(self):
        self.pre("설계"), self.post("설계"), self.pre("구현")
        self._poke(inflight={"구현": 1, "설계": 4})
        self.pre("설계", tool="SendMessage")
        self.assertEqual(self.run_()["inflight"], {"설계": 1})

    def bash(self, raw):
        return self._ev("PreToolUse", "", tool="Bash", raw=raw)

    def test_untagged_bash_nudge(self):
        self.assertIsNone(self.bash("ls"))   # no open run
        self.pre("설계")
        o = self.bash("ls")
        self.assertNotIn("permissionDecision", o)
        self.assertIn("[pl:%s/설계]" % N, o["additionalContext"])
        self.assertIn("[pl:-]", o["additionalContext"])
        self.t += 600 - 1
        self.assertIsNone(self.bash("ls"))   # rate-limited
        self.t += 2
        self.assertIn("additionalContext", self.bash("ls"))
        self.t += 700
        self.assertIsNone(self.bash("[pl:-] ls"))
        self.assertIsNone(self.bash("[pl-skip:nope/x] r"))
        self.assertIsNone(self.bash("[pl:%s/설계] ls" % N))
        self.assertIn("additionalContext", self.bash("ls"))   # those three did not use the window

    def test_no_nudge_for_subagent_bash(self):
        self.pre("설계")
        ev = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": SID, "cwd": self.proj,
              "agent_id": "a97015b8e84f092f4", "tool_input": {"command": "ls", "description": "ls"}}
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", out):
            H.main()
        self.assertEqual(out.getvalue(), "")
        self.assertIn("additionalContext", self.bash("ls"))   # main's window is still unspent

    def test_nudge_inside_window_takes_no_lock(self):
        self.pre("설계"), self.bash("ls")
        with mock.patch.object(H, "_Lock", wraps=H._Lock) as lk:
            self.assertIsNone(self.bash("ls"))
        self.assertFalse(lk.called)

    def test_nudge_silent_when_save_fails(self):
        self.pre("설계")

        def boom(path, d):
            raise OSError("disk")
        with mock.patch.object(H, "_save", boom):
            self.assertIsNone(self.bash("ls"))
        self.assertIn("additionalContext", self.bash("ls"))   # nothing saved: the next Bash still nudges

    def test_nudge_silent_when_lock_held(self):
        self.pre("설계")
        with mock.patch.object(H, "LOCK_WAIT_S", 0.0):
            open(os.path.join(self.marks, SID + ".runs.json.lock"), "w").close()
            self.assertIsNone(self.bash("ls"))

    def _whylog(self):
        os.makedirs(self.marks, exist_ok=True)   # _why never creates the dir
        p = os.path.join(self.marks, SID + ".why")
        return open(p, encoding="utf-8").read() if os.path.exists(p) else ""

    def test_why_logs_no_project_metadata_only(self):
        self._whylog()
        with mock.patch.object(H, "_project", lambda *a: None):
            self.assertIsNone(self.pre("설계"))
        w = self._whylog()
        self.assertRegex(w, r"^\S+ PreToolUse Agent no-project\n$")
        self.assertNotIn("secret", w)

    def test_why_silent_for_untagged_calls(self):
        self._whylog()
        with mock.patch.object(H, "_project", lambda *a: None):
            self._ev("PreToolUse", "", raw="plain task")
            self._ev("PreToolUse", "", tool="Bash", raw="ls")
            self._ev("PostToolUse", "", raw="plain task")
        self.assertEqual(self._whylog(), "")

    def test_why_logs_exception_type(self):
        self._whylog()
        def boom(*a):
            raise KeyError("x secret")
        with mock.patch.object(H, "_stages", boom):
            with self.assertRaises(KeyError):   # __main__ swallows it; main() re-raises after logging
                self.pre("설계")
        w = self._whylog()
        self.assertIn(" exc:KeyError\n", w)
        self.assertNotIn("secret", w)

    def test_why_log_capped(self):
        self._whylog()
        with mock.patch.object(H, "WHY_MAX", 2000), mock.patch.object(H, "_project", lambda *a: None):
            for _ in range(300):
                self.pre("설계")
        self.assertLessEqual(len(self._whylog().encode()), 2000 + 100)
        self.assertTrue(self._whylog().endswith("no-project\n"))

    def test_why_never_raises(self):
        with mock.patch.object(H, "MARK_DIR", os.path.join(self.tmp, "f")):
            open(os.path.join(self.tmp, "f"), "w").close()   # MARK_DIR is a file: makedirs fails
            H._why({"session_id": SID}, "x")


class AwayHome(unittest.TestCase):
    """A session whose cwd has no pipelines still records its run in the known project that owns the tagged name."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.marks = os.path.join(self.tmp, "plmark")
        self.cwd = os.path.join(self.tmp, "triage")
        os.makedirs(self.cwd)
        self.a, self.b = self._own("agent"), self._own("origin")
        self.cj = os.path.join(self.tmp, ".claude.json")
        self._known([self.cwd, self.a, self.b])
        self.tp = os.path.join(self.tmp, "t.jsonl")
        with open(self.tp, "w", encoding="utf-8") as f:   # the session only `cd`s into ~/agent
            f.write(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "input": {"command": "cd ~/agent/docs && ls"}}]}}) + "\n")
        for k, v in (("MARK_DIR", self.marks), ("CONFIG_PATH", os.path.join(self.tmp, "cfg.json")), ("_now", lambda: 1000.0),
                     ("CLAUDE_DIR", os.path.join(self.tmp, "uc")), ("HOME_DIR", self.tmp), ("DATA_DIR", self.tmp),
                     ("DIRS_DIR", os.path.join(self.tmp, "plbrief")), ("CLAUDE_JSON", self.cj),
                     ("PROJ_STORE", os.path.join(self.tmp, "pp.json"))):
            p = mock.patch.object(H, k, v)
            p.start()
            self.addCleanup(p.stop)

    def _own(self, name):
        d = os.path.join(self.tmp, name)
        os.makedirs(os.path.join(d, ".claude", "pipelines"))
        with open(os.path.join(d, ".claude", "pipelines", N + ".json"), "w", encoding="utf-8") as f:
            json.dump(PIPE, f, ensure_ascii=False)
        return d

    def _known(self, ps):
        with open(self.cj, "w", encoding="utf-8") as f:
            json.dump({"projects": {p: {} for p in ps}}, f)

    def _proj(self, tp=True):
        ev = {"hook_event_name": "PreToolUse", "tool_name": "Agent", "session_id": SID, "cwd": self.cwd,
              "tool_input": {"description": "[pl:%s/설계] x" % N, "subagent_type": "sidereus-designer"}}
        if tp:
            ev["transcript_path"] = self.tp
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", io.StringIO()):
            H.main()
        try:
            with open(os.path.join(self.marks, SID + ".runs.json"), encoding="utf-8") as f:
                return json.load(f)["runs"][N]["proj"]
        except OSError:
            return None

    def test_touched_owner_wins(self):
        self.assertEqual(self._proj(), self.a)

    def test_ambiguous_without_transcript_records_nothing(self):
        self.assertIsNone(self._proj(tp=False))

    def test_sole_known_owner(self):
        self._known([self.cwd, self.b])
        self.assertEqual(self._proj(tp=False), self.b)


if __name__ == "__main__":
    unittest.main()
