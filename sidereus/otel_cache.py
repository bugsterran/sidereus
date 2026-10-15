"""Per-day / per-session prompt-cache split from OTel api_request (read vs creation tokens) for the retro «Cache rewrites» card."""
import json
import os
import threading
import time
from sidereus.config import DATA_DIR
from sidereus.bus import _atomic_write
from sidereus.timefmt import ymd as _ymd


# Shape {ymd: {"t": [read, create], "s": {sid: [read, create]}}} — token counts and session ids only (metadata).
# ⚠Fed from otel._otel_ingest while `_otel_lock` is held: this module has its own lock and never takes `_otel_lock`.
OC_FILE = os.path.join(DATA_DIR, "otel-cache.json")
OC_KEEP_D = 31
OC_SESS_CAP = 200           # sessions per day; beyond it merge into the existing «Other» data key
OC_SAVE_S = 60
OC_TOP = 5
OC_MIN_TOK = 100000         # a session below this many cache tokens is too small for its share to mean anything
_oc = {}
_oc_meta = {"loaded": False, "savedAt": 0.0, "dirty": False}
_oc_lock = threading.Lock()


def _oc_int(v):
    try:
        return max(0, int(v or 0))
    except (TypeError, ValueError):
        return 0


def _oc_add(ts, sid, read, create):
    """Add one api_request's cache tokens to its day total and its session."""
    r, c = _oc_int(read), _oc_int(create)
    if not (r or c):
        return
    with _oc_lock:
        d = _oc.setdefault(_ymd(ts), {"t": [0, 0], "s": {}})
        d["t"][0] += r
        d["t"][1] += c
        s = d["s"]
        k = str(sid or "") or "기타"
        k = k if (k in s or len(s) < OC_SESS_CAP) else "기타"
        v = s.setdefault(k, [0, 0])
        v[0] += r
        v[1] += c
        _oc_meta["dirty"] = True


def _oc_pair(v):
    return [_oc_int(v[0]), _oc_int(v[1])] if isinstance(v, list) and len(v) == 2 else None


def _oc_load():
    """Merge the saved file into memory (adds, so events ingested before the load are kept)."""
    try:
        with open(OC_FILE, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = None
    src = (d.get("d") if isinstance(d, dict) else None) or {}
    with _oc_lock:
        if _oc_meta["loaded"]:      # ⚠a second merge would double-count
            return
        _oc_meta["loaded"] = True
        for day, row in (src.items() if isinstance(src, dict) else ()):
            if not (isinstance(day, str) and isinstance(row, dict)):
                continue
            dst = _oc.setdefault(day, {"t": [0, 0], "s": {}})
            t = _oc_pair(row.get("t"))
            if t:
                dst["t"][0] += t[0]
                dst["t"][1] += t[1]
            ss = row.get("s")
            for k, v in (ss.items() if isinstance(ss, dict) else ()):
                p = _oc_pair(v)
                if p is None:
                    continue
                kk = k if (k in dst["s"] or len(dst["s"]) < OC_SESS_CAP) else "기타"
                c = dst["s"].setdefault(kk, [0, 0])
                c[0] += p[0]
                c[1] += p[1]


def _oc_save(now=None, force=False):
    """Prune days older than 31 and write atomically — at most every 60s, only when changed. Returns True if written."""
    now = now or time.time()
    if not _oc_meta["loaded"]:
        _oc_load()
    if not force and now - _oc_meta["savedAt"] < OC_SAVE_S:
        return False
    cut = _ymd(now - OC_KEEP_D * 86400)
    with _oc_lock:
        old = [k for k in _oc if k < cut]
        for k in old:
            _oc.pop(k, None)
        if not (old or _oc_meta["dirty"] or force):
            return False
        blob = json.dumps({"v": 1, "d": _oc}, separators=(",", ":"), ensure_ascii=False)
        _oc_meta["dirty"] = False
    _oc_meta["savedAt"] = now
    try:
        _atomic_write(OC_FILE, blob.encode("utf-8"), prefix=".otel-cache.")
    except OSError:
        _oc_meta["dirty"] = True
        return False
    return True


def _oc_pct(r, c):
    return int(round(100.0 * c / (r + c))) if (r + c) else 0


def _oc_view(since_ymd, src=None):
    """Days >= since_ymd with creation share, plus the top sessions by creation share (>= OC_MIN_TOK cache tokens).
    src = one account's days in the same shape (otel_acct); None = all."""
    if not _oc_meta["loaded"]:
        _oc_load()
    oc = _oc if src is None else src
    acc = {}
    days = []
    with _oc_lock:
        for day in sorted(oc):
            if day < since_ymd:
                continue
            r, c = oc[day]["t"]
            days.append({"d": day, "read": r, "create": c, "pct": _oc_pct(r, c)})
            for k, v in oc[day]["s"].items():
                a = acc.setdefault(k, [0, 0])
                a[0] += v[0]
                a[1] += v[1]
    ss = [{"sid": k, "read": v[0], "create": v[1], "pct": _oc_pct(v[0], v[1])}
          for k, v in acc.items() if k != "기타" and v[0] + v[1] >= OC_MIN_TOK]
    ss.sort(key=lambda x: (-x["pct"], -x["create"], x["sid"]))
    return {"days": days, "sessions": ss[:OC_TOP]}
