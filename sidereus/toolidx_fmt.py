"""Pure helpers for the toolidx disk cache (no toolidx globals): packed-array codec, cache path spelling, hook digest, id sort."""
import base64
import contextlib
import hashlib
import heapq
import os
import sys
import tempfile
import time
from array import array
from sidereus import bus


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


def _write_rows(path, rows, prefix):
    """Stream `rows` (str, one per line) to a 0600 tmp in `path`'s folder and swap it in like `bus._atomic_write`.
    ⚠Never join/encode the whole snapshot (★2026-10-25 #26: join 50.3 MB + encode ~50 MB on a ~50 MB cache,
    save peak 265 MB traced vs ~110 MB before it; boot RSS peak 317-442 MB at t~3.6 s). On failure tmp is removed, error re-raised."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", prefix=prefix)
    try:
        with os.fdopen(fd, "wb") as f:
            for ln in rows:
                f.write(ln.encode("utf-8"))
                f.write(b"\n")
        for i in range(bus._ATOMIC_TRIES):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:     # ⚠Windows: target open elsewhere
                if i == bus._ATOMIC_TRIES - 1:
                    raise
                time.sleep(bus._ATOMIC_WAIT)
    except BaseException:
        with contextlib.suppress(OSError):     # tmp already gone; the original error is re-raised
            os.unlink(tmp)
        raise


def hook_hash(cmd):
    """12-hex digest of a hook command — matches config to `hook_success.command` without keeping the text."""
    return hashlib.sha1(cmd.encode("utf-8", "replace"), usedforsecurity=False).hexdigest()[:12]  # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1
