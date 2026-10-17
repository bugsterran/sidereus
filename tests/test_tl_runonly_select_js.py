"""Timeline toolbar «Rows» (web/js/74b tlCtlHtml): a select with «All rows» / «Running only» (0/1), not a toggle chip."""
import re
import unittest

from tests._load import js_fn


class TlRunOnlySelect(unittest.TestCase):
    def test_select_with_two_options(self):
        src = js_fn("tlCtlHtml")
        self.assertIn("<select class=tlsel id=tlro", src)
        self.assertRegex(src, r"<option value=\"0\".*All rows")
        self.assertRegex(src, r"<option value=\"1\".*Running only")
        self.assertNotRegex(src, r"id=tlro[^>]*role=button")

    def test_wired_on_change_same_storage(self):
        src = js_fn("tlWireCtl")
        self.assertIn("ro.onchange", src)
        self.assertNotIn("ro.onclick", src)
        self.assertTrue(re.search(r"lsSet\('sidereus\.tlrun', tlRunOnly \? '1' : '0'\)", src))


if __name__ == "__main__":
    unittest.main()
