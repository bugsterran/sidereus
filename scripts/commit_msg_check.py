#!/usr/bin/env python3
"""commit-msg hook body: refuse GitHub closing keywords («Closes #N») outside a release commit.

A closing keyword in a dev commit closes the issue as soon as the commit lands on the default
branch, and a Sidereus to-do number written as «#64» points at an unrelated GitHub issue.
Only the release commit (it stages CHANGELOG.md) may carry «Closes #N».
"""
import re
import subprocess
import sys

# GitHub closing keywords, optional colon, optional owner/repo before #N (case-insensitive).
CLOSE_RE = re.compile(r"\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\b:?\s+([\w.-]+/[\w.-]+)?#\d+", re.I)
HINT = 'use Refs #N; a Sidereus to-do number is not an issue — write "to-do 64" without #'


SCISSORS = "# ------------------------ >8 ------------------------"


def _body(msg):
    # `commit -v` appends the diff below the scissors line; git cuts it, then drops '#' lines
    lines = msg.splitlines()
    if SCISSORS in lines:
        lines = lines[:lines.index(SCISSORS)]
    return "\n".join(ln for ln in lines if not ln.startswith("#"))


def check(msg, staged, head=()):
    """Return None when allowed, else an error string. `staged` = staged paths; `head` = HEAD's paths (message-only amend)."""
    m = CLOSE_RE.search(_body(msg))
    if not m:
        return None
    if "CHANGELOG.md" in staged:
        return None
    # message-only `commit --amend` of the release commit stages nothing
    if not staged and "CHANGELOG.md" in head:
        return None
    return "commit-msg: closing keyword %r outside a release commit (no CHANGELOG.md staged) — %s" % (m.group(0), HINT)


def _names(argv):
    r = subprocess.run(["git"] + argv, capture_output=True, text=True)
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]


def _staged():
    return _names(["diff", "--cached", "--name-only"])


def _head_files():
    return _names(["diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"])


def main(argv):
    if len(argv) < 2:
        return 0
    with open(argv[1], encoding="utf-8", errors="replace") as fh:
        msg = fh.read()
    staged = _staged()
    err = check(msg, staged, () if staged else _head_files())
    if err:
        sys.stderr.write(err + "\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
