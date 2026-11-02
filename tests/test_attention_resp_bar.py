"""The «Needs your response» bar is an inset shadow, not a wider border (keeps row content aligned)."""
import os
import re
import unittest

CSS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "css", "62-attention.css")


class AttentionRespBar(unittest.TestCase):
    def test_resp_row_uses_inset_shadow(self):
        with open(CSS, encoding="utf-8") as f:
            src = f.read()
        rules = re.findall(r"html\[data-ui=next\] \.attn \.atr\.resp\{([^}]*)\}", src)
        self.assertTrue(rules)
        body = ";".join(rules)
        self.assertNotIn("border-left", body)
        # ⚠ must out-specify `.acb:is(.sxw,.srecr,.atr)` (60-sessions.css) so the teal shadow does not stack
        self.assertIn("box-shadow:inset 3px 0 0 var(--nx-err)", body)


if __name__ == "__main__":
    unittest.main()
