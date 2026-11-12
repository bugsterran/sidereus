"""Hook-less rows for CLIs whose record folder shows a session (Cursor, Copilot, pi) — same shape as ext.ext_rollout_rows.

`rollout: True` means «row from the CLI's record files, no hook events»; state is always "unknown".
A hook row wins: same sid in the store, an ended/dismissed sid, or a hook row of the same platform in the same cwd.
⚠Not `ext_store.PLAT_MODS` — that registry drives token reads (Cursor's come from hook `stop` counts).
"""
import os
import time

from sidereus.warn import warn_once
from sidereus.ident import _proj_name, _sid8, mbox_pi
from sidereus.timefmt import iso_local
from sidereus import plat_copilot, plat_cursor, plat_pi
from sidereus import ext_store   # module access: tests patch `ext_store._pid_start`
from sidereus.ext_store import EXT_PLAT, EXT_EV_N, _ext, _ext_lock, _sid_ok, _tok_sum, ext_ended
from sidereus import ext_side
from sidereus.ext import ROLL_WIN_S, ext_work
from sidereus.adapter import adapter_scan
from sidereus import live_probe, term   # module access: tests patch `_ps_snap_cache` / `_probe_cwd`

PRES_MODS = {plat_cursor.PLAT: plat_cursor, plat_copilot.PLAT: plat_copilot, plat_pi.PLAT: plat_pi}
PRES_NAME = {"cursor": "Cursor", "copilot": "Copilot", "pi": "Pi"}
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


def _is_pi_argv(cmd):
    a = str(cmd or "").split()
    b = [os.path.basename(x) for x in a[:2]]
    return bool(b) and (b[0] == "pi" or (b[0] in ("node", "bun") and b[1:] == ["pi"]))


def _pi_procs(now):
    """{cwd: pid} of running `pi` CLIs, or None = unknown. Reads the poll's ps snapshot and term's cached lsof cwd
    (same path as the external-row «To terminal» fallback); ⚠never forks ps. Non-Mac: no snapshot -> None."""
    at, snap = live_probe._ps_snap_cache[0], live_probe._ps_snap_cache[1]
    if snap is None or not 0 <= now - at < live_probe.LIVE_STALE_S:
        return None
    pids = sorted({str(p) for p, _pp, cmd in snap if _is_pi_argv(cmd)}, key=lambda p: int(p) if p.isdigit() else 0)
    if not pids:
        return {}
    term._probe_cwd(set(pids))
    out = {}
    for p in pids:
        cwd = (term._CWD_CACHE.get(p) or (0, ""))[1]
        if cwd and p.isdigit():
            out.setdefault(cwd, int(p))
    return out


def _pi_cands(now):
    """pi files written within PRES_WIN_S, plus the newest file of every cwd a `pi` process runs in (any age).
    ⚠One cwd with several running pi processes shows only its newest file (no pid -> session file link)."""
    c = adapter_scan(plat_pi, now - PRES_WIN_S)
    procs = _pi_procs(now) or {}
    for cwd, pid in procs.items():
        try:
            n = plat_pi.newest(cwd)
        except Exception:
            n = None
        if not n:
            continue
        hit = next((x for x in c if x.get("sid") == n["sid"]), None)
        if hit is None:
            c.append(n)
            hit = n
        hit["pid"] = pid
    return c


def _cands(plat, now):
    m = _PRES_MEMO.get(plat)
    if m and 0 <= now - m[0] < PRES_MEMO_S:
        return m[1]
    if plat == "cursor":
        c = plat_cursor.scan(now - PRES_WIN_S, PRES_MAX_N, PRES_STAT_N)
    elif plat == "pi":            # no liveness file: a running pi in the cwd, else a file written within PRES_WIN_S
        c = _pi_cands(now)
    else:
        c = [x for x in plat_copilot.scan(PRES_MAX_N) if _copilot_live(x, now)]
    _PRES_MEMO[plat] = (now, c)
    return c


def _row(plat, c, now):
    cwd = c.get("cwd") or ""
    last = float(c.get("mtime") or now)
    first = float(c.get("start") or last)
    sid = c["sid"]
    pi = plat == "pi"
    tk = _tok_sum(c.get("msgs") or {}) if pi else ext_side.ext_side_tok(plat, sid) or {}   # Copilot usage records; Cursor stays 0 here
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
        "model": str((c.get("model") if pi else tk.get("model")) or "")[:40], "tok": tk.get("tok", 0),
        "tokSplit": {k: tk.get(k, 0) for k in ("in", "out", "cache", "thought")},
        "estCost": tk.get("cost") if pi else None, "costMiss": tk.get("costMiss", 0),
        "ageSec": max(0, int(now - last)),
        "runmin": {"sub": 0, "bg": 0, "run": max(0, int((last - first) / 60))},
        "kind": plat, "goneWhy": "", "rollout": True,
        "pid": c["pid"] if pi and isinstance(c.get("pid"), int) and c["pid"] > 1 else 0,   # running pi CLI, for «To terminal»
        "hooksOff": plat == "copilot" and plat_copilot.hooks_disabled(cwd),
        "extOld": "",   # no hook events: no rev to compare (R4)
    })
    if pi:   # the pi mailbox id (`pi:<cwd>` or <folder>-pi), never the Claude id; "" made room members show the Claude logo
        row["mbox"], row["mboxSrc"] = mbox_pi(cwd)
        cr = plat_pi.credit(c.get("msgs"))   # Anthropic OAuth spend; tok is filled by state._who_pi
        if cr:
            row["credit"] = cr
    return row


def ext_presence_rows(now=None):
    now = now or time.time()
    rows = []
    try:
        with _ext_lock:
            # ⚠A parented child (pi subagent) counts as ended here: its cwd must not hide the hookless parent pi row.
            store = [(p, sid, v.get("cwd") or "", bool(v.get("ended") or v.get("parent"))) for (p, sid), v in _ext.items()]
        for plat in PRES_MODS:
            known = {sid for p, sid, _c, _e in store if p == plat} | ext_ended(plat, now)
            cwds = {cwd for p, _, cwd, end in store if p == plat and cwd and not end}   # ⚠a folded row must not hide a new session in its folder
            for c in _cands(plat, now):
                sid = c.get("sid") or ""
                if not _sid_ok(sid) or sid in known or (c.get("cwd") or "") in cwds:
                    continue
                rows.append(_row(plat, c, now))
    except Exception as e:                        # the rest of the list must survive
        warn_once("ext-presence-rows", "Could not build external session rows ({err})", vars={"err": type(e).__name__})
    return rows


def ext_work_any(plat, sid, now=None):
    """ext.ext_work, then the record-folder row (metadata only) for a hook-less Cursor/Copilot/pi session."""
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
    if c is None:                                 # not live any more (timeline, recent list): read its folder by sid
        try:
            c = PRES_MODS[name].one(sid)
        except Exception:
            c = None
    if c is None:
        return out
    first, last = float(c.get("start") or 0), float(c.get("mtime") or 0)
    iso = lambda t: iso_local(t) if t else ""
    return {"ok": True, "ext": True, "plat": EXT_PLAT[name], "platform": name, "sid": sid,
            "type": PRES_NAME[name] + " · " + _sid8(sid), "desc": c.get("cwd") or "",
            "cwd": c.get("cwd") or "", "model": str(c.get("model") or "")[:40] if name == "pi" else "",
            # src 'file': no hook record, rows read from the session folder; tool = last recorded tool name (pi only)
            "state": "unknown", "src": "file", "tool": (c.get("tools") or [(0, "")])[-1][1] if name == "pi" else "",
            "blocked": False,
            "firstSeen": first, "lastSeen": last, "first": iso(first), "last": iso(last),
            "events": [{"e": "PostToolUse", "tool": n, "t": t} for t, n in (c.get("tools") or [])[-EXT_EV_N:]],
            "parent": "", "steps": [], "cutSteps": 0, "says": []}
