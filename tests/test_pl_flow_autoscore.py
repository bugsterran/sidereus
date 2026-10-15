"""hooks/pl_flow.py run end -> detached `pl_eval.py score --auto`: only with seeds.json, once per closed run. Tmp dirs only."""
import hashlib
import os
import unittest
from unittest import mock

from tests import test_pl_flow as F   # ⚠not `from … import Flow`: its tests would run again here

H = F.H
_Base = type("_Base", (F.Flow,), {k: None for k in dir(F.Flow) if k.startswith("test")})   # helpers only, not Flow's tests


class AutoScore(_Base):
    def setUp(self):
        super().setUp()
        self.spawned = []
        for k, v in (("_spawn", self.spawned.append), ("SCORE_SCRIPT", "/x/scripts/pl_eval.py")):
            p = mock.patch.object(H, k, v)
            p.start()
            self.addCleanup(p.stop)

    def seeds(self):
        key = hashlib.sha1(os.path.realpath(self.proj).encode("utf-8")).hexdigest()[:16]
        d = os.path.join(self.tmp, "eval", key)
        os.makedirs(d)
        open(os.path.join(d, "seeds.json"), "w").close()

    def close_by_commit(self):
        self.pre("설계"), self.post("설계"), self.pre("구현")
        self.t += 5
        self._cmd("git commit -m x")

    def test_no_seeds_no_spawn(self):
        self.close_by_commit()
        self.assertEqual(self.run_()["end"], 1005.0)
        self.assertEqual(self.spawned, [])

    def test_commit_close_spawns_once(self):
        self.seeds()
        self.close_by_commit()
        pf = os.path.join(self.proj, ".claude", "pipelines", "sidereus-change.json")
        self.assertEqual(len(self.spawned), 1)
        self.assertEqual(self.spawned[0][1:], ["/x/scripts/pl_eval.py", "score", "--repo", self.proj, "--pipeline", pf, "--auto",
                                               "--since", "1005"])   # commit close: score only if the commit lands
        self._cmd("git commit -m again")   # run already ended: nothing new closes
        self.assertEqual(len(self.spawned), 1)

    def test_end_tag_and_last_stage(self):
        self.seeds()
        self.pre("설계")
        self.pre("설계", tool="Bash", raw="[pl-end:sidereus-change/설계] done")
        self.assertEqual(len(self.spawned), 1)
        self.assertNotIn("--since", self.spawned[0])
        for s in ("설계", "구현", "검증", "리뷰"):
            self.pre(s), self.post(s)
        self.pre("라이브 검증"), self.post("라이브 검증")   # last stage back -> run complete
        self.assertEqual(len(self.spawned), 2)

    def test_spawn_error_fails_open(self):
        self.seeds()
        with mock.patch.object(H, "_spawn", side_effect=OSError("boom")):
            self.close_by_commit()
        self.assertEqual(self.run_()["end"], 1005.0)


if __name__ == "__main__":
    unittest.main()
