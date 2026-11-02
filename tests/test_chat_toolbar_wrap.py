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
        self.assertEqual(d.get("flex"), "1 1 160px")
        self.assertEqual(d.get("max-width"), "max-content")


if __name__ == "__main__":
    unittest.main()
