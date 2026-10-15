"""perm_mark hook: an MCP elicitation dialog writes the same {sid, t} marker; idle prompts still do not. Tmp dir only."""
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

_P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks", "perm_mark.py")
_spec = importlib.util.spec_from_file_location("perm_mark_hook_elicit", _P)
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)

SID = "0123abcd-0000-4000-8000-0123456789ab"
NOW = 1_800_000_000.0


class PermMarkElicit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        p = mock.patch.object(H, "MARK_DIR", self.tmp)
        p.start()
        self.addCleanup(p.stop)

    def _hook(self, ntype):
        ev = {"hook_event_name": "Notification", "session_id": SID, "notification_type": ntype, "message": "SECRET"}
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch.object(H.time, "time", return_value=NOW):
            H.main()

    def test_elicitation_writes_marker(self):
        self._hook("elicitation_dialog")
        with open(os.path.join(self.tmp, SID + ".json")) as f:
            self.assertEqual(json.load(f), {"sid": SID, "t": NOW})

    def test_idle_prompt_still_ignored(self):
        self._hook("idle_prompt")
        self.assertEqual(os.listdir(self.tmp), [])


if __name__ == "__main__":
    unittest.main()
