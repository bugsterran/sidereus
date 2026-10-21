"""Self-only project flag (pipeline_projects.project_list, pipeline.pipelines): a clone's own repo listed only because
it is the clone is flagged `self_only`, so the page never opens it by default. Known via history/session = normal.

⚠Projects live in a tmp dir: known_projects/_allowed_cwds/_remembered/CODE_DIR on pipeline_projects, IS_CLONE on config.
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

PL = sidereus("pipeline")
PP = sidereus("pipeline_projects")
CFG = sidereus("config")


def _mk(root, name):
    d = os.path.join(root, ".claude", "pipelines")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name + ".json"), "w", encoding="utf-8") as f:
        json.dump({"v": 1, "name": name, "title": name, "rules": "r", "defaults": {"model": "inherit", "retry": 0},
                   "stages": [{"title": "t", "agent": "a"}]}, f)


class SelfOnly(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.me, self.other = os.path.join(self.tmp, "sidereus"), os.path.join(self.tmp, "other")
        os.makedirs(self.me)
        os.makedirs(self.other)
        _mk(self.me, "arch-map")
        self.known, self.cwds = [], {}
        for o, k, v in ((PP, "known_projects", lambda: list(self.known)), (PP, "_allowed_cwds", lambda: dict(self.cwds)),
                        (PP, "_remembered", lambda: []), (PP, "CODE_DIR", self.me), (PL, "CODE_DIR", self.me),
                        (CFG, "IS_CLONE", True)):
            p = mock.patch.object(o, k, v)
            p.start()
            self.addCleanup(p.stop)

    def _list(self):
        code, out = PL.pipelines("")
        self.assertEqual(code, 200)
        return {x["path"]: x.get("self_only", False) for x in out["projects"]}

    def test_fresh_clone_flags_self(self):
        self.assertEqual(PP.project_list(), ([self.me], self.me))
        self.assertEqual(self._list(), {self.me: True})
        self.assertIn(self.me, PP.allowed_projects())   # still allowed (chip stays clickable)

    def test_history_makes_it_normal(self):
        self.known = [self.me]
        self.assertEqual(PP.project_list()[1], "")
        self.assertEqual(self._list(), {self.me: False})

    def test_live_session_cwd_makes_it_normal(self):
        self.cwds = {self.me: {"cwd": self.me, "repos": []}}
        self.assertEqual(self._list(), {self.me: False})

    def test_session_repo_makes_it_normal(self):
        self.cwds = {self.other: {"cwd": self.other, "repos": [self.other, self.me]}}
        self.assertEqual(PP.project_list()[1], "")

    def test_installed_package_lists_no_self(self):
        with mock.patch.object(CFG, "IS_CLONE", False):
            self.assertEqual(PP.project_list(), ([], ""))


if __name__ == "__main__":
    unittest.main()
