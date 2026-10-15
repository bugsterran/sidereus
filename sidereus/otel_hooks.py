"""Per-day hook cost from OTel hook_execution_complete (count, time, failures per hook event type) for the retro «Hook cost» card."""
import json
import os
import threading
import time
from sidereus.config import DATA_DIR
from sidereus.bus import _atomic_write
from sidereus.timefmt import ymd as _ymd


# Shape {ymd: {hook_event: [runs, durMsSum, fails]}} — hook event type only (R1, metadata).
# ⚠Never store hook_name, hook_definitions, *_chars or session.id: those name user scripts or size their output.
# ⚠Fed from otel._otel_ingest while `_otel_lock` is held: this module has its own lock and never takes `_otel_lock`.
OH_FILE = os.path.join(DATA_DIR, "otel-hooks.json")
OH_KEEP_D = 31
OH_CAP = 40                 # event types per day; beyond it merge into «Other»
OH_EV_MAX = 40              # hook_event string length cap
OH_SAVE_S = 60
OH_OTHER = "Other"
_oh = {}
_oh_meta = {"loaded": False, "savedAt": 0.0, "dirty": False}
_oh_lock = threading.Lock()


def _oh_int(v):
    try:
        return max(0, int(v or 0))
    except (TypeError, ValueError):
        return 0


def _oh_key(day, ev):
    k = (str(ev or "") or "?")[:OH_EV_MAX]
    return k if (k in day or len(day) < OH_CAP) else OH_OTHER


def _oh_add(ts, ev, dur, fail):
    """Add one hook firing (total_duration_ms covers all matching hooks of that firing) to its day and event type."""
    with _oh_lock:
        day = _oh.setdefault(_ymd(ts), {})
        v = day.setdefault(_oh_key(day, ev), [0, 0, 0])
        v[0] += 1
        v[1] += _oh_int(dur)
        v[2] += _oh_int(fail)
        _oh_meta["dirty"] = True


def _oh_load():
    """Merge the saved file into memory (adds, so events ingested before the load are kept)."""
    try:
        with open(OH_FILE, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = None
    src = (d.get("d") if isinstance(d, dict) else None) or {}
    with _oh_lock:
        if _oh_meta["loaded"]:      # ⚠a second merge would double-count
            return
        _oh_meta["loaded"] = True
        for dk, row in (src.items() if isinstance(src, dict) else ()):
            if not (isinstance(dk, str) and isinstance(row, dict)):
                continue
            dst = _oh.setdefault(dk, {})
            for k, v in row.items():
                if not (isinstance(v, list) and len(v) == 3):
                    continue
                c = dst.setdefault(_oh_key(dst, k), [0, 0, 0])
                for i in range(3):
                    c[i] += _oh_int(v[i])


def _oh_save(now=None, force=False):
    """Prune days older than 31 and write atomically — at most every 60s, only when changed. Returns True if written."""
    now = now or time.time()
    if not _oh_meta["loaded"]:
        _oh_load()
    if not force and now - _oh_meta["savedAt"] < OH_SAVE_S:
        return False
    cut = _ymd(now - OH_KEEP_D * 86400)
    with _oh_lock:
        old = [k for k in _oh if k < cut]
        for k in old:
            _oh.pop(k, None)
        if not (old or _oh_meta["dirty"] or force):
            return False
        blob = json.dumps({"v": 1, "d": _oh}, separators=(",", ":"), ensure_ascii=False)
        _oh_meta["dirty"] = False
    _oh_meta["savedAt"] = now
    try:
        _atomic_write(OH_FILE, blob.encode("utf-8"), prefix=".otel-hooks.")
    except OSError:
        _oh_meta["dirty"] = True
        return False
    return True


def _oh_view(since_ymd, top=6, src=None):
    """R2: top hook event types by total time over days >= since_ymd; from = first day with data.
    src = one account's days in the same shape (otel_acct); None = all."""
    if not _oh_meta["loaded"]:
        _oh_load()
    oh = _oh if src is None else src
    acc = {}
    first = ""
    with _oh_lock:
        for dk in sorted(oh):
            if dk < since_ymd or not oh[dk]:
                continue
            first = first or dk
            for k, v in oh[dk].items():
                a = acc.setdefault(k, [0, 0, 0])
                for i in range(3):
                    a[i] += v[i]
    rows = [{"ev": k, "count": v[0], "ms": v[1], "avg": int(round(float(v[1]) / v[0])) if v[0] else 0, "fail": v[2]}
            for k, v in acc.items()]
    rows.sort(key=lambda x: (-x["ms"], -x["count"], x["ev"]))
    return {"rows": rows[:top], "n": sum(v[0] for v in acc.values()), "from": first}
