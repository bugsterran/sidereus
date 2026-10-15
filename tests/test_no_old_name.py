"""The old code name is gone: no tracked path and no tracked text file contains it (any case).

Reads repo files listed by `git ls-files` only.
"""
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ⚠ Built from two halves so this file does not match itself.
OLD = re.compile("ag" + "ora", re.IGNORECASE)


def tracked():
    out = subprocess.run(["git", "-C", ROOT, "ls-files", "-z"], stdout=subprocess.PIPE, check=True).stdout
    return [p for p in out.decode("utf-8", "surrogateescape").split("\0") if p]


class NoOldName(unittest.TestCase):
    def test_paths(self):
        bad = [p for p in tracked() if OLD.search(p)]
        self.assertEqual(bad, [], "tracked paths with the old name")

    def test_contents(self):
        bad = []
        for p in tracked():
            fp = os.path.join(ROOT, p)
            if not os.path.isfile(fp) or os.path.islink(fp):
                continue
            with open(fp, "rb") as fh:
                data = fh.read()
            if b"\0" in data:
                continue  # binary
            text = data.decode("utf-8", "replace")
            for n, line in enumerate(text.splitlines(), 1):
                if OLD.search(line):
                    bad.append("%s:%d" % (p, n))
                    break
        self.assertEqual(bad, [], "tracked text files with the old name (first line each)")


if __name__ == "__main__":
    unittest.main()
