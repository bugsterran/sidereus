"""«Compacts in ~N turns» estimate for Claude Code rows (row `cmpEta`) + the compaction-window rules burn_scan shares.

Owns COMPACT_DEFAULT, ETA_MIN, ETA_KEEP, ETA_DROP, CW_FILE, SETTINGS_FILE, _SET_MEMO, SERIES_CAP, _SERIES; tests patch them here.
⚠Metadata only: reads `usage`, `message.id`, `isSidechain` and the `compact_boundary` type — never content."""
import json
import math
import os
import statistics
import threading
from collections import OrderedDict
from sidereus.config import DATA_DIR, claude_home
from sidereus import claude_roots

COMPACT_DEFAULT = 1_000_000
ETA_MIN = 3        # growth samples (diffs) needed before any estimate — fewer is a guess
ETA_KEEP = 11      # newest points kept (-> at most 10 diffs)
ETA_DROP = 0.7     # newer ctx below 70% of the older one = a compaction we did not see marked: cut there
CW_FILE = os.path.join(DATA_DIR, "compact-win.json")   # read only — sidereus/burn_scan.py owns and writes it
SETTINGS_FILE = os.path.join(claude_home(), "settings.json")   # primary account; read only
SET_MAX = 1_000_000
_SET_MEMO = {}     # path -> (mtime_ns, size, parsed object); settings files + CW_FILE, a handful of paths
# ⚠The parse tail (400 KB / 600 lines) can hold only a few responses after big tool results, so the series is kept
#   per transcript across parses; recomputing it from each tail alone made k fall below ETA_MIN and the hint flicker.
SERIES_CAP = 256   # transcript paths kept, oldest dropped
_SERIES = OrderedDict()   # path -> (ino, size, [(message.id, ctx)] oldest first, <= ETA_KEEP)
_SERIES_LOCK = threading.Lock()


def settings_compact(d):
    """settings.json object -> (window, enabled). Window rules unchanged from burn_scan._compact_setting."""
    d = d if isinstance(d, dict) else {}   # ⚠a non-object top level / `env` falls back to the default, not a crash
    win = d.get("autoCompactWindow")
    env = d.get("env")
    env = env if isinstance(env, dict) else {}
    off = d.get("autoCompactEnabled") is False
    # An env override in the settings file wins (only window-sized keys, not the *_PCT_* percentage).
    for k, v in env.items():
        ku = str(k).upper()
        kn = ku.replace("_", "")
        # ⚠Only *WINDOW keys — a DISABLE_AUTOCOMPACT=1 flag must not become a 1-token window.
        if "AUTOCOMPACT" in kn and ku.endswith("WINDOW") and "PCT" not in ku:
            win = v
        if kn in ("DISABLEAUTOCOMPACT", "DISABLECOMPACT") and str(v).strip().lower() not in ("", "0", "false", "no", "off", "none"):
            off = True
    try:
        win = int(win) if win is not None else COMPACT_DEFAULT
    except (TypeError, ValueError):
        win = COMPACT_DEFAULT
    return (win if win >= 10000 else COMPACT_DEFAULT), not off


def sess_win(born, cw):
    """Window a session born at `born` runs with, or None when unknown (born before a change we did not record)."""
    if not isinstance(cw, dict) or cw.get("value") is None:
        return None
    return cw["value"] if born > (cw.get("since") or 0) else cw.get("prev")


def _json_at(path):
    """Parsed JSON at `path`; {} when missing, None when unreadable/mid-write (unknown, never a default)."""
    try:
        st = os.stat(path)
    except OSError:
        return {}
    hit = _SET_MEMO.get(path)
    if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
        return hit[2]
    if st.st_size > SET_MAX:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            v = json.load(f)
    except (OSError, ValueError):
        return None                        # ⚠not memoized: the next poll retries a half-written file
    _SET_MEMO[path] = (st.st_mtime_ns, st.st_size, v)
    return v


def _tail_samples(rows):
    """([(message.id, ctx)] newest first, cut seen) — main-thread responses of the tail since the last compaction."""
    out, seen = [], set()
    for line in reversed(rows):
        if '"usage"' not in line and "compact_boundary" not in line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        if d.get("type") == "system" and d.get("subtype") == "compact_boundary":
            return out, True
        msg = d.get("message")
        if d.get("type") != "assistant" or d.get("isSidechain") is True or not isinstance(msg, dict):
            continue
        u = msg.get("usage")
        if not isinstance(u, dict):
            continue
        mid = msg.get("id") if isinstance(msg.get("id"), str) else None
        if mid and mid in seen:
            continue                       # one response is written as several lines with the same usage
        try:
            c = int(u.get("input_tokens") or 0) + int(u.get("cache_read_input_tokens") or 0) \
                + int(u.get("cache_creation_input_tokens") or 0)
        except (TypeError, ValueError):
            continue
        if c <= 0:
            continue
        if mid:
            seen.add(mid)
        if out and out[-1][1] < ETA_DROP * c:
            return out, True               # newer is far below this one: compacted in between
        out.append((mid, c))
        if len(out) >= ETA_KEEP:
            break
    return out, False


def _older_kept(kept, tail):
    """Kept samples older than the tail's earliest one (oldest first), cut at a drop like the tail itself."""
    ids = [m for m, _c in tail if m]
    hit = [i for i, (m, _c) in enumerate(kept) if m and m in ids]
    if hit:
        # ⚠Only a contiguous join: the tail's earliest response must be a kept one, else order is unknown.
        older = kept[:hit[0]] if kept[hit[0]][0] == tail[-1][0] else []
    else:
        older = list(kept)                 # the tail moved past everything kept
    out, newer = [], tail[-1][1]
    for m, c in reversed(older):
        if newer < ETA_DROP * c:
            break
        out.append((m, c))
        newer = c
    out.reverse()
    return out


def ctx_turns(rows, fp=None):
    """Context size per main-thread API response since the last compaction, oldest first (<= ETA_KEEP ints).
    ⚠A «turn» is one assistant API response (one message.id), not one human prompt.
    With `fp`, samples older than the tail are taken from the series kept for that transcript (reset on a cut,
    a shrunk or replaced file)."""
    tail, cut = _tail_samples(rows)
    if not fp:
        return [c for _m, c in reversed(tail)]
    try:
        st = os.stat(fp)
        ino, size = st.st_ino, st.st_size
    except OSError:
        ino, size = None, 0
    with _SERIES_LOCK:
        prev = _SERIES.get(fp)
    same = bool(prev) and not cut and prev[0] == ino and size >= prev[1]
    if same and not tail:
        series = prev[2]                   # no response in this tail at all: keep what was seen
    else:
        older = _older_kept(prev[2], tail) if same and len(tail) < ETA_KEEP else []
        series = (older + list(reversed(tail)))[-ETA_KEEP:]
    with _SERIES_LOCK:
        _SERIES[fp] = (ino, size, series)
        _SERIES.move_to_end(fp)
        while len(_SERIES) > SERIES_CAP:
            _SERIES.popitem(last=False)
    return [c for _m, c in series]


def _acct_window(fp, sid):
    """(session compaction window or None, auto-compaction enabled or None) for the account that ran `sid`."""
    _lab, adir = claude_roots.acct_of(sid, fp)
    sp = os.path.join(adir, "settings.json") if adir else SETTINGS_FILE
    d = _json_at(sp)
    if d is None:
        return None, None
    win, on = settings_compact(d)
    if adir:
        return win, on                     # no change log for an extra account: its current setting
    try:
        st = os.stat(fp)
    except OSError:
        return None, on
    born = getattr(st, "st_birthtime", 0) or st.st_ctime
    cw = _json_at(CW_FILE)
    return sess_win(born, cw if isinstance(cw, dict) else {}), on


def row_eta(fp, p, win, dead):
    """{} or {"cmpEta": {n, pt, grow, k}} — n = ceil((pt - ctx) / median per-turn growth), pt = min(model, session window)."""
    if dead or not win:
        return {}
    ctxs = p.get("ctxs") or []
    diffs = [b - a for a, b in zip(ctxs, ctxs[1:])][-(ETA_KEEP - 1):]
    if len(diffs) < ETA_MIN:
        return {}
    grow = statistics.median(diffs)
    if grow <= 0:
        return {}
    sid = p.get("sid") or os.path.basename(fp)[:-6]
    cw, on = _acct_window(fp, sid)
    if not on or not cw:
        return {}
    pt = min(int(win), int(cw))
    ctx = int(p.get("ctx") or 0)
    if pt <= ctx:
        return {}
    return {"cmpEta": {"n": int(math.ceil((pt - ctx) / grow)), "pt": pt, "grow": int(round(grow)), "k": len(diffs)}}
