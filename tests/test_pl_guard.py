"""Hook hooks/pl_guard.py (via hooks/pl_flow.py): pipeline guards. Tmp dirs only, fixed clock, no live files."""
import importlib.util
import io
import json
import os
import re
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus   # noqa: F401  (sets MAILBOX_DIR to a tmp dir before any import)
from sidereus import pipeline_schema

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _mod(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


H = _mod("pl_flow_guard_t", "hooks/pl_flow.py")
G = _mod("pl_guard_t", "hooks/pl_guard.py")

N = "sidereus-change"
SID = "sess-0002"
PIPE = {"v": 1, "name": N, "guards": {"requireGates": ["검증"], "maxLoopBacks": 1}, "stages": [
    {"title": "설계", "agent": "sidereus-designer"},
    {"title": "구현", "agent": "sidereus-implementer", "gate": "scripts/check.sh --fast"},
    {"title": "검증", "agent": "sidereus-verifier", "gate": "scripts/check.sh --full", "onFail": {"goto": "구현", "max": 2}},
    {"title": "리뷰", "agent": "sidereus-reviewer"}]}


class Guard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(os.path.join(self.proj, ".git"))
        os.makedirs(os.path.join(self.proj, ".claude", "pipelines"))
        self.pipe(PIPE)
        self.marks = os.path.join(self.tmp, "plmark")
        os.makedirs(self.marks)
        self.evf = os.path.join(self.tmp, "evidence.jsonl")
        self.t = 1000.0
        for k, v in (("MARK_DIR", self.marks), ("CONFIG_PATH", os.path.join(self.tmp, "cfg.json")), ("_now", lambda: self.t),
                     ("CLAUDE_DIR", os.path.join(self.tmp, "u")), ("HOME_DIR", self.tmp),
                     ("DIRS_DIR", os.path.join(self.tmp, "plbrief")), ("DATA_DIR", self.tmp)):
            p = mock.patch.object(H, k, v)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(G, "EV_FILE", self.evf)
        p.start()
        self.addCleanup(p.stop)

    def pipe(self, body):
        with open(os.path.join(self.proj, ".claude", "pipelines", N + ".json"), "w", encoding="utf-8") as f:
            f.write(body if isinstance(body, str) else json.dumps(body, ensure_ascii=False))

    def runs(self, st, cur="리뷰", loops=None, **kw):
        r = dict(H._new_run(self.proj, 900.0), proj=self.proj, cur=cur, st=st, t1=990.0, loops=loops or {}, **kw)
        with open(os.path.join(self.marks, SID + ".runs.json"), "w", encoding="utf-8") as f:
            json.dump({"v": 1, "runs": {N: r}}, f, ensure_ascii=False)

    def ev(self, *rows):
        with open(self.evf, "w", encoding="utf-8") as f:
            for r in rows:
                f.write((r if isinstance(r, str) else json.dumps(dict({"v": 1, "kind": "check", "repo": os.path.realpath(self.proj)}, **r))) + "\n")

    def bash(self, cmd="git commit -m x", desc="commit"):
        return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": SID, "cwd": self.proj,
                "tool_input": {"command": cmd, "description": desc}}

    def check(self, e):
        return G.check("cc", e, H)

    DONE = {"검증": {"s": "done", "t0": 900.0, "p0": 940.0, "t1": 960.0, "n": 1}}

    def test_commit_denied_without_evidence(self):
        self.runs(self.DONE)
        why = self.check(self.bash())
        self.assertIn("검증", why)
        self.assertIn("no full evidence", why)

    def test_commit_from_powershell_tool_denied(self):
        self.runs(self.DONE)
        e = dict(self.bash(), tool_name="PowerShell")
        self.assertIn("no full evidence", self.check(e))

    def test_commit_allowed_with_rc0_after_pass_start(self):
        self.runs(self.DONE)
        self.ev({"ts": 950, "mode": "full", "rc": 0})
        self.assertIsNone(self.check(self.bash()))
        self.assertIsNone(self.check(self.bash("git -C %s commit -m x" % self.proj)))

    def test_commit_denied_later_failure(self):
        self.runs(self.DONE)
        self.ev({"ts": 950, "mode": "full", "rc": 0}, {"ts": 955, "mode": "full", "rc": 1})
        self.assertIn("rc=1", self.check(self.bash()))

    def test_commit_denied_evidence_before_pass_or_other_mode_or_repo(self):
        self.runs(self.DONE)
        self.ev({"ts": 930, "mode": "full", "rc": 0}, {"ts": 950, "mode": "fast", "rc": 0},
                {"ts": 951, "mode": "full", "rc": 0, "repo": "/elsewhere"})
        self.assertIn("검증", self.check(self.bash()))

    def test_commit_denied_when_skipped_or_not_run(self):
        self.ev({"ts": 950, "mode": "full", "rc": 0})
        self.runs({"검증": {"s": "skip", "t0": 900.0, "t1": 900.0, "n": 0}})
        self.assertIn("skipped", self.check(self.bash()))
        self.runs({})
        self.assertIn("not run", self.check(self.bash()))

    def test_commit_outside_project_or_no_run_allowed(self):
        self.runs(self.DONE)
        e = self.bash()
        e["cwd"] = self.tmp
        self.assertIsNone(self.check(e))
        self.assertIsNone(self.check(self.bash("git status")))
        self.assertIsNone(self.check(self.bash("git commit --dry-run")))
        self.runs(self.DONE, end=995.0)
        self.assertIsNone(self.check(self.bash()))

    def test_skip_of_required_stage_denied(self):
        self.runs({})
        self.assertIn("required gate", self.check(self.bash("true", "[pl-skip:%s/검증] not needed" % N)))
        self.assertIsNone(self.check(self.bash("true", "[pl-skip:%s/리뷰] not needed" % N)))

    def dispatch(self, stage, event="PreToolUse"):
        return {"hook_event_name": event, "tool_name": "SendMessage", "session_id": SID, "cwd": self.proj,
                "tool_input": {"summary": "[pl:%s/%s] fix" % (N, stage), "to": "a1"}}

    def test_loop_budget_denies_next_loopback(self):
        st = {"검증": {"s": "run", "t0": 950.0, "t1": 950.0, "n": 1}}
        self.runs(st, cur="검증")
        self.assertIsNone(self.check(self.dispatch("구현")))
        self.runs(st, cur="검증", loops={"검증": 1})
        self.assertIn("loop budget 1 reached", self.check(self.dispatch("구현")))
        self.assertIsNone(self.check(self.dispatch("리뷰")))   # moving on is not a loop-back

    def test_loop_budget_rewrites_fail_handoff(self):
        self.runs({"검증": {"s": "run", "t0": 950.0, "t1": 950.0, "n": 1}}, cur="검증", loops={"검증": 1},
                  inflight={"검증": 1})
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            G.run("cc", self.dispatch("검증", "PostToolUse"), H, H._flow)
        ctx = json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"]
        self.assertIn("FAIL → loop budget 1 reached: stop and report.", ctx)
        self.assertIn("PASS → next", ctx)
        self.assertNotIn("SendMessage the", ctx)

    def test_fail_open(self):
        self.runs(self.DONE)
        for body in ("{bad", json.dumps(dict(PIPE, guards=["x"])), json.dumps(dict(PIPE, guards={"maxLoopBacks": 99}))):
            self.pipe(body)
            self.assertIsNone(self.check(self.bash()))
        self.pipe(PIPE)
        self.ev("junk", '{"v":1,"kind":"check","repo":"%s","ts":"x","mode":"full","rc":0}' % os.path.realpath(self.proj))
        self.assertIn("검증", self.check(self.bash()))   # junk rows are no evidence, and never raise
        called = []
        with mock.patch.object(G, "check", side_effect=RuntimeError("boom")), mock.patch("sys.stdout", io.StringIO()) as out:
            G.run("cc", self.bash(), H, lambda p, e: called.append(1))
        self.assertEqual((called, out.getvalue()), ([1], ""))
        self.assertIsNone(G.check("codex", self.bash(), H))

    def stop(self, body):
        os.makedirs(os.path.join(self.tmp, "plstop"), exist_ok=True)
        with open(os.path.join(self.tmp, "plstop", SID + ".json"), "w", encoding="utf-8") as f:
            f.write(body if isinstance(body, str) else json.dumps(body))

    def saved(self):
        with open(os.path.join(self.marks, SID + ".runs.json"), encoding="utf-8") as f:
            return json.load(f)["runs"][N]

    def agent(self, stage):
        return {"hook_event_name": "PreToolUse", "tool_name": "Agent", "session_id": SID, "cwd": self.proj,
                "tool_input": {"description": "[pl:%s/%s] x" % (N, stage), "subagent_type": "sidereus-reviewer"}}

    def test_stop_denies_dispatch_and_ends_run(self):
        # R4: a stopped run's next stage dispatch is denied; the run is ended and the deny noted as «stop».
        self.runs({"검증": {"s": "run", "t0": 950.0, "t1": 950.0, "n": 1}}, cur="검증")
        self.stop({N: {"at": 995.0, "mid": "m1", "of": "req-7"}})
        why = self.check(self.agent("리뷰"))
        self.assertIn("Run %s was stopped from Sidereus (request req-7)" % N, why)
        r = self.saved()
        self.assertEqual((r["stop"], r["end"], r["st"]["검증"]["s"]), (995.0, 1000.0, "done"))
        self.assertEqual(r["dl"][-1]["c"], "stop")
        self.assertIn("stopped", self.check(self.dispatch("구현")))   # still pending: a new run cannot start
        self.assertIsNone(self.check(self.bash("true", "[pl-skip:%s/리뷰] x" % N)))   # Bash markers are not denied

    def test_stop_before_run_start_or_expired_passes(self):
        # R4: a run started after the stop, or a stale pending stop, is not affected.
        self.runs({}, cur="설계")   # t0 = 900
        self.stop({N: {"at": 800.0, "of": "r"}})
        self.assertIsNone(self.check(self.agent("리뷰")))
        self.runs({}, cur="설계", end=950.0)
        self.t = 800.0 + G.STOP_PENDING_S + 1
        self.assertIsNone(self.check(self.agent("리뷰")))
        self.t = 800.0 + G.STOP_PENDING_S
        self.assertIn("stopped", self.check(self.agent("리뷰")))

    def test_stop_rewrites_post_handoff(self):
        # R4: the returning dispatch's PASS/FAIL hand-off becomes the stop line.
        self.runs({"검증": {"s": "run", "t0": 950.0, "t1": 950.0, "n": 1}}, cur="검증", inflight={"검증": 1})
        self.stop({N: {"at": 995.0, "of": "req-7"}})
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            G.run("cc", self.dispatch("검증", "PostToolUse"), H, H._flow)
        ctx = json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(ctx, G._stop_line(N, "req-7"))

    def test_stop_marker_fail_open(self):
        # R4: a missing, broken, oversize or malformed marker never denies.
        self.runs({}, cur="설계")
        self.assertIsNone(self.check(self.agent("리뷰")))
        for body in ("{bad", "[]", json.dumps({N: {"at": "x"}}), json.dumps({N: {"at": True}}),
                     json.dumps({"other": {"at": 950.0}}), json.dumps({N: {"at": 950.0, "pad": "x" * 5000}})):
            self.stop(body)
            self.assertIsNone(self.check(self.agent("리뷰")), body[:40])
        self.stop({N: {"at": 950.0, "of": "<b>"}})
        self.assertIn("(request -)", self.check(self.agent("리뷰")))

    def test_flow_main_denies_commit_and_keeps_run_open(self):
        self.runs(self.DONE)
        with mock.patch("sys.stdin", io.StringIO(json.dumps(self.bash()))), mock.patch("sys.stdout", io.StringIO()) as out:
            H.main([])
        d = json.loads(out.getvalue())["hookSpecificOutput"]
        self.assertEqual(d["permissionDecision"], "deny")
        self.assertIn("검증", d["permissionDecisionReason"])
        with open(os.path.join(self.marks, SID + ".runs.json"), encoding="utf-8") as f:
            self.assertFalse(json.load(f)["runs"][N].get("end"))


class Modes(unittest.TestCase):
    def test_deny_codes_equal(self):
        from sidereus import harness_flow
        self.assertEqual(H.DENY_CODES, harness_flow.HF_DENY_CODES)
        self.assertIn("stop", H.DENY_CODES)

    def test_mirror_equal(self):
        self.assertEqual(G.GATE_MODES, pipeline_schema.GATE_MODES)
        with open(os.path.join(_ROOT, ".claude", "workflows", "pipeline.js"), encoding="utf-8") as f:
            m = re.search(r"^const GATE_MODES = (\[.*\])$", f.read(), re.M)
        self.assertEqual([tuple(x) for x in json.loads(m.group(1))], list(G.GATE_MODES))

    def test_gate_mode(self):
        for g, want in (("scripts/check.sh --fast", "fast"), ("bash scripts/check.sh --full", "full"),
                        ("scripts/check.sh --fastx", None), ("/usr/bin/python3 scripts/arch_checks.py --verify --last", None),
                        ("scripts/arch_checks.py --verify --category quality", None),
                        ("scripts/arch_checks.py --verify --last --category security", "checks-security"),
                        ("scripts/arch_checks.py --verify --category style", None), ("scripts/arch_checks.py --last", None),
                        ("/usr/bin/python3 scripts/arch_verify.py --last", None), (None, None)):
            self.assertEqual(G.gate_mode(g), want, g)
            self.assertEqual(pipeline_schema.gate_mode(g), want, g)


if __name__ == "__main__":
    unittest.main()
