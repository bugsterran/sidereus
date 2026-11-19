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
        # 10-feed shows the server text as the shared dialog's body; 36-wkcompose as an inline note.
        sites = (("web/js/10-feed.js", r"uiAlert\(\s*T\('Could not send'\)\s*,\s*\{\s*body:\s*TE\(e\.message\)\s*\}\s*\)"),
                 ("web/js/36-wkcompose.js", r"T\('Could not send'\)\s*\+\s*': '\s*\+\s*TE\(e\.message\)"))
        for rel, pat in sites:
            s = _src(rel)
            self.assertNotRegex(s, r"(?<![A-Za-z_])T\(\s*e\.message\s*\)", rel)
            self.assertRegex(s, pat, rel)


if __name__ == "__main__":
    unittest.main()
