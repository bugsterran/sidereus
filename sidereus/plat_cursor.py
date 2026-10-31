"""Cursor CLI presence from its own record folder (no hooks needed): `<root>/chats/<workspace-hash>/<sid>/meta.json`.

Read by sidereus/ext_presence.py only — ⚠not an adapter: registering it in `ext_store.PLAT_MODS` would change
Cursor's token path (hook `stop` counts, ext_store `_hooktok`).
⚠Metadata only: `cwd`, `createdAtMs`, `updatedAtMs` of meta.json; `store.db` / `prompt_history.json` are never opened.
"""
import json
import os

from sidereus.ident import _real_home

PLAT = "cursor"
META_MAX = 64 * 1024          # meta.json is ~200 bytes; anything bigger is not the file we know
_ACT_FILES = ("meta.json", "store.db", "store.db-wal")


def root():
    return os.path.join(_real_home(), ".cursor")


def _mt(p):
    try:
        return os.stat(p).st_mtime
    except OSError:
        return 0.0


def _meta(p):
    """(cwd, start) from meta.json or None. Only the allow-listed keys leave this function."""
    try:
        if os.path.getsize(p) > META_MAX:
            return None
        with open(p, encoding="utf-8") as f:
            j = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(j, dict):
        return None
    cwd = j.get("cwd")
    ms = j.get("createdAtMs")
    if not isinstance(cwd, str) or not cwd:
        return None
    start = float(ms) / 1000.0 if isinstance(ms, (int, float)) and not isinstance(ms, bool) and ms > 0 else 0.0
    return cwd[:1024], start


def scan(since, max_n, stat_n=None):
    """[{sid, cwd, start, mtime}] of the `max_n` freshest chats active at or after `since`; ≤ `stat_n` sid folders stat'ed.
    ⚠The chats dir mtime is no signal (store.db writes don't touch it) ⇒ rank sids by their own file mtimes, then cap."""
    stat_n = max_n * 10 if stat_n is None else stat_n
    base = os.path.join(root(), "chats")
    try:
        ws = [os.path.join(base, n) for n in os.listdir(base)]
    except OSError:
        return []
    ws.sort(key=_mt, reverse=True)
    act, n = [], 0
    for w in ws:
        try:
            sids = os.listdir(w)
        except OSError:
            continue
        for sid in sids:
            if n >= stat_n:
                break
            n += 1
            d = os.path.join(w, sid)
            last = max(_mt(os.path.join(d, f)) for f in _ACT_FILES)
            if last >= since:
                act.append((last, sid, d))
    act.sort(reverse=True)
    out = []
    for last, sid, d in act[:max_n]:
        m = _meta(os.path.join(d, "meta.json"))
        if m is not None:
            out.append({"sid": sid, "cwd": m[0], "start": m[1] or last, "mtime": last})
    return out
