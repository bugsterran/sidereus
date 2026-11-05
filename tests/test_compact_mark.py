"""Compaction marker: hooks/compact_mark.py writes/removes {sid, t[, trig]}; sidereus.compact_marks.compacting reads it. Tmp dirs only."""
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from sidereus import compact_marks as CM
from sidereus import claude_roots, transcript

_P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks", "compact_mark.py")
_spec = importlib.util.spec_from_file_location("compact_mark_hook", _P)
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)

SID = "0123abcd-0000-4000-8000-0123456789ab"
NOW = 1_800_000_000.0


def _boundary(ms, ts):
    return json.dumps({"type": "system", "subtype": "compact_boundary", "timestamp": ts,
                       "compactMetadata": {"trigger": "auto", "preTokens": 1, "durationMs": ms}}, separators=(",", ":"))


class CompactMark(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.marks = os.path.join(self.tmp, "compacting")
        self.proj = os.path.join(self.tmp, "projects")
        os.makedirs(os.path.join(self.proj, "p"))
        for obj, k, v in ((H, "MARK_DIR", self.marks), (CM, "CMP_DIR", self.marks), (CM, "_MS_CACHE", {}),
                          (CM, "_FILE_MEMO", {}), (transcript, "CLAUDE_PROJECTS", self.proj),
                          (claude_roots, "acct_of", lambda sid, fp: ("", ""))):
            p = mock.patch.object(obj, k, v)
            p.start()
            self.addCleanup(p.stop)

    def _hook(self, ev, raw=None):
        with mock.patch("sys.stdin", io.StringIO(raw if raw is not None else json.dumps(ev))), \
                mock.patch.object(H.time, "time", return_value=NOW):
            H.main()

    def _marker(self):
        with open(os.path.join(self.marks, SID + ".json"), encoding="utf-8") as f:
            return json.load(f)

    def _transcript(self, lines, name="a.jsonl"):
        fp = os.path.join(self.proj, "p", name)
        with open(fp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        os.utime(fp, (NOW - 60, NOW - 60))
        return fp

    def test_hook_writes_then_removes(self):
        self._hook({"hook_event_name": "PreCompact", "session_id": SID, "trigger": "manual",
                    "custom_instructions": "SECRET"})
        self.assertEqual(self._marker(), {"sid": SID, "t": NOW, "trig": "manual"})
        self._hook({"hook_event_name": "PostCompact", "session_id": SID})
        self.assertEqual(os.listdir(self.marks), [])

    def test_hook_drops_unknown_trigger(self):
        self._hook({"hook_event_name": "PreCompact", "session_id": SID, "trigger": "x"})
        self.assertEqual(self._marker(), {"sid": SID, "t": NOW})

    def test_hook_bad_input_writes_nothing(self):
        self._hook({"hook_event_name": "PreCompact", "session_id": "../../x"})
        self._hook({"hook_event_name": "Stop", "session_id": SID})
        self._hook(None, raw="not json{")
        self._hook(None, raw="[1, 2]")
        self.assertFalse(os.path.exists(self.marks))

    def test_hook_garbage_exits_zero(self):
        import subprocess
        import sys
        r = subprocess.run([sys.executable, _P], input=b"\xff garbage", capture_output=True,
                           env=dict(os.environ, MAILBOX_DIR=self.tmp), timeout=20)
        self.assertEqual((r.returncode, r.stdout), (0, b""))
        self.assertFalse(os.path.exists(self.marks))

    def _mark(self, t):
        os.makedirs(self.marks, exist_ok=True)
        with open(os.path.join(self.marks, SID + ".json"), "w", encoding="utf-8") as f:
            json.dump({"sid": SID, "t": t}, f)

    def test_fresh_marker_with_median(self):
        self._transcript([_boundary(64523, "2026-11-01T00:00:01Z"), _boundary(109902, "2026-11-01T00:00:02Z")], "a.jsonl")
        self._transcript([_boundary(89907, "2026-11-01T00:00:03Z"), '{"type":"user","x":1}'], "b.jsonl")
        self._mark(NOW - 10)
        self.assertEqual(CM.compacting(SID, "", NOW - 20, NOW), {"at": int(NOW - 10), "estMs": 89907, "n": 3})

    def test_no_history_estimate_zero(self):
        self._transcript(['{"type":"user","message":"hi"}'])
        self._mark(NOW - 10)
        self.assertEqual(CM.compacting(SID, "", NOW - 20, NOW), {"at": int(NOW - 10), "estMs": 0, "n": 0})

    def test_user_line_mentioning_boundary_ignored(self):
        self._transcript(['{"type":"user","subtype":"compact_boundary","compactMetadata":{"durationMs":5000}}'])
        self._mark(NOW - 10)
        self.assertEqual(CM.compacting(SID, "", NOW - 20, NOW)["estMs"], 0)

    def test_newer_activity_hides(self):
        self._mark(NOW - 10)
        self.assertIsNone(CM.compacting(SID, "", NOW - 5, NOW))
        self.assertIsNone(CM.compacting(SID, "", NOW - 10, NOW))

    def test_orphan_older_than_cap_hides(self):
        self._mark(NOW - CM.CMP_MAX_S - 1)
        self.assertIsNone(CM.compacting(SID, "", NOW - 1000, NOW))

    def test_no_marker_or_bad_sid(self):
        self.assertIsNone(CM.compacting(SID, "", 0, NOW))
        self.assertIsNone(CM.compacting("../x", "", 0, NOW))


if __name__ == "__main__":
    unittest.main()
