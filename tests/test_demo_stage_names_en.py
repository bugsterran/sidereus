"""Every stage title the demo world puts in a «pipeline · stage» chip has an English name in PLG_NAMES.en.

⚠A demo stage title missing from the map showed Hangul in the English demo's Tools list; demo titles must reuse
the real pipelines' titles, which the map covers."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class DemoStageNamesEn(unittest.TestCase):
    def test_demo_tools_stages_translated(self):
        w = _read(os.path.join("web", "js", "06-i18n-w.js"))
        en = re.search(r"^const PLG_NAMES = \{ en: \{([\s\S]*?)^\}\s*\};?$", w, re.M)
        self.assertIsNotNone(en, "PLG_NAMES.en not found")
        keys = set(re.findall(r"'([^']+)':", en.group(1)))
        stages = set(re.findall(r'"stage": "([^"]+)"', _read(os.path.join("sidereus", "demo_tools.py"))))
        self.assertTrue(stages)
        self.assertEqual(sorted(s for s in stages if re.search("[가-힣]", s) and s not in keys), [])


if __name__ == "__main__":
    unittest.main()
