#!/usr/bin/env python3
"""Fix-stage gate: a sidereus/*.py change must come with a docs/dev/traps/*.md entry.

Reads `git status --porcelain` only (untracked files count). Last line is PASS or FAIL.
⚠A git error is FAIL «unknown», never PASS: an unreadable worktree proves nothing.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _is_code(p):
    return p.startswith("sidereus/") and p.endswith(".py")


def _is_trap(p):
    return p.startswith("docs/dev/traps/") and p.endswith(".md") and "/" not in p[len("docs/dev/traps/"):]


def verdict(paths, deleted=()):
    """(ok, message) for the changed repo-relative paths; `deleted` paths count as code changes, never as trap entries."""
    code = sorted(p for p in paths if _is_code(p))
    traps = sorted(p for p in paths if _is_trap(p) and p not in deleted)
    if not code:
        return True, "no sidereus/*.py change"
    if traps:
        return True, "%d sidereus/*.py + %s" % (len(code), ", ".join(traps))
    return False, ("%d sidereus/*.py changed (%s) and no docs/dev/traps/*.md entry"
                   % (len(code), ", ".join(code[:5]) + (" …" if len(code) > 5 else "")))


def parse_porcelain_z(out):
    """(paths, deleted) from `git status --porcelain -z` (rename/copy: the new path; the source entry is skipped)."""
    paths, deleted, parts, i = [], set(), out.split("\0"), 0
    while i < len(parts):
        e = parts[i]
        i += 1
        if len(e) < 4:
            continue
        paths.append(e[3:])
        if "D" in e[:2]:
            deleted.add(e[3:])
        if e[0] in "RC":
            i += 1   # -z puts the source path in the next field
    return paths, deleted


def _git(argv, cwd):
    return subprocess.run(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, encoding="utf-8", timeout=30)


def main(argv=None, cwd=ROOT):
    try:
        p = _git(["git", "status", "--porcelain", "-z", "--untracked-files=all"], cwd)
        if p.returncode != 0:
            err = (p.stderr or "").strip().splitlines()
            raise RuntimeError(err[-1] if err else "git status rc %d" % p.returncode)
    except Exception as e:  # noqa: BLE001 - any failure is unknown
        print("trap_check: FAIL unknown — git status failed (%s)" % e)
        return 1
    ok, msg = verdict(*parse_porcelain_z(p.stdout))
    if not ok:
        print("trap_check: FAIL %s — add a docnote-shaped entry to docs/dev/traps/<domain>.md" % msg)
        return 1
    print("trap_check: PASS %s" % msg)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
