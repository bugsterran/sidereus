"""Every character of the page sources stays at or below U+FFFF.

★One astral character (a literal emoji) turned the whole inline PAGE str into 4 bytes/char:
  9.7 MB -> 4.8 MB without it, 51 -> 46 MB RSS on the --demo server (Linux, 2026-10-28).
Write such characters as \\uXXXX escapes (JS strings and non-`u` regexes read them as the same two code units)."""
import glob
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class PageBmp(unittest.TestCase):
    def test_no_astral_chars_in_page_sources(self):
        files = [os.path.join(ROOT, "web", "index.html")]
        for pat in ("web/*.js", "web/js/*.js", "web/css/*.css"):
            files += glob.glob(os.path.join(ROOT, pat))
        bad = []
        for f in sorted(files):
            with open(f, encoding="utf-8") as fh:
                for n, line in enumerate(fh, 1):
                    bad += ["%s:%d U+%X" % (os.path.relpath(f, ROOT), n, ord(c)) for c in line if ord(c) > 0xFFFF]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
