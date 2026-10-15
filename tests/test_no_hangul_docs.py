"""Markdown without `.ko` in its name carries no Hangul at all; Korean docs live only in *.ko.md.

Tracked files only (`git ls-files`): local scratch (arch/, backup/) is not shipped. UI labels are quoted by
their English source text, Korean pipeline stage titles by their English meaning.
"""
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANGUL = re.compile("[가-힣ᄀ-ᇿ㄰-㆏]")


def tracked_md():
    try:
        out = subprocess.run(["git", "-C", ROOT, "ls-files", "*.md"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode:
        return None
    return [p for p in out.stdout.splitlines() if ".ko." not in os.path.basename(p)]


class NoHangulDocs(unittest.TestCase):
    def test_english_markdown_has_no_hangul(self):
        files = tracked_md()
        if files is None:
            self.skipTest("not a git checkout")
        bad = []
        for rel in files:
            path = os.path.join(ROOT, rel)
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8", errors="replace") as f:
                for n, line in enumerate(f, 1):
                    if HANGUL.search(line):
                        bad.append("%s:%d" % (rel, n))
        self.assertEqual(bad[:20], [], "%d line(s) with Hangul outside *.ko.md" % len(bad))


if __name__ == "__main__":
    unittest.main()
