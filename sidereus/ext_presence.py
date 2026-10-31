"""Hook-less rows for CLIs whose record folder shows a session (Cursor, Copilot) — same shape as ext.ext_rollout_rows.

`rollout: True` means «row from the CLI's record files, no hook events»; state is always "unknown".
A hook row wins: same sid in the store, an ended/dismissed sid, or a hook row of the same platform in the same cwd.
⚠Not `ext_store.PLAT_MODS` — that registry drives token reads (Cursor's come from hook `stop` counts).
"""
import time

from sidereus.warn import warn_once
from sidereus.ident import _proj_name, _sid8
from sidereus.timefmt import iso_local
from sidereus import plat_copilot, plat_cursor
from sidereus import ext_store   # module access: tests patch `ext_store._pid_start`
from sidereus.ext_store import EXT_PLAT, _ext, _ext_lock, _sid_ok, ext_ended
from sidereus.ext import ROLL_WIN_S, ext_work

PRES_MODS = {plat_cursor.PLAT: plat_cursor, plat_copilot.PLAT: plat_copilot}
PRES_NAME = {"cursor": "Cursor", "copilot": "Copilot"}
PRES_WIN_S = ROLL_WIN_S       # Cursor has no liveness file: a chat written this recently counts as open
PRES_MAX_N = 300              # sid folders stat'ed per root per scan
PRES_MEMO_S = 5
PRES_STAT_N = 3000            # Cursor: sid folders stat'ed per scan (ranked by mtime, then PRES_MAX_N kept)
PRES_STALE_S = 24 * 3600      # Copilot lock whose pid start time is unknown: live only if touched this recently
PRES_SLACK_S = 5              # ps lstart has 1 s resolution; the lock is written just after the CLI starts
_PRES_MEMO = {}               # plat -> (t, cands)


def _start_ts(s):
    try:
        return time.mktime(time.strptime(s, "%a %b %d %H:%M:%S %Y"))
    except (TypeError, ValueError, OverflowError):
        return None


def _copilot_live(c, now):
    """A lock pid counts only if that process started before the lock was written (else the pid was reused
    after a crash). Start unknown (no ps / Windows) -> live only while the session was touched within PRES_STALE_S."""
    for pid, lmt in c.get("locks") or []:
        st = ext_store._pid_start(pid)
        if st == "":
            continue                              # ps: no such process
        t = _start_ts(st) if st else None
        if t is None:
            if now - max(lmt, float(c.get("mtime") or 0)) <= PRES_STALE_S:
                return True
        elif t <= lmt + PRES_SLACK_S:
            return True
    return False


def _cands(plat, now):
    m = _PRES_MEMO.get(plat)
    if m and 0 <= now - m[0] < PRES_MEMO_S:
        return m[1]
    if plat == "cursor":
        c = plat_cursor.scan(now - PRES_WIN_S, PRES_MAX_N, PRES_STAT_N)
    else:
        c = [x for x in plat_copilot.scan(PRES_MAX_N) if _copilot_live(x, now)]
    _PRES_MEMO[plat] = (now, c)
    return c


def _row(plat, c, now):
    cwd = c.get("cwd") or ""
    last = float(c.get("mtime") or now)
    first = float(c.get("start") or last)
    sid = c["sid"]
    tk = ext_store.ext_side_tok(plat, sid) or {}   # Copilot usage records; Cursor stays 0 here
    row = {
        "id": "", "sid": "", "project": "?", "gotPrompt": 0,
        "creq": 0, "burn": 0, "rpm": 0, "cwd": "", "branch": "",
        "tool": "", "targ": "", "sub": [], "bgs": [], "mon": [],
        "runmin": {}, "kind": "", "ageSec": 0, "bytes": 0, "repos": [],
        "mbox": "", "mboxSrc": "", "cost": 0, "ctx": 0, "model": "",
        "win": 0, "winSrc": "", "winN": 0,
        "git": "", "state": "unknown", "blocked": "",
        "otel": False, "otelEv": "", "otelAt": 0, "err": False, "plat": EXT_PLAT[plat],
    }
    row.update({
        "id": _sid8(sid), "sid": sid, "project": _proj_name(cwd) or "?", "cwd": cwd,
        "branch": str(c.get("branch") or "")[:200],
        "model": str(tk.get("model") or "")[:40], "tok": tk.get("tok", 0),
        "tokSplit": {k: tk.get(k, 0) for k in ("in", "out", "cache", "thought")},
        "estCost": None, "costMiss": tk.get("costMiss", 0),
        "ageSec": max(0, int(now - last)),
        "runmin": {"sub": 0, "bg": 0, "run": max(0, int((last - first) / 60))},
        "kind": plat, "goneWhy": "", "pid": 0, "rollout": True,
    })
    return row


def ext_presence_rows(now=None):
    now = now or time.time()
    rows = []
    try:
        with _ext_lock:
            store = [(p, sid, v.get("cwd") or "") for (p, sid), v in _ext.items()]
        for plat in PRES_MODS:
            known = {sid for p, sid, _ in store if p == plat} | ext_ended(plat, now)
            cwds = {cwd for p, _, cwd in store if p == plat and cwd}
            for c in _cands(plat, now):
                sid = c.get("sid") or ""
                if not _sid_ok(sid) or sid in known or (c.get("cwd") or "") in cwds:
                    continue
                rows.append(_row(plat, c, now))
    except Exception as e:                        # the rest of the list must survive
        warn_once("ext-presence-rows", "Could not build external session rows ({err})", vars={"err": type(e).__name__})
    return rows


def ext_work_any(plat, sid, now=None):
    """ext.ext_work, then the record-folder row (metadata only) for a hook-less Cursor/Copilot session."""
    out = ext_work(plat, sid, now)
    if out.get("ok"):
        return out
    p = str(plat or "").strip().lower()
    name = p if p in PRES_MODS else next((k for k in PRES_MODS if EXT_PLAT.get(k) == p), "")
    sid = str(sid or "").strip()
    if not name or not _sid_ok(sid):
        return out
    now = now or time.time()
    c = next((c for c in _cands(name, now) if c.get("sid") == sid), None)
    if c is None:
        return out
    first, last = float(c.get("start") or 0), float(c.get("mtime") or 0)
    iso = lambda t: iso_local(t) if t else ""
    return {"ok": True, "ext": True, "plat": EXT_PLAT[name], "platform": name, "sid": sid,
            "type": PRES_NAME[name] + " · " + _sid8(sid), "desc": c.get("cwd") or "",
            "cwd": c.get("cwd") or "", "model": "", "state": "unknown", "tool": "", "blocked": False,
            "firstSeen": first, "lastSeen": last, "first": iso(first), "last": iso(last),
            "events": [], "parent": "", "steps": [], "cutSteps": 0, "says": []}
