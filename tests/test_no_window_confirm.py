"""R1: every confirm in web/js goes through the shared <dialog> uiConfirm (08c); window.confirm() is gone.
R4 (prompt run): prompt() is gone too (uiPrompt); window.alert() has its own test (test_no_window_alert.py).
Static source scan only; no live files beyond the repo's own web/ sources."""
import glob
import os
import re
import unittest

from tests._load import js_fn

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = os.path.join(ROOT, "web", "js")
WEB = os.path.join(ROOT, "web")

# The 7 named functions that used window.confirm (97-saved-views.js holds the other 2, in anonymous handlers).
FNS = ("plRemove", "plApplySet", "mwSaveRun","mpSrvSetRun", "mpAcctApplyRun", "mpCcSetRun", "mpUiResetRun")


def _code(path):
    with open(path, encoding="utf-8") as f:
        src = f.read()
    return re.sub(r"(^|[^:\\'\"])//[^\n]*", r"\1", src)   # drop // comments (keeps «http://» in strings)


class NoWindowConfirm(unittest.TestCase):
    def test_r4_no_bare_prompt_or_confirm_call(self):
        # ⚠No \s before «(»: the i18n key 'Failure alert ({n})' style text would false-hit a spaced pattern.
        bad = []
        files = sorted(glob.glob(os.path.join(WEB, "*.js")) + glob.glob(os.path.join(JS, "*.js")) + [os.path.join(WEB, "index.html")])
        self.assertGreater(len(files), 50)
        for p in files:
            code = _code(p)
            for m in re.finditer(r"(?<![\w$.])(?:prompt|confirm)\(|window\.(?:prompt|confirm)\b", code):
                bad.append("%s:%d" % (os.path.basename(p), code.count("\n", 0, m.start()) + 1))
        self.assertEqual(bad, [])

    def test_named_sites_await_ui_confirm(self):
        for name in FNS:
            with self.subTest(fn=name):
                self.assertIn("await uiConfirm(", js_fn(name))

    def test_saved_views_two_sites(self):
        self.assertEqual(_code(os.path.join(JS, "97-saved-views.js")).count("await uiConfirm("), 2)


if __name__ == "__main__":
    unittest.main()
