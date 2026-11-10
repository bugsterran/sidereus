"""Sessions list: the tool-state bar shares the account band's geometry (left 0, full height, 3px)."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def css(name):
    with open(os.path.join(ROOT, "web", "css", name), encoding="utf-8") as fh:
        return re.sub(r"/\*.*?\*/", "", fh.read(), flags=re.S)


def decl(src, selector):
    m = re.search(re.escape(selector) + r"\{([^}]*)\}", src)
    assert m, selector
    return dict(
        (k.strip(), v.strip())
        for k, v in (p.split(":", 1) for p in m.group(1).split(";") if ":" in p)
    )


class ToolBarGeometry(unittest.TestCase):
    def test_tool_bar_matches_account_band(self):
        src = css("60-sessions.css")
        band = decl(src, ".acb:is(.sxw,.srecr,.atr)")
        self.assertEqual(band["box-shadow"], "inset 3px 0 0 var(--acc)")
        bar = decl(src, ".sxw.s-tool::before")
        self.assertEqual(bar["left"], "0")
        self.assertEqual(bar["top"], "0")
        self.assertEqual(bar["bottom"], "0")
        self.assertEqual(bar["width"], "3px")

    def test_no_override_moves_the_bar(self):
        for name in sorted(os.listdir(os.path.join(ROOT, "web", "css"))):
            if name.endswith(".css"):
                for m in re.finditer(r"s-tool::before\{([^}]*)\}", css(name)):
                    self.assertNotIn("left:-", m.group(1), name)


if __name__ == "__main__":
    unittest.main()
