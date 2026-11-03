"""Chat toolbar row (#tbchat) wraps instead of scrolling sideways at 1100 (six English filter chips + search/views)."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _decls(selector):
    with open(os.path.join(ROOT, "web/css/93-header-toolbar.css"), encoding="utf-8") as f:
        css = re.sub(r"/\*.*?\*/", "", f.read(), flags=re.S)
    out = {}
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        if sel.strip() == selector:
            for d in body.split(";"):
                if ":" in d:
                    k, v = d.split(":", 1)
                    out[k.strip()] = v.strip()
    return out


class ChatToolbarWrap(unittest.TestCase):
    def test_row_wraps(self):
        self.assertEqual(_decls("html[data-ui=next] #tbchat").get("flex-wrap"), "wrap")

    def test_room_part_small_basis_capped_at_content(self):
        # A content-sized basis lets a long member list push every part onto its own line (3 rows measured).
        d = _decls("html[data-ui=next] #tbchat > .rooms")
        # 320px: name (≤200) plus a readable member slice; 160px left members 5px wide at en 1440.
        self.assertEqual(d.get("flex"), "1 1 320px")
        self.assertEqual(d.get("max-width"), "max-content")

    def test_room_name_does_not_shrink_before_members(self):
        # 21-member room at 1100: the name got 31 of 72px while members kept theirs.
        d = _decls("html[data-ui=next] .tbs > .rooms > .rmname")
        self.assertEqual(d.get("flex-shrink"), "0")
        self.assertEqual(d.get("max-width"), "200px")


if __name__ == "__main__":
    unittest.main()
