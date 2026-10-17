"""Pipelines / Structure / Branch content heads do not repeat the header tab title (#vtitle).

Static reads of web/js/48-pipeline.js, 80-structure.js, 88-branch.js and web/css/75-structure.css.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def src(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class TabHeadDedupeB(unittest.TestCase):
    def test_no_tab_title_in_wvht_bold(self):
        for rel, name in (("web/js/48-pipeline.js", "Pipelines"), ("web/js/80-structure.js", "Structure"),
                          ("web/js/88-branch.js", "Branches")):
            for line in src(rel).splitlines():
                if "wvht" in line:
                    self.assertNotIn("T('%s')" % name, line, rel)

    def test_pipeline_keeps_tooling_and_caption(self):
        s = src("web/js/48-pipeline.js")
        self.assertIn("'<b>' + esc(T('Harness')) + '</b>'", s)
        self.assertIn("T('Agent and model per stage')", s)

    def test_structure_head_keeps_controls(self):
        m = re.search(r"const head = \(note, ex, pre\) =>(.*?)\n\s*\+ '<div class=strctl>'", src("web/js/80-structure.js"), re.S)
        self.assertIsNotNone(m)
        self.assertNotIn("<b>", m.group(1))

    def test_branch_head_keeps_count_span(self):
        self.assertIn("function brHeadHtml(n){ return '<div class=\"wvh wvht\"><span>' + n", src("web/js/88-branch.js"))

    def test_dead_strh_bold_rules_gone(self):
        css = src("web/css/75-structure.css")
        self.assertNotIn(".strh>b", css)
        self.assertIn(".wvh.strh>span{flex:1 1 auto", css)


if __name__ == "__main__":
    unittest.main()
