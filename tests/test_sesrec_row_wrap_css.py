"""Recently ended sessions: a row wraps instead of overflowing a narrow pinned column."""
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


class RecentRowWrap(unittest.TestCase):
    def test_row_wraps(self):
        row = decl(css("92-sessions-drawer.css"), ".srec .srecr")
        self.assertEqual(row["display"], "flex")
        self.assertEqual(row["flex-wrap"], "wrap")

    def test_no_later_rule_turns_wrap_off(self):
        for name in sorted(os.listdir(os.path.join(ROOT, "web", "css"))):
            if name.endswith(".css"):
                for m in re.finditer(r"\.srecr\{([^}]*)\}", css(name)):
                    self.assertNotIn("nowrap", m.group(1), name)


if __name__ == "__main__":
    unittest.main()
