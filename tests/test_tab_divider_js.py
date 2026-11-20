"""One header-to-content divider: tab captions (.wvh.wvht) draw no rule except the timeline axis top,
no extra top padding before the first content, and the Pipelines and Tools sub-view switches live in #tbar (Tokens has none).
Static source reads only."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def src(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class TabDivider(unittest.TestCase):
    def assertBodyFree(self, s, fn, rel):
        """Every statement that builds tab-body html (#feed innerHTML / head / body / h) must not call fn."""
        stmts = re.findall(r"(?:innerHTML\s*=|const (?:head|body|h)\s*=)(.*?);\n", s, re.S)
        self.assertTrue(stmts, rel)
        for st in stmts:
            self.assertNotIn(fn + "(", st, rel)

    def test_caption_has_no_rule_except_timeline_axis(self):
        css = src("web/css/40-tokens.css")
        self.assertIn(".wvh.wvht{border-bottom-width:0}", css)
        self.assertIn("#feed .wvh.wvht:has(+ .tlaxr){border-bottom:1px solid var(--nx-rule)}", css)
        # the timeline caption is directly followed by the axis row
        self.assertIn("box.innerHTML = tlHead\n", src("web/js/74-timeline.js"))
        self.assertRegex(src("web/js/74-timeline.js"), r"= tlHead\s*(//[^\n]*\n\s*)*\+ \('<div class=tlaxr>")

    def test_no_extra_top_padding(self):
        self.assertIn(".brep{container-type:inline-size;padding:0 0 14px}", src("web/css/40-tokens.css"))
        self.assertIn(".rcw{padding:0 4px 20px}", src("web/css/50-layout-feed.css"))

    def test_r2_token_has_no_segment(self):
        s = src("web/js/46-tokens-tab.js")
        self.assertNotIn("tkViewSeg", s)   # Tools/Connections moved to the Pipelines switch
        self.assertIn("tbSet('token', '')", s)   # the toolbar slot is cleared, not left with a stale switch

    def test_pipeline_segment_in_toolbar(self):
        s = src("web/js/48-pipeline.js")
        self.assertRegex(s, r"tbSlot\('pipe',[^;]*plViewSeg\(\)")
        self.assertBodyFree(s, "plViewSeg", "web/js/48-pipeline.js")
        self.assertIn("aria-pressed", s)
        self.assertIn(".tbs > .tkvs{margin:0}", src("web/css/41-tools.css"))

    def test_r1_tools_segment_in_toolbar(self):
        s = src("web/js/47a-tools-tab.js")
        self.assertIn("tbSlot('tools', tlViewSeg())", s)
        self.assertNotIn("innerHTML", s)   # the switch never enters the #feed body
        self.assertIn("aria-pressed", s)
        self.assertIn("html[data-mv=tools] .wrap{max-width:none}", src("web/css/41-tools.css"))


if __name__ == "__main__":
    unittest.main()
