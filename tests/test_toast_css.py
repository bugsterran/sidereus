"""Toasts wrap long unbroken text (e.g. a saved-view name) instead of running past the viewport."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def css(name):
    with open(os.path.join(ROOT, "web", "css", name), encoding="utf-8") as fh:
        return re.sub(r"/\*.*?\*/", "", fh.read(), flags=re.S)


class ToastWrap(unittest.TestCase):
    def test_toast_breaks_long_words(self):
        m = re.search(r"(?:^|[}\s])\.toast\{([^}]*)\}", css("70-health.css"))
        self.assertIsNotNone(m)
        self.assertIn("overflow-wrap:anywhere", m.group(1))


if __name__ == "__main__":
    unittest.main()
