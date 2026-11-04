"""R2: an «Export HTML › Simple» arch-brief run request is accepted, stoppable and tracked (Sent · Running · stage · done)."""
import unittest
from unittest import mock

from tests._load import sidereus

PQ = sidereus("pl_reqs")
SID = "0a1b2c3d-0000"
NOW = 1_000_000.0
REPO = "/tmp/repo"  # nosec B108 -- fake path, never touched
OK = {"relay": True, "sid": SID, "to": "alice"}
ROW = {"sid": SID, "project": "repo", "state": "think"}


class BriefReq(unittest.TestCase):
    def setUp(self):
        self.res = {}   # pipeline -> result time arch_map.result_at reports
        for obj, k, v in ((PQ, "PLREQ_PATH", None), (PQ, "PLSTOP_DIR", None), (PQ, "_MEM", []), (PQ, "_now", lambda: NOW),
                          (PQ.arch_map, "result_at", lambda pl, root: self.res.get(pl, 0.0))):
            p = mock.patch.object(obj, k, v)
            p.start()
            self.addCleanup(p.stop)

    def send(self, pipeline="arch-brief", mid="m1"):
        p, why = PQ.check({"kind": "req", "pipeline": pipeline, "repo": REPO}, OK)
        self.assertIsNone(why)
        PQ.record(p, SID, "alice", mid)
        return p

    def one(self, pipeline="arch-brief", **kw):
        return [v for v in PQ.view([ROW], {}, {}, NOW, **kw)[REPO] if v["pipeline"] == pipeline][0]

    def test_check_accepts_req_and_stop(self):
        self.assertEqual(self.send(), {"kind": "req", "pipeline": "arch-brief", "repo": REPO})
        p, why = PQ.check({"kind": "stop", "pipeline": "arch-brief", "repo": REPO, "of": "m1"}, OK)
        self.assertIsNone(why)
        self.assertEqual(p["of"], "m1")
        self.assertIn("arch-brief", PQ.RUNS)

    def test_sent_then_running_stage(self):
        self.send()
        self.assertEqual(self.one()["state"], "sent")
        v = self.one(brief_run={REPO: {"sid": SID, "stage": "Draft", "t0": NOW}})
        self.assertEqual((v["state"], v["stage"]), ("run", "Draft"))

    def test_brief_ok_newer_than_send_is_done(self):
        self.send()
        self.res["arch-brief"] = NOW - 10   # an older overview does not answer this request
        self.assertEqual(self.one()["state"], "sent")
        self.res["arch-brief"] = NOW + 5
        self.assertEqual(self.one()["state"], "done")

    def test_other_pipelines_unchanged(self):
        self.send("arch-map", "m0")
        self.send()
        self.res["arch-brief"] = NOW + 5   # a brief result never ends an arch-map request
        a = PQ.view([ROW], {}, {}, NOW, brief_run={REPO: {"sid": SID, "stage": "Draft"}})[REPO]
        st = {v["pipeline"]: (v["state"], v["stage"]) for v in a}
        self.assertEqual(st["arch-map"], ("sent", ""))
        self.assertEqual(st["arch-brief"], ("run", "Draft"))
        a = PQ.view([ROW], {REPO: {"sid": SID, "stage": "Plan"}}, {}, NOW)[REPO]
        self.assertEqual([v["state"] for v in a if v["pipeline"] == "arch-map"], ["run"])


if __name__ == "__main__":
    unittest.main()
