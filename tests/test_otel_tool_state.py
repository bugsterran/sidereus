"""OTel `api_request` (-> think) must not override a transcript `tool`/`wait` (it hid «waiting for approval»).

Synthetic parse dicts only; sessions._otel_state/_dead are monkeypatched and the clock is a fixed NOW.
"""
import unittest

from tests._load import sidereus

sessions = sidereus("sessions")

CWD = "/w/repo-o"
NOW = 1_800_000_000.0
LIVE = {CWD: 1}


def prow(shape, tool="", **kw):
    p = {"sid": "s1", "cwd": CWD, "shape": shape, "tool": tool, "ask": False, "askTool": False,
         "abort": False, "err": False, "actAt": NOW - 30, "bgs": [], "pmode": ""}
    p.update(kw)
    return p


class OtelToolState(unittest.TestCase):
    def setUp(self):
        self.otel = None
        for n, v in {"_otel_state": lambda sid: self.otel, "_dead": lambda *a: False}.items():
            old = getattr(sessions, n)
            setattr(sessions, n, v)
            self.addCleanup(setattr, sessions, n, old)

    def state(self, p, otel, mt=NOW - 30):
        self.otel = otel
        st, o, got, dead = sessions._row_state(mt, NOW, LIVE, p, False)
        return st, sessions._row_status(st, o, p, NOW, mt)

    def test_api_request_keeps_pending_edit_blocked(self):
        st, s = self.state(prow("tool", "Edit"), {"state": "think", "ev": "api_request", "at": NOW - 2})
        self.assertEqual(st, "tool")
        self.assertEqual(s["blocked"], "Edit waiting for approval")

    def test_api_request_keeps_wait_with_running_sub(self):
        p = prow("text", sub=[{"label": "a", "start": NOW - 60}])
        st, _ = self.state(p, {"state": "think", "ev": "api_request", "at": NOW - 2})
        self.assertEqual(st, "wait")

    def test_tool_decision_still_applies(self):
        st, _ = self.state(prow("result"), {"state": "tool", "ev": "tool_decision", "at": NOW - 2, "tool": "Bash"})
        self.assertEqual(st, "tool")

    def test_user_prompt_after_wait_still_think(self):
        st, _ = self.state(prow("text"), {"state": "think", "ev": "user_prompt", "at": NOW - 2})
        self.assertEqual(st, "think")

    def test_tool_result_keeps_pending_tool(self):
        # R1: the previous call's tool_result (think) says nothing about the pending tool_use
        st, _ = self.state(prow("tool", "Bash"), {"state": "think", "ev": "tool_result", "at": NOW - 2})
        self.assertEqual(st, "tool")

    def test_user_prompt_keeps_pending_tool(self):
        # R1
        st, _ = self.state(prow("tool", "Bash"), {"state": "think", "ev": "user_prompt", "at": NOW - 2})
        self.assertEqual(st, "tool")

    def test_tool_decision_on_pending_tool_stays_tool(self):
        # R3
        st, _ = self.state(prow("tool", "Bash"), {"state": "tool", "ev": "tool_decision", "at": NOW - 2, "tool": "Bash"})
        self.assertEqual(st, "tool")

    def test_result_shape_tool_result_still_think(self):
        # R3: unchanged when no tool is pending
        st, _ = self.state(prow("result"), {"state": "think", "ev": "tool_result", "at": NOW - 2})
        self.assertEqual(st, "think")


if __name__ == "__main__":
    unittest.main()
