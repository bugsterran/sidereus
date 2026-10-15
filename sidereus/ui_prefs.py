"""Browser UI prefs kept on the server: GET /api/ui-prefs.js, POST /api/ui-prefs, POST /api/ui-prefs/reset.

The page used to keep these in localStorage, which is per-origin (a port change lost them) and per-browser.
One JSON object {key: value} in DATA_DIR/ui-prefs.json; only allow-listed keys, size-capped.
⚠`null` from GET (no file) is the page's signal to migrate localStorage once; reset writes {"_v": 1} so it does not re-migrate.
⚠PATH None = memory-only (`--demo`): nothing is read or written.
"""
import json
import os
import re
import shutil
import threading
import time

from sidereus.config import DATA_DIR
from sidereus import bus as _bus
from sidereus.warn import warn_once

PATH = os.path.join(DATA_DIR, "ui-prefs.json")   # None = memory-only (demo); ⚠tests set a tmp path
BAK_DIR = None               # None = DATA_DIR/ui-prefs-bak; ⚠tests set a tmp dir
_LOCK = threading.Lock()
_MEM = {}                    # memory-only store while PATH is None

# ⚠The one key allow-list (page localStorage names): `mb*` / `sidereus.*` prefixes and four exact keys.
KEY_RE = re.compile(r"^(?:mb|sidereus\.|agPH$|dfW$|relPaView$|_v$)")
KEY_MAX = 128
VALUE_MAX = 64 * 1024        # JSON-encoded bytes per value
FILE_MAX = 512 * 1024        # JSON-encoded bytes of the whole store
BODY_MAX = FILE_MAX + 4096
RESET_BODY = {"_v": 1}


def memory_only():
    """`--demo`: keep prefs in memory only (called by chat_server.main before serving)."""
    global PATH
    PATH = None


def _key_ok(k):
    return isinstance(k, str) and 0 < len(k) <= KEY_MAX and bool(KEY_RE.match(k)) \
        and not re.search(r"[\x00-\x1f\x7f]", k)


def _enc(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _read():
    """(dict | None, corrupt) — None = no file; corrupt = the file exists but is not a JSON object."""
    try:
        with open(PATH, encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        return None, False
    except (OSError, ValueError) as e:
        warn_once("ui-prefs-read", "Could not read the UI settings file ui-prefs.json ({err})",
                  vars={"err": type(e).__name__})
        return {}, True
    return (d, False) if isinstance(d, dict) else ({}, True)


def load():
    """Stored dict, or None when there is no file (migration signal). Memory-only: the memory dict."""
    if PATH is None:
        return dict(_MEM)
    return _read()[0]


def script():
    """Body of GET /api/ui-prefs.js."""
    # `<` only occurs inside JSON strings, so < keeps the literal safe even if it is ever inlined
    return "window.__UIP=%s;" % json.dumps(load(), ensure_ascii=False).replace("<", "\\u003c")


def update(req):
    """{set: {k: v}, del: [k]} merged under the lock -> (code, out)."""
    if not isinstance(req, dict):
        return 400, {"ok": False, "error": "bad request"}
    sets, dels = req.get("set", {}), req.get("del", [])
    if not isinstance(sets, dict) or not isinstance(dels, list):
        return 400, {"ok": False, "error": "bad request"}
    # Per key: a bad key or oversize value is skipped and reported, so it never blocks the rest of the delta
    skipped = [str(k)[:KEY_MAX] for k in list(sets) + dels if not _key_ok(k)]
    skipped += [k for k, v in sets.items() if _key_ok(k) and len(_enc(v)) > VALUE_MAX]
    with _LOCK:
        if PATH is None:
            cur, corrupt = dict(_MEM), False
        else:
            cur, corrupt = _read()
            cur = cur or {}
        cur.update((k, v) for k, v in sets.items() if _key_ok(k) and len(_enc(v)) <= VALUE_MAX)
        for k in dels:
            if _key_ok(k):
                cur.pop(k, None)
        data = _enc(cur)
        if len(data) > FILE_MAX:
            return 400, {"ok": False, "error": "store too large"}
        if PATH is None:
            _MEM.clear()
            _MEM.update(cur)
        else:
            if corrupt:
                _to_bak()            # ⚠an unreadable file is kept in the backup folder, never overwritten
            _bus._atomic_write(PATH, data + b"\n", mkdir=True)
    return 200, {"ok": True, "skipped": skipped} if skipped else {"ok": True}


def _strftime(fmt):
    return time.strftime(fmt)            # tests patch this, not the time module


def _to_bak():
    """Move PATH into ui-prefs-bak/<ts>[-n]/ (never deletes) -> the new path. Caller holds _LOCK."""
    base = os.path.join(BAK_DIR or os.path.join(DATA_DIR, "ui-prefs-bak"), _strftime("%Y%m%d-%H%M%S"))
    d, n = base, 1
    while os.path.exists(d):
        n += 1
        d = "%s-%d" % (base, n)
    os.makedirs(d)
    moved = os.path.join(d, os.path.basename(PATH))
    shutil.move(PATH, moved)     # ⚠shutil.move: the backup folder may be on another volume
    return moved


def reset():
    """Move the file into the backup folder (never deletes), then write {"_v": 1} -> (code, out)."""
    if PATH is None:
        return 200, {"ok": True}
    with _LOCK:
        moved = _to_bak() if os.path.exists(PATH) else None
        _bus._atomic_write(PATH, _enc(RESET_BODY) + b"\n", mkdir=True)
    return 200, {"ok": True, "backup": os.path.basename(os.path.dirname(moved)) if moved else None}
