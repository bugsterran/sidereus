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
        self.saved = (h._oh, h._ohn, h._ohx, h._oh_meta, h.OH_FILE, h.OH_CAP)
        self.tmp = tempfile.mkdtemp()
        h.OH_FILE = os.path.join(self.tmp, "otel-hooks.json")
        self._reset()

    def tearDown(self):
        (h._oh, h._ohn, h._ohx, h._oh_meta, h.OH_FILE, h.OH_CAP) = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _reset(self):
        h._oh = {}
        h._ohn = {}
        h._ohx = {}
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


class HookFiresCase(_Base):
    """Per-firing counts by event:subject (`_ohn`) and their attribution to one matcher (`hook_fires`)."""

    def _fire(self, d, ev, name):
        h._oh_add(_ts(d), ev, 5, 0, name)

    def test_key_parsing_keeps_only_event_and_tool_like_subject(self):
        self.assertEqual(h._ohn_key("PreToolUse", "PreToolUse:Bash"), "PreToolUse:Bash")
        self.assertEqual(h._ohn_key("Stop", "Stop"), "Stop")
        self.assertEqual(h._ohn_key("Stop", None), "Stop")
        for bad in ("secret-hook-name", "Stop:x", "PreToolUse:a b", "PreToolUse:/tmp/x.sh"):
            self.assertIsNone(h._ohn_key("PreToolUse", bad), bad)

    def test_matcher_attribution_counts_silent_runs(self):
        for name in ("PreToolUse:Bash", "PreToolUse:Bash", "PreToolUse:Edit", "PreToolUse:Write"):
            self._fire("2026-10-01", "PreToolUse", name)
        self._fire("2026-10-02", "Stop", "Stop")
        self.assertEqual(h.hook_fires("PreToolUse", "Bash", "2026-09-30"), (2, "2026-10-01", False))
        self.assertEqual(h.hook_fires("PreToolUse", "Edit|Write", "2026-09-30")[0], 2)
        self.assertEqual(h.hook_fires("PreToolUse", "", "2026-09-30")[0], 4)
        self.assertEqual(h.hook_fires("PreToolUse", "Read", "2026-09-30")[0], 0)
        self.assertEqual(h.hook_fires("Stop", "", "2026-09-30")[0], 1)
        self.assertIsNone(h.hook_fires("Stop", "", "2026-10-03"))   # no firing recorded since then

    def test_sanitised_or_missing_subject_is_ambiguous_for_specific_matchers(self):
        self._fire("2026-10-01", "PreToolUse", "PreToolUse:mcp_tool")
        self._fire("2026-10-01", "SubagentStop", "SubagentStop")
        self.assertTrue(h.hook_fires("PreToolUse", "mcp__x__.*", "2026-10-01")[2])
        self.assertFalse(h.hook_fires("PreToolUse", "Bash", "2026-10-01")[2])   # Bash can never be an MCP tool
        self.assertTrue(h.hook_fires("SubagentStop", "Explore", "2026-10-01")[2])
        self.assertEqual(h.hook_fires("SubagentStop", "", "2026-10-01"), (1, "2026-10-01", False))

    def test_round_trip_and_prune(self):
        self._fire("2026-08-01", "PreToolUse", "PreToolUse:Bash")
        self._fire("2026-10-01", "PreToolUse", "PreToolUse:Bash")
        self.assertTrue(h._oh_save(now=NOW, force=True))
        self._reset()
        self.assertEqual(h.hook_fires("PreToolUse", "Bash", "2026-01-01"), (1, "2026-10-01", False))


class HookCostIngestCase(_Base):
    """#28 R4: `_ohx` cost counts from hook_execution_complete — counts only, old files load, missing = not measured."""

    def setUp(self):
        super(HookCostIngestCase, self).setUp()
        self.osaved = (o._otel, o._otel_stat, o._otel_tools)
        o._otel, o._otel_stat, o._otel_tools = {}, _fresh_stat(), {}
        self.tp = mock.patch.object(o.time, "time", return_value=NOW)
        self.tp.start()

    def tearDown(self):
        self.tp.stop()
        (o._otel, o._otel_stat, o._otel_tools) = self.osaved
        super(HookCostIngestCase, self).tearDown()

    def _rec(self, **kw):
        at = {"hook_name": "PreToolUse:Bash", "num_blocking": 0, "stdout_chars": 0, "stderr_chars": 0}
        at.update(kw)
        return _hook("PreToolUse", at.pop("dur", 40), **at)

    def test_r4_only_counts_saved(self):
        o._otel_ingest(_payload(self._rec(stdout_chars=12, hook_definitions="python3 /x/def.py",
                                          **{"session.id": "sid-cost-77"}),
                                self._rec(num_blocking=2, dur=60)))
        self.assertTrue(h._oh_save(now=NOW, force=True))
        with open(h.OH_FILE, encoding="utf-8") as f:
            raw = f.read()
        for bad in ("chars", "hook_definitions", "def.py", "sid-cost-77"):
            self.assertNotIn(bad, raw)
        x = json.loads(raw)["x"]["2026-10-01"]
        self.assertEqual(x, {"PreToolUse:Bash": [2, 100, 1, 1]})
        for row in x.values():
            self.assertTrue(len(row) == 4 and all(type(v) is int for v in row))

    def test_r4_missing_attr_is_unmeasured(self):
        no_blk = _hook("PreToolUse", 40, hook_name="PreToolUse:Bash", stdout_chars=0, stderr_chars=0)
        no_blk["attributes"] = [a for a in no_blk["attributes"] if a["key"] != "num_blocking"]
        o._otel_ingest(_payload(no_blk))
        o._otel_ingest(_payload(_hook("PreToolUse", 40, hook_name="PreToolUse:Bash", num_blocking=0, stderr_chars=0)))
        self.assertEqual(h.hook_fires("PreToolUse", "Bash", "2026-09-30")[0], 2)   # runs still counted
        self.assertIsNone(h.hook_cost("PreToolUse", "Bash", "2026-09-30"))


class HookCostCase(_Base):
    def _fire(self, name, dur, blk=False, out=False, d="2026-10-01"):
        h._oh_add(_ts(d), name.partition(":")[0], dur, 0, name, blk=blk, out=out)

    def test_r1_rollup_and_matching(self):
        self._fire("PreToolUse:Bash", 1500)
        self._fire("PreToolUse:Bash", 500, out=True)
        self._fire("PreToolUse:Edit", 100, blk=True)
        self._fire("PreToolUse:Bash", 9999, d="2026-09-01")    # before since
        c = h.hook_cost("PreToolUse", "Bash", "2026-09-30")
        self.assertEqual(c, {"mruns": 2, "ms": 2000, "blk": 0, "out": 1, "subs": ["Bash"], "amb": False})
        c = h.hook_cost("PreToolUse", "*", "2026-09-30")
        self.assertEqual((c["mruns"], c["blk"], sorted(c["subs"])), (3, 1, ["Bash", "Edit"]))
        self.assertIsNone(h.hook_cost("PreToolUse", "Read", "2026-09-30"))

    def test_r4_ambiguous_subject(self):
        self._fire("PreToolUse:mcp_tool", 10)
        self.assertTrue(h.hook_cost("PreToolUse", "mcp__x__.*", "2026-09-30") is None)
        self.assertFalse(h.hook_cost("PreToolUse", "", "2026-09-30")["amb"])

    def test_r4_v1_file_without_x_loads(self):
        with open(h.OH_FILE, "w", encoding="utf-8") as f:
            json.dump({"v": 1, "d": {}, "n": {"2026-10-01": {"PreToolUse:Bash": 7}}}, f)
        h._oh_load()
        self.assertEqual(h._ohn, {"2026-10-01": {"PreToolUse:Bash": 7}})
        self.assertEqual(h._ohx, {})
        self.assertIsNone(h.hook_cost("PreToolUse", "Bash", "2026-09-30"))   # not measured yet, never clean

    def test_r4_bad_x_rows_skipped_and_round_trip(self):
        with open(h.OH_FILE, "w", encoding="utf-8") as f:
            json.dump({"v": 1, "d": {}, "n": {}, "x": {"2026-10-01": {"A:b": [1, 2, 3], "Stop": [2, 30, 0, 1]}}}, f)
        h._oh_load()
        self.assertEqual(h._ohx, {"2026-10-01": {"Stop": [2, 30, 0, 1]}})
        self.assertTrue(h._oh_save(now=NOW, force=True))
        self._reset()
        h._oh_load()
        self.assertEqual(h._ohx, {"2026-10-01": {"Stop": [2, 30, 0, 1]}})


if __name__ == "__main__":
    unittest.main()
