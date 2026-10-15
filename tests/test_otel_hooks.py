"""Per-day hook cost (sidereus/otel_hooks.py) and its feed from otel hook_execution_complete (R1, R2, R4).

File path and module state are swapped per test; timestamps are fixed — no live file, clock or network.
"""
import json
import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

from tests import _load

h = _load.sidereus("otel_hooks")
o = _load.sidereus("otel")

NOW = time.mktime(time.strptime("2026-10-01 12", "%Y-%m-%d %H"))


def _ts(d, hr=12):
    return time.mktime(time.strptime("%s %02d" % (d, hr), "%Y-%m-%d %H"))


def _attrs(at):
    return {"attributes": [{"key": k, "value": ({"intValue": v} if isinstance(v, int) else {"stringValue": v})}
                           for k, v in at.items()]}


def _hook(ev, dur, nbe=0, **extra):
    at = {"event.name": "hook_execution_complete", "session.id": "s1", "hook_event": ev,
          "total_duration_ms": dur, "num_hooks": 1, "num_success": 1, "num_blocking": 1,
          "num_non_blocking_error": nbe}
    at.update(extra)
    return _attrs(at)


def _payload(*recs):
    return {"resourceLogs": [{"scopeLogs": [{"logRecords": list(recs)}]}]}


class _Base(unittest.TestCase):
    def setUp(self):
        self.saved = (h._oh, h._oh_meta, h.OH_FILE, h.OH_CAP)
        self.tmp = tempfile.mkdtemp()
        h.OH_FILE = os.path.join(self.tmp, "otel-hooks.json")
        self._reset()

    def tearDown(self):
        (h._oh, h._oh_meta, h.OH_FILE, h.OH_CAP) = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _reset(self):
        h._oh = {}
        h._oh_meta = {"loaded": False, "savedAt": 0.0, "dirty": False}


class HookStoreCase(_Base):
    def test_r1_save_load_round_trip_is_additive(self):
        h._oh_add(_ts("2026-10-01"), "Stop", 100, 1)
        self.assertTrue(h._oh_save(now=_ts("2026-10-01", 13)))
        self._reset()
        h._oh_add(_ts("2026-10-01"), "Stop", 5, 0)      # ingested after restart, before the load
        h._oh_load()
        h._oh_load()                                    # second load does not double-count
        self.assertEqual(h._oh["2026-10-01"]["Stop"], [2, 105, 1])

    def test_r1_prune_older_than_31_days(self):
        h._oh_add(_ts("2026-08-20"), "Stop", 1, 0)
        h._oh_add(_ts("2026-09-20"), "Stop", 1, 0)
        self.assertTrue(h._oh_save(now=_ts("2026-10-05")))
        self.assertEqual(list(h._oh), ["2026-09-20"])

    def test_r1_type_cap_merges_into_other_and_name_is_capped(self):
        h.OH_CAP = 2
        for ev in ("A", "B", "C", "D"):
            h._oh_add(_ts("2026-10-01"), ev, 10, 0)
        self.assertEqual(h._oh["2026-10-01"], {"A": [1, 10, 0], "B": [1, 10, 0], "Other": [2, 20, 0]})
        h.OH_CAP = 40
        h._oh_add(_ts("2026-10-02"), "x" * 100, 1, 0)
        self.assertEqual(list(h._oh["2026-10-02"]), ["x" * 40])

    def test_r2_view_top_by_total_time(self):
        h._oh_add(_ts("2026-09-01"), "Old", 9999, 0)    # before since — excluded
        h._oh_add(_ts("2026-10-01"), "PreToolUse", 10, 0)
        h._oh_add(_ts("2026-10-02"), "PreToolUse", 20, 1)
        h._oh_add(_ts("2026-10-02"), "Stop", 300, 0)
        v = h._oh_view("2026-10-01", top=6)
        self.assertEqual(v["rows"], [{"ev": "Stop", "count": 1, "ms": 300, "avg": 300, "fail": 0},
                                     {"ev": "PreToolUse", "count": 2, "ms": 30, "avg": 15, "fail": 1}])
        self.assertEqual((v["n"], v["from"]), (3, "2026-10-01"))
        self.assertEqual(len(h._oh_view("2026-10-01", top=1)["rows"]), 1)

    def test_r3_empty_store(self):
        self.assertEqual(h._oh_view("2026-10-01"), {"rows": [], "n": 0, "from": ""})


def _fresh_stat():
    return {"posts": 0, "recs": 0, "kept": 0, "dropName": 0, "dropSeq": 0, "dropSid": 0,
            "acct": 0, "dupReq": 0, "reSeq": 0, "names": {}, "lastPost": 0, "lastKept": 0, "hooks": 0}


class HookIngestCase(_Base):
    def setUp(self):
        super(HookIngestCase, self).setUp()
        self.osaved = (o._otel, o._otel_stat, o._otel_tools)
        o._otel, o._otel_stat, o._otel_tools = {}, _fresh_stat(), {}
        self.tp = mock.patch.object(o.time, "time", return_value=NOW)
        self.tp.start()

    def tearDown(self):
        self.tp.stop()
        (o._otel, o._otel_stat, o._otel_tools) = self.osaved
        super(HookIngestCase, self).tearDown()

    def test_r1_day_file_runs_ms_fails(self):
        o._otel_ingest(_payload(_hook("PreToolUse", 40), _hook("PreToolUse", 60, nbe=1),
                                _hook("Stop", 500, num_cancelled=1),
                                _attrs({"event.name": "hook_execution_start", "session.id": "s1", "hook_event": "Stop"})))
        self.assertTrue(h._oh_save(now=NOW, force=True))
        with open(h.OH_FILE, encoding="utf-8") as f:
            day = json.load(f)["d"]["2026-10-01"]
        # num_blocking=1 on every record is not a failure; start events are ignored
        self.assertEqual(day, {"PreToolUse": [2, 100, 1], "Stop": [1, 500, 1]})
        self.assertEqual(o._otel_stat["hooks"], 3)

    def test_r1_no_hook_name_command_or_output_stored(self):
        o._otel_ingest(_payload(_hook("PreToolUse", 5, hook_name="secret-hook-name",
                                      hook_definitions="python3 /secret/cmd.py", stdout_chars=1234567,
                                      stderr_chars=7654321, **{"session.id": "sid-secret-123"})))
        h._oh_save(now=NOW, force=True)
        with open(h.OH_FILE, encoding="utf-8") as f:
            raw = f.read()
        for bad in ("secret", "cmd.py", "1234567", "7654321", "sid-secret", "hook_name", "chars"):
            self.assertNotIn(bad, raw)

    def test_r4_live_state_unchanged_by_hook_events(self):
        tool = _attrs({"event.name": "tool_decision", "session.id": "s1", "tool_name": "Bash", "event.sequence": 1})
        o._otel_ingest(_payload(tool))
        before = (json.dumps(o._otel, sort_keys=True), o._otel_stat["kept"], o._otel_stat["dropName"],
                  o._otel_stat["dropSeq"], o._otel_state("s1"))
        o._otel_ingest(_payload(_hook("PreToolUse", 5), _hook("Stop", 9, **{"event.sequence": 99})))
        after = (json.dumps(o._otel, sort_keys=True), o._otel_stat["kept"], o._otel_stat["dropName"],
                 o._otel_stat["dropSeq"], o._otel_state("s1"))
        self.assertEqual(before, after)
        self.assertNotIn("hook_execution_complete", o.OTEL_KEEP)
        self.assertNotIn("hook_execution_complete", o._OTEL_STATE)


if __name__ == "__main__":
    unittest.main()
