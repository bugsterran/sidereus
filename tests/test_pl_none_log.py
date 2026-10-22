"""#16 [pl-none:<cat>] per-project log: hooks/pl_flow.py _none_log (R1, R2) and pl_runs.pl_none_counts (R3).
Tmp dirs only, fixed clock."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests import test_pl_flow_none as N   # ⚠not `from … import PlNone`: its tests would run again here
from tests._load import sidereus

H = N.H
R = sidereus("pl_runs")
DAY = 86400


class NoneLog(unittest.TestCase):
    setUp = N.PlNone.setUp
    _ev = N.PlNone._ev
    bash = N.PlNone.bash
    denied = N.PlNone.denied

    def lines(self):
        p = os.path.join(self.marks, H.NONE_LOG)
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            return [json.loads(x) for x in f.read().splitlines()]

    def test_r1_declaration_appends_one_line_and_keeps_session_file(self):
        self.bash("ls", "[pl-none:small-fix] why")
        self.t = 1005.0
        self.bash("ls", "[pl-none:explore] why")
        self.assertEqual(self.lines(), [{"v": 1, "proj": self.proj, "cat": "small-fix", "t": 1000.0},
                                        {"v": 1, "proj": self.proj, "cat": "explore", "t": 1005.0}])
        with open(self.nf, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"v": 1, "cat": "explore", "t": 1005.0})   # per-session overwrite unchanged

    def test_r1_no_project_or_bad_category_appends_nothing(self):
        self.bash("ls", "[pl-none:small-fix] why", cwd=self.bare)
        self.bash("ls", "[pl-none:bogus] why")
        self.assertEqual(self.lines(), [])

    def test_r2_log_holds_no_description(self):
        self.bash("ls -la /secret/dir", "[pl-none:other] secret reason text")
        with open(os.path.join(self.marks, H.NONE_LOG), encoding="utf-8") as f:
            raw = f.read()
        self.assertNotIn("secret", raw)
        self.assertEqual(set(json.loads(raw)), {"v", "proj", "cat", "t"})

    def test_r1_log_failure_never_blocks(self):
        with mock.patch.object(H.os, "open", side_effect=OSError("disk")):
            H._none_log(self.proj, "other", 1000.0)   # no raise
        with mock.patch.object(H, "_none_log", side_effect=RuntimeError("x")):
            self.assertFalse(self.denied(self.bash("ls", "[pl-none:other] x")))   # fail-open even if logging raised

    def test_r1_trim_drops_old_lines_and_caps_size(self):
        os.makedirs(self.marks, exist_ok=True)
        p = os.path.join(self.marks, H.NONE_LOG)
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps({"v": 1, "proj": self.proj, "cat": "other", "t": 0}) + "\n")
        now = 100 * DAY
        H._none_log(self.proj, "explore", now)
        self.assertEqual([x["t"] for x in self.lines()], [now])   # older than 90 d gone
        with mock.patch.object(H, "NONE_LOG_MAX", 400):
            for i in range(20):
                H._none_log(self.proj, "explore", now + i)
            self.assertLessEqual(os.path.getsize(p), 400)
        self.assertEqual(self.lines()[-1]["t"], now + 19)   # newest kept


class NoneCounts(unittest.TestCase):
    def setUp(self):
        self.d0 = R.PLR_DIR
        R.PLR_DIR = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, R.PLR_DIR)
        self.addCleanup(setattr, R, "PLR_DIR", self.d0)

    def _put(self, rows):
        with open(os.path.join(R.PLR_DIR, R.PLR_NONE_LOG), "w", encoding="utf-8") as f:
            for r in rows:
                f.write((r if isinstance(r, str) else json.dumps(r)) + "\n")

    def test_r3_counts_per_project_and_category_within_days(self):
        now = 50 * DAY
        self._put([{"v": 1, "proj": "/a", "cat": "small-fix", "t": now - 1},
                   {"v": 1, "proj": "/a", "cat": "small-fix", "t": now - 2 * DAY},
                   {"v": 1, "proj": "/a", "cat": "explore", "t": now - 3},
                   {"v": 1, "proj": "/b", "cat": "no-fit", "t": now - 6 * DAY},
                   {"v": 1, "proj": "/b", "cat": "no-fit", "t": now - 8 * DAY},   # outside 7 d
                   {"v": 1, "proj": "/b", "cat": "refactor", "t": now},          # not allow-listed
                   {"v": 1, "proj": "rel", "cat": "other", "t": now},            # not absolute
                   {"v": 1, "proj": "/b", "cat": "other", "t": True},
                   "not json", "[1]"])
        self.assertEqual(R.pl_none_counts(7, now), {"/a": {"small-fix": 2, "explore": 1}, "/b": {"no-fit": 1}})
        self.assertEqual(R.pl_none_counts(1, now), {"/a": {"small-fix": 1, "explore": 1}})

    def test_r3_missing_file_and_byte_cap(self):
        self.assertEqual(R.pl_none_counts(7, 0), {})
        self._put([{"v": 1, "proj": "/a", "cat": "other", "t": 10}] * 50)
        with mock.patch.object(R, "PLR_NONE_LOG_MAX", 200):
            n = R.pl_none_counts(7, 10)["/a"]["other"]
        self.assertTrue(0 < n < 50)   # bounded tail read, cut first line skipped


if __name__ == "__main__":
    unittest.main()
