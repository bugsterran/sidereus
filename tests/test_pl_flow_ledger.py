"""hooks/pl_flow.py run ledger: one allow-listed row per ended run in DATA_DIR/eval/<key>/runs.jsonl. Tmp dirs only."""
import hashlib
import json
import os
import unittest
from unittest import mock

from tests import test_pl_flow as F   # ⚠not `from … import Flow`: its tests would run again here

H = F.H
_Base = type("_Base", (F.Flow,), {k: None for k in dir(F.Flow) if k.startswith("test")})   # helpers only
KEYS = {"name", "t0", "end", "lb", "deny", "dc", "h0", "h1"}


class Ledger(_Base):
    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.proj, ".git"))   # the ledger is written for git repos only
        key = hashlib.sha1(os.path.realpath(self.proj).encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
        self.lf = os.path.join(self.tmp, "eval", key, "runs.jsonl")
        p = mock.patch.object(H, "_head", lambda proj: "abc1234")
        p.start()
        self.addCleanup(p.stop)

    def rows(self):
        if not os.path.exists(self.lf):
            return []
        with open(self.lf, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]

    def test_commit_close_row_allow_listed(self):
        self.pre("설계"), self.post("설계"), self.pre("구현")
        self.t += 5
        self._cmd("git commit -m secret-message")
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertLessEqual(set(rows[0]), KEYS)
        self.assertEqual((rows[0]["name"], rows[0]["t0"], rows[0]["end"], rows[0]["h0"]), (F.N, 1000.0, 1005.0, "abc1234"))
        with open(self.lf, encoding="utf-8") as f:
            raw = f.read()
        self.assertNotIn("secret", raw)
        self._cmd("git commit -m again")   # already ended: no second row
        self.assertEqual(len(self.rows()), 1)

    def test_jump_deny_counted(self):
        self.pre("설계"), self.post("설계")
        self.assertEqual(self.pre("검증")["permissionDecision"], "deny")   # skips 구현
        self._cmd("git commit -m x")
        self.assertEqual(self.rows()[0]["dc"], {"jump": 1})

    def test_last_stage_close(self):
        self.to_review()
        self.pre("리뷰"), self.post("리뷰")
        self.pre("라이브 검증"), self.post("라이브 검증")   # last stage back -> run complete
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["dc"], {})

    def test_denied_commit_writes_no_row(self):
        self.pre("설계"), self.post("설계")
        with mock.patch.object(H, "_flow", lambda plat, ev: True):   # a guard denied the commit
            self._cmd("git commit -m x")
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.run_()["end"], 0)

    def test_no_git_no_row(self):
        os.rmdir(os.path.join(self.proj, ".git"))
        self.pre("설계"), self.post("설계")
        self._cmd("git commit -m x")
        self.assertEqual(self.rows(), [])

    def test_cap_keeps_newest(self):
        with mock.patch.object(H, "OC_LEDGER_MAX", 3):
            for i in range(5):
                H._ledger_add({"proj": self.proj, "t0": i, "lb": [{"f": "a", "g": "b", "n": 1, "x": 1}]}, F.N, 100.0 + i)
        rows = self.rows()
        self.assertEqual([r["end"] for r in rows], [102.0, 103.0, 104.0])
        self.assertEqual(rows[0]["lb"], [{"f": "a", "g": "b", "n": 1}])
        self.assertEqual(sorted(os.listdir(os.path.dirname(self.lf))), ["runs.jsonl"])   # no tmp or lock left behind


if __name__ == "__main__":
    unittest.main()
