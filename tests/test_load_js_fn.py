"""tests/_load.js_fn finds both `function name(` and `async function name(` at top level,
so tests do not carry their own regex copy for async functions."""
import unittest

from tests._load import js_fn


class JsFn(unittest.TestCase):
    def test_async_function_found_whole(self):
        src = js_fn("plLoadProjs")
        self.assertTrue(src.startswith("async function plLoadProjs("), src[:60])
        self.assertTrue(src.endswith("}"))

    def test_plain_function_unchanged(self):
        self.assertTrue(js_fn("plOvPick").startswith("function plOvPick("))

    def test_missing_name_raises(self):
        with self.assertRaises(LookupError):
            js_fn("noSuchFunctionAnywhere")


if __name__ == "__main__":
    unittest.main()
