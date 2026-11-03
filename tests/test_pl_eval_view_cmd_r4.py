"""R4: the red-check command in the DM works without a clone (`sidereus redcheck`); a clone keeps the script path."""
import os
import unittest
from unittest import mock

from tests import _load

_load.load()
from sidereus import config, pl_eval_view as PV  # noqa: E402


class RedcheckCmd(unittest.TestCase):
    def test_install_uses_console_script(self):
        with mock.patch.object(config, "IS_CLONE", False):
            c = PV.redcheck_cmd("/p q", "flow", "Verify", nt=False)
            w = PV.redcheck_cmd("C:\\p q", "flow", "a b", nt=True)
        self.assertTrue(c.startswith("sidereus redcheck --pipeline "), c)
        self.assertIn("--stage Verify --repo '/p q'", c)
        self.assertNotIn("_bundle", c)
        self.assertTrue(w.startswith("sidereus redcheck ") and '--stage "a b"' in w)

    def test_clone_keeps_script_path(self):
        with mock.patch.object(config, "IS_CLONE", True):
            c = PV.redcheck_cmd("/p", "flow", "Verify", nt=False)
        self.assertTrue(c.startswith("python3 "))
        self.assertIn(os.path.join(config.ASSET_DIR, "scripts", "pl_eval.py") + " redcheck", c)

    def test_explicit_code_dir_keeps_script_form(self):   # the demo passes its fake code dir
        with mock.patch.object(config, "IS_CLONE", False):
            self.assertIn(" redcheck --pipeline", PV.redcheck_cmd("/p", "f", "t", code_dir="/ag", nt=False))
            self.assertFalse(PV.redcheck_cmd("/p", "f", "t", code_dir="/ag", nt=False).startswith("sidereus "))

    def test_suggested_for_every_non_empty_gate(self):
        st = [{"title": "a", "gate": "npm test"}, {"title": "b", "gate": "scripts/check.sh --fast"}, {"title": "c", "gate": " "}]
        sg = PV.suggest(st, None, {}, set(), {}, [], lambda t: "cmd " + t)
        self.assertEqual([(s["code"], s["stage"]) for s in sg], [("redcheck", "a"), ("redcheck", "b")])


if __name__ == "__main__":
    unittest.main()
