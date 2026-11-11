"""pl_outcome.verdict (R1) at each boundary, demo body agrees (R1), shipped guides for the ids (R3). Pure: no files but repo docs."""
import os
import unittest

from tests._load import ROOT, load, sidereus

load()
OC = sidereus("pl_outcome")
VG = sidereus("verdict_guide")
DT = sidereus("demo_tools")


def oc(broke=0, runs=5, cur=(0, 10), prev=(0, 10)):
    """Raw outcome() shape (with a per-PASS list), counts() reads it."""
    return {"proc": {"runs": runs, "jump": 0},
            "lb": {"cur": {"n": cur[1], "k": cur[0]}, "prev": {"n": prev[1], "k": prev[0]}},
            "result": {"n": max(broke, 1), "broke": broke, "fixed": 0, "unchecked": 0, "partial": False, "list": []}}


class Verdict(unittest.TestCase):
    def test_r1_broke_first(self):
        self.assertEqual(OC.verdict(oc(broke=1, runs=3)), "pl_broke")

    def test_r1_too_few_boundary(self):
        self.assertEqual(OC.verdict(oc(runs=4)), "pl_too_few")
        self.assertNotEqual(OC.verdict(oc(runs=5)), "pl_too_few")

    def test_r1_loopback_rise_boundary(self):
        self.assertEqual(OC.OC_LB_RISE_PP, 15)
        self.assertEqual(OC.verdict(oc(cur=(14, 100), prev=(0, 10))), "healthy")
        self.assertEqual(OC.verdict(oc(cur=(15, 100), prev=(0, 10))), "pl_loopback")

    def test_r1_missing_prev_is_not_zero(self):
        self.assertEqual(OC.verdict(oc(cur=(10, 10), prev=(0, 0))), "healthy")

    def test_r1_raw_and_counts_shapes_agree(self):
        for o in (oc(broke=1, runs=3), oc(runs=4), oc(cur=(15, 100)), oc()):
            c = OC.counts(o)
            self.assertEqual(OC.verdict(o), OC.verdict(c))
            self.assertEqual(c["verdict"], OC.verdict(o))
            self.assertIn(OC.verdict(o), OC.OC_VERDICT)

    def test_r1_junk_is_too_few(self):
        self.assertEqual(OC.verdict(None), "pl_too_few")

    def test_r1_demo_literal_matches(self):
        demo = DT.DEMO_EVAL["outcome"]
        self.assertEqual(demo["verdict"], "pl_broke")
        self.assertEqual(demo["verdict"], OC.verdict(demo))


class Guides(unittest.TestCase):
    def setUp(self):
        self._old = VG.VG_DIR
        VG.VG_DIR = os.path.join(ROOT, "docs", "verdicts")   # repo docs, not live user data
        VG._VG_CACHE.clear()

    def tearDown(self):
        VG.VG_DIR = self._old
        VG._VG_CACHE.clear()

    def test_r3_ids_load_en_and_ko(self):
        en, ko = VG.load("en"), VG.load("ko")
        for vid, who in (("pl_broke", "ai"), ("pl_loopback", "ai"), ("pl_too_few", "owner")):
            self.assertTrue(os.path.isfile(os.path.join(VG.VG_DIR, vid + ".ko.md")), vid)
            self.assertEqual(en[vid]["who"], who)
            self.assertEqual(ko[vid]["who"], who)
            self.assertNotEqual(en[vid]["meaning"], ko[vid]["meaning"])
        self.assertNotIn("healthy", en)
