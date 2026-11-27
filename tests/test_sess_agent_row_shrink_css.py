"""Subagent row (.sti): the running tool name and the «quiet» chip shrink, so a 320px pinned column never scrolls sideways."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def css(name):
    with open(os.path.join(ROOT, "web", "css", name), encoding="utf-8") as fh:
        return re.sub(r"/\*.*?\*/", "", fh.read(), flags=re.S)


def decl(src, selector):
    m = re.search(r"(?m)^" + re.escape(selector) + r"\{([^}]*)\}", src)
    assert m, selector
    return dict(
        (k.strip(), v.strip())
        for k, v in (p.split(":", 1) for p in m.group(1).split(";") if ":" in p)
    )


class AgentRowShrink(unittest.TestCase):
    def assert_shrinks(self, d):
        self.assertNotEqual(d["flex"].split()[1], "0", d)   # flex-shrink > 0
        self.assertIn("min-width", d)
        self.assertEqual(d["overflow"], "hidden")
        self.assertEqual(d["text-overflow"], "ellipsis")
        self.assertEqual(d["white-space"], "nowrap")

    def test_tool_name_shrinks(self):
        # MCP tool names (~40-60 chars) were flex 0 0 auto and pushed a 300px row 132-315px wide
        self.assert_shrinks(decl(css("60-sessions.css"), ".sti .tn"))

    def test_quiet_chip_shrinks(self):
        self.assert_shrinks(decl(css("60-sessions.css"), ".stq"))

    def test_tool_name_has_title(self):
        with open(os.path.join(ROOT, "web", "js", "40b-sessions-list.js"), encoding="utf-8") as fh:
            js = fh.read()
        self.assertIn("'<span class=tn title=\"'+esc(tool)+'\">'", js)


if __name__ == "__main__":
    unittest.main()
