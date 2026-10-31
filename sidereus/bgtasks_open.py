"""Open background-shell rows persisted across viewer restarts (split from bgtasks_parse for its size cap)."""
import json
import os
from sidereus.config import DATA_DIR
from sidereus.warn import warn_once
from sidereus.bus import _atomic_write
from sidereus.bgtasks_parse import _bg_dropped, _bg_out

# ⚠Open bg rows live only in memory, and a subagent's launch is read only while its log is within the 6 h window
#   (`bgtasks._sub_transcripts`), so a dev server started by a subagent vanished after a restart. Rows are saved here
#   (fp → {tid: [label, launch ts, output path]}) and restored on that fp's first scan; `bgtasks` filters what is restored.
BG_OPEN_FILE = os.path.join(DATA_DIR, "bg-open.json")
BG_OPEN_MAX = 200          # rows kept in the file (newest launches first)


def _bg_open_load(path):
    """Previous run's open bg rows, sessions whose transcript is gone dropped; {} when missing or malformed."""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    out = {}
    if not isinstance(d, dict):
        return out
    for fp, rows in d.items():
        if not isinstance(fp, str) or not isinstance(rows, dict) or not os.path.exists(fp):
            continue
        ok = {}
        for k, v in rows.items():
            if (isinstance(k, str) and isinstance(v, list) and len(v) == 3 and isinstance(v[0], str)
                    and isinstance(v[1], (int, float)) and not isinstance(v[1], bool) and isinstance(v[2], str)
                    and _bg_out("Output is being written to: " + v[2]) == v[2]):
                ok[k] = [v[0][:48], float(v[1]), v[2]]
        if ok:
            out[fp] = ok
    return out


_bg_open_prev = _bg_open_load(BG_OPEN_FILE)   # restore source, consumed per fp (popped on its first scan)
_bg_open_saved = {fp: dict(r) for fp, r in _bg_open_prev.items()}   # what the file holds now


def _bg_open_restore(fp, open_now, boot):
    """Seed `open_now` with fp's saved bg rows. ⚠Skips dismissed rows and rows whose output file is missing or
    older than `boot` (that shell cannot be running; same rule as `bgtasks.bg_idle`)."""
    for k, v in (_bg_open_prev.pop(fp, None) or {}).items():
        if k in _bg_dropped:
            continue
        try:
            mt = os.stat(v[2]).st_mtime
        except OSError:
            continue
        if boot and mt < boot:
            continue
        open_now.setdefault(k, ("bg", v[0], v[1], v[2]))


def _bg_open_save(fp, open_now):
    """Write the bg-row file when fp's open bg rows changed (atomic; capped at BG_OPEN_MAX newest rows)."""
    cur = {k: [v[1], v[2], v[3] if len(v) > 3 else ""] for k, v in open_now.items() if v[0] == "bg"}
    cur = {k: v for k, v in cur.items() if v[2]}   # no output path yet: nothing to check liveness by after a restart
    if cur == _bg_open_saved.get(fp, {}):
        return
    if cur:
        _bg_open_saved[fp] = cur
    else:
        _bg_open_saved.pop(fp, None)
    flat = sorted(((v[1], f, k) for f, r in _bg_open_saved.items() for k, v in r.items()), reverse=True)
    for _ts, f, k in flat[BG_OPEN_MAX:]:
        _bg_open_saved[f].pop(k, None)
        if not _bg_open_saved[f]:
            _bg_open_saved.pop(f, None)
    try:
        _atomic_write(BG_OPEN_FILE, json.dumps(_bg_open_saved).encode("utf-8"))
    except OSError as e:
        warn_once("bgopen", "Could not save open background shells ({err}) — they vanish after a restart",
                  vars={"err": str(e)}, soft=True)
