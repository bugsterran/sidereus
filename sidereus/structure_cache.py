"""Structure disk cache (split out of sidereus/structure_scan.py for the size cap): gzip JSON files under STRUCT_DISK_DIR,
build encode/decode, per-file parse cache load/save, prune. Owns `_struct_fc_loaded`/`_struct_fc_sig`;
`_struct_file_cache`/`_struct_lock` stay owned by structure_scan (mutated in place here)."""
import gzip
import hashlib
import json
import os
import time
import zlib
from sidereus.config import DATA_DIR
from sidereus.warn import warn_once
from sidereus.bus import _atomic_write
from sidereus.structure_scan import STRUCT_FCACHE_N, STRUCT_RULES_VER, _struct_file_cache, _struct_lock, _struct_tmode


# ── disk cache ───────────────────────────────────────────────────────────────
# ★2026-09-22: analysis is computed and cached on request, but
#   the cache lived **only in memory**, so every restart was cold. Sidereus restarts often.
#   Measured cold (right after restart): Sidereus 2.6s · repo-B 4.6s · repo-A 4.1s · warm 0.00~0.05s.
# ★Past snapshots (git sha · tar · old-baks) are **immutable** — parsed once they are valid forever,
#   and they are most of the cold cost. So storage priority is (1) snapshot parse results (2) per-file parses of the current tree
#   (3) the final response.
# ⚠`STRUCT_RULES_VER` **must** be in the key — otherwise old results come back even after changing the classification rules.
# ⚠Read failures (broken file·version mismatch·hash collision) are **silently ignored and recomputed**.
#   The API must not die because of the cache.
# ⚠Writes are temp file + `os.replace` (the existing `_save_json` convention) — even if two requests write concurrently
#   no half-written file remains.
STRUCT_DISK_DIR = os.path.join(DATA_DIR, "struct-cache")   # ⚠`HOME` here is the data dir (`DATA_DIR`, default `~/.mailbox-mcp`, `:46`), not the user's home
STRUCT_DISK_VER = 1                      # file layout version. Bumping it discards old files automatically
STRUCT_DISK_MAX_MB = 200                 # total cap
STRUCT_DISK_MAX_DAYS = 30                # age cap — delete oldest first by whichever of the two hits first


def _struct_disk_file(kind, key):
    """⚠Mix the versions (`STRUCT_DISK_VER`·`STRUCT_RULES_VER`) **into the file name**. With only the `rv` check in the body,
    two copies of different versions alternately overwrite the same file and neither side's cache hits
    (measured 2026-09-22: changing the rules version and running once invalidated repo-B's blob cache entirely)."""
    h = hashlib.sha1(("%d|%d|%s" % (STRUCT_DISK_VER, STRUCT_RULES_VER, key))
                     .encode("utf-8", "replace")).hexdigest()
    return os.path.join(STRUCT_DISK_DIR, "%s-%s.json.gz" % (kind, h))


def _struct_disk_read(kind, key):
    """None if missing·broken·version differs. The caller just recomputes."""
    p = _struct_disk_file(kind, key)
    try:
        with gzip.open(p, "rb") as f:
            obj = json.loads(f.read().decode("utf-8"))
        if (not isinstance(obj, dict) or obj.get("v") != STRUCT_DISK_VER
                or obj.get("rv") != STRUCT_RULES_VER or obj.get("k") != key):
            return None                  # version mismatch or hash collision — discard
        try:
            os.utime(p, None)            # access mark for cleanup (oldest first)
        except OSError:
            pass                         # read-only or just evicted: only the cleanup order suffers
        return obj.get("d")
    except (OSError, EOFError, ValueError, zlib.error):
        return None                      # missing or broken cache file: the caller recomputes


def _struct_disk_write(kind, key, data):
    try:
        body = json.dumps({"v": STRUCT_DISK_VER, "rv": STRUCT_RULES_VER,
                           "k": key, "d": data}, ensure_ascii=False).encode("utf-8")
        _atomic_write(_struct_disk_file(kind, key), gzip.compress(body, 6), mkdir=True)
        return True
    except Exception as e:
        warn_once("struct-disk-write", "structure cache write failed ({err}) — recomputed every time",
                  soft=True, vars={"err": f"{type(e).__name__}: {e}"})
        return False


def _struct_enc_build(got):
    """`_struct_build` result -> JSON-able form. The function dict's `file` can be restored, so it is dropped."""
    total, fns, trunc, nf, nsk, ex, tfiles = got
    return [total, [[f["file"], f["name"], f["lang"], f["line"], f["lines"], f["h"]]
                    for f in fns],
            bool(trunc), nf, nsk, ex, sorted(tfiles)]


def _struct_dec_build(d):
    if not isinstance(d, list) or len(d) != 7:
        return None
    try:
        return (d[0], [{"file": r[0], "name": r[1], "lang": r[2], "line": r[3],
                        "lines": r[4], "h": r[5]} for r in d[1]],
                bool(d[2]), d[3], d[4], dict(d[5]), set(d[6]))
    except (IndexError, KeyError, TypeError, ValueError):
        return None                      # malformed cached payload: the caller recomputes


# **Per-file** parse cache of the current tree — so that in a new process «when only one file changed» the rest
# is not re-parsed (past snapshots are handled wholesale by the blob cache above).
# ⚠Holds only one project's «current tree» share (≤ STRUCT_MAX_FILES) — collecting globally makes the file large enough
#   that loading costs more than it saves.
_struct_fc_loaded = set()                # (root, tests) — loaded only once per process
_struct_fc_sig = {}                      # (root, tests) -> fingerprint of the key set last saved


def _struct_fc_key(root, tests):
    return "fc|%s|%d" % (root, _struct_tmode(tests))


def _struct_fcache_load(root, tests):
    ck = (root, _struct_tmode(tests))
    if ck in _struct_fc_loaded:
        return
    _struct_fc_loaded.add(ck)
    d = _struct_disk_read("fcache", _struct_fc_key(root, tests))
    if not isinstance(d, dict):
        return
    add = {}
    try:
        for k, v in d.items():
            rel, sep, h = k.partition("\t")
            if not sep:
                continue
            add[("f", rel, h)] = (v[0], [{"file": rel, "name": r[0], "lang": r[1],
                                          "line": r[2], "lines": r[3], "h": r[4]}
                                         for r in v[1]], v[2])
    except Exception:
        return                           # broken file — silently discard and recompute
    with _struct_lock:
        if len(_struct_file_cache) + len(add) > STRUCT_FCACHE_N:
            _struct_file_cache.clear()
        _struct_file_cache.update(add)


def _struct_fcache_save(root, tests, fkeys):
    """Keep only the keys `_struct_now` used this time. Do not write if nothing changed."""
    ck = (root, _struct_tmode(tests))
    sig =hashlib.md5("\n".join(sorted(k[1] + "\t" + k[2] for k in fkeys))
                      .encode("utf-8", "replace")).hexdigest()
    if _struct_fc_sig.get(ck) == sig:
        return
    with _struct_lock:
        hits = [(k, _struct_file_cache.get(k)) for k in fkeys]
    out = {}
    for k, hit in hits:
        if not hit:
            continue
        out[k[1] + "\t" + k[2]] = [hit[0], [[f["name"], f["lang"], f["line"],
                                             f["lines"], f["h"]] for f in hit[1]], hit[2]]
    if out and _struct_disk_write("fcache", _struct_fc_key(root, tests), out):
        _struct_fc_sig[ck] = sig


def _struct_disk_prune():
    """**Oldest first** by whichever hits first of total STRUCT_DISK_MAX_MB or STRUCT_DISK_MAX_DAYS.
    ⚠Do not call from the request path — warm-up thread only."""
    now = time.time()
    rows = []
    try:
        for fn in os.listdir(STRUCT_DISK_DIR):
            p = os.path.join(STRUCT_DISK_DIR, fn)
            try:
                st = os.stat(p)
            except OSError:
                continue
            if fn.startswith(".tmp-"):   # half-written — clean up if over an hour old
                if now - st.st_mtime > 3600:
                    try:
                        os.unlink(p)
                    except OSError:
                        pass     # another thread cleaned it first
                continue
            if not fn.endswith(".json.gz"):
                continue
            if now - st.st_mtime > STRUCT_DISK_MAX_DAYS * 86400:
                try:
                    os.unlink(p)
                except OSError:
                    pass         # another thread cleaned it first
                continue
            rows.append((st.st_mtime, st.st_size, p))
    except OSError:
        return
    rows.sort()
    tot = sum(s for _m, s, _p in rows)
    lim = STRUCT_DISK_MAX_MB * 1024 * 1024
    for _mt, sz, p in rows:
        if tot <= lim:
            break
        try:
            os.unlink(p)
            tot -= sz
        except OSError:
            pass                 # already gone; the cap is re-checked on the next cleanup
