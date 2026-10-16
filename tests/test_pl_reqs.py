"""sidereus/pl_reqs.py: run requests / stop markers (R1-R3). Tmp files, fixed clock."""
import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

PQ = sidereus("pl_reqs")
SID = "0a1b2c3d-0000"
NOW = 1_000_000.0
REPO = "/tmp/repo"


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.path = os.path.join(self.tmp, "plreq.json")
        self.stop_dir = os.path.join(self.tmp, "plstop")
        for k, v in (("PLREQ_PATH", self.path), ("PLSTOP_DIR", self.stop_dir), ("_now", lambda: NOW)):
            p = mock.patch.object(PQ, k, v)
            p.start()
            self.addCleanup(p.stop)

    def req(self, pipeline="arch-map", mid="m1"):
        PQ.record({"kind": "req", "pipeline": pipeline, "repo": REPO}, SID, "alice", mid)

    def marker(self):
        with open(os.path.join(self.stop_dir, SID + ".json"), encoding="utf-8") as f:
            return json.load(f)


class StoreTest(_Base):
    def test_r1_record_survives_fresh_module_load(self):
        self.req()
        spec = importlib.util.spec_from_file_location("pl_reqs_fresh", PQ.__file__)
        fresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh)
        fresh.PLREQ_PATH, fresh._now = self.path, lambda: NOW
        rows = fresh.view([{"sid": SID, "project": "repo", "state": "wait"}], {})
        self.assertEqual([(r["id"], r["sid"], r["to"], r["project"], r["state"]) for r in rows[REPO]],
                         [("m1", SID, "alice", "repo", "sent")])

    def test_r1_no_body_key_and_caps(self):
        for i in range(PQ.REQ_MAX + 5):
            self.req(mid="m%d" % i)
        with open(self.path, encoding="utf-8") as f:
            recs = json.load(f)["reqs"]
        self.assertEqual(len(recs), PQ.REQ_MAX)
        self.assertEqual(set(recs[0]), {"id", "repo", "pipeline", "sid", "to", "mid", "at"})

    def test_r1_old_dropped(self):
        self.req()
        with mock.patch.object(PQ, "_now", lambda: NOW + PQ.REQ_KEEP_S + 1):
            self.assertEqual(PQ.view([], {}), {})

    def test_r3_stop_marker_replaced_then_cleared_by_new_req(self):
        os.makedirs(self.stop_dir)
        with open(os.path.join(self.stop_dir, SID + ".json"), "w", encoding="utf-8") as f:
            json.dump({"arch-map": {"at": 1, "mid": "z", "of": "y"}, "deps-audit": {"at": 1, "mid": "z", "of": "y"}}, f)
        self.req()
        p, why = PQ.check({"kind": "stop", "pipeline": "arch-map", "repo": REPO, "of": "m1"},
                          {"relay": True, "sid": SID, "to": "alice"})
        self.assertIsNone(why)
        PQ.stop(p, SID, "alice", "s1")
        self.assertEqual(self.marker(), {"arch-map": {"at": NOW, "mid": "s1", "of": "m1"}})   # unknown pipelines dropped
        self.req(mid="m2")   # a later request lifts the stop
        self.assertFalse(os.path.exists(os.path.join(self.stop_dir, SID + ".json")))

    def test_r3_check_refusals(self):
        self.req()
        ok = {"relay": True, "sid": SID, "to": "alice"}
        stop = {"kind": "stop", "pipeline": "arch-map", "repo": REPO, "of": "m1"}
        self.assertIsNone(PQ.check(stop, ok)[1])
        for bad in (dict(stop, of="nope"), dict(stop, repo="/other"), dict(stop, pipeline="security-checks"),
                    dict(stop, of=None)):
            self.assertIsNotNone(PQ.check(bad, ok)[1], bad)
        self.assertIsNotNone(PQ.check(stop, dict(ok, to="bob"))[1])
        self.assertIsNotNone(PQ.check(stop, dict(ok, sid="ffff0000-1111"))[1])
        self.assertIsNotNone(PQ.check(stop, dict(ok, relay=False))[1])
        for bad in ({"kind": "req", "pipeline": "x", "repo": REPO}, {"kind": "req", "pipeline": "arch-map", "repo": "rel"},
                    {"kind": "req", "pipeline": "arch-map", "repo": "/" + "a" * 300}, {"kind": "go", "pipeline": "arch-map", "repo": REPO}):
            self.assertIsNotNone(PQ.check(bad, ok)[1], bad)

    def test_memory_only_writes_nothing(self):
        with mock.patch.object(PQ, "PLREQ_PATH", None), mock.patch.object(PQ, "PLSTOP_DIR", None), \
                mock.patch.object(PQ, "_MEM", []):
            self.req()
            self.assertEqual(len(PQ.view([], {})[REPO]), 1)
        self.assertEqual(os.listdir(self.tmp), [])


class ViewStateTest(_Base):
    """R2: precedence stopped > stopping > run > done > gone > sent."""

    def row(self, state="think", **run):
        r = {"sid": SID, "project": "repo", "state": state}
        if run:
            r["plrun"] = [dict({"name": "arch-map", "t0": NOW, "end": 0, "stop": 0, "cur": "Run"}, **run)]
        return r

    def st(self, rows, arch=None, stopped=False):
        self.n = getattr(self, "n", 0) + 1
        mid = "m%d" % self.n
        self.req(pipeline="arch-map", mid=mid)
        if stopped:
            PQ.stop({"pipeline": "arch-map", "of": mid}, SID, "alice", "s1")
        v = PQ.view(rows, arch or {})[REPO][0]
        return v["state"], v["stage"]

    def test_sent(self):
        self.assertEqual(self.st([self.row()]), ("sent", ""))

    def test_run_with_stage(self):
        self.assertEqual(self.st([self.row(cur="Lint")]), ("run", "Lint"))

    def test_older_run_not_linked(self):
        self.assertEqual(self.st([self.row(t0=NOW - PQ.RUN_SLACK_S - 1)]), ("sent", ""))

    def test_done(self):
        self.assertEqual(self.st([self.row(state="done", end=NOW + 5)]), ("done", ""))

    def test_gone(self):
        self.assertEqual(self.st([]), ("gone", ""))
        self.assertEqual(self.st([self.row(state="gone")]), ("gone", ""))

    def test_stopping_then_stopped(self):
        self.assertEqual(self.st([self.row()], stopped=True)[0], "stopped")   # no run seen
        self.assertEqual(self.st([self.row(cur="Lint")], stopped=True), ("stopping", "Lint"))
        self.assertEqual(self.st([self.row(stop=NOW + 3)], stopped=True)[0], "stopped")
        self.assertEqual(self.st([], stopped=True)[0], "stopped")

    def test_arch_run_counts_as_running(self):
        PQ.record({"kind": "req", "pipeline": "arch-map", "repo": REPO}, SID, "alice", "a1")
        v = PQ.view([self.row()], {REPO: {"stage": "Draw", "sid": SID}})[REPO][0]
        self.assertEqual((v["state"], v["stage"]), ("run", "Draw"))
        v = PQ.view([self.row()], {REPO: {"stage": "Draw", "sid": "ffff0000-1111"}})[REPO][0]
        self.assertEqual(v["state"], "sent")


if __name__ == "__main__":
    unittest.main()
