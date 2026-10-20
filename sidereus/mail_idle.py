"""Unread mail held by a session that nothing will wake -> row["mailIdle"] = {n, age} (metadata only).

A fresh `.wake/<sid>.lock` means an async waiter is holding the session for mail (shown as a «Mailbox watch»
row); without one, a `wait` session with old unread DMs/room posts sits idle until a person nudges it.
⛔Only counts and ages leave this module — never subject, body or sender text (AGENTS.md rule 1).
"""
import json
import os
import time
from sidereus import bus
from sidereus.config import CFG, DATA_DIR
from sidereus.sessions import WAKE_STALE_S

MI_LOCK_STALE_S = WAKE_STALE_S   # same liveness rule as sessions._wake_rows (waiter touches the lock every 2 s)
MI_MIN_DEFAULT = 10              # minutes; CFG["mail_idle_min"] overrides
# ⚠Same window as hooks/mailbox_stop.LOOKBACK_S (source of truth): a wake never surfaces older mail, so it is not flagged.
MI_LOOKBACK_S = 6 * 3600
MI_WATCH = {"lab": "Mailbox watch", "src": "proc"}


def _t_s(t):
    t = int(t or 0)
    return t / 1e9 if t > 10 ** 12 else float(t)   # bus `t` is ns; tolerate seconds


def _lock_fresh(sid, now):
    if not sid or not all(c.isalnum() or c in "-_" for c in sid):
        return False
    try:
        mt = os.path.getmtime(os.path.join(DATA_DIR, ".wake", sid[:64] + ".lock"))
    except OSError:
        return False
    return now - mt < MI_LOCK_STALE_S


def _min_n():
    try:
        v = float(CFG.get("mail_idle_min", MI_MIN_DEFAULT))
    except (TypeError, ValueError):
        v = MI_MIN_DEFAULT
    return max(1.0, v)


def _bus_after(t0):
    """Bus posts with t > t0 from the shared parse cache — only those lines are decoded (the cache holds valid JSON only)."""
    rows, _bad, _err = bus._cached(bus.BUS, bus._bus_parse)
    return [json.loads(line) for t, line in rows if t > t0]


def _seen(m, who, acks):
    e = (acks or {}).get(m.get("id")) or {}
    return who in (e.get("delivered") or []) or any(isinstance(a, dict) and a.get("who") == who for a in (e.get("ack") or []))


def annotate(rows, msgs, cursors, acks, rooms, now=None):
    """Copies changed rows (the cached sessions snapshot stays untouched). `msgs=None` reads the bus cache."""
    now = time.time() if now is None else now
    cursors, rooms = cursors or {}, rooms if isinstance(rooms, dict) else {}
    floor = now - min(MI_LOOKBACK_S, bus.ACK_KEEP_S)   # acks older than ACK_KEEP_S are pruned, so never look past it
    need, out = [], []
    for r in rows or []:
        if not isinstance(r, dict):
            out.append(r)
            continue
        fresh = _lock_fresh(r.get("sid") or "", now)
        if fresh and r.get("plat") not in (None, "cc") and not any(isinstance(x, dict) and x.get("lab") == MI_WATCH["lab"] for x in (r.get("mon") or [])):
            r = dict(r, mon=list(r.get("mon") or []) + [dict(MI_WATCH)])
        if not fresh and r.get("mbox") and r.get("state") == "wait":
            need.append(len(out))
        out.append(r)
    if not need:
        return out
    if msgs is None:
        # ⚠Clamp to the floor: a missing/0 cursor would decode the whole bus on every state() poll.
        msgs = _bus_after(max(min(int(cursors.get(out[i]["mbox"], 0) or 0) for i in need), int(floor * 1e9)))
    cut_s = _min_n() * 60
    for i in need:
        r = out[i]
        who = r["mbox"]
        cur = int(cursors.get(who, 0) or 0)
        mine = {n for n, rm in rooms.items() if isinstance(rm, dict) and who in (rm.get("members") or [])}
        ts = []
        for m in msgs:
            if not isinstance(m, dict) or int(m.get("t", 0) or 0) <= cur or m.get("from") == who:
                continue
            room = m.get("room")
            if not (room in mine if room else m.get("to") == who):
                continue
            ts_s = _t_s(m.get("t"))
            if ts_s < floor or _seen(m, who, acks):
                continue
            ts.append(ts_s)
        if ts and now - min(ts) >= cut_s:
            out[i] = dict(r, mailIdle={"n": len(ts), "age": int(now - min(ts))})
    return out
