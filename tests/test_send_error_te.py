"""Send-failure alerts pass server error text through TE(), never T(): the text may carry a typed room name."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class TestSendErrorTE(unittest.TestCase):
    def test_call_sites_use_te(self):
        for rel in ("web/js/10-feed.js", "web/js/36-wkcompose.js"):
            s = _src(rel)
            self.assertNotRegex(s, r"(?<![A-Za-z_])T\(\s*e\.message\s*\)", rel)
            self.assertRegex(s, r"T\('Could not send'\)\s*\+\s*': '\s*\+\s*TE\(e\.message\)", rel)


if __name__ == "__main__":
    unittest.main()
