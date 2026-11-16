"""sidereus/agent_brief.py _why_en: loop/toolfail drop attention.py's Korean unknown-tool fallback word; a named tool still shows."""
import re
import unittest
from tests._load import sidereus

ab = sidereus("agent_brief")
HANGUL = re.compile("[가-힣]")
FALLBACK = "도구"   # attention.py's unknown-tool fallback word
TOOLFAIL = "같은 오류 %d회 반복 · %s"   # attention.py toolfail why template
LOOP = "%s 같은 호출 %d회 반복"   # attention.py loop why template


class ToolFallback(unittest.TestCase):
    def test_unknown_tool_has_no_hangul(self):
        tf = ab._why_en({"k": "toolfail", "why": TOOLFAIL % (4, FALLBACK)})
        lp = ab._why_en({"k": "loop", "why": LOOP % (FALLBACK, 6)})
        self.assertEqual(tf, "Same error repeated 4×")
        self.assertEqual(lp, "Same call repeated 6×")
        self.assertIsNone(HANGUL.search(tf + lp))

    def test_named_tool_still_shows(self):
        self.assertEqual(ab._why_en({"k": "toolfail", "why": TOOLFAIL % (4, "Bash")}), "Same error repeated 4× · Bash")
        self.assertEqual(ab._why_en({"k": "loop", "why": LOOP % ("Bash", 6)}), "Same call repeated 6× · Bash")


if __name__ == "__main__":
    unittest.main()
