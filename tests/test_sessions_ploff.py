"""Row `plOff` (sessions._pl_off): Apply off for the cwd + [pl:] tagged agents -> True; boolean only.
⚠prefs.CONFIG_PATH points at a temp file and pl_runs._ag_by_name is stubbed — no live config or transcripts."""
import json
import os
import tempfile
import unittest

from tests._load import sidereus

S = sidereus("sessions")
P = sidereus("prefs")
R = sidereus("pl_runs")


class PlOff(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cfg = os.path.join(self.d, "config.local.json")
        self.p0, self.ag0, self.root0, self.memo0 = P.CONFIG_PATH, R._ag_by_name, S._proj_root, dict(S._PL_APPLY)
        P.CONFIG_PATH = self.cfg
        S._proj_root = lambda c: c
        self.ags = {}
        R._ag_by_name = lambda sd, now: self.ags
        self._apply({"mode": "auto", "projects": {"/w/p": "off"}})

    def tearDown(self):
        P.CONFIG_PATH, R._ag_by_name, S._proj_root = self.p0, self.ag0, self.root0
        S._PL_APPLY.clear()
        S._PL_APPLY.update(self.memo0)

    def _apply(self, v):
        with open(self.cfg, "w", encoding="utf-8") as f:
            json.dump({"pipeline_apply": v}, f)
        S._PL_APPLY.update(at=0.0, v=None)

    def test_tag_sources(self):
        lab = [{"lab": "sidereus-implementer: [pl:sidereus-change/Implement] x"}]
        self.assertTrue(S._pl_off("/w/p", "/sd", lab, "", 1000))
        self.assertTrue(S._pl_off("/w/p", "/sd", [], "[pl:x/Verify] run", 1000))
        self.ags = {"x": [{"t1": 1000 - S.PL_OFF_S + 1}]}
        self.assertTrue(S._pl_off("/w/p", "/sd", [], "", 1000))
        self.ags = {"x": [{"t1": 1000 - S.PL_OFF_S - 1}]}   # too old
        self.assertFalse(S._pl_off("/w/p", "/sd", [], "", 1000))
        self.assertFalse(S._pl_off("/w/p", "/sd", [{"lab": "no tag"}], "plain", 1000))

    def test_apply_on_or_other_project(self):
        lab = [{"lab": "[pl:x/A]"}]
        self.assertFalse(S._pl_off("/w/q", "/sd", lab, "", 1000))   # global auto
        self._apply({"mode": "ask", "projects": {}})
        self.assertFalse(S._pl_off("/w/p", "/sd", lab, "", 1000))
        self._apply({"mode": "off", "projects": {"/w/p": "auto"}})
        self.assertFalse(S._pl_off("/w/p", "/sd", lab, "", 1000))   # own override wins
        self.assertTrue(S._pl_off("/w/q", "/sd", lab, "", 1000))
        self.assertFalse(S._pl_off("", "/sd", lab, "", 1000))

    def test_row_key_only_when_true(self):
        with open(S.__file__, encoding="utf-8") as f:
            self.assertIn('**({"plOff": True} if ploff else {})', f.read())


if __name__ == "__main__":
    unittest.main()
