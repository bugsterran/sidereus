"""Sub-agent completion shapes in `_running_bg`: old notice, attachment notice, resume, end_turn fallback. No live files."""
import json
import os
import shutil
import tempfile
import time
import unittest

from tests._load import sidereus

bt = sidereus("bgtasks")


def _ts(off=0):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() + off))


def _notice(aid, tuid):
    return ("<task-notification>\n<task-id>%s</task-id>\n<tool-use-id>%s</tool-use-id>\n"
            "<status>completed</status>\n<summary>Agent \"x\" finished</summary>\n</task-notification>" % (aid, tuid))


class BgCompletion(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.fp = os.path.join(self.dir, "sess.jsonl")
        os.makedirs(os.path.join(self.dir, "sess", "subagents"))
        self._boot = bt.boot_time
        bt.boot_time = lambda: 0
        self.lines = []
        sidereus("bgtasks_parse")._bg_said.clear()
        bt._bg_sent.clear()

    def tearDown(self):
        bt.boot_time = self._boot
        for d in (bt._bg_open, bt._bg_open_at, bt._bg_offset):
            d.pop(self.fp, None)
        bt._bg_seeded.discard(self.fp)
        shutil.rmtree(self.dir, ignore_errors=True)

    def agent(self, aid, tuid, last, quiet_s=0):
        """Register a subagent: meta + own log whose last message record is `last`."""
        base = os.path.join(self.dir, "sess", "subagents", "agent-" + aid)
        with open(base + ".meta.json", "w") as f:
            json.dump({"toolUseId": tuid, "agentType": "fe-builder", "description": "d"}, f)
        with open(base + ".jsonl", "w") as f:
            f.write(json.dumps({"type": "user", "message": {"role": "user", "content": "go"}}) + "\n")
            f.write(json.dumps(last) + "\n")
            f.write(json.dumps({"type": "attachment", "attachment": {"type": "hook_success"}}) + "\n")
        t = time.time() - quiet_s
        os.utime(base + ".jsonl", (t, t))
        sidereus("agents")._AGENT_META.pop(os.path.join(self.dir, "sess"), None)

    def add(self, *recs):
        with open(self.fp, "a") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")

    def launch(self, tuid):
        self.add({"type": "assistant", "timestamp": _ts(), "message": {"content": [
                     {"type": "tool_use", "id": tuid, "name": "Agent",
                      "input": {"subagent_type": "fe-builder", "description": "d"}}]}},
                 {"type": "user", "timestamp": _ts(), "message": {"content": [
                     {"type": "tool_result", "tool_use_id": tuid, "content": "Async agent launched successfully."}]}})

    def open_ids(self):
        subs, _, _ = bt._running_bg(self.fp)
        return sorted(r[4] for r in subs if len(r) > 4)

    RUNNING_TOOL = {"type": "assistant", "message": {"stop_reason": "tool_use",
                                                    "content": [{"type": "tool_use", "name": "Bash"}]}}
    ENDED = {"type": "assistant", "message": {"stop_reason": "end_turn", "content": [{"type": "text", "text": "."}]}}

    def test_old_notice_in_message_content(self):
        self.agent("a1", "T1", self.RUNNING_TOOL)
        self.launch("T1")
        self.assertEqual(self.open_ids(), ["T1"])
        self.add({"type": "user", "timestamp": _ts(), "message": {"content": _notice("a1", "T1")}})
        self.assertEqual(self.open_ids(), [])

    def test_request_blob_replay_does_not_reopen_denied_agent(self):
        use = {"type": "tool_use", "id": "T9blob", "name": "Agent", "input": {"description": "[pl:bugfix/fix] d"}}
        self.add({"type": "assistant", "timestamp": _ts(), "message": {"content": [use]}},
                 {"type": "user", "timestamp": _ts(), "message": {"content": [
                     {"type": "tool_result", "tool_use_id": "T9blob", "is_error": True, "content": "denied by hook"}]}},
                 {"type": "api-request-blob", "sessionId": "s", "hash": "h", "message": {"content": [use]}})
        subs, _, _ = bt._running_bg(self.fp)
        self.assertEqual(subs, [])

    def test_attachment_queued_command_notice(self):
        self.agent("a2", "T2", self.RUNNING_TOOL)
        self.launch("T2")
        self.assertEqual(self.open_ids(), ["T2"])
        self.add({"type": "attachment", "timestamp": _ts(), "attachment": {
            "type": "queued_command", "commandMode": "task-notification", "prompt": _notice("a2", "T2")}})
        self.assertEqual(self.open_ids(), [])

    def test_resumed_agent_opens_then_closes(self):
        self.agent("a3", "T3", self.RUNNING_TOOL)
        self.launch("T3")
        self.add({"type": "attachment", "timestamp": _ts(), "attachment": {
            "type": "queued_command", "commandMode": "task-notification", "prompt": _notice("a3", "T3")}})
        self.assertEqual(self.open_ids(), [])
        self.add({"type": "assistant", "timestamp": _ts(), "message": {"content": [
                     {"type": "tool_use", "id": "R3", "name": "SendMessage", "input": {"to": "a3", "message": "m"}}]}},
                 {"type": "user", "timestamp": _ts(), "message": {"content": [
                     {"type": "tool_result", "tool_use_id": "R3", "content": '{"success":true,"message":"Resuming agent a3"}'}]}})
        self.assertEqual(self.open_ids(), ["R3"])
        self.add({"type": "attachment", "timestamp": _ts(), "attachment": {
            "type": "queued_command", "commandMode": "task-notification", "prompt": _notice("a3", "R3")}})
        self.assertEqual(self.open_ids(), [])

    def test_notice_written_in_two_halves_completes(self):
        # A notice line caught mid-write must not be consumed broken — the next read parses it whole.
        self.agent("a8", "T8", self.RUNNING_TOOL)
        self.launch("T8")
        self.assertEqual(self.open_ids(), ["T8"])
        line = json.dumps({"type": "attachment", "timestamp": _ts(), "attachment": {
            "type": "queued_command", "commandMode": "task-notification", "prompt": _notice("a8", "T8")}}) + "\n"
        half = len(line) // 2
        with open(self.fp, "a") as f:
            f.write(line[:half])
        self.assertEqual(self.open_ids(), ["T8"])
        with open(self.fp, "a") as f:
            f.write(line[half:])
        self.assertEqual(self.open_ids(), [])

    def test_long_running_tool_stays_open(self):
        self.agent("a4", "T4", self.RUNNING_TOOL, quiet_s=3600)
        self.launch("T4")
        self.assertEqual(self.open_ids(), ["T4"])

    def test_ended_turn_quiet_counts_as_done(self):
        self.agent("a5", "T5", self.ENDED, quiet_s=bt.SUB_DONE_QUIET_S + 60)
        self.launch("T5")
        self.assertEqual(self.open_ids(), [])

    def test_ended_turn_recent_stays_open(self):
        self.agent("a6", "T6", self.ENDED, quiet_s=10)
        self.launch("T6")
        self.assertEqual(self.open_ids(), ["T6"])

    HANDBACK = {"type": "assistant", "message": {"stop_reason": "tool_use", "content": [
        {"type": "tool_use", "id": "hb1", "name": "SubagentHandback", "input": {"message": "x"}}]}}

    def handback_agent(self, aid, tuid, is_error=False, quiet_s=0):
        self.agent(aid, tuid, self.HANDBACK)
        res = {"type": "tool_result", "tool_use_id": "hb1", "content": "ok"}
        if is_error:
            res["is_error"] = True
        self.grow(aid, {"type": "user", "message": {"role": "user", "content": [res]}}, quiet_s=quiet_s)
        return os.path.join(self.dir, "sess", "subagents", "agent-%s.jsonl" % aid)

    def test_handback_counts_as_ended_turn(self):
        f = self.handback_agent("h1", "H1")
        self.assertTrue(bt._ended_turn(f, os.path.getmtime(f)))

    def test_handback_quiet_retired(self):
        self.handback_agent("h2", "H2", quiet_s=bt.SUB_DONE_QUIET_S + 60)
        self.launch("H2")
        self.assertEqual(self.open_ids(), [])

    def test_handback_error_not_ended(self):
        f = self.handback_agent("h3", "H3", is_error=True, quiet_s=bt.SUB_DONE_QUIET_S + 60)
        self.assertFalse(bt._ended_turn(f, os.path.getmtime(f)))
        self.launch("H3")
        self.assertEqual(self.open_ids(), ["H3"])

    def test_last_bash_tool_use_not_ended(self):
        self.agent("h4", "H4", self.RUNNING_TOOL, quiet_s=bt.SUB_DONE_QUIET_S + 60)
        f = os.path.join(self.dir, "sess", "subagents", "agent-h4.jsonl")
        self.assertFalse(bt._ended_turn(f, os.path.getmtime(f)))
        self.launch("H4")
        self.assertEqual(self.open_ids(), ["H4"])

    def notice_att(self, aid, tuid):
        self.add({"type": "attachment", "timestamp": _ts(), "attachment": {
            "type": "queued_command", "commandMode": "task-notification", "prompt": _notice(aid, tuid)}})

    def grow(self, aid, rec, quiet_s=0):
        """Append a record to the agent's own log (the resumed turn) and set its mtime."""
        f = os.path.join(self.dir, "sess", "subagents", "agent-%s.jsonl" % aid)
        with open(f, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
        t = time.time() - quiet_s
        os.utime(f, (t, t))

    def test_resumed_after_notice_is_live_again(self):
        # «Message queued» resume (row dropped by design) after the notice: log growth alone must reopen it
        self.agent("a7", "T7", self.ENDED, quiet_s=5)
        self.launch("T7")
        self.notice_att("a7", "T7")
        self.assertEqual(self.open_ids(), [])
        self.add({"type": "assistant", "timestamp": _ts(), "message": {"content": [
                     {"type": "tool_use", "id": "Q7", "name": "SendMessage", "input": {"to": "a7", "message": "m"}}]}},
                 {"type": "user", "timestamp": _ts(), "message": {"content": [
                     {"type": "tool_result", "tool_use_id": "Q7", "content": '{"success":true,"message":"Message queued for delivery to a7"}'}]}})
        self.grow("a7", {"type": "user", "message": {"role": "user", "content": "more"}}, quiet_s=-2)
        self.assertEqual(self.open_ids(), ["T7"])
        self.grow("a7", self.ENDED, quiet_s=-3)
        self.notice_att("a7", "T7")
        self.assertEqual(self.open_ids(), [])          # finished again → closes

    def test_stale_duplicate_notice_does_not_hide_resumed(self):
        self.agent("a8", "T8", self.ENDED, quiet_s=5)
        self.launch("T8")
        self.notice_att("a8", "T8")
        self.open_ids()
        self.add({"type": "assistant", "timestamp": _ts(), "message": {"content": [
                     {"type": "tool_use", "id": "R8", "name": "SendMessage", "input": {"to": "a8", "message": "m"}}]}},
                 {"type": "user", "timestamp": _ts(), "message": {"content": [
                     {"type": "tool_result", "tool_use_id": "R8", "content": '{"success":true,"message":"Resuming agent a8"}'}]}})
        self.assertEqual(self.open_ids(), ["R8"])
        self.notice_att("a8", "T8")                     # re-delivered old notice (queue-operation dup, measured 11111111)
        self.grow("a8", self.RUNNING_TOOL, quiet_s=-2)
        self.assertEqual(self.open_ids(), ["T8"])

    def test_resumed_long_tool_wait_stays_live(self):
        self.agent("a9", "T9", self.ENDED, quiet_s=5)
        self.launch("T9")
        self.notice_att("a9", "T9")
        self.open_ids()
        bt._bg_popped["T9"] = time.time() - bt.SUB_DONE_QUIET_S + 20   # notice seen long ago
        self.grow("a9", self.RUNNING_TOOL, quiet_s=bt.SUB_LIVE_S + 60)   # quiet past SUB_LIVE_S inside a tool
        self.assertEqual(self.open_ids(), ["T9"])

    def test_trailing_flush_without_end_turn_is_not_revived(self):
        # killed/failed agent: last flush lands inside the grace after its notice, no end_turn, no SendMessage
        self.agent("c1", "V1", self.RUNNING_TOOL, quiet_s=5)
        self.launch("V1")
        self.notice_att("c1", "V1")
        self.assertEqual(self.open_ids(), [])
        self.grow("c1", self.RUNNING_TOOL, quiet_s=-5)
        self.assertEqual(self.open_ids(), [])
        bt._bg_popped["V1"] = time.time() - 100          # notice long ago; a write now is past the grace
        self.grow("c1", self.RUNNING_TOOL)
        self.assertEqual(self.open_ids(), ["V1"])

    def test_late_duplicate_notice_does_not_hide_resumed(self):
        # a notice written before the SendMessage, delivered after it, must not hide the resumed run
        self.agent("d1", "W1", self.ENDED, quiet_s=200)
        self.launch("W1")
        old = {"type": "attachment", "timestamp": _ts(-180), "attachment": {
            "type": "queued_command", "commandMode": "task-notification", "prompt": _notice("d1", "W1")}}
        self.add(old)
        self.assertEqual(self.open_ids(), [])
        self.add({"type": "assistant", "timestamp": _ts(-60), "message": {"content": [
                     {"type": "tool_use", "id": "RD1", "name": "SendMessage", "input": {"to": "d1", "message": "m"}}]}},
                 {"type": "user", "timestamp": _ts(-60), "message": {"content": [
                     {"type": "tool_result", "tool_use_id": "RD1", "content": '{"success":true,"message":"Resuming agent d1"}'}]}})
        self.grow("d1", self.RUNNING_TOOL, quiet_s=50)
        self.assertEqual(self.open_ids(), ["RD1"])
        self.add(old)                                   # late duplicate of the old notice
        self.assertEqual(self.open_ids(), ["RD1"])
        self.notice_att("d1", "RD1")                    # the resumed run's own notice still closes it
        self.assertEqual(self.open_ids(), [])

    def labels(self):
        subs, _, _ = bt._running_bg(self.fp)
        return sorted(r[0] for r in subs)

    def resume(self, aid, tuid, ok, **inp):
        inp.update(to=aid, message="body")
        self.add({"type": "assistant", "timestamp": _ts(), "message": {"content": [
                     {"type": "tool_use", "id": tuid, "name": "SendMessage", "input": inp}]}},
                 {"type": "user", "timestamp": _ts(), "message": {"content": [
                     {"type": "tool_result", "tool_use_id": tuid, "content": ok}]}})

    def test_resumed_label_uses_sendmessage_summary(self):
        # ★2026-10-01: resumed agent kept its spawn label; the summary must replace it, the message body never shows
        self.agent("e1", "X1", self.RUNNING_TOOL)
        self.launch("X1")
        self.notice_att("e1", "X1")
        self.resume("e1", "RX1", '{"success":true,"message":"Resuming agent e1"}', summary="[pl:bugfix/수정] 리뷰 권고 반영")
        self.assertEqual(self.labels(), ["fe-builder: [pl:bugfix/수정] 리뷰 권고 반영"])
        self.assertNotIn("body", " ".join(self.labels()))

    def test_queued_resume_revived_row_uses_summary(self):
        self.agent("e2", "X2", self.ENDED, quiet_s=5)
        self.launch("X2")
        self.notice_att("e2", "X2")
        self.open_ids()
        self.resume("e2", "QX2", '{"success":true,"message":"Message queued for delivery to e2"}', summary="s2")
        self.grow("e2", self.RUNNING_TOOL, quiet_s=-2)
        self.assertEqual(self.labels(), ["fe-builder: s2"])

    def test_queued_message_to_running_agent_is_not_a_completion(self):
        # ⚠«Message queued» to a running agent must not land in the bell's «N개 완료» card
        fin = sidereus("bgtasks_parse")._bg_finished
        fin.pop(self.fp, None)
        self.agent("q1", "QT1", self.RUNNING_TOOL)
        self.launch("QT1")
        self.assertEqual(self.open_ids(), ["QT1"])
        self.resume("q1", "QS1", '{"success":true,"message":"Message queued for delivery to q1 at its next tool round."}')
        self.assertEqual(self.open_ids(), ["QT1"])
        self.assertEqual(fin.get(self.fp, []), [])
        self.notice_att("q1", "QT1")                     # control: the real end still counts once
        self.assertEqual(self.open_ids(), [])
        self.assertEqual([k for k, _, _ in fin.pop(self.fp, [])], ["sub"])

    def test_resumed_without_summary_keeps_description(self):
        self.agent("e3", "X3", self.RUNNING_TOOL)
        self.launch("X3")
        self.notice_att("e3", "X3")
        self.resume("e3", "RX3", '{"success":true,"message":"Resuming agent e3"}')
        self.assertEqual(self.labels(), ["fe-builder: d"])

    def test_subs_newer_sees_log_growth(self):
        # the sessions() parse cache re-reads on this even with `_bg_open` empty (the 11111111 sub=[] cause)
        ag = sidereus("agents")
        self.agent("b2", "U2", self.ENDED, quiet_s=100)
        sd = os.path.join(self.dir, "sess")
        self.assertFalse(ag._subs_newer(sd, time.time() - 50))
        self.grow("b2", {"type": "user", "message": {"role": "user", "content": "more"}})
        self.assertTrue(ag._subs_newer(sd, time.time() - 50))

    def test_resumed_then_done_and_quiet_is_not_live(self):
        self.agent("b1", "U1", self.ENDED, quiet_s=5)
        self.launch("U1")
        self.notice_att("b1", "U1")
        self.open_ids()
        bt._bg_popped["U1"] = time.time() - 2 * bt.SUB_DONE_QUIET_S
        self.grow("b1", self.ENDED, quiet_s=bt.SUB_DONE_QUIET_S + 30)
        self.assertEqual(self.open_ids(), [])

    USER_LAST = {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "r"}]}}

    def _revived_user_last(self, aid, tuid):
        """Finished agent whose log ends on a `user` record, re-opened by a revive after its consumed notice."""
        self.agent(aid, tuid, self.USER_LAST, quiet_s=5)
        self.launch(tuid)
        self.notice_att(aid, tuid)
        self.assertEqual(self.open_ids(), [])
        bt._bg_popped[tuid] = time.time() - 100           # a write now is past the revive grace
        self.grow(aid, self.USER_LAST)
        self.assertEqual(self.open_ids(), [tuid])

    def test_notice_consumed_and_quiet_retires_any_last_record(self):
        self._revived_user_last("g1", "G1")
        bt._bg_popped["G1"] = time.time() - 2 * bt.SUB_DONE_QUIET_S
        self.grow("g1", self.USER_LAST, quiet_s=bt.SUB_DONE_QUIET_S + 30)
        self.assertEqual(self.open_ids(), [])

    def test_notice_consumed_then_resumed_stays_live(self):
        self._revived_user_last("g2", "G2")
        self.resume("g2", "RG2", '{"success":true,"message":"Resuming agent g2"}')
        self.grow("g2", self.RUNNING_TOOL)                 # the resumed turn writes fresh lines
        self.assertEqual(self.open_ids(), ["RG2"])

    def test_late_read_resume_not_retired_mid_tool(self):
        # notice + resuming SendMessage read in one batch: the notice must be stamped with its line time, not the read time
        self.agent("r1", "T1", self.ENDED, quiet_s=600)
        self.launch("T1")
        self.add({"type": "attachment", "timestamp": _ts(-500), "attachment": {
                     "type": "queued_command", "commandMode": "task-notification", "prompt": _notice("r1", "T1")}},
                 {"type": "assistant", "timestamp": _ts(-489), "message": {"content": [
                     {"type": "tool_use", "id": "R1", "name": "SendMessage", "input": {"to": "r1", "message": "m"}}]}},
                 {"type": "user", "timestamp": _ts(-489), "message": {"content": [
                     {"type": "tool_result", "tool_use_id": "R1", "content": '{"success":true,"message":"Resuming agent r1"}'}]}})
        self.grow("r1", self.RUNNING_TOOL, quiet_s=bt.SUB_DONE_QUIET_S + 100)   # long tool, 400s quiet
        self.assertEqual(self.open_ids(), ["R1"])


class LiveSiblingsConflict(unittest.TestCase):
    """Two live sibling subagents, rows built by the real `_running_bg` → `_bg_show` path, fire the conflict rule."""

    def setUp(self):
        self.fo = sidereus("file_owner")
        self.tmp = tempfile.mkdtemp()
        self.proj = os.path.join(self.tmp, "projects")
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.repo, ".git"))
        self.sd = os.path.join(self.proj, "-repo", "s1")
        os.makedirs(os.path.join(self.sd, "subagents"))
        self.fp = self.sd + ".jsonl"
        self._saved = (self.fo.CLAUDE_PROJECTS, self.fo.wt_files, bt.boot_time)
        self.fo.CLAUDE_PROJECTS = self.proj
        self.fo.wt_files = lambda cwd: (200, {"ok": True, "cwd": cwd, "n": 1, "files": [{"st": "M", "path": "a.py"}]})
        bt.boot_time = lambda: 0
        self.fo._FO.update(at=0.0, off={}, per={}, who={})
        self.fo._FO_GIT.clear()

    def tearDown(self):
        self.fo.CLAUDE_PROJECTS, self.fo.wt_files, bt.boot_time = self._saved
        self.fo._FO.update(at=0.0, off={}, per={}, who={})
        self.fo._FO_GIT.clear()
        for d in (bt._bg_open, bt._bg_open_at, bt._bg_offset):
            d.pop(self.fp, None)
        bt._bg_seeded.discard(self.fp)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_two_live_siblings_conflict(self):
        now = time.time()
        pa = os.path.join(self.repo, "a.py")
        with open(self.fp, "w") as f:
            for tu in ("V1", "V2"):
                f.write(json.dumps({"type": "assistant", "timestamp": _ts(), "message": {"content": [
                    {"type": "tool_use", "id": tu, "name": "Agent",
                     "input": {"subagent_type": "general-purpose", "description": tu}}]}}) + "\n")
        for aid, tu in (("x1", "V1"), ("x2", "V2")):
            base = os.path.join(self.sd, "subagents", "agent-" + aid)
            with open(base + ".meta.json", "w") as f:
                json.dump({"toolUseId": tu, "agentType": "general-purpose", "description": tu}, f)
            with open(base + ".jsonl", "w") as f:
                f.write(json.dumps({"type": "assistant", "timestamp": _ts(-30), "cwd": self.repo, "message": {
                    "stop_reason": "tool_use", "content": [
                        {"type": "tool_use", "name": "Edit", "id": "e", "input": {"file_path": pa}}]}}) + "\n")
        sidereus("agents")._AGENT_META.pop(self.sd, None)
        subs, _, _ = bt._running_bg(self.fp)
        rows = [{"sid": "s1", "state": "tool", "sub": sidereus("agents")._bg_show(subs, now, False)}]
        self.assertEqual(sorted(s["aid"] for s in rows[0]["sub"]), ["x1", "x2"])
        cf = self.fo.conflicts(rows, now)
        self.assertEqual(len(cf), 1)
        self.assertEqual(cf[0]["units"], [("s1", "x1"), ("s1", "x2")])


if __name__ == "__main__":
    unittest.main()
