"""Keyboard focus survives repaints: segment toggles, the git chip repaint, timeline pipeline chips, and Esc on #tlhc."""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def src(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class KbFocusKeep(unittest.TestCase):
    def test_segment_toggles_refocus(self):
        t = src("web/js/46-tokens-tab.js")
        self.assertIn("function kbHold(", src("web/js/08-ui-kit.js"))
        self.assertIn("kbHold('.wkrgb[data-tv].on')", t)
        self.assertIn("kbHold('.wkrgb[data-plv].on')", src("web/js/48-pipeline.js"))
        self.assertIn("kbHold('#strmd button[data-md]')", src("web/js/81-structure-panel.js"))
        a = src("web/js/84j-structure-arch.js")
        self.assertIn("kbHold('#strmd button[data-ma]')", a)
        self.assertIn("kbHold('.archtab [data-arq]')", a)

    def test_git_chip_repaint_refocuses(self):
        s = src("web/js/77-timeline-git.js")
        body = s[s.index("function tlgPaint("):]
        body = body[:body.index("\n}\n")]
        self.assertIn("if(popIsOpen('ppop')) return;", body)   # an open session picker is never repainted
        self.assertIn("f.focus({preventScroll: true})", body)

    def test_pipeline_chip_lands_on_pipeline(self):
        s = src("web/js/74c-timeline-plrun.js")
        body = s[s.index("function tlPlGo("):]
        body = body[:body.index("\n}\n")]
        self.assertIn("kbHold('.plw [data-ppk=\"plsel\"]', '.mvb.on')", body)

    def test_esc_closes_hover_card(self):
        s = src("web/js/74-timeline.js")
        i = s.index("e.key === 'Escape'")
        self.assertIn("tlHovHide()", s[i:i + 120])


if __name__ == "__main__":
    unittest.main()
