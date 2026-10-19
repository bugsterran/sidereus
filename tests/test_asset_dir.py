"""Asset folder: a clone reads web/ etc. from the repo root; a pipx/uv install reads them from sidereus/_bundle."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests import _load
from tests.test_cli import CliBase

ROOT = _load.ROOT
_load.load()
import mailbox_config  # noqa: E402
from sidereus import config, page, pipeline_projects as PP, pl_eval_view as PV, stage_catalog as SC  # noqa: E402


class Resolver(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-asset-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_clone_tree_is_its_own_asset_dir(self):
        os.makedirs(os.path.join(self.tmp, "web"))
        os.makedirs(os.path.join(self.tmp, "sidereus", "_bundle", "web"))   # a stale bundle must not win in a clone
        self.assertEqual(mailbox_config.asset_dir(self.tmp), self.tmp)

    def test_installed_tree_uses_bundle(self):
        os.makedirs(os.path.join(self.tmp, "sidereus", "_bundle", "web"))
        self.assertEqual(mailbox_config.asset_dir(self.tmp), os.path.join(self.tmp, "sidereus", "_bundle"))


class CloneUnchanged(unittest.TestCase):
    def test_clone_paths(self):
        self.assertEqual(os.path.realpath(config.CODE_DIR), os.path.realpath(ROOT))
        self.assertEqual(config.ASSET_DIR, config.CODE_DIR)
        self.assertTrue(config.IS_CLONE)
        self.assertEqual(page.WEB_DIR, os.path.join(config.CODE_DIR, "web"))


class InstalledPackage(unittest.TestCase):
    def test_pipeline_projects_drop_code_dir(self):
        tmp = tempfile.mkdtemp(prefix="sidereus-asset-")
        self.addCleanup(shutil.rmtree, tmp, True)
        with mock.patch.object(PP, "known_projects", lambda: []), mock.patch.object(PP, "_allowed_cwds", lambda: {}), \
                mock.patch.object(PP, "PROJ_STORE", os.path.join(tmp, "none.json")):
            self.assertIn(config.CODE_DIR, PP.allowed_projects())
            with mock.patch.object(config, "IS_CLONE", False):
                self.assertNotIn(config.CODE_DIR, PP.allowed_projects())

    def test_catalog_hides_templates_needing_the_repo(self):
        with mock.patch.object(SC, "_which", lambda b: None):
            ids = {t["id"] for t in SC.catalog()["items"]}
            needs = {t["id"] for t in SC.load()["templates"]
                     if any("{sidereus}" in str(t.get(k) or "") for k in ("gate", "task"))} & ids
            self.assertTrue(needs)
            with mock.patch.object(config, "IS_CLONE", False):
                left = SC.catalog()["items"]
        self.assertEqual({t["id"] for t in left}, ids - needs)
        self.assertNotIn(config.CODE_DIR, repr(left))

    def test_redcheck_uses_venv_python(self):
        with mock.patch.object(PV.sys, "executable", "/venv/bin/python"):
            self.assertTrue(PV.redcheck_cmd("/p", "x", "t", nt=False).startswith("python3 "))
            with mock.patch.object(config, "IS_CLONE", False):
                self.assertTrue(PV.redcheck_cmd("/p", "x", "t", nt=False).startswith("/venv/bin/python "))


class InstallServiceRefused(CliBase):
    def test_install_service_exits_2_writing_nothing(self):
        c = self.cli
        c.IS_CLONE, c.IS_MAC, c.IS_WIN = False, True, False
        plist = os.path.join(self.tmp, "LaunchAgents", "x.plist")
        c.mac_plist_path = lambda label: plist
        c.answering = lambda port: self.fail("must not probe the port")
        before = sorted(os.listdir(self.tmp))
        self.assertEqual(c.main(["start", "--install-service"]), 2)
        self.assertEqual(sorted(os.listdir(self.tmp)), before)   # no config.local.json, no plist
        self.assertFalse(os.path.exists(plist))
        self.assertEqual(self.ran, [])


if __name__ == "__main__":
    unittest.main()
