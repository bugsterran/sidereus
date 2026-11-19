"""Pure helpers for the toolidx disk cache (no toolidx globals): packed-array codec, cache path spelling, hook digest, id sort, streamed save rows."""
import base64
import contextlib
import hashlib
import heapq
import json
import os
import re
import sys
import tempfile
import time
from array import array
from sidereus import bus

TI_NAME_MAX = 120            # keys are names, not text — cap anything odd
_ERR_RE = re.compile(r"[A-Z_]{1,24}")
_SRV_RE = re.compile(r"[^A-Za-z0-9_-]")   # config name -> tool-name prefix form (`claude.ai X` -> `claude_ai_X`)
_AUTH_TOOLS = frozenset(("authenticate", "complete_authentication"))   # all a connector exposes before sign-in


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


def _ent_row(fp, ent, names):
    """Inverse of toolidx `_ent_from`: one compact JSON line (keys written once per file, events as packed arrays)."""
    loc = {}
    lk = array("I", [loc.setdefault(g, len(loc)) for g in ent["ki"]])
    keys = [names[g] for g in sorted(loc, key=loc.get)]
    return json.dumps([fp, ent["sz"], ent["off"], keys, _b64(ent["ids"]), _b64(ent["ts"]), _b64(lk),
                       ent["fail"], ent.get("conn", {})], separators=(",", ":"))


def _ent_ref(ent):
    """Lock-time view of `ent`: arrays by reference + their length (scans only append in place; `_trim` swaps in new arrays)."""
    ids, ts, ki, conn = ent["ids"], ent["ts"], ent["ki"], ent.get("conn")
    return (ent["sz"], ent["off"], ids, ts, ki, len(ids), len(ts), len(ki),
            dict(ent["fail"]) if ent["fail"] else None, dict(conn) if conn else None)


class _Rows(object):
    """Cache lines (`head`, then one per `_ent_ref`) rendered one at a time while `_write_rows` streams them.
    ⚠Rendering every row under the lock held the whole file as strings until the write ended (boot RSS peak, #30)."""
    __slots__ = ("refs", "head", "names")

    def __init__(self, refs, head, names):
        self.refs, self.head, self.names = refs, head, names

    def __iter__(self):
        yield self.head
        for fp, (sz, off, ids, ts, ki, ni, nt, nk, fail, conn) in self.refs:
            # grown after the lock was released: cut back to the locked state
            yield _ent_row(fp, {"sz": sz, "off": off, "ids": ids if len(ids) == ni else ids[:ni],
                                "ts": ts if len(ts) == nt else ts[:nt], "ki": ki if len(ki) == nk else ki[:nk],
                                "fail": fail or {}, "conn": conn or {}}, self.names)

    def __len__(self):
        return len(self.refs) + 1

    def __getitem__(self, i):
        return list(self)[i]


def hook_hash(cmd):
    """12-hex digest of a hook command — matches config to `hook_success.command` without keeping the text."""
    return hashlib.sha1(cmd.encode("utf-8", "replace"), usedforsecurity=False).hexdigest()[:12]  # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1


def _fails_of(d):
    """[(mcp key, errorCode)] reported failed by one record. ⚠Only `name`/`errorCode` are read — `error` is free text."""
    a = d.get("attachment")
    if d.get("type") != "attachment" or not isinstance(a, dict) or not isinstance(a.get("failedMcpServers"), list):
        return []
    out = []
    for s in a["failedMcpServers"]:
        nm = s.get("name") if isinstance(s, dict) else None
        if isinstance(nm, str) and nm.strip():
            code = str(s.get("errorCode") or "")[:24]
            out.append(("mcp:" + _SRV_RE.sub("_", nm.strip())[:TI_NAME_MAX - 4], code if _ERR_RE.fullmatch(code) else ""))
    return out


def _conns_of(d):
    """Keys per server whose tools a `deferred_tools_delta` record adds: `mcp:<srv>` = connected at that time,
    `mcpauth:<srv>` = only its sign-in tools were added (a connector waiting for login — ⚠not a connect)."""
    a = d.get("attachment")
    if d.get("type") != "attachment" or not isinstance(a, dict) or a.get("type") != "deferred_tools_delta":
        return []
    by = {}
    for k in ("addedNames", "readdedNames"):
        for nm in a.get(k) if isinstance(a.get(k), list) else ():
            if isinstance(nm, str) and nm.startswith("mcp__") and nm[5:].split("__", 1)[0]:
                srv, _, tool = nm[5:].partition("__")
                by.setdefault(srv, set()).add(tool)
    out = set()
    for srv, tools in by.items():
        pre = "mcpauth:" if tools <= _AUTH_TOOLS else "mcp:"
        out.add(pre + srv[:TI_NAME_MAX - len(pre)])
    return sorted(out)


def sess_status(mc, conn, auth, fail):
    """Per-key state of one session from its newest call / connect / sign-in prompt / failure times (pure).
    fail = a failure newer than all three; auth = sign-in tools offered at/after the last connect with no later call."""
    st = {}
    for k in set(mc) | set(conn) | set(auth) | set(fail):
        c, o, a, f = mc.get(k, 0.0), conn.get(k, 0.0), auth.get(k, 0.0), fail.get(k, (0.0, ""))
        if f[0] > max(c, o, a) or not (c or o or a):
            s = "fail"
        elif a and a >= o and a >= c:
            s = "auth"
        else:
            s = "ok"
        st[k] = {"status": s, "err": f[1] if s == "fail" else "", "fail_at": int(f[0]), "ok_at": int(max(c, o))}
    return st
