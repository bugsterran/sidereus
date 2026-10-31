"""Copilot CLI presence and token counts from its own record folder (no hooks needed):
`<root>/session-state/<uuid>/workspace.yaml` (presence) and `events.jsonl` (usage, quota).

Read by sidereus/ext_presence.py and sidereus/ext_store.py — ⚠not an adapter (`ext_store.PLAT_MODS` stays Gemini + Codex).
⚠Metadata only: workspace.yaml is parsed line by line through `_KEYS`; `name` / `summary*` lines are dropped
before anything is kept. In events.jsonl only lines starting with `_USE_PFX` are json-parsed; the quota is cut out
of `model.model_call_success` lines (which carry request/response content) by `raw_decode` from its key, never by
parsing the line — see docs/dev/traps/platform.md.
"""
import json
import os
import re
import threading
import time
from datetime import datetime

from sidereus import config        # module access: tests patch `config.pid_alive`
from sidereus.ident import _real_home

PLAT = "copilot"
YAML_MAX = 64 * 1024
_KEYS = ("id", "cwd", "branch", "created_at", "updated_at")
_LINE = re.compile(r"^([a-z_]+):[ \t]*(.*?)[ \t]*$")
_LOCK = re.compile(r"^inuse\.(\d{1,10})\.lock$")


def _root_for(h):
    return h if h and os.path.isabs(h) else os.path.join(_real_home(), ".copilot")


def root():
    return _root_for(os.environ.get("COPILOT_HOME") or "")


def _mt(p):
    try:
        return os.stat(p).st_mtime
    except OSError:
        return 0.0


def _yaml(p):
    """Allow-listed top-level `key: value` pairs of workspace.yaml, or None when unreadable."""
    try:
        if os.path.getsize(p) > YAML_MAX:
            return None
        out = {}
        with open(p, encoding="utf-8") as f:
            for ln in f:
                m = _LINE.match(ln.rstrip("\r\n"))
                if not m or m.group(1) not in _KEYS:
                    continue
                v = m.group(2)
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                    v = v[1:-1]
                out[m.group(1)] = v[:1024]
    except (OSError, ValueError):
        return None
    return out


def _ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _locks(d):
    """[(pid, lock mtime)] of `inuse.<pid>.lock` files whose pid is running. The caller checks pid reuse
    (ext_presence, via ext_store._pid_start). ⚠config.pid_alive only — os.kill(pid, 0) terminates the process on Windows."""
    try:
        names = os.listdir(d)
    except OSError:
        return []
    out = []
    for n in names:
        m = _LOCK.match(n)
        if m and config.pid_alive(int(m.group(1))) is True:
            out.append((int(m.group(1)), _mt(os.path.join(d, n))))
    return out


def scan(max_n):
    """[{sid, cwd, branch, start, mtime, locks}] of sessions with a running lock pid; at most `max_n` folders are read
    (newest folder mtime first — creating the lock file touches it)."""
    base = os.path.join(root(), "session-state")
    try:
        ds = [(n, os.path.join(base, n)) for n in os.listdir(base)]
    except OSError:
        return []
    ds.sort(key=lambda x: _mt(x[1]), reverse=True)
    out = []
    for sid, d in ds[:max_n]:
        locks = _locks(d)
        if not locks:
            continue
        y = _yaml(os.path.join(d, "workspace.yaml"))
        if not y or y.get("id") != sid or not y.get("cwd"):
            continue
        last = _mt(os.path.join(d, "events.jsonl")) or _ts(y.get("updated_at")) or _mt(d)
        out.append({"sid": sid, "cwd": y["cwd"], "branch": y.get("branch") or "",
                    "start": _ts(y.get("created_at")) or last, "mtime": last, "locks": locks})
    return out


# ── token counts and quota from events.jsonl (incremental, per path) ──
SCAN_MAX = 256 << 20          # skip events.jsonl files larger than this
EV_SCAN_N = 300               # newest session folders read by msgs_since / quota
# ★Measured (CLI 1.0.105, 13/13 files): `type` is the first key, compact separators. ⚠If that changes nothing is parsed.
_USE_PFX = b'{"type":"session.usage_record"'
_CALL_PFX = b'{"type":"model.model_call_success"'
_QS_KEY = '"quotaSnapshots":'
_TS_KEY = '"timestamp":"'
_QNUM = ("isUnlimitedEntitlement", "entitlementRequests", "usedRequests", "remainingPercentage", "overage")
_BUCKET = re.compile(r"^[a-z_]{1,40}$")
_SID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_ev_lock = threading.Lock()
_ev = {}    # path -> {"ino", "off", "msgs": {key: (in, out, cache, 0, ts, model, None)}, "quota": (at, buckets) | None}


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v < 10 ** 12 else 0


def _usage_line(ln, off):
    """(key, msg) from one `session.usage_record` line, or None. inputTokens includes the cache read + write."""
    try:
        d = json.loads(ln)
    except ValueError:
        return None
    u = (d.get("data") or {}).get("usage") if isinstance(d, dict) and isinstance(d.get("data"), dict) else None
    if not isinstance(u, dict):
        return None
    cr, cw = _int(u.get("cacheReadTokens")), _int(u.get("cacheWriteTokens"))
    acc = u.get("accounting") if isinstance(u.get("accounting"), dict) else {}
    key = acc.get("usageId") if isinstance(acc.get("usageId"), str) and acc.get("usageId") else "@%d" % off
    model = u.get("model") if isinstance(u.get("model"), str) else ""
    return key[:200], (max(0, _int(u.get("inputTokens")) - cr - cw), _int(u.get("outputTokens")), cr + cw, 0,
                       _ts(d.get("timestamp")), model[:40], None)


def _quota_line(ln):
    """(at, {bucket: {numbers, reset}}) cut out of a model_call_success line, or None.
    ⚠Never json.loads the line: it holds requestMessages/response text. Only numbers/bools + resetDate are kept."""
    s = ln.decode("utf-8", "replace")
    i = s.rfind(_QS_KEY)
    if i < 0:
        return None
    try:
        q, _end = json.JSONDecoder().raw_decode(s, i + len(_QS_KEY))
    except ValueError:
        return None
    if not isinstance(q, dict):
        return None
    out = {}
    for b, v in q.items():
        if not isinstance(v, dict) or not isinstance(b, str) or not _BUCKET.match(b):
            continue
        e = {k: v[k] for k in _QNUM if isinstance(v.get(k), (int, float, bool))}
        e["reset"] = _ts(v.get("resetDate")) if isinstance(v.get("resetDate"), str) else 0.0
        out[b] = e
    j = s.rfind(_TS_KEY)
    at = _ts(s[j + len(_TS_KEY):s.find('"', j + len(_TS_KEY))]) if j >= 0 else 0.0
    return (at, out) if out and at else None


def _refresh(path):
    """Read new complete lines of one events.jsonl into `_ev`; returns its entry (or None when unreadable/too big).
    ⚠A partial last line waits for its newline; a shorter file or a new inode starts over."""
    try:
        with open(path, "rb") as f:
            st = os.fstat(f.fileno())
            if st.st_size > SCAN_MAX:
                return None
            with _ev_lock:
                e = _ev.get(path)
                if e is None or e["ino"] != st.st_ino or st.st_size < e["off"]:
                    e = _ev[path] = {"ino": st.st_ino, "off": 0, "msgs": {}, "quota": None}
                if st.st_size == e["off"]:
                    return e
                f.seek(e["off"])
                buf = f.read(st.st_size - e["off"])
                end = buf.rfind(b"\n")
                if end < 0:
                    return e
                pos = e["off"]
                for ln in buf[:end].split(b"\n"):
                    at, pos = pos, pos + len(ln) + 1
                    ln = ln.rstrip(b"\r")
                    if ln.startswith(_USE_PFX):
                        r = _usage_line(ln, at)
                        if r:
                            e["msgs"][r[0]] = r[1]
                    elif ln.startswith(_CALL_PFX) and b'"quotaSnapshots":' in ln:
                        q = _quota_line(ln)
                        if q and (e["quota"] is None or q[0] >= e["quota"][0]):
                            e["quota"] = q
                e["off"] += end + 1
                return e
    except OSError:
        return None


def _ev_path(sid):
    return os.path.join(root(), "session-state", sid, "events.jsonl")


def usage_msgs(sid):
    """{key: (in, out, cache, 0, ts, model, None)} of one session (the `ext_store._tok_sum` shape), {} if unknown."""
    if not isinstance(sid, str) or not _SID.match(sid):
        return {}
    e = _refresh(_ev_path(sid))
    if e is None:
        return {}
    with _ev_lock:
        return dict(e["msgs"])


def _recent(since):
    """[(sid, path)] of the newest EV_SCAN_N events.jsonl files modified at or after `since`."""
    base = os.path.join(root(), "session-state")
    try:
        names = [n for n in os.listdir(base) if _SID.match(n)]
    except OSError:
        return []
    ps = [(n, os.path.join(base, n, "events.jsonl")) for n in names]
    ps = sorted(((n, p, _mt(p)) for n, p in ps), key=lambda x: x[2], reverse=True)
    ps = [x for x in ps if x[2]][:EV_SCAN_N]
    # ⚠Evict by the newest-EV_SCAN_N set, never by `since`: a narrow caller must not drop what quota() re-reads.
    keep = {p for _n, p, _t in ps}
    with _ev_lock:
        for k in [k for k in _ev if k not in keep]:
            _ev.pop(k, None)
    return [(n, p) for n, p, t in ps if t >= since]


def msgs_since(since):
    """{sid: {key: msg}} for usage records at or after `since`."""
    out = {}
    for sid, p in _recent(since):
        e = _refresh(p)
        if e is None:
            continue
        with _ev_lock:
            ms = {k: v for k, v in e["msgs"].items() if v[4] >= since}
        if ms:
            out[sid] = ms
    return out


def quota(now=None):
    """{bucket, used, ent, unl, pct, reset, at} from the newest quota snapshot across sessions, or None.
    pct = remainingPercentage as reported; a snapshot whose resetDate has passed is dropped (numbers are stale)."""
    now = now or time.time()
    best = None
    for _sid, p in _recent(0.0):
        e = _refresh(p)
        if e is not None and e["quota"] and (best is None or e["quota"][0] > best[0]):
            best = e["quota"]
    if best is None:
        return None
    at, qs = best
    pr = qs.get("premium_interactions") or {}
    name = "premium_interactions" if (pr.get("entitlementRequests") or 0) > 0 \
        or pr.get("isUnlimitedEntitlement") is True else "chat"
    b = qs.get(name)
    if not b or (b["reset"] and b["reset"] <= now):
        return None
    return {"bucket": name, "used": b.get("usedRequests"), "ent": b.get("entitlementRequests"),
            "unl": b.get("isUnlimitedEntitlement") is True, "pct": b.get("remainingPercentage"),
            "reset": b["reset"] or None, "at": at}
