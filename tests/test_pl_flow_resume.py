"""hooks/pl_flow.py resume stamp: the first allowed tagged Pre after a deny sets dl[-1]["r"] (time only).
Tmp dirs only, fixed clock."""
import json
import os
import unittest

from tests import test_pl_flow as F   # ⚠not `from … import Flow`: its tests would run again here

H = F.H
SID = F.SID


class PlResume(unittest.TestCase):
    setUp = F.Flow.setUp
    _pipe = F.Flow._pipe
    _ev = F.Flow._ev
    pre = F.Flow.pre
    post = F.Flow.post
    run_ = F.Flow.run_

    def raw(self):
        with open(os.path.join(self.marks, SID + ".runs.json"), encoding="utf-8") as f:
            return f.read()

    def test_r3_resume_stamped_once_on_next_allowed_pre(self):
        self.pre("설계"), self.post("설계")
        self.t = 1010.0
        self.assertEqual(self.pre("검증", text=" secret-a")["permissionDecision"], "deny")   # jump
        self.assertNotIn("r", self.run_()["dl"][-1])
        self.t = 1070.0
        self.assertIsNone(self.pre("구현", text=" secret-b"))
        e = self.run_()["dl"][-1]
        self.assertEqual(e, {"t": 1010.0, "title": "검증", "c": "jump", "r": 1070.0})
        self.post("구현")
        self.t = 1200.0
        self.assertIsNone(self.pre("검증"))   # a later allowed Pre never moves the first resume time
        self.assertEqual(self.run_()["dl"][-1]["r"], 1070.0)
        self.assertNotIn("secret", self.raw())

    def test_r3_denied_pre_not_stamp(self):
        self.pre("설계"), self.post("설계")
        self.t = 1010.0
        self.pre("검증")
        self.t = 1020.0
        self.assertEqual(self.pre("구현", sub="Explore")["permissionDecision"], "deny")   # agent
        dl = self.run_()["dl"]
        self.assertEqual([(x["c"], "r" in x) for x in dl], [("jump", False), ("agent", False)])
        self.assertEqual(json.loads(self.raw())["runs"][F.N]["deny"], 2)


if __name__ == "__main__":
    unittest.main()
