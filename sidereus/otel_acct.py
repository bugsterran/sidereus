"""Per-account copies of the retro OTel aggregates (tool days, api buckets, cache split, hook cost) for the account picker."""
import json
import os
import threading
import time
from sidereus.config import DATA_DIR
from sidereus.bus import _atomic_write
from sidereus.memo import BoundedMemo
from sidereus.timefmt import ymd as _ymd
from sidereus import claude_roots


# Shape {"v":1, "since":epoch, "a": {key: {"since": epoch, "t": tday rows, "s": bysrc buckets, "c": cache days, "h": hook days}}}.
# Per-account "since" = that account's first add; the top-level "since" (first add of any account) is the fallback
#   for boxes written before per-account since existed.
# Each part has the owner store's shape (otel `_otel_tday`/`_otel_src`, otel_cache `_oc`, otel_hooks `_oh`).
# key = account label; the primary account is "" (a rename leaves the old label's history orphaned).
# ⚠No email, account uuid or config path is stored — only the label. A sid with no SessionStart record is
#   «unknown»: nothing is stored and it counts only under All (`otel._otel_stat["acctUnk"]`).
# ⚠Lock order: `otel._otel_lock` -> `_oa_lock` (adds run under `_otel_lock`); this module never takes `_otel_lock`.
OA_FILE = os.path.join(DATA_DIR, "otel-acct.json")
OA_ACCT_CAP = 8
OA_SAVE_S = 60
OA_KEEP_D = 31              # t / c / h days, as the owner stores
OA_SRC_KEEP = 8 * 86400     # s buckets, as otel.OTEL_SRC_KEEP
OA_SRC_STEP = 300
OA_TDAY_CAP, OA_SRC_CAP, OA_SESS_CAP, OA_HOOK_CAP = 160, 64, 200, 40
OA_OTHER_T, OA_OTHER_S, OA_OTHER_C, OA_OTHER_H = "기타", "other", "기타", "Other"   # ⚠same overflow keys as the owners (views filter on them)
_oa = {}
_oa_meta = {"loaded": False, "savedAt": 0.0, "dirty": False, "since": 0}
_oa_lock = threading.Lock()
_oa_sid = BoundedMemo(2000)   # sid -> account key
_oa_miss = BoundedMemo(2000)  # sid -> time of an unknown result; retried after OA_MISS_S so a new session's late record resolves
OA_MISS_S = 60


def _oa_label(sid):
    """Account key for `sid`: "" primary · label for an extra account · None when unknown (no record or no match)."""
    if not sid:
        return None
    hit = _oa_sid.get(sid)
    if hit is not None:
        return hit
    now = time.time()
    if now - _oa_miss.get(sid, -OA_MISS_S - 1.0) <= OA_MISS_S:
        return None
    rd = claude_roots._acct_rec(sid)   # ⚠not acct_of(sid, None): that falls back to the primary silently
    for a in (claude_roots.accounts() if rd else ()):
        if os.path.realpath(a["dir"]) == rd:
            if a.get("primary"):
                return _oa_sid.put(sid, "")
            if a.get("label"):      # ⚠an extra account without a label must not share the primary's key ""
                return _oa_sid.put(sid, a["label"])
            break
    _oa_miss.put(sid, now)
    return None


def _oa_box(key, ts):
    """Account box (creates it under the cap) or None. ⚠Caller holds `_oa_lock`."""
    b = _oa.get(key)
    if b is None:
        if key is None or len(_oa) >= OA_ACCT_CAP:
            return None
        b = _oa[key] = {"t": {}, "s": {}, "c": {}, "h": {}}
    if not b.get("since"):
        b["since"] = int(ts)
    if not _oa_meta["since"]:
        _oa_meta["since"] = int(ts)
    _oa_meta["dirty"] = True
    return b


def _oa_slot(d, k, cap, other, zero):
    return d.setdefault(k if (k in d or len(d) < cap) else other, list(zero))


def _oa_tool(key, ts, nm, bad, dur_ms):
    """Mirror of otel._otel_tday_add for one account (nm already normalised by otel)."""
    with _oa_lock:
        b = _oa_box(key, ts)
        if b is None:
            return
        c = _oa_slot(b["t"].setdefault(_ymd(ts), {}), nm, OA_TDAY_CAP, OA_OTHER_T, (0, 0, 0.0, 0, 0.0))
        c[0] += 1
        c[1] += bad
        try:
            ms = float(dur_ms) if dur_ms is not None else -1.0
        except (TypeError, ValueError):
            ms = -1.0
        if ms >= 0:
            c[2] += ms
            c[3] += 1
            if bad:
                c[4] += ms


def _oa_src(key, ts, bk, tokens):
    """Mirror of otel._otel_src_add (5-min bucket, model|query_source key)."""
    with _oa_lock:
        b = _oa_box(key, ts)
        if b is None:
            return
        c = _oa_slot(b["s"].setdefault(int(ts // OA_SRC_STEP * OA_SRC_STEP), {}), bk, OA_SRC_CAP, OA_OTHER_S, (0, 0))
        c[0] += 1
        c[1] += int(tokens or 0)


def _oa_int(v):
    try:
        return max(0, int(v or 0))
    except (TypeError, ValueError):
        return 0


def _oa_cache(key, ts, sid, read, create):
    """Mirror of otel_cache._oc_add."""
    r, cr = _oa_int(read), _oa_int(create)
    if not (r or cr):
        return
    with _oa_lock:
        b = _oa_box(key, ts)
        if b is None:
            return
        d = b["c"].setdefault(_ymd(ts), {"t": [0, 0], "s": {}})
        d["t"][0] += r
        d["t"][1] += cr
        v = _oa_slot(d["s"], str(sid or "") or OA_OTHER_C, OA_SESS_CAP, OA_OTHER_C, (0, 0))
        v[0] += r
        v[1] += cr


def _oa_hook(key, ts, ev, dur, fail):
    """Mirror of otel_hooks._oh_add — hook event type only, never the session id."""
    with _oa_lock:
        b = _oa_box(key, ts)
        if b is None:
            return
        v = _oa_slot(b["h"].setdefault(_ymd(ts), {}), (str(ev or "") or "?")[:40], OA_HOOK_CAP, OA_OTHER_H, (0, 0, 0))
        v[0] += 1
        v[1] += _oa_int(dur)
        v[2] += _oa_int(fail)


def _oa_merge(dst, src, n):
    """Add list rows of `src` into `dst` (both {k: [n numbers]}); bad rows are skipped."""
    for k, v in (src.items() if isinstance(src, dict) else ()):
        if not (isinstance(k, str) and isinstance(v, list) and len(v) == n):
            continue
        c = dst.setdefault(k, [0] * n)
        try:
            for i in range(n):
                c[i] += v[i] if isinstance(v[i], (int, float)) and not isinstance(v[i], bool) else 0
        except TypeError:
            continue


def _oa_load():
    """Merge the saved file into memory (adds, so events ingested before the load are kept)."""
    try:
        with open(OA_FILE, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = None
    d = d if isinstance(d, dict) else {}
    acc = d.get("a") if isinstance(d.get("a"), dict) else {}
    with _oa_lock:
        if _oa_meta["loaded"]:      # ⚠a second merge would double-count
            return
        _oa_meta["loaded"] = True
        s = d.get("since")
        if isinstance(s, int) and s > 0 and not isinstance(s, bool):
            _oa_meta["since"] = min(s, _oa_meta["since"] or s)
        for key, box in acc.items():
            if not (isinstance(key, str) and isinstance(box, dict)) or (key not in _oa and len(_oa) >= OA_ACCT_CAP):
                continue
            b = _oa.setdefault(key, {"t": {}, "s": {}, "c": {}, "h": {}})
            bs = box.get("since")
            bs = bs if isinstance(bs, int) and bs > 0 and not isinstance(bs, bool) else (s if isinstance(s, int) and s > 0 else 0)
            if bs:
                b["since"] = min(bs, b.get("since") or bs)
            for part, n in (("t", 5), ("s", 2), ("h", 3)):
                rows = box.get(part)
                for k, row in (rows.items() if isinstance(rows, dict) else ()):
                    kk = k if part != "s" else (int(k) if str(k).isdigit() else None)
                    if kk is not None and isinstance(row, dict):
                        _oa_merge(b[part].setdefault(kk, {}), row, n)
            rows = box.get("c")
            for k, row in (rows.items() if isinstance(rows, dict) else ()):
                if isinstance(k, str) and isinstance(row, dict):
                    dc = b["c"].setdefault(k, {"t": [0, 0], "s": {}})
                    _oa_merge(dc, {"t": row.get("t")}, 2)
                    _oa_merge(dc["s"], row.get("s"), 2)


def _oa_save(now=None, force=False):
    """Prune old days/buckets and write atomically — at most every 60s, only when changed. Returns True if written."""
    now = now or time.time()
    if not _oa_meta["loaded"]:
        _oa_load()
    if not force and now - _oa_meta["savedAt"] < OA_SAVE_S:
        return False
    cut, bcut = _ymd(now - OA_KEEP_D * 86400), now - OA_SRC_KEEP
    with _oa_lock:
        old = 0
        for b in _oa.values():
            for part in ("t", "c", "h"):
                for k in [k for k in b[part] if k < cut]:
                    b[part].pop(k, None)
                    old += 1
            for k in [k for k in b["s"] if k < bcut]:
                b["s"].pop(k, None)
                old += 1
        if not (old or _oa_meta["dirty"] or force):
            return False
        blob = json.dumps({"v": 1, "since": int(_oa_meta["since"] or 0),
                           "a": {k: {"since": int(b.get("since") or 0), "t": b["t"],
                                     "s": {str(t): r for t, r in b["s"].items()}, "c": b["c"], "h": b["h"]}
                                 for k, b in _oa.items()}},
                          separators=(",", ":"), ensure_ascii=False)
        _oa_meta["dirty"] = False
    _oa_meta["savedAt"] = now
    try:
        _atomic_write(OA_FILE, blob.encode("utf-8"), prefix=".otel-acct.")
    except OSError:
        _oa_meta["dirty"] = True
        return False
    return True


def _oa_snap(key):
    """Deep copy of one account's parts {t, s, c, h} (empty parts when it has none) and its `since` (0 = never)."""
    if not _oa_meta["loaded"]:
        _oa_load()
    with _oa_lock:
        b = _oa.get(key) or {"t": {}, "s": {}, "c": {}, "h": {}}
        out = {p: {k: ({kk: (list(vv) if isinstance(vv, list) else {s: list(x) for s, x in vv.items()})
                        for kk, vv in row.items()}) for k, row in b[p].items()} for p in ("t", "s", "c", "h")}
        return out, int(b.get("since") or 0)
