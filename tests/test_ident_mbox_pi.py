"""pi rows get the id pi logs in as (`pi:<cwd>` or <folder>-pi, same rule as gemini_mail_stop.gemini_id for pi), never the Claude id."""
import os
import tempfile
import unittest

from tests._load import sidereus

ident = sidereus("ident")


class MboxPi(unittest.TestCase):
    def setUp(self):
        self.cwd = os.path.join(os.path.realpath(tempfile.mkdtemp()), "proj")
        os.makedirs(self.cwd)
        self.idj = {}
        self._load = ident._load
        ident._load = lambda name, default: self.idj if name == "identity.json" else default

    def tearDown(self):
        ident._load = self._load

    def test_folder_fallback_not_claude_id(self):
        self.idj[self.cwd] = "claude-role"
        self.assertEqual(ident.mbox_pi(self.cwd), ("proj-pi", "folder"))

    def test_explicit_entry_may_name_claude_id(self):
        self.idj[self.cwd] = "advocate"
        self.idj["pi:" + self.cwd] = "advocate"
        self.assertEqual(ident.mbox_pi(self.cwd), ("advocate", "identity"))

    def test_folder_fallback_owned_by_claude_is_refused(self):
        self.idj["/elsewhere"] = "proj-pi"
        self.assertEqual(ident.mbox_pi(self.cwd), ("", "none"))

    def test_matches_wake_rule(self):
        import importlib.util
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        spec = importlib.util.spec_from_file_location("gms_t", os.path.join(here, "ext-hooks", "gemini_mail_stop.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m.set_platform("pi")
        for idj in ({}, {self.cwd: "c"}, {"pi:" + self.cwd: "x"}):
            self.idj = idj
            want = m.gemini_id(self.cwd, idj)
            self.assertEqual(ident.mbox_pi(self.cwd)[0], want or "")


if __name__ == "__main__":
    unittest.main()
