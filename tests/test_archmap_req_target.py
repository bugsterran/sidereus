"""arch_map.runs + pl_reqs.view: a run requested for a repo only its subagents touched (not in the row's cwd/repos)
ends once that repo's verify.json is written, even while the plrun stays open at «검증» hold and the session is busy."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

AM = sidereus("arch_map")
AV = sidereus("arch_verify")
PL = sidereus("pl_reqs")
C1 = "b" * 40
SID = "7abc9110-0000-4000-8000-000000000001"
NOW = 1792637980.0
PLAN_T, VERIFY_T, ST_T = 1792636977.0, 1792637109.0, 1792637050.05
AG_T0, AG_T1 = 1792637121.74, 1792637121.83   # ★live: a finished agent's t0 and t1 are both stamped after verify.json
REQ_AT, RUN_T0 = 1792635575.0, 1792635600.0
TITLES = ["읽기 계획", "모듈 그리기", "흐름 그리기", "검증"]


class ReqTargetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-archreq-"))
        self.cwd, self.target = os.path.join(self.tmp, "origin"), os.path.join(self.tmp, "newrepo")
        self.home = os.path.join(self.tmp, "sidereus")
        for d in (self.cwd, self.target, self.home):
            os.makedirs(d)
        self.store = os.path.join(self.tmp, "store")
        self.mem = [{"id": "m1", "repo": self.target, "pipeline": "arch-map", "sid": SID, "to": "orch", "mid": "m1",
                     "at": REQ_AT}]
        self.p = [mock.patch.object(AM, "ARCH_DIR", self.store), mock.patch.object(AM, "SIDEREUS_ROOT", self.home),
                  mock.patch.object(AM, "_titles", lambda: list(TITLES)), mock.patch.object(AM, "_RUN_SEEN", {}),
                  mock.patch.object(PL, "PLREQ_PATH", None), mock.patch.object(PL, "PLSTOP_DIR", None),
                  mock.patch.object(PL, "_MEM", self.mem), mock.patch.object(PL, "_now", lambda: NOW)]
        for p in self.p:
            p.start()
        self.put("plan.json", PLAN_T)
        self.put("verify.json", VERIFY_T)

    def tearDown(self):
        for p in self.p:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, name, mtime):
        d = os.path.join(self.store, AV.repo_key(self.target), C1)
        os.makedirs(d, exist_ok=True)
        fp = os.path.join(d, name)
        with open(fp, "w", encoding="utf-8") as f:
            f.write("{}")
        os.utime(fp, (mtime, mtime))

    def row(self, ag_run=False):
        ag = {"aid": "af588f9e", "tid": "t", "lab": "[pl:arch-map/검증] verify", "run": ag_run, "t0": AG_T0,
              "t1": NOW if ag_run else AG_T1}
        st = {"o": "done", "n": 1, "t0": ST_T, "t1": ST_T, "ag": [ag]}
        run = {"name": "arch-map", "cur": "검증", "t0": RUN_T0, "t1": ST_T, "end": 0, "stages": {"검증": st}}
        return {"sid": SID, "state": "think", "cwd": self.cwd, "repos": [self.cwd], "sub": [], "plrun": [run]}

    def test_finished_agent_ends_run_and_request(self):
        s = self.row()
        arch = AM.runs([s], NOW)
        self.assertEqual(arch, {})
        v = PL.view([s], arch, {}, NOW)
        self.assertEqual(v[self.target][0]["state"], "done")

    def test_running_agent_keeps_request_open(self):
        s = self.row(ag_run=True)
        self.assertFalse(AM._closed_by_result(s["plrun"][0], self.target))
        s["sub"] = [{"lab": "general-purpose: [pl:arch-map/검증] verify", "min": 1}]
        arch = AM.runs([s], NOW)
        self.assertEqual(list(arch), [self.target])
        self.assertEqual(PL.view([s], arch, {}, NOW)[self.target][0]["state"], "run")

    def test_no_request_falls_back_to_cwd(self):
        del self.mem[:]
        s = self.row()
        self.assertEqual(list(AM.runs([s], NOW)), [self.cwd])


if __name__ == "__main__":
    unittest.main()
