"""Permission-prompt marker: hooks/perm_mark.py writes {sid, t}; sidereus.perm_marks.perm_rows turns it into «승인 대기». Tmp dirs only."""
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from sidereus import perm_marks as LP

_P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks", "perm_mark.py")
_spec = importlib.util.spec_from_file_location("perm_mark_hook", _P)
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)

SID = "0123abcd-0000-4000-8000-0123456789ab"
NOW = 1_800_000_000.0


class PermMark(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        for obj, k in ((H, "MARK_DIR"), (LP, "PERM_DIR")):
            p = mock.patch.object(obj, k, self.tmp)
            p.start()
            self.addCleanup(p.stop)
        self.busy = None                      # no live ps probe
        self.tp = ""                          # transcript path for _pend_ts ("" = none; never the live projects dir)
        for k, v in (("tool_busy", lambda: self.busy), ("_DEC_AT", {}), ("_pend_cache", {}),
                     ("_sid_transcript", lambda sid: self.tp)):
            p = mock.patch.object(LP, k, v)
            p.start()
            self.addCleanup(p.stop)

    def _hook(self, ev, t=NOW):
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch.object(H.time, "time", return_value=t):
            H.main()

    def _row(self, age, state="tool", blocked=""):
        return {"sid": SID, "state": state, "tool": "mcp__x__click", "ageSec": age, "blocked": blocked}

    def test_hook_stores_no_text(self):
        self._hook({"hook_event_name": "Notification", "session_id": SID, "notification_type": "permission_prompt",
                    "message": "Claude needs your permission to use SECRET", "title": "t", "cwd": "/x"})
        with open(os.path.join(self.tmp, SID + ".json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"sid": SID, "t": NOW})

    def test_hook_ignores_other_notifications_and_bad_sid(self):
        self._hook({"hook_event_name": "Notification", "session_id": SID, "notification_type": "idle_prompt"})
        self._hook({"hook_event_name": "Notification", "session_id": "../../x", "notification_type": "permission_prompt"})
        self.assertEqual(os.listdir(self.tmp), [])

    def test_marker_newer_than_activity_blocks(self):
        self._hook({"hook_event_name": "Notification", "session_id": SID, "notification_type": "permission_prompt"}, t=NOW - 10)
        out = LP.perm_rows([self._row(age=30)], now=NOW)
        self.assertEqual(out[0]["blocked"], "click waiting for approval")

    def test_activity_after_marker_clears(self):
        self._hook({"hook_event_name": "PermissionRequest", "session_id": SID}, t=NOW - 10)
        self.assertEqual(LP.perm_rows([self._row(age=2)], now=NOW)[0]["blocked"], "")

    def test_old_marker_kept_other_states_ignored(self):
        # no age cap: an unanswered prompt shows at any age while the row is still tool (process alive)
        for ago in (31 * 60, 2 * 3600, 24 * 3600):
            self._hook({"hook_event_name": "Notification", "session_id": SID, "notification_type": "permission_prompt"},
                       t=NOW - ago)
            self.assertEqual(LP.perm_rows([self._row(age=ago + 60)], now=NOW)[0]["blocked"], "click waiting for approval")
        # a dead Claude process makes the row `done`: the marker no longer applies
        self.assertEqual(LP.perm_rows([self._row(age=24 * 3600 + 60, state="done")], now=NOW)[0]["blocked"], "")
        self._hook({"hook_event_name": "Notification", "session_id": SID, "notification_type": "permission_prompt"}, t=NOW - 10)
        self.assertEqual(LP.perm_rows([self._row(age=30, state="done")], now=NOW)[0]["blocked"], "")

    def test_snapshot_rows_not_mutated(self):
        self._hook({"hook_event_name": "Notification", "session_id": SID, "notification_type": "permission_prompt"}, t=NOW - 10)
        rows = [self._row(age=30)]
        LP.perm_rows(rows, now=NOW)
        self.assertEqual(rows[0]["blocked"], "")

    def _mark(self, t=NOW - 10):
        self._hook({"hook_event_name": "Notification", "session_id": SID, "notification_type": "permission_prompt"}, t=t)

    def _wait(self, sub, age=180, state="wait"):
        return {"sid": SID, "state": state, "ageSec": age, "blocked": "", "sub": sub}

    def test_wait_row_with_quiet_sub_blocks(self):
        self._mark()
        out = LP.perm_rows([self._wait([{"lab": "x", "min": 3, "idle": 200}])], now=NOW)
        self.assertEqual(out[0]["blocked"], "subagent waiting for approval")

    def test_wait_row_sub_active_after_marker_clears(self):
        self._mark()
        self.assertEqual(LP.perm_rows([self._wait([{"lab": "x", "min": 3, "idle": 2}])], now=NOW)[0]["blocked"], "")

    def test_wait_row_sub_without_idle_ignored(self):
        self._mark()
        r = self._wait([{"lab": "x", "min": 3, "idle": 200}, {"lab": "y", "min": 1}])
        self.assertEqual(LP.perm_rows([r], now=NOW)[0]["blocked"], "")

    def test_wait_row_without_sub_ignored(self):
        self._mark()
        self.assertEqual(LP.perm_rows([self._wait([])], now=NOW)[0]["blocked"], "")

    def test_tool_row_with_subs_keeps_tool_label(self):
        self._mark()
        r = dict(self._row(age=30), sub=[{"lab": "x", "min": 3, "idle": 200}])
        self.assertEqual(LP.perm_rows([r], now=NOW)[0]["blocked"], "click waiting for approval")

    def test_done_and_gone_rows_with_sub_ignored(self):
        self._mark()
        for st in ("done", "gone"):
            r = self._wait([{"lab": "x", "min": 3, "idle": 200}], state=st)
            self.assertEqual(LP.perm_rows([r], now=NOW)[0]["blocked"], "")

    def test_blocked_at_is_marker_time(self):
        self._mark(t=NOW - 10)
        self.assertEqual(LP.perm_rows([self._row(age=30)], now=NOW)[0]["blockedAt"], int(NOW - 10))
        out = LP.perm_rows([self._wait([{"lab": "x", "min": 3, "idle": 200}])], now=NOW)
        self.assertEqual(out[0]["blockedAt"], int(NOW - 10))

    def test_prompt_unanswered_past_30_min_still_blocks(self):
        self._mark(t=NOW - 31 * 60)
        self.assertEqual(LP.perm_rows([self._row(age=40 * 60)], now=NOW)[0]["blocked"], "click waiting for approval")
        self.assertEqual(LP.perm_rows([self._row(age=60)], now=NOW)[0]["blocked"], "")   # newer activity clears

    def test_approved_long_tool_not_blocked(self):
        self._mark(t=NOW - 40 * 60)
        r = dict(self._row(age=41 * 60), otelEv="tool_decision", otelAt=int(NOW - 39 * 60))
        self.assertEqual(LP.perm_rows([r], now=NOW)[0]["blocked"], "")
        r = dict(r, otelEv="", otelAt=0)                       # OTel entry aged out: the seen decision still counts
        self.assertEqual(LP.perm_rows([r], now=NOW)[0]["blocked"], "")

    def test_decision_before_marker_keeps_blocked(self):
        self._mark(t=NOW - 31 * 60)
        r = dict(self._row(age=40 * 60), otelEv="tool_decision", otelAt=int(NOW - 32 * 60))
        self.assertEqual(LP.perm_rows([r], now=NOW)[0]["blocked"], "click waiting for approval")

    def test_running_bash_shell_not_blocked(self):
        self._mark(t=NOW - 31 * 60)
        r = dict(self._row(age=40 * 60), tool="Bash", cwd="/w/p")
        self.busy = {"/w/p": True}
        self.assertEqual(LP.perm_rows([r], now=NOW)[0]["blocked"], "")
        self.busy = {}
        self.assertEqual(LP.perm_rows([r], now=NOW)[0]["blocked"], "Bash waiting for approval")
        self.busy = {"/w/p": True}                             # a background command blurs the probe: keep the badge
        self.assertEqual(LP.perm_rows([dict(r, bgs=[{"x": 1}])], now=NOW)[0]["blocked"], "Bash waiting for approval")

    def test_subagent_decision_clears_wait_row(self):
        self._mark(t=NOW - 10)
        r = dict(self._wait([{"lab": "x", "min": 3, "idle": 200}]), otelEv="tool_result", otelAt=int(NOW - 5))
        self.assertEqual(LP.perm_rows([r], now=NOW)[0]["blocked"], "")

    def _wf(self, end, st="run", run=True):
        return dict(self._wait([]), wf=[{"id": "w", "run": run, "agents": [{"aid": "1", "st": st, "end": end}]}])

    def test_workflow_agent_waiting_blocks(self):
        self._mark(t=NOW - 10)
        out = LP.perm_rows([self._wf(int(NOW - 60))], now=NOW)
        self.assertEqual((out[0]["blocked"], out[0]["blockedAt"]), ("subagent waiting for approval", int(NOW - 10)))

    def test_workflow_agent_active_after_marker_clears(self):
        self._mark(t=NOW - 10)
        self.assertEqual(LP.perm_rows([self._wf(int(NOW - 2))], now=NOW)[0]["blocked"], "")

    def test_workflow_not_running_or_agents_done_ignored(self):
        self._mark(t=NOW - 10)
        for r in (self._wf(int(NOW - 60), run=False), self._wf(int(NOW - 60), st="done")):
            self.assertEqual(LP.perm_rows([r], now=NOW)[0]["blocked"], "")

    def test_wait_snapshot_row_not_mutated(self):
        self._mark()
        rows = [self._wait([{"lab": "x", "min": 3, "idle": 200}])]
        out = LP.perm_rows(rows, now=NOW)
        self.assertEqual(rows[0]["blocked"], "")
        self.assertIsNot(out[0], rows[0])

    def test_tool_row_blocks_until_tool_result(self):
        self._hook({"hook_event_name": "Notification", "session_id": SID, "notification_type": "permission_prompt"}, t=NOW - 10)
        out = LP.perm_rows([self._row(age=30)], now=NOW)
        self.assertEqual(out[0]["blocked"], "click waiting for approval")
        done = dict(self._row(age=30), otelEv="tool_result", otelAt=int(NOW - 5))
        self.assertEqual(LP.perm_rows([done], now=NOW)[0]["blocked"], "")

    def test_think_row_with_tool_blocks_on_newer_marker(self):
        # Parallel tool calls: one result landed (shape result -> think) while the other waits on its prompt.
        self._hook({"hook_event_name": "Notification", "session_id": SID, "notification_type": "permission_prompt"}, t=NOW - 10)
        row = dict(self._row(age=30, state="think"), tool="Bash")
        out = LP.perm_rows([row], now=NOW)[0]
        self.assertEqual((out["blocked"], out["blockedTool"], out["blockedAt"]), ("Bash waiting for approval", "Bash", int(NOW - 10)))
        # an older marker (activity after it) and a think row with no tool stay unblocked
        self.assertEqual(LP.perm_rows([dict(row, ageSec=5)], now=NOW)[0]["blocked"], "")
        self.assertEqual(LP.perm_rows([dict(row, tool="")], now=NOW)[0]["blocked"], "")
        done = dict(row, otelEv="tool_decision", otelAt=int(NOW - 5))
        self.assertEqual(LP.perm_rows([done], now=NOW)[0]["blocked"], "")


    def _transcript(self, lines):
        self.tp = os.path.join(self.tmp, "t.jsonl")
        with open(self.tp, "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(x) + "\n" for x in lines))

    @staticmethod
    def _ts(t):
        import datetime
        return datetime.datetime.utcfromtimestamp(t).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def _use(self, t, uid, name, mid="m1"):
        return {"type": "assistant", "timestamp": self._ts(t),
                "message": {"id": mid, "content": [{"type": "tool_use", "id": uid, "name": name, "input": {}}]}}

    def test_ask_row_blocks_on_prompt_opened_mid_message(self):
        # Write prompt opened at T; later Bash/AskUserQuestion lines of the same message push last activity past it.
        T = NOW - 60
        self._transcript([self._use(T - 0.3, "a", "Write"), self._use(T + 1.5, "b", "Bash"),
                          self._use(T + 6.3, "c", "AskUserQuestion")])
        self._hook({"hook_event_name": "PermissionRequest", "session_id": SID, "tool_name": "Write"}, t=T)
        row = dict(self._row(age=int(NOW - T - 6), state="ask"), tool="AskUserQuestion")
        out = LP.perm_rows([row], now=NOW)[0]
        self.assertEqual((out["blocked"], out["blockedTool"], out["blockedAt"]), ("Write waiting for approval", "Write", int(T)))
        # the same on a tool row whose newest line is the later Bash call
        out = LP.perm_rows([dict(row, state="tool", tool="Bash")], now=NOW)[0]
        self.assertEqual(out["blocked"], "Write waiting for approval")
        # a decision for Write clears it; one for another tool does not
        LP._DEC_AT[SID] = {"t": int(NOW), "tools": {"Bash": int(NOW)}}
        self.assertEqual(LP.perm_rows([row], now=NOW)[0]["blocked"], "Write waiting for approval")
        LP._DEC_AT[SID]["tools"]["Write"] = int(NOW)
        self.assertEqual(LP.perm_rows([row], now=NOW)[0]["blocked"], "")

    def test_main_bash_decision_unattributable_when_sub_wrote_after(self):
        # Main Bash prompt at T; a sub's auto-approved Bash decision lands later and must not clear the main wait.
        T = NOW - 60
        self._transcript([self._use(T - 0.3, "a", "Bash")])
        self._hook({"hook_event_name": "PermissionRequest", "session_id": SID, "tool_name": "Bash"}, t=T)
        LP._DEC_AT[SID] = {"t": int(NOW - 15), "tools": {"Bash": int(NOW - 15)}}
        row = dict(self._row(age=10), tool="Bash", cwd="/w/p")
        with mock.patch.object(LP, "_SUB_LOG", {}):
            busy = dict(row, sub=[{"aid": "s1", "lab": "x", "idle": 20}])        # sub active after the marker
            self.assertEqual(LP.perm_rows([busy], now=NOW)[0]["blocked"], "Bash waiting for approval")
            unknown = dict(row, sub=[{"aid": "s1", "lab": "x"}])                 # unknown activity: unattributable
            self.assertEqual(LP.perm_rows([unknown], now=NOW)[0]["blocked"], "Bash waiting for approval")
            self.busy = {"/w/p": True}                                           # a running shell still clears it
            self.assertEqual(LP.perm_rows([busy], now=NOW)[0]["blocked"], "")
            self.busy = None
            quiet = dict(row, sub=[{"aid": "s1", "lab": "x", "idle": 100}])      # control: sub quiet since before T
            self.assertEqual(LP.perm_rows([quiet], now=NOW)[0]["blocked"], "")
            self.assertEqual(LP.perm_rows([row], now=NOW)[0]["blocked"], "")

    def test_stale_or_answered_marker_gives_no_badge(self):
        T = NOW - 60
        self._hook({"hook_event_name": "PermissionRequest", "session_id": SID, "tool_name": "Write"}, t=T)
        row = dict(self._row(age=10, state="ask"), tool="AskUserQuestion")
        # marker older than every pending tool_use (an earlier prompt)
        self._transcript([self._use(T + 2, "a", "Write"), self._use(T + 3, "c", "AskUserQuestion")])
        self.assertEqual(LP.perm_rows([row], now=NOW)[0]["blocked"], "")
        # the Write call already has its tool_result
        self._transcript([self._use(T - 0.3, "a", "Write"),
                          {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "a"}]}},
                          self._use(T + 6, "c", "AskUserQuestion")])
        self.assertEqual(LP.perm_rows([row], now=NOW)[0]["blocked"], "")
        # an AskUserQuestion marker on an ask row is the question itself
        self._transcript([self._use(T - 0.3, "c", "AskUserQuestion")])
        self._hook({"hook_event_name": "PermissionRequest", "session_id": SID, "tool_name": "AskUserQuestion"}, t=T)
        self.assertEqual(LP.perm_rows([row], now=NOW)[0]["blocked"], "")


if __name__ == "__main__":
    unittest.main()
