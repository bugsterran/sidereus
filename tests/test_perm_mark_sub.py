"""perm_mark: a subagent's prompt gets its own <sid>.<aid>.json marker, compared with that agent's activity. Tmp dirs only."""
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
_spec = importlib.util.spec_from_file_location("perm_mark_hook_sub", _P)
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)

SID = "0123abcd-0000-4000-8000-0123456789ab"
AID = "a1b2c3d4e5f6"
NOW = 1_800_000_000.0
SUB_MSG = "subagent waiting for approval"


class PermMarkSub(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        for obj, k in ((H, "MARK_DIR"), (LP, "PERM_DIR")):
            p = mock.patch.object(obj, k, self.tmp)
            p.start()
            self.addCleanup(p.stop)
        self.busy = None
        for k, v in (("tool_busy", lambda: self.busy), ("_DEC_AT", {}), ("_SUB_LOG", {})):
            p = mock.patch.object(LP, k, v)
            p.start()
            self.addCleanup(p.stop)

    def _hook(self, ev, t=NOW - 10):
        ev = dict({"session_id": SID, "message": "SECRET", "tool_input": {"command": "SECRET"}}, **ev)
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch.object(H.time, "time", return_value=t):
            H.main()

    def _sub_req(self, aid=AID, t=NOW - 10):
        self._hook({"hook_event_name": "PermissionRequest", "agent_id": aid, "tool_name": "Bash"}, t=t)

    def _row(self, state, age=1, idle=60, now_tool="Read", **kw):
        return dict({"sid": SID, "state": state, "ageSec": age, "blocked": "", "tool": "Edit",
                     "sub": [{"lab": "x", "min": 3, "idle": idle, "aid": AID, "now": now_tool}]}, **kw)

    def test_hook_writes_sub_file_without_text(self):
        self._sub_req()
        with open(os.path.join(self.tmp, SID + "." + AID + ".json")) as f:
            raw = f.read()
        self.assertEqual(json.loads(raw), {"sid": SID, "t": NOW - 10, "k": "req", "aid": AID, "tool": "Bash"})
        self.assertNotIn("SECRET", raw)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, SID + ".json")))

    def test_hook_bad_aid_falls_back_to_session_file(self):
        self._hook({"hook_event_name": "PermissionRequest", "agent_id": "../x", "tool_name": "Bash"})
        self.assertEqual(os.listdir(self.tmp), [SID + ".json"])

    def test_main_notification_keeps_request_tool(self):
        self._hook({"hook_event_name": "PermissionRequest", "tool_name": "AskUserQuestion"}, t=NOW - 10)
        self._hook({"hook_event_name": "Notification", "notification_type": "permission_prompt"}, t=NOW - 4)
        with open(os.path.join(self.tmp, SID + ".json")) as f:
            self.assertEqual(json.load(f), {"sid": SID, "t": NOW - 4, "tool": "AskUserQuestion"})

    def test_hook_prunes_old_sub_markers(self):
        self._sub_req(aid="old", t=NOW - 8 * 86400)
        self._sub_req(aid="new", t=NOW)
        self.assertEqual(sorted(os.listdir(self.tmp)), [SID + ".new.json"])

    def test_r1_sub_badge_in_every_main_state_even_with_newer_main_activity(self):
        self._sub_req()
        for st in ("run", "think", "tool", "ask", "wait"):
            out = LP.perm_rows([self._row(st, age=1)], now=NOW)
            self.assertEqual((out[0]["blocked"], out[0]["blockedAt"]), (SUB_MSG, int(NOW - 10)), st)

    def test_main_tool_marker_wins_first(self):
        self._sub_req()
        self._hook({"hook_event_name": "PermissionRequest", "tool_name": "Edit"}, t=NOW - 5)
        out = LP.perm_rows([self._row("tool", age=30)], now=NOW)
        self.assertEqual(out[0]["blocked"], "Edit waiting for approval")

    def test_sub_activity_after_marker_clears(self):
        self._sub_req()
        self.assertEqual(LP.perm_rows([self._row("run", idle=2)], now=NOW)[0]["blocked"], "")

    def test_sub_running_bash_clears(self):
        self._sub_req()
        r = self._row("run", now_tool="Bash", cwd="/w/p")
        self.busy = {"/w/p": True}
        self.assertEqual(LP.perm_rows([r], now=NOW)[0]["blocked"], "")
        self.busy = {}
        self.assertEqual(LP.perm_rows([r], now=NOW)[0]["blocked"], SUB_MSG)

    def test_parent_own_bash_does_not_hide_sub_badge(self):
        # The shell probe is per cwd: the parent's own running Bash must not read as the sub's approved Bash.
        self._sub_req()
        self.busy = {"/w/p": True}
        r = self._row("tool", age=5, now_tool="Bash", cwd="/w/p", tool="Bash")
        self.assertEqual(LP.perm_rows([r], now=NOW)[0]["blocked"], SUB_MSG)

    def test_sibling_sub_bash_does_not_hide_sub_badge(self):
        # A sibling sub's Bash in the same cwd makes the probe busy; the shell cannot be attributed to the waiting sub.
        self._sub_req()
        self.busy = {"/w/p": True}
        r = self._row("wait", now_tool="Bash", cwd="/w/p")
        r["sub"].append({"lab": "y", "min": 1, "idle": 1, "aid": "b9c8d7e6", "now": "Bash"})
        self.assertEqual(LP.perm_rows([r], now=NOW)[0]["blocked"], SUB_MSG)
        r["sub"][1]["now"] = "Read"                     # no other possible owner: the shell is this sub's approved Bash
        self.assertEqual(LP.perm_rows([r], now=NOW)[0]["blocked"], "")

    def test_sub_log_flush_just_after_marker_still_badges(self):
        # Hook lines timestamped before the prompt are flushed ~0.1 s later, after the marker.
        log = os.path.join(self.tmp, "agent-f.jsonl.log")
        with open(log, "w") as f:
            f.write("{}\n")
        LP.note_sub_log(AID, log)
        self._sub_req(t=NOW - 10)
        os.utime(log, (NOW - 9.95, NOW - 9.95))
        self.assertEqual(LP.perm_rows([self._row("run", idle=10)], now=NOW)[0]["blocked"], SUB_MSG)
        os.utime(log, (NOW - 8, NOW - 8))
        self.assertEqual(LP.perm_rows([self._row("run", idle=8)], now=NOW)[0]["blocked"], "")

    def test_main_decision_does_not_clear_sub_badge(self):
        self._sub_req()
        r = self._row("run", otelEv="tool_decision", otelAt=int(NOW - 2))
        self.assertEqual(LP.perm_rows([r], now=NOW)[0]["blocked"], SUB_MSG)

    def _approved(self, **kw):
        # Sub Bash prompt at NOW-40, parent quiet on its own Bash since NOW-60, Bash decision at NOW-10 (t+30).
        self._sub_req(t=NOW - 40)
        return self._row("tool", age=60, now_tool="Bash", cwd="/w/p",
                         **dict({"tool": "Bash", "otelEv": "tool_decision", "otelAt": int(NOW - 10)}, **kw))

    def test_sole_prompt_matching_decision_clears_sub_badge(self):
        self.assertEqual(LP.perm_rows([self._approved()], now=NOW)[0]["blocked"], "")

    def test_decision_for_other_tool_keeps_sub_badge(self):
        self.assertEqual(LP.perm_rows([self._approved(tool="Edit")], now=NOW)[0]["blocked"], SUB_MSG)

    def test_two_open_prompts_one_decision_keeps_badge(self):
        r = self._approved()
        self._sub_req(aid="b9c8d7e6", t=NOW - 35)
        r["sub"].append({"lab": "y", "min": 1, "idle": 60, "aid": "b9c8d7e6", "now": "Bash"})
        self.assertEqual(LP.perm_rows([r], now=NOW)[0]["blocked"], SUB_MSG)

    def test_open_main_prompt_keeps_sub_badge(self):
        r = self._approved()
        self._hook({"hook_event_name": "PermissionRequest", "tool_name": "Bash"}, t=NOW - 30)
        self.assertEqual(LP.perm_rows([dict(r, state="run")], now=NOW)[0]["blocked"], SUB_MSG)

    def test_notification_fallback_main_marker_is_same_prompt(self):
        r = self._approved()
        self._hook({"hook_event_name": "Notification", "notification_type": "permission_prompt"}, t=NOW - 32)
        self.assertEqual(LP.perm_rows([r], now=NOW)[0]["blocked"], "")
        self._hook({"hook_event_name": "Notification", "notification_type": "permission_prompt"}, t=NOW - 20)
        self.assertEqual(LP.perm_rows([dict(r, state="run")], now=NOW)[0]["blocked"], SUB_MSG)

    def test_later_writer_keeps_sub_badge(self):
        # The parent or a sibling wrote after the prompt: the Bash decision may be its own auto-approved call.
        self.assertEqual(LP.perm_rows([self._approved(ageSec=5)], now=NOW)[0]["blocked"], SUB_MSG)
        r = self._approved()
        r["sub"].append({"lab": "y", "min": 1, "idle": 5, "aid": "b9c8d7e6", "now": "Read"})
        self.assertEqual(LP.perm_rows([r], now=NOW)[0]["blocked"], SUB_MSG)

    def test_workflow_agent_aid_matches(self):
        self._sub_req()
        r = {"sid": SID, "state": "run", "ageSec": 1, "blocked": "",
             "wf": [{"id": "w", "run": True, "agents": [{"aid": AID, "st": "run", "end": int(NOW - 60)}]}]}
        self.assertEqual(LP.perm_rows([r], now=NOW)[0]["blocked"], SUB_MSG)

    def test_unknown_aid_or_idle_missing_ignored(self):
        self._sub_req(aid="zzz")
        self.assertEqual(LP.perm_rows([self._row("run")], now=NOW)[0]["blocked"], "")
        self._sub_req()
        r = self._row("run")
        r["sub"][0].pop("idle")
        self.assertEqual(LP.perm_rows([r], now=NOW)[0]["blocked"], "")

    def test_done_row_ignored(self):
        self._sub_req()
        self.assertEqual(LP.perm_rows([self._row("done")], now=NOW)[0]["blocked"], "")

    def test_r2_main_ask_and_elicit_never_sub_badge(self):
        sub = [{"lab": "x", "min": 3, "idle": 200, "aid": AID}]
        wait = {"sid": SID, "state": "wait", "ageSec": 180, "blocked": "", "sub": sub}
        self._hook({"hook_event_name": "PermissionRequest", "tool_name": "AskUserQuestion"})
        self.assertEqual(LP.perm_rows([wait], now=NOW)[0]["blocked"], "")
        self._hook({"hook_event_name": "Notification", "notification_type": "permission_prompt"}, t=NOW - 6)
        self.assertEqual(LP.perm_rows([wait], now=NOW)[0]["blocked"], "")
        for st in ("run", "ask"):
            self.assertEqual(LP.perm_rows([dict(wait, state=st, ageSec=1)], now=NOW)[0]["blocked"], "")
        os.remove(os.path.join(self.tmp, SID + ".json"))
        self._hook({"hook_event_name": "Notification", "notification_type": "elicitation_dialog"})
        for st in ("run", "ask"):
            self.assertEqual(LP.perm_rows([dict(wait, state=st, ageSec=1)], now=NOW)[0]["blocked"], "")

    def test_r3_old_marker_parses(self):
        with open(os.path.join(self.tmp, SID + ".json"), "w") as f:
            json.dump({"sid": SID, "t": NOW - 10}, f)
        r = {"sid": SID, "state": "tool", "tool": "Edit", "ageSec": 30, "blocked": ""}
        self.assertEqual(LP.perm_rows([r], now=NOW)[0]["blocked"], "Edit waiting for approval")

    def test_sub_badge_steady_across_polls_with_frozen_idle(self):
        # Sub log last written at NOW-20, prompt at NOW-10; `idle` was snapshotted at NOW-15 and stays frozen.
        log = os.path.join(self.tmp, "agent-x.jsonl.log")
        with open(log, "w") as f:
            f.write("{}\n")
        os.utime(log, (NOW - 20, NOW - 20))
        LP.note_sub_log(AID, log)
        self._sub_req(t=NOW - 10)
        for now, idle in ((NOW, 5), (NOW + 30, 5), (NOW + 31, 51)):   # third poll = cache refreshed
            out = LP.perm_rows([self._row("wait", age=1, idle=idle)], now=now)[0]
            self.assertEqual((out["blocked"], out.get("blockedAt")), (SUB_MSG, int(NOW - 10)), now)
        os.utime(log, (NOW + 40, NOW + 40))                          # the sub wrote after the prompt: cleared
        self.assertEqual(LP.perm_rows([self._row("wait", age=1, idle=51)], now=NOW + 41)[0]["blocked"], "")


if __name__ == "__main__":
    unittest.main()
