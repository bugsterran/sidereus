"""Shared filesystem helpers for tests."""
import os
import shutil
import stat
import sys


def _retry_writable(func, path, _exc):
    # ⚠Windows: git marks .git/objects files read-only, so a plain rmtree fails with WinError 5.
    os.chmod(path, stat.S_IWRITE)
    func(path)


def rmtree_force(path):
    """shutil.rmtree that clears the read-only bit and retries (temp git repos on Windows)."""
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_retry_writable)
    else:
        shutil.rmtree(path, onerror=_retry_writable)


# ⚠Windows has no POSIX permission bits (stat reports 0o666/0o777) and readlink adds a \\?\ prefix.
POSIX = os.name == "posix"


def assert_mode(tc, path, mode):
    """Assert path's permission bits on POSIX; no-op on Windows."""
    if POSIX:
        tc.assertEqual(oct(stat.S_IMODE(os.stat(path).st_mode)), oct(mode), path)
