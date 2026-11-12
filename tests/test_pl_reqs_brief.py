"""R2: an «Export HTML › Simple» arch-brief run request is accepted, stoppable and tracked (Sent · Running · stage · done);
R1: a brief-ask DM is plain (sent · gone · done on a newer brief.ok.json, no stop)."""
import unittest
from unittest import mock

from tests._load import sidereus

PQ = sidereus("pl_reqs")
SID = "0a1b2c3d-0000"
NOW = 1_000_000.0
REPO = "/tmp/repo"  # nosec B108 -- fake path, never touched
OK = {"relay": True, "sid": SID, "to": "alice"}
ROW = {"sid": SID, "project": "repo", "state": "think"}


class _Base(unittest.TestCase):
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


class BriefReq(_Base):
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


class BriefAsk(_Base):
    """R1: «Ask the session to draw» is a plain DM — sent/gone, done on a newer brief.ok.json, never stoppable."""
    def test_r1_accepted_as_plain(self):
        self.assertEqual(self.send("brief-ask"), {"kind": "req", "pipeline": "brief-ask", "repo": REPO})
        self.assertIn("brief-ask", PQ.PLAIN)
        self.assertNotIn("brief-ask", PQ.RUNS)

    def test_r1_done_after_newer_brief_ok(self):
        self.send("brief-ask")
        self.assertEqual(self.one("brief-ask")["state"], "sent")
        self.res["arch-brief"] = NOW - 10   # an overview older than the request does not answer it
        self.assertEqual(self.one("brief-ask")["state"], "sent")
        self.res["security-checks"] = NOW + 5   # another pipeline's result never ends it
        self.assertEqual(self.one("brief-ask")["state"], "sent")
        self.res["arch-brief"] = NOW + 5
        self.assertEqual(self.one("brief-ask")["state"], "done")

    def test_r1_gone_when_session_ended(self):
        self.send("brief-ask")
        v = [x for x in PQ.view([dict(ROW, state="gone")], {}, {}, NOW)[REPO] if x["pipeline"] == "brief-ask"][0]
        self.assertEqual(v["state"], "gone")

    def test_r1_stop_refused(self):
        self.send("brief-ask")
        p, why = PQ.check({"kind": "stop", "pipeline": "brief-ask", "repo": REPO, "of": "m1"}, OK)
        self.assertIsNone(p)
        self.assertEqual(why, "Invalid pipeline request")

    def test_r1_brief_run_does_not_light_it(self):
        self.send("brief-ask")
        v = self.one("brief-ask", brief_run={REPO: {"sid": SID, "stage": "Draft", "t0": NOW}})
        self.assertEqual((v["state"], v["stage"]), ("sent", ""))


if __name__ == "__main__":
    unittest.main()
