"""No private word, real home path or launchd uid in any tracked path or text file.

Words come from the untracked tests/.private-deny (parsed by scripts/leakscan.py only); skipped when it is missing (CI, forks).
Reads repo files listed by `git ls-files` only.
"""
import importlib.util
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DENY = os.path.join(ROOT, "tests", ".private-deny")
# ⚠ Patterns built from parts so this file does not match itself.
HOMEDIR = re.compile("/" + "Users/([a-z][^/\\s\"'`)]*)")
UID = re.compile("gui" + "/501(?![0-9])")
ALLOW = "leakscan" + ": allow"
PLACEHOLDERS = {"x", "a", "me", "you", "user", "username", "name", "demo", "example", "alice", "bob"}


def _leakscan():
    spec = importlib.util.spec_from_file_location("leakscan", os.path.join(ROOT, "scripts", "leakscan.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tracked():
    out = subprocess.run(["git", "-C", ROOT, "ls-files", "-z"], stdout=subprocess.PIPE, check=True).stdout
    return [p for p in out.decode("utf-8", "surrogateescape").split("\0") if p]


def texts():
    for p in tracked():
        fp = os.path.join(ROOT, p)
        if not os.path.isfile(fp) or os.path.islink(fp):
            continue
        with open(fp, "rb") as fh:
            data = fh.read()
        if b"\0" in data:
            continue  # binary
        yield p, data.decode("utf-8", "replace").splitlines()


def real_home(line):
    return any(m.group(1) not in PLACEHOLDERS for m in HOMEDIR.finditer(line))


class NoPrivateWords(unittest.TestCase):
    def test_words(self):
        if not os.path.exists(DENY):
            self.skipTest("tests/.private-deny missing")
        words = _leakscan().private_words(ROOT)
        bad = [p for p in tracked() if any(rx.search(p) for rx in words)]
        for p, lines in texts():
            for n, line in enumerate(lines, 1):
                if any(rx.search(line) for rx in words):
                    bad.append("%s:%d" % (p, n))
        self.assertEqual(bad, [], "tracked paths/lines with a private word")

    def test_home_and_uid(self):
        bad = []
        for p, lines in texts():
            for n, line in enumerate(lines, 1):
                # Same opt-out as scripts/leakscan.py (fake paths in its own tests).
                if ALLOW not in line and (real_home(line) or UID.search(line)):
                    bad.append("%s:%d" % (p, n))
        self.assertEqual(bad, [], "tracked lines with a real home path or launchd uid")


if __name__ == "__main__":
    unittest.main()
