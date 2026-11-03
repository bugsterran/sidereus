"""R3: «Request a red check» is a plain relay DM record — name + stage required, sent/gone only, no stop marker, no body."""
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
REPO = "/tmp/repo"  # nosec B108 -- fake path, never touched
OK = {"relay": True, "sid": SID, "to": "alice"}


class RedcheckReq(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.path = os.path.join(self.tmp, "plreq.json")
        self.stop_dir = os.path.join(self.tmp, "plstop")
        for k, v in (("PLREQ_PATH", self.path), ("PLSTOP_DIR", self.stop_dir), ("_now", lambda: NOW)):
            p = mock.patch.object(PQ, k, v)
            p.start()
            self.addCleanup(p.stop)

    def chk(self, **kw):
        return PQ.check(dict({"kind": "req", "pipeline": "redcheck", "repo": REPO}, **kw), OK)

    def test_name_and_stage_required(self):
        for kw in ({}, {"name": "change"}, {"stage": "Verify"}, {"name": "Bad", "stage": "Verify"},
                   {"name": "change", "stage": "a\nb"}, {"name": "change", "stage": "x" * 201}, {"name": "change", "stage": " "}):
            self.assertEqual(self.chk(**kw), (None, "Invalid pipeline request"), kw)
        p, why = self.chk(name="change", stage="Verify", body="secret text")
        self.assertIsNone(why)
        self.assertEqual(p, {"kind": "req", "pipeline": "redcheck", "repo": REPO, "name": "change", "stage": "Verify"})

    def test_no_stop(self):
        self.assertEqual(PQ.check({"kind": "stop", "pipeline": "redcheck", "repo": REPO, "of": "m1"}, OK)[1],
                         "Invalid pipeline request")

    def test_record_view_sent_gone_no_marker(self):
        os.makedirs(self.stop_dir)
        mk = os.path.join(self.stop_dir, SID + ".json")
        with open(mk, "w", encoding="utf-8") as f:
            json.dump({"arch-map": {"at": 1, "mid": "x", "of": "y"}}, f)
        p, _ = self.chk(name="change", stage="Verify")
        PQ.record(p, SID, "alice", "m1")
        with open(mk, encoding="utf-8") as f:
            self.assertIn("arch-map", json.load(f))   # a plain DM never lifts another pipeline's stop
        with open(self.path, encoding="utf-8") as f:
            raw = f.read()
        self.assertNotIn("secret", raw)
        self.assertEqual(set(json.loads(raw)["reqs"][0]), {"id", "repo", "pipeline", "sid", "to", "mid", "at", "name", "stage"})
        v = PQ.view([{"sid": SID, "project": "repo", "state": "think"}], {}, {}, NOW)[REPO][0]
        self.assertEqual((v["pipeline"], v["state"], v["name"], v["stage"]), ("redcheck", "sent", "change", "Verify"))
        self.assertEqual(PQ.view([], {}, {}, NOW)[REPO][0]["state"], "gone")


if __name__ == "__main__":
    unittest.main()
