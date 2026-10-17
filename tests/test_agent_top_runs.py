"""«오늘 비싼 작업 상위 5»: top-N subagent runs from the usage index (sidereus/agentcost.py _agc_top/_day0/_agc_rows)."""
import json
import os
import tempfile
import time
import unittest

from tests._load import sidereus, load

load()
ac = sidereus("agentcost")


def _h(pairs):
    return {str(k): {"m": list(v)} for k, v in pairs}


class TopRuns(unittest.TestCase):
    def setUp(self):
        self.d0 = ac._day0(1, now=time.mktime((2026, 9, 25, 15, 30, 0, 0, 0, -1)))
        self.S = os.sep + "p" + os.sep + "sid1" + os.sep + "subagents" + os.sep

    def test_day0_is_local_midnight(self):
        lt = time.localtime(self.d0)
        self.assertEqual((lt.tm_mday, lt.tm_hour, lt.tm_min), (25, 0, 0))
        self.assertEqual(ac._day0(7, now=self.d0 + 3600), self.d0 - 6 * 86400)

    def test_order_boundary_share(self):
        d0 = self.d0
        items = [
            (self.S + "agent-a.jsonl", _h([(d0, (10, 0, 0, 0)), (d0 - 3600, (999, 0, 0, 0))])),  # yesterday excluded
            (self.S + "agent-b.jsonl", _h([(d0 + 3600, (20, 5, 3, 2))])),
            (self.S + "agent-c.jsonl", _h([(d0 - 7200, (500, 0, 0, 0))])),                       # only before today
            ("/p/sid1.jsonl", _h([(d0, (60, 0, 0, 0))])),                                          # main: total only
        ]
        runs, tot = ac._agc_top(items, d0, n=5)
        self.assertEqual([fp.rsplit(os.sep, 1)[1] for _t, fp in runs], ["agent-b.jsonl", "agent-a.jsonl"])
        self.assertEqual([t for t, _fp in runs], [30, 10])
        self.assertEqual(tot, 100)
        self.assertEqual(len(ac._agc_top(items, d0, n=1)[0]), 1)
        self.assertEqual(ac._agc_top(items, d0 - 86400)[0][0][0], 1009)   # wider window picks up yesterday

    def test_rows_metadata_and_share(self):
        root = tempfile.mkdtemp()
        sub = os.path.join(root, "-x-proj", "sid9", "subagents")
        os.makedirs(sub)
        fp = os.path.join(sub, "agent-z.jsonl")
        open(fp, "w", encoding="utf-8").close()
        with open(fp[:-6] + ".meta.json", "w", encoding="utf-8") as f:
            json.dump({"agentType": "Explore", "description": "Find thing", "toolUseId": "toolu_1"}, f)
        orig = ac._agc_cwd
        ac._agc_cwd = lambda slug: ""
        try:
            r = ac._agc_rows([(25, fp)], 200)[0]
        finally:
            ac._agc_cwd = orig
            ac._agc_meta.pop(fp, None)
        self.assertEqual((r["type"], r["desc"], r["tid"], r["proj"], r["share"]),
                         ("Explore", "Find thing", "toolu_1|sid9", "-x-proj", 12.5))


if __name__ == "__main__":
    unittest.main()
