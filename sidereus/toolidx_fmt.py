"""Pure helpers for the toolidx disk cache (no toolidx globals): packed-array codec and cache path spelling."""
import base64
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
