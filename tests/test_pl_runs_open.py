"""sidereus/pl_runs.pl_model: an open run (end 0) with nothing live is shown ended after PLR_OPEN_S. Tmp dir, fixed clock."""
import json
import os
import unittest

from tests._load import sidereus
from tests import test_pl_runs as T   # module import: importing the class would re-run its tests here

PR = sidereus("pl_runs")
NOW, SID = T.NOW, T.SID
N = "sidereus-change"


class OpenRun(unittest.TestCase):
    setUp, _ag = T.AgByName.setUp, T.AgByName._ag

    def _file(self, st, cur, t1):
        fp = os.path.join(self.tmp, SID + ".runs.json")
        with open(fp, "w", encoding="utf-8") as f:
            json.dump({"v": 1, "runs": {N: {"t0": t1 - 600, "t1": t1, "cur": cur, "end": 0, "st": st}}}, f)
        os.utime(fp, (NOW, NOW))

    def _main_tail(self, age):
        # (a) last stage run by main via a Bash tag, then a push and no commit: the hook never writes end
        last = NOW - age
        self._file({"리뷰": {"s": "done", "t0": last - 300, "t1": last - 100, "n": 1},
                    "라이브 검증": {"s": "run", "t0": last - 60, "t1": last, "n": 0, "m": True}}, "라이브 검증", last)
        return last

    def _model(self, sub=(), plm=None, bgs=()):
        return PR.pl_model(SID, self.sd, list(sub), plm, NOW, "run", (), list(bgs))[0]

    def test_main_tail_closes_after_idle(self):
        last = self._main_tail(PR.PLR_OPEN_S + 1)
        r = self._model()
        self.assertEqual((r["end"], r["stages"]["라이브 검증"]["o"]), (last, "done"))

    def test_bg_last_stage_closes_after_idle(self):
        # (b) last stage dispatched in background: bg Post only decrements, the agent finished long ago
        last = NOW - PR.PLR_OPEN_S - 60
        self._file({"검증": {"s": "run", "t0": last - 100, "t1": last - 50, "n": 1}}, "검증", last - 50)
        self._ag("b1", "[pl:%s/검증] verify" % N, last - 3)   # jsonl mtime = last
        r = self._model()
        self.assertEqual((r["end"], r["stages"]["검증"]["o"]), (last, "done"))

    def test_skipped_tail_closes_after_idle(self):
        # (c) remaining stages [pl-skip]ed by an older hook that never ended the run
        last = NOW - PR.PLR_OPEN_S - 5
        self._file({"구현": {"s": "done", "t0": last - 100, "t1": last - 10, "n": 1},
                    "라이브 검증": {"s": "skip", "t0": last, "t1": last, "n": 0}}, "구현", last - 10)
        self.assertEqual(self._model()["end"], last)

    def test_idle_short_stays_open(self):
        self._main_tail(600)
        self.assertEqual(self._model()["end"], 0)

    def test_live_agent_keeps_old_run_open(self):
        self._main_tail(45 * 60)
        sub = [{"lab": "general-purpose: [pl:%s/라이브 검증] ship" % N, "min": 45, "aid": "z9", "tid": "tu_z9"}]
        r = self._model(sub=sub)
        self.assertEqual((r["end"], r["stages"]["라이브 검증"]["o"]), (0, "run"))
        self.assertEqual(self._model(bgs=sub)["end"], 0)   # a tagged bg task counts the same

    def test_main_marker_keeps_run_open(self):
        self._main_tail(45 * 60)
        self.assertEqual(self._model(plm={"name": N, "title": "라이브 검증", "age": 5})["end"], 0)
        self.assertEqual(self._model(plm={"name": N, "title": "elsewhere", "age": 5})["end"], 0)

    def test_runs_file_untouched(self):
        self._main_tail(PR.PLR_OPEN_S + 1)
        fp = os.path.join(self.tmp, SID + ".runs.json")
        with open(fp, encoding="utf-8") as f:
            before = f.read()
        self._model()
        with open(fp, encoding="utf-8") as f:
            self.assertEqual(f.read(), before)


if __name__ == "__main__":
    unittest.main()
