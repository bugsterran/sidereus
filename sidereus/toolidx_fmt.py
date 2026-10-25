"""Pure helpers for the toolidx disk cache (no toolidx globals): packed-array codec, cache path spelling, hook digest, id sort."""
import base64
import hashlib
import heapq
import os
import sys
from array import array


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _arr(code, s):
    """base64 little-endian bytes -> array; ValueError on a bad string or a length that is not whole items."""
    if type(s) is not str:
        raise ValueError("arr")
    a = array(code)
    a.frombytes(base64.b64decode(s, validate=True))
    if sys.byteorder == "big":
        a.byteswap()
    return a


def _b64(a):
    if sys.byteorder == "big":
        a = array(a.typecode, a)
        a.byteswap()
    return base64.b64encode(a.tobytes()).decode("ascii")


def _canon(fp, pre, rpre):
    """Cache row path -> the current root spelling `pre` when it is the same file under another spelling
    (CLAUDE_CONFIG_DIR alias or symlink; `rpre` = realpath of the root); otherwise unchanged."""
    if fp.startswith(pre):
        return fp
    rp = os.path.realpath(fp)
    return pre + rp[len(rpre):] if rp.startswith(rpre) else fp


def _merge_sorted(arrays, chunk):
    """Id arrays -> (one sorted array("q"), set of ids seen twice+), via sorted runs of ~`chunk` ids + heapq.merge.
    ⚠Never `sorted()` every id at once (★#26, 1.5M ids: peak 77 -> 25 MB traced, 1.19 -> 1.30 s)."""
    runs, buf = [], array("q")
    for a in arrays:
        buf.extend(a)
        if len(buf) >= chunk:
            runs.append(array("q", sorted(buf)))
            buf = array("q")
    if buf:
        runs.append(array("q", sorted(buf)))
    del buf
    out, dup, prev = array("q"), set(), None
    for x in heapq.merge(*runs):
        if x == prev:
            dup.add(x)
        out.append(x)
        prev = x
    return out, dup


def hook_hash(cmd):
    """12-hex digest of a hook command — matches config to `hook_success.command` without keeping the text."""
    return hashlib.sha1(cmd.encode("utf-8", "replace"), usedforsecurity=False).hexdigest()[:12]  # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1
