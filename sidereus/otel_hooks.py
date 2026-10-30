"""Per-day hook cost from OTel hook_execution_complete (count, time, failures per hook event type) for the retro «Hook cost» card,
plus per-day firings by `<Event>:<subject>` (`_ohn`) so the Harness view can count runs of hooks that print nothing,
and per-firing cost counts (`_ohx`) for the «slow» / «no_effect» Harness verdicts."""
import json
import os
import re
import threading
import time
from sidereus.config import DATA_DIR
from sidereus.bus import _atomic_write
from sidereus.timefmt import ymd as _ymd


# Shape {ymd: {hook_event: [runs, durMsSum, fails]}} — hook event type only (R1, metadata).
# `_ohn` shape {ymd: {"<Event>" | "<Event>:<subject>": runs}}; subject = the tool name or source the matchers were tried on
# (hook_name is built as `${event}:${matchQuery}`, MCP tools arrive as «mcp_tool» unless OTEL_LOG_TOOL_DETAILS=1).
# ⚠Never store hook_definitions, *_chars or session.id, and keep hook_name only when it parses as event + tool-like subject:
# definitions name user scripts and *_chars size their output.
# ⚠Fed from otel._otel_ingest while `_otel_lock` is held: this module has its own lock and never takes `_otel_lock`.
OH_FILE = os.path.join(DATA_DIR, "otel-hooks.json")
OH_KEEP_D = 31
OH_CAP = 40                 # event types per day; beyond it merge into «Other»
OH_EV_MAX = 40              # hook_event string length cap
OH_SAVE_S = 60
OH_OTHER = "Other"
OHN_CAP = 300               # event:subject keys per day; beyond it the firing is dropped (counts become a lower bound)
OHN_SUB_RE = re.compile(r"[A-Za-z0-9_.\-]{1,80}")
OHN_AMBIG = ("mcp_tool", "mcp_server")   # sanitised subjects: a specific matcher cannot be tested against them
OHN_NOSUB = ("SubagentStart", "SubagentStop")   # matchers apply, but hook_name carries no subject
_oh = {}
_ohn = {}
# `_ohx` shape {ymd: {same key as `_ohn`: [mruns, msSum, blocked, withOutput]}}; mruns = firings that carried duration,
# num_blocking and both *_chars (others raise only `_ohn`). Only counts and booleans-turned-counts are stored.
# ⚠Shares OHN_CAP with `_ohn`: past the cap a firing is dropped, so every count is a lower bound.
_ohx = {}
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


def _ohn_key(ev, name):
    """`<Event>` or `<Event>:<subject>` from hook_event + hook_name; None when hook_name does not parse that way."""
    ev = str(ev or "")
    if not ev or len(ev) > OH_EV_MAX or not ev.isalpha():
        return None
    nm = str(name or "")
    if nm in ("", ev):
        return ev
    e, sep, sub = nm.partition(":")
    return ev + ":" + sub if sep and e == ev and OHN_SUB_RE.fullmatch(sub) else None


def _oh_add(ts, ev, dur, fail, name=None, blk=None, out=None):
    """Add one hook firing (total_duration_ms covers all matching hooks of that firing) to its day and event type.
    blk / out = the firing blocked / printed anything (booleans); None = attribute missing, so `_ohx` is not raised."""
    with _oh_lock:
        dk = _ymd(ts)
        day = _oh.setdefault(dk, {})
        v = day.setdefault(_oh_key(day, ev), [0, 0, 0])
        v[0] += 1
        v[1] += _oh_int(dur)
        v[2] += _oh_int(fail)
        k = _ohn_key(ev, name)
        nd = _ohn.setdefault(dk, {})
        if k and (k in nd or len(nd) < OHN_CAP):
            nd[k] = nd.get(k, 0) + 1
            if dur is not None and blk is not None and out is not None:
                xd = _ohx.setdefault(dk, {})
                if k in xd or len(xd) < OHN_CAP:
                    x = xd.setdefault(k, [0, 0, 0, 0])
                    x[0] += 1
                    x[1] += _oh_int(dur)
                    x[2] += int(bool(blk))
                    x[3] += int(bool(out))
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
        nsrc = d.get("n") if isinstance(d, dict) and isinstance(d.get("n"), dict) else {}
        for dk, row in nsrc.items():
            if not (isinstance(dk, str) and isinstance(row, dict)):
                continue
            dst = _ohn.setdefault(dk, {})
            for k, v in row.items():
                if isinstance(k, str) and (k in dst or len(dst) < OHN_CAP):
                    dst[k] = dst.get(k, 0) + _oh_int(v)
        # R4: a file without "x" predates cost counts and loads as «not measured yet».
        xsrc = d.get("x") if isinstance(d, dict) and isinstance(d.get("x"), dict) else {}
        for dk, row in xsrc.items():
            if not (isinstance(dk, str) and isinstance(row, dict)):
                continue
            dst = _ohx.setdefault(dk, {})
            for k, v in row.items():
                if not (isinstance(k, str) and isinstance(v, list) and len(v) == 4):
                    continue
                if k in dst or len(dst) < OHN_CAP:
                    c = dst.setdefault(k, [0, 0, 0, 0])
                    for i in range(4):
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
        old = [k for k in _oh if k < cut] + [k for k in _ohn if k < cut] + [k for k in _ohx if k < cut]
        for k in old:
            _oh.pop(k, None)
            _ohn.pop(k, None)
            _ohx.pop(k, None)
        if not (old or _oh_meta["dirty"] or force):
            return False
        blob = json.dumps({"v": 1, "d": _oh, "n": _ohn, "x": _ohx}, separators=(",", ":"), ensure_ascii=False)
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


def _ohn_fits(matcher, sub):
    try:
        return bool(re.fullmatch(matcher, sub))
    except re.error:
        return matcher == sub


def _oh_match(ev, m, k):
    """(subject, counted, ambiguous) of one `_ohn` / `_ohx` key for hook event `ev` and matcher `m` — hook_fires' rules."""
    e, _, sub = k.partition(":")
    if e != ev:
        return sub, False, False
    if not m or m == "*" or (not sub and ev not in OHN_NOSUB):
        return sub, True, False
    if not sub or sub in OHN_AMBIG:
        return sub, False, not sub or "mcp" in m.lower()
    return sub, _ohn_fits(m, sub), False


def hook_cost(ev, matcher, since_ymd):
    """{mruns, ms, blk, out, subs, amb} of one hook entry from `_ohx` over days >= since_ymd (same matching as hook_fires);
    None when no measured firing was recorded. subs = subjects that contributed ("" = event-level key)."""
    if not _oh_meta["loaded"]:
        _oh_load()
    m = matcher if isinstance(matcher, str) else ""
    r = {"mruns": 0, "ms": 0, "blk": 0, "out": 0, "subs": [], "amb": False}
    with _oh_lock:
        for dk in sorted(_ohx):
            if dk < since_ymd:
                continue
            for k, v in _ohx[dk].items():
                sub, ok, amb = _oh_match(ev, m, k)
                r["amb"] = r["amb"] or amb
                if not ok:
                    continue
                r["mruns"] += v[0]
                r["ms"] += v[1]
                r["blk"] += v[2]
                r["out"] += v[3]
                if sub not in r["subs"]:
                    r["subs"].append(sub)
    return r if r["mruns"] else None


def hook_fires(ev, matcher, since_ymd):
    """(runs, from_ymd, ambiguous) of one hook entry from `_ohn` over days >= since_ymd; None when no firing was recorded since then.
    Every hook whose matcher fits the firing's subject runs in that firing, so a silent hook is counted too.
    ambiguous = some firings could not be attributed (sanitised MCP subject, or a subagent event with a specific matcher)."""
    if not _oh_meta["loaded"]:
        _oh_load()
    m = matcher if isinstance(matcher, str) else ""
    allm = not m or m == "*"
    n, first, amb = 0, "", False
    with _oh_lock:
        for dk in sorted(_ohn):
            if dk < since_ymd or not _ohn[dk]:
                continue
            first = first or dk
            for k, c in _ohn[dk].items():
                e, _, sub = k.partition(":")
                if e != ev:
                    continue
                if allm or (not sub and ev not in OHN_NOSUB):
                    n += c
                elif not sub or sub in OHN_AMBIG:
                    amb = amb or not sub or "mcp" in m.lower()
                elif _ohn_fits(m, sub):
                    n += c
    return (n, first, amb) if first else None
