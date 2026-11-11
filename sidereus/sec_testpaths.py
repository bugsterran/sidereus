"""Test-code paths for a security scan with test code excluded (`scripts/arch_checks.py --no-tests`).

Only the code scanners (CODE_IDS) read a copy of the exported tree without these paths; dependency and image scanners
(npm audit, osv-scanner, trivy) keep the full tree. ⚠Only the skipped-file count and the fixed PATTERNS list are
stored, never the names of skipped files. Stdlib only, Python 3.9.
"""
import fnmatch
import os
import shutil

DIRS = ("tests", "test", "__tests__", "spec", "fixtures", "mocks")
FILES = ("*_test.*", "*.test.*", "*.spec.*", "test_*.py")
CODE_IDS = ("gitleaks", "semgrep", "bandit")
PATTERNS = tuple(d + "/" for d in DIRS) + FILES   # stored as `tests_excluded.patterns` (checked by the gate)


def _file_hit(name):
    # ⚠fnmatchcase: fnmatch.fnmatch folds case on macOS/Windows, so `Test_x.PY` would differ per OS
    return any(fnmatch.fnmatchcase(name, p) for p in FILES)


def is_test(rel):
    """True when a repo-relative path is test code: a folder component in DIRS, or a basename matching FILES."""
    if not isinstance(rel, str) or not rel:
        return False
    parts = [p for p in rel.replace("\\", "/").split("/") if p]
    return bool(parts) and (any(p in DIRS for p in parts[:-1]) or _file_hit(parts[-1]))


def _count(fp):
    """Files under a skipped folder (symlinks count as one entry, never followed)."""
    n = 0
    for _dp, _dns, fns in os.walk(fp):   # followlinks=False: a linked folder inside is listed, not entered
        n += len(fns) + sum(1 for d in _dns if os.path.islink(os.path.join(_dp, d)))
    return n


def prune_copy(src, dst):
    """Copy src to dst without .git and test code; the number of test files skipped. Symlinks are copied as links."""
    n = [0]

    def ignore(dp, names):
        skip = set()
        for name in names:
            fp = os.path.join(dp, name)
            if name == ".git":
                skip.add(name)
            elif os.path.islink(fp):
                if name in DIRS or _file_hit(name):
                    skip.add(name)
                    n[0] += 1
            elif os.path.isdir(fp):
                if name in DIRS:
                    skip.add(name)
                    n[0] += _count(fp)
            elif _file_hit(name):
                skip.add(name)
                n[0] += 1
        return skip
    shutil.copytree(src, dst, symlinks=True, ignore=ignore, dirs_exist_ok=True)
    return n[0]
