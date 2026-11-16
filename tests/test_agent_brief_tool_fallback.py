"""attention.py: an unknown tool is None in v (never a fallback word) and the English why drops the tail; a named tool shows."""
import re
import unittest
from tests._load import sidereus

ab = sidereus("agent_brief")
att = sidereus("attention")
HANGUL = re.compile("[\uac00-\ud7a3]")


class ToolFallback(unittest.TestCase):
    def test_unknown_tool_is_none(self):
        self.assertIsNone(att._tf_tool("Something odd happened"))
        tf = att._why("toolfail", {"n": 4, "tool": None})
        lp = att._why("loop", {"n": 6, "tool": None})
        self.assertEqual(tf, "Same error repeated 4×")
        self.assertEqual(lp, "Same call repeated 6×")
        self.assertEqual(ab._why_en({"k": "loop", "why": lp}), lp)
        self.assertIsNone(HANGUL.search(tf + lp))

    def test_named_tool_still_shows(self):
        self.assertEqual(att._tf_tool("Exit code 2"), "Bash")
        self.assertEqual(att._why("toolfail", {"n": 4, "tool": "Bash"}), "Same error repeated 4× · Bash")
        self.assertEqual(att._why("loop", {"n": 6, "tool": "Bash"}), "Same call repeated 6× · Bash")


if __name__ == "__main__":
    unittest.main()
