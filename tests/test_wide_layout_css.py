"""web/css wide-screen caps: history rows / branch commit details are capped only at >= 1441px; prose keeps 90ch."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def css(name):
    with open(os.path.join(ROOT, "web", "css", name), encoding="utf-8") as fh:
        return re.sub(r"/\*.*?\*/", "", fh.read(), flags=re.S)


def wide_blocks(src):
    """Bodies of every `@media (min-width:1441px){...}` block (one nesting level)."""
    out = []
    for m in re.finditer(r"@media\s*\(min-width:\s*1441px\)\s*\{", src):
        i, depth = m.end(), 1
        while depth:
            depth += {"{": 1, "}": -1}.get(src[i], 0)
            i += 1
        out.append(src[m.end():i - 1])
    return out


class WideCaps(unittest.TestCase):
    def test_history_rows_capped_only_when_wide(self):
        src = css("60-sessions.css")
        wide = "".join(wide_blocks(src))
        self.assertRegex(wide, r"\.hsd,\.hsr\{max-width:1200px\}")
        self.assertRegex(wide, r"\.hub\{max-width:1182px\}")
        rest = src
        for b in wide_blocks(src):
            rest = rest.replace(b, "")
        self.assertNotIn("max-width:1200px", rest)   # below 1441 the rows stay full width

    def test_branch_details_capped_only_when_wide(self):
        src = css("80-branch.css")
        wide = "".join(wide_blocks(src))
        self.assertIn(".brpan.brdt{max-width:min(56%,700px)}", wide)
        self.assertRegex(src, r"\.brpan\.brdt\{flex:1 1 420px;max-width:56%;")   # base rule unchanged
        # the dragged width (88g) must still beat the cap
        self.assertIn("html.brpsz .brpan.brdt{flex:0 0 var(--brpw)", src)

    def test_prose_line_length(self):
        src = css("65-code-compose-alarm.css")
        m = re.search(r"div\.bd > :is\(([^)]*)\)\{max-width:90ch\}", src)
        self.assertTrue(m)
        tags = m.group(1).split(",")
        self.assertIn("p", tags)
        for t in ("table", "pre"):
            self.assertNotIn(t, tags)   # tables and code blocks keep the full bubble width


if __name__ == "__main__":
    unittest.main()
