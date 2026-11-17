"""Side-pane rows (`.brdf`): only commit rows keep their meta on one line; worktree file rows wrap their owner chips."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def css(name):
    with open(os.path.join(ROOT, "web", "css", name), encoding="utf-8") as fh:
        return re.sub(r"/\*.*?\*/", "", fh.read(), flags=re.S)


def rule(src, sel):
    m = re.search(re.escape(sel) + r"\{([^}]*)\}", src)
    return m.group(1) if m else None


class BranchRowMeta(unittest.TestCase):
    def test_nowrap_scoped_to_commit_rows(self):
        src = css("80-branch.css")
        base = rule(src, ".brdf em")
        self.assertIsNotNone(base)
        # a worktree file row's em carries up to 4 owner chips: nowrap + no shrink there squeezes the path to 0 px
        self.assertNotIn("nowrap", base)
        self.assertNotIn("flex:0 0 auto", base)
        commit = rule(src, ".brdf[data-bpp] em")
        self.assertIsNotNone(commit)
        self.assertIn("white-space:nowrap", commit)
        self.assertIn("flex:0 0 auto", commit)

    def test_worktree_owner_chips_wrap(self):
        # chips are adjacent spans with no break point: only a wrapping flex em lets the row shrink
        wk = rule(css("80-branch.css"), ".brdf[data-wkd] em")
        self.assertIsNotNone(wk)
        for decl in ("display:flex", "flex-wrap:wrap", "min-width:0", "max-width:"):
            self.assertIn(decl, wk)


if __name__ == "__main__":
    unittest.main()
