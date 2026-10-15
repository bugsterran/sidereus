"""sessions_health.perm_hook_check: one warning per signed-in account whose settings.json lacks perm_mark. Tmp dirs only."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

SH = sidereus("sessions_health")
NOW = 1_800_000_000.0
HOOKED = {"hooks": {"Notification": [{"matcher": "permission_prompt|elicitation_dialog",
                                      "hooks": [{"type": "command", "command": "python3 /x/hooks/perm_mark.py"}]}]},
          "env": {"API_KEY": "SECRET"}}


class PermHookCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.accts = []
        for lab in ("main", "work"):
            d = os.path.join(self.tmp, lab)
            os.makedirs(d)
            self.accts.append({"dir": d, "label": lab, "primary": lab == "main"})
        self.warns = []
        for obj, k, v in ((SH.claude_roots, "accounts", lambda: [dict(a) for a in self.accts]),
                          (SH, "warn_once", lambda key, msg, **kw: self.warns.append((key, msg, kw))),
                          (SH, "_perm_chk", {"at": 0.0, "mt": {}})):
            p = mock.patch.object(obj, k, v)
            p.start()
            self.addCleanup(p.stop)

    def _write(self, lab, cfg):
        with open(os.path.join(self.tmp, lab, "settings.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)

    def test_one_account_missing(self):
        self._write("main", HOOKED)
        self._write("work", {"hooks": {"Stop": [{"hooks": [{"command": "python3 /x/hooks/perm_mark.py"}]}]}})
        self.assertEqual(SH.perm_hook_check(NOW), ["work"])
        self.assertEqual([w[0] for w in self.warns], ["hooks:perm_mark:work"])
        self.assertNotIn("SECRET", repr(self.warns))

    def test_both_hooked_no_warning(self):
        self._write("main", HOOKED)
        self._write("work", {"enabledPlugins": {"sidereus@sidereus": True}})
        self.assertEqual(SH.perm_hook_check(NOW), [])
        self.assertEqual(self.warns, [])

    def test_unused_account_skipped(self):
        self.assertEqual(SH.perm_hook_check(NOW), [])     # no settings.json, no projects/ = fresh install
        self.assertEqual(self.warns, [])

    def test_used_account_without_settings_warns(self):
        os.makedirs(os.path.join(self.tmp, "work", "projects"))
        self.assertEqual(SH.perm_hook_check(NOW), ["work"])
        self.assertIn("setup-claude", self.warns[0][1])

    def test_hook_present_with_projects_no_warning(self):
        for lab in ("main", "work"):
            os.makedirs(os.path.join(self.tmp, lab, "projects"))
            self._write(lab, HOOKED)
        self.assertEqual(SH.perm_hook_check(NOW), [])
        self.assertEqual(self.warns, [])

    def test_throttled(self):
        for lab in ("main", "work"):
            os.makedirs(os.path.join(self.tmp, lab, "projects"))
        self.assertEqual(SH.perm_hook_check(NOW), ["main", "work"])     # used account, no settings file = no hook
        self.assertIsNone(SH.perm_hook_check(NOW + 10))
        self.assertEqual(len(self.warns), 2)


if __name__ == "__main__":
    unittest.main()
