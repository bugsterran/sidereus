"""A background shell stopped with TaskStop/KillShell closes its row (no completion notice exists). Synthetic lines only."""
import json
import unittest

from tests._load import sidereus

bp = sidereus("bgtasks_parse")

FP = "/tmp/x/sess.jsonl"
NOW = 1_800_000_000.0
TS = "2027-01-15T08:00:00.000Z"


def _line(block, role="assistant"):
    return json.dumps({"type": role, "timestamp": TS, "message": {"content": [block]}})


def _launch(tuid):
    return _line({"type": "tool_use", "id": tuid, "name": "Bash",
                  "input": {"command": "sleep 99", "description": "Long job", "run_in_background": True}})


def _result(tuid, text):
    return _line({"type": "tool_result", "tool_use_id": tuid, "content": text}, role="user")


def _receipt(tuid, sid):
    return _result(tuid, "Command running in background with ID: %s. Output is being written to: "
                         "/tmp/x/tasks/%s.output" % (sid, sid))


def _stop(tuid, sid):
    return _line({"type": "tool_use", "id": tuid, "name": "TaskStop", "input": {"task_id": sid}})


class BgStop(unittest.TestCase):
    def setUp(self):
        self._fin = bp._bg_finished.get(FP)
        bp._bg_finished.pop(FP, None)

    def tearDown(self):
        bp._bg_finished.pop(FP, None)
        if self._fin is not None:
            bp._bg_finished[FP] = self._fin

    def _feed(self, op, seeding, *lines):
        for ln in lines:
            bp._bg_on_line(ln, op, FP, seeding, NOW)

    def test_stopped_shell_closes(self):
        for seeding in (False, True):
            with self.subTest(seeding=seeding):
                op = {}
                tu, st = "toolu_L%d" % seeding, "toolu_S%d" % seeding
                self._feed(op, seeding, _launch(tu), _receipt(tu, "bx1"))
                self.assertIn(tu, op)
                self._feed(op, seeding, _stop(st, "bx1"),
                           _result(st, "Successfully stopped task: bx1 (sleep 99)"))
                self.assertEqual(op, {})
                self.assertFalse(bp._bg_finished.get(FP))     # stopped, not «finished»

    def test_stopped_shell_closes_json_content(self):
        op = {}
        self._feed(op, False, _launch("toolu_LJ"), _receipt("toolu_LJ", "bx3"))
        body = json.dumps({"message": "Successfully stopped task: bx3 (sleep 99)", "task_id": "bx3",
                           "task_type": "local_bash", "command": "sleep 99"}, separators=(",", ":"))
        self._feed(op, False, _stop("toolu_SJ", "bx3"), _result("toolu_SJ", body))
        self.assertEqual(op, {})

    def test_quoted_phrase_does_not_close(self):
        op = {}
        self._feed(op, False, _launch("toolu_LQ"), _receipt("toolu_LQ", "bx4"))
        self._feed(op, False, _result("toolu_RQ", "log: Successfully stopped task: bx4 (sleep 99)"))
        self.assertIn("toolu_LQ", op)

    def test_stopped_monitor_closes(self):
        op = {"task:mx1": ("mon", "Watch x", NOW)}
        self._feed(op, False, _stop("toolu_SM", "mx1"), _result("toolu_SM", "Successfully stopped task: mx1 (w)"))
        self.assertEqual(op, {})

    def test_unknown_id_leaves_rows(self):
        op = {}
        self._feed(op, False, _launch("toolu_K"), _receipt("toolu_K", "bx2"))
        op["task:mx2"] = ("mon", "Watch y", NOW)
        self._feed(op, False, _stop("toolu_SU", "zz9"), _result("toolu_SU", "Successfully stopped task: zz9 (c)"))
        self.assertEqual(set(op), {"toolu_K", "task:mx2"})


if __name__ == "__main__":
    unittest.main()
