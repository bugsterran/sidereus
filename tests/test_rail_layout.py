"""Left rail + one-row header: index.html skeleton ids and the 93b-rail.css contract (z-order, padding, clipped labels, popups)."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _rules(css):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return re.findall(r"([^{}]+)\{([^{}]*)\}", css)


class RailSkeleton(unittest.TestCase):
    def setUp(self):
        self.html = _read("web/index.html")
        self.nav = re.search(r"<nav id=rail[^>]*>(.*?)</nav>", self.html, re.S)
        self.hdr = re.search(r"<header>(.*?)</header>", self.html, re.S)

    def test_rail_before_header_with_label(self):
        self.assertIsNotNone(self.nav)
        self.assertLess(self.html.index("<nav id=rail"), self.html.index("<header>"))
        self.assertIn('aria-label="Main navigation"', self.nav.group(0).split(">", 1)[0])

    def test_rail_children_in_order(self):
        body = self.nav.group(1)
        order = ["class=rbrand", "id=railtg", "id=rattn ", "id=rattnn", "id=rattnl", "id=rattnb", "id=mvw", "class=rbot", "id=bell", "id=gear"]
        pos = [body.find(k) for k in order]
        self.assertNotIn(-1, pos, dict(zip(order, pos)))
        self.assertEqual(pos, sorted(pos))
        tg = re.search(r"<button[^>]*id=railtg[^>]*>", body).group(0)
        self.assertIn("aria-controls=rail", tg)
        self.assertIn("aria-expanded=false", tg)
        for b in ("bell", "gear"):
            m = re.search(r"<button[^>]*id=%s[^>]*>(.*?)</button>" % b, body, re.S)
            self.assertIn("<span class=rlab>", m.group(1))

    def test_ids_once_and_header_row(self):
        for i in ("rail", "railtg", "rattn", "rattnn", "rattnl", "rattnb", "railscrim", "vtitle", "mvw", "bell", "gear", "dot"):
            self.assertEqual(len(re.findall(r"id=%s[ >]" % i, self.html)), 1, i)
        self.assertRegex(self.html, r"<div id=railscrim hidden></div>")
        row = re.search(r"<div class=hrow>(.*?)\n</div>", self.hdr.group(1), re.S).group(1)
        order = ["id=vtitle", "id=todo", "id=sesb"]
        pos = [row.find(k) for k in order]
        self.assertNotIn(-1, pos)
        self.assertEqual(pos, sorted(pos))
        for gone in ("id=mvw", "id=bell", "id=gear", "id=dot", "<h1>", "id=actv"):  # activity strip removed
            self.assertNotIn(gone, self.hdr.group(1))
        for kept in ("id=todo2", "id=hlb", "id=tbar"):
            self.assertIn(kept, self.hdr.group(1))
        self.assertNotRegex(self.hdr.group(1), r"id=kn[ >]")  # header KPI strip removed


class RailCss(unittest.TestCase):
    def setUp(self):
        self.css = _read("web/css/93b-rail.css")
        self.rules = _rules(self.css)

    def _decl(self, sel_re):
        out = [d for s, d in self.rules if re.search(sel_re, s)]
        self.assertTrue(out, sel_re)
        return " ".join(out)

    def test_every_rule_scoped_and_tokens_only(self):
        for sel, decl in self.rules:
            for part in re.split(r",(?![^()]*\))", sel):
                self.assertTrue(part.strip().startswith("html[data-ui=next]"), part)   # keeps the #nxcss twin pass off
            self.assertEqual(re.findall(r"#[0-9a-fA-F]{3,8}\b", decl.replace("#fff", "")), [], sel)

    def test_hidden_unless_body_rail(self):
        self.assertIn("display:none", self._decl(r"^\s*html\[data-ui=next\] #rail,"))
        self.assertIn("display:flex", self._decl(r"body\.rail #rail$"))

    def test_padding_and_widths(self):
        self.assertIn("padding-left:56px", self._decl(r"body\.rail$"))
        self.assertIn("padding-left:208px", self._decl(r"body\.rail\.railpush$"))
        self.assertIn("width:56px", self._decl(r"body\.rail #rail$"))
        self.assertIn("width:208px", self._decl(r"body\.rail #rail\.open$"))

    def test_z_order_below_drawer_alarm_modals(self):
        z = lambda d: int(re.search(r"z-index:(\d+)", d).group(1))
        collapsed, over, scrim = z(self._decl(r"body\.rail #rail$")), z(self._decl(r"body\.railover #rail$")), z(self._decl(r"#railscrim:not"))
        self.assertEqual((collapsed, over, scrim), (25, 43, 42))
        self.assertLess(over, 44)   # sessions drawer 44 · alarm 45 · popups 46/47 · modals 60

    def test_collapsed_labels_clipped_not_display_none(self):
        m = re.search(r"#rail:not\(\.open\) :is\(([^)]*)\)\{([^}]*)\}", self.css)
        self.assertIsNotNone(m)
        for k in (".mvl", ".rlab", ".rbrand > h1"):
            self.assertIn(k, m.group(1))
        self.assertIn("clip-path:inset(50%)", m.group(2))
        for sel, decl in self.rules:
            if re.search(r"\.(mvl|rlab)\b", sel):
                self.assertNotIn("display:none", decl, sel)

    def test_toggle_in_brand_row_over_mark_when_collapsed(self):
        # Open = borderless button at the brand row's right end; collapsed = laid over the 34px mark, no layout shift.
        brand = re.search(r"<div class=rbrand>(.*?)</div>", _read("web/index.html"), re.S).group(1)
        self.assertLess(brand.index("id=dot"), brand.index("id=railtg"))
        base = self._decl(r"#rail \.railtg$")
        for k in ("border:0", "width:28px", "height:28px", "margin:0 0 0 auto"):
            self.assertIn(k, base)
        self.assertIn("width:34px;height:34px", self._decl(r"\.rbrand > \.brandmk$"))
        self.assertIn("position:absolute", self._decl(r"#rail:not\(\.open\) \.railtg$"))
        self.assertIn("position:relative", self._decl(r"#rail \.rbrand$"))
        self.assertIn("visibility:hidden", self._decl(r":has\(> \.railtg:is\(:hover,:focus-visible\)\) > \.brandmk$"))
        self.assertIn("outline:", self._decl(r"\.railtg:focus-visible$"))

    def test_popups_drop_rail_and_padding(self):
        self.assertIn("display:none", self._decl(r"body:is\(\.dpop,\.spop,\.wpop\) #rail"))
        self.assertIn("padding-left:0", self._decl(r"body\.rail:is\(\.dpop,\.spop,\.wpop\)$"))
        # the popup reset comes after the push padding (equal specificity, later wins)
        self.assertGreater(self.css.index("body.rail:is(.dpop,.spop,.wpop)"), self.css.index("body.rail.railpush{"))


class HeaderRow(unittest.TestCase):
    def test_ladder_gone_and_row_one_line(self):
        css = _read("web/css/93-header-toolbar.css")
        self.assertNotRegex(css, r"\.hf[1-6]\b")
        self.assertNotIn(".mvic{display:none}", css)
        m = re.search(r"\.hrow\{([^}]*min-height:48px[^}]*)\}", css)
        self.assertIsNotNone(m)
        self.assertIn("flex-wrap:nowrap", m.group(1))
        self.assertRegex(css, r"\.brandmk\{")

    def test_no_activity_strip_css(self):
        css = _read("web/css/94-activity.css")
        self.assertNotRegex(css, r"\.actv\b|\.acc\b|\.actpop\b")

    def test_alarm_below_bar(self):
        css = _read("web/css/65-code-compose-alarm.css")
        self.assertRegex(css, r"\.alarm\{[^}]*top:56px")


class KpiStripCssGone(unittest.TestCase):
    def test_no_strip_selectors(self):
        for f in ("web/css/90-main-ui.css", "web/css/91-light.css", "web/css/40-tokens.css"):
            css = _read(f)
            for sel in (".kni", "#kn", ".knpop", ".knlv", "--ut0"):
                self.assertNotIn(sel, css.replace(".knad", ""), (f, sel))
        self.assertIn(".knad{", _read("web/css/90-main-ui.css"))  # still used by 35b-worklog-view.js


if __name__ == "__main__":
    unittest.main()
