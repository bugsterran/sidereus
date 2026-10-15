"""Brand mark in web/index.html: title, favicon data URI and the header svg; the FAV_DOT unread variant keeps its anchor."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class BrandMark(unittest.TestCase):
    def setUp(self):
        self.html = _read("web/index.html")
        m = re.search(r'<link rel=icon id=fav href="([^"]+)">', self.html)
        self.assertIsNotNone(m)
        self.fav = m.group(1)

    def test_title_starts_with_sidereus(self):
        m = re.search(r"<title>([^<]*)</title>", self.html)
        self.assertTrue(m and m.group(1).startswith("Sidereus"), m and m.group(1))

    def test_favicon_ends_with_svg_close(self):
        self.assertTrue(self.fav.startswith("data:image/svg+xml,"))
        self.assertTrue(self.fav.endswith("%3C/svg%3E"))

    def test_header_mark_is_status_dot_with_moon_phase(self):
        m = re.search(r"<nav id=rail[^>]*>\s*<div class=rbrand>(<svg class=brandmk[^>]*>)(.*?)</svg><h1>Sidereus</h1>(?:<button class=railtg [^>]*>.*?</button>)?</div>", self.html, re.S)
        self.assertIsNotNone(m)
        tag, body = m.group(1), m.group(2)
        self.assertIn("id=dot", tag)
        self.assertEqual(self.html.count("id=dot"), 1)   # poll() / statusbar read this one element
        self.assertIn("role=img", tag)
        self.assertIn("aria-label=Sidereus", tag)
        self.assertNotIn("aria-hidden", tag)
        self.assertTrue(body.startswith("<title>Sidereus</title>"))
        self.assertEqual(body.count("<title>"), 1)   # 92e-moon.js rewrites this one as the phase tooltip
        self.assertEqual(len(re.findall(r"<circle class=bmdk ", body)), 1)
        self.assertEqual(len(re.findall(r"<path class=bmlit ", body)), 1)
        self.assertIn('<circle class="bmlit bmpk" ', body)
        self.assertEqual(len(re.findall(r"<circle class=bmol ", body)), 1)
        # maria are clipped by the lit path (92e-moon.js writes the same d to both)
        self.assertRegex(body, r'<clipPath id=bmclip><path d="[^"]+"/></clipPath>')
        self.assertEqual(self.html.count("id=bmclip"), 1)
        mar = re.search(r'<g class=bmmar clip-path="url\(#bmclip\)">(.*?)</g>', body)
        self.assertTrue(mar and mar.group(1).count("<circle") >= 2)
        for old in ("bmorb", "bmpl", "bmbd", "bmring"):
            self.assertNotIn(old, body)

    def test_off_rules_and_no_orbit_left(self):
        css = _read("web/css/93-header-toolbar.css")
        self.assertRegex(css, r"\.brandmk\.off \.bmlit\{opacity:\.4\}")
        self.assertRegex(css, r"\.brandmk\.off \.bmol\{stroke:var\(--nx-err")
        self.assertRegex(css, r"\.brandmk\.es \.bmdk\{")   # new moon = earthshine disc
        self.assertRegex(css, r"html\[data-theme=light\] \.brandmk\{--bm-dk:")
        # light theme sets variables only: a themed .bmol rule would outrank the .off error stroke
        self.assertNotRegex(css, r"html\[data-theme=light\] \.brandmk \.bm")
        for old in ("bmorb", "bmorbit", "bmpl", "bmring", "prefers-reduced-motion:reduce){.brandmk"):
            self.assertNotIn(old, css)
        self.assertNotIn("Jupiter", _read("web/index.html"))
        self.assertNotIn("Galilean", _read("web/index.html"))

    def test_wordmark_clipped_while_collapsed_visible_when_open(self):
        css = _read("web/css/93b-rail.css")
        self.assertEqual(self.html.count("<h1>"), 1)
        # collapsed: clipped (not display:none, so screen readers keep the name)
        m = re.search(r"#rail:not\(\.open\) :is\(([^)]*)\)\{([^}]*)\}", css)
        self.assertIsNotNone(m)
        self.assertIn(".rbrand > h1", m.group(1))
        self.assertIn("clip-path:inset(50%)", m.group(2))
        self.assertIn("position:absolute", m.group(2))
        # open: no rule clips or hides the wordmark
        base = re.search(r"#rail \.rbrand > h1\{([^}]*)\}", css)
        self.assertIsNotNone(base)
        self.assertNotIn("clip", base.group(1))
        self.assertNotRegex(css, r"#rail\.open[^{]*h1\{[^}]*(clip|display:none)")
        self.assertNotRegex(css, r"h1\{display:none")
        self.assertNotIn("hf4", _read("web/css/93-header-toolbar.css"))

    def test_fav_dot_anchor_found_once_at_end(self):
        js = _read("web/js/15-alarms.js")
        m = re.search(r'FAV_PLAIN\.replace\("([^"]+)"', js)
        self.assertIsNotNone(m)
        anchor = m.group(1)
        # String.replace hits the first occurrence; it must be the closing tag so the dot is drawn on top
        self.assertEqual(self.fav.find(anchor), len(self.fav) - len(anchor))
        self.assertIn("viewBox='0 0 32 32'", self.fav)
        self.assertEqual(self.fav.count("%3C/svg%3E"), 1)
        self.assertIn("%3Cpath d=", self.fav)   # lit half with the rough terminator
        # the badge must not touch the moon disc or anything on it
        b = re.search(r"cx='([\d.]+)' cy='([\d.]+)' r='([\d.]+)'", js[m.end():])
        bx, by, br = (float(v) for v in b.groups())
        self.assertLessEqual(bx + br, 32.01)
        self.assertGreaterEqual(by - br, -0.01)
        for cx, cy, r in re.findall(r"%3Ccircle cx='([\d.]+)' cy='([\d.]+)' r='([\d.]+)'", self.fav):
            gap = ((bx - float(cx)) ** 2 + (by - float(cy)) ** 2) ** .5 - br - float(r)
            self.assertGreater(gap, 0.3, (cx, cy, r))


if __name__ == "__main__":
    unittest.main()
