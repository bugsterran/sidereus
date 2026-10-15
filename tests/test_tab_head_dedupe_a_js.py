"""Tab heads do not repeat the header title (#vtitle): timeline, tokens, tools and insights keep only the caption.
Static source reads only."""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def src(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class TabHeadDedupeA(unittest.TestCase):
    FILES = {"web/js/74-timeline.js": "Timeline", "web/js/46-tokens-tab.js": "Token report",
             "web/js/47-tools.js": "Token report", "web/js/86-retro.js": "Insights"}

    def test_no_tab_name_in_head(self):
        for rel, name in self.FILES.items():
            s = src(rel)
            self.assertNotIn("T('%s')" % name, s, rel)
            for line in s.splitlines():
                if "tlhd" in line or "wvht" in line:
                    self.assertNotRegex(line, r"<b>'\s*\+\s*esc\(T\('", rel)

    def test_captions_stay(self):
        self.assertIn("Building timeline…", src("web/js/74-timeline.js"))
        self.assertIn("Measuring…", src("web/js/46-tokens-tab.js"))
        self.assertIn("Tool list · 30-day use", src("web/js/47-tools.js"))
        self.assertRegex(src("web/js/86-retro.js"), r"meta \? '<div class=tlhd>'\+meta")

    def test_subagent_timeline_head_stays(self):
        self.assertIn("Subagent timeline", src("web/js/74b-timeline-rows.js"))

    def test_i18n_entry_gone(self):
        self.assertNotIn("'Token report':", src("web/js/05a-i18n-en.js"))

    def test_css_guard(self):
        css = src("web/css/40-tokens.css")
        self.assertIn(".wvh.wvht:not(:has(>b))", css)
        self.assertIn(".tlhd:empty{display:none}", css)


if __name__ == "__main__":
    unittest.main()
