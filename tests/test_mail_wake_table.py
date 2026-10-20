"""hooks/mail_wait.WAKE: one row per CLI naming how its idle session is woken (EXT_PLAT read as data, no sidereus import)."""
import ast
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("mail_wait_tbl", os.path.join(ROOT, "hooks", "mail_wait.py"))
MW = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(MW)


def ext_plat():
    with open(os.path.join(ROOT, "sidereus", "ext_store.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "EXT_PLAT" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("EXT_PLAT not found")


class WakeTable(unittest.TestCase):
    def test_R4_every_EXT_PLAT_and_claude_has_method(self):
        plats = list(ext_plat()) + ["claude"]
        self.assertGreater(len(plats), 10)
        for p in plats:
            self.assertIn(p, MW.WAKE, p)                   # a new CLI needs its own row
            self.assertIn(MW.wake_method(p), MW.METHODS, p)
        self.assertEqual(set(MW.WAKE), set(plats))         # no stale rows
        self.assertEqual((MW.wake_method("claude"), MW.wake_method("codex"), MW.wake_method("gemini")),
                         ("async-rewake", "app-server-turn", "turn-end"))

    def test_R4_unknown_is_none(self):
        for p in ("nope", "", None, 3, "CODEX"):
            self.assertEqual(MW.wake_method(p), "none")


if __name__ == "__main__":
    unittest.main()
