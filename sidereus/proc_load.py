"""`srvLoad.top` — which Claude session's process tree loads the machine most (metadata only, no subprocess).

★Load 105-135 on 12 CPUs (2026-11-04): ~35 node test processes from one session; finding the culprit needed a
  manual ppid trace. ⇒ Reuse the poll's one `ps` (pcpu/rss columns, ★0.02 s for 621 procs) and sum each process
  into its outermost claude ancestor (★parse 0.5 ms). ⚠Output is the repo name, totals and executable basenames —
  never arguments (they can hold tokens and prompt text).
"""
import os
import re
import time

from sidereus import live_probe
from sidereus.ident import _proj_root, is_claude_argv
from sidereus.memo import on_request_path, serve_last
from sidereus.warn import warn_once

PL_TOP_TTL = 2.0       # s — recompute at most this often (the snapshot itself turns over every PS_SNAP_TTL)
PL_EXE_MAX = 5
PL_EXE_LEN = 32
PL_REPO_LEN = 80
_EXE_BAD = re.compile(r"[^A-Za-z0-9._+-]")
_top_cache = [0.0, None, 0.0]   # (snapshot time, top dict or None, computed at)
_now = time.time                # ⚠tests patch this


def _num(s, cast):
    try:
        v = cast(str(s).replace(",", "."))   # ⚠pcpu uses the locale's decimal comma on some macOS setups
    except (TypeError, ValueError):
        return None
    return v if v == v and v >= 0 else None   # NaN / negative = unparseable


def _exe(cmd):
    """Basename of the first command token only, filtered — never an argument."""
    tok = (cmd or "").split(None, 1)
    if not tok:
        return ""
    return _EXE_BAD.sub("", os.path.basename(tok[0].replace("\\", "/")))[:PL_EXE_LEN]


def _owners(rows):
    """pid -> outermost claude ancestor pid (itself included), "" = reaches pid 1 with none, None = other roots."""
    par = {pid: ppid for pid, ppid, _c in rows}
    claude = {pid for pid, _p, c in rows if is_claude_argv(c)}
    memo = {}
    for pid in par:
        chain, p = [], pid
        while p not in memo and p in par and p not in chain:
            chain.append(p)
            if p == "1":
                break
            p = par[p]
        top = memo.get(p) if p in memo else ("" if p == "1" else None)
        for q in reversed(chain):
            if q == "1":
                top = ""
            elif q in claude and not top:
                top = q            # walking down: the first claude seen is the outermost
            memo[q] = top
    return memo


def _calc(now):
    at, res = live_probe._ps_res[0], live_probe._ps_res[1]
    snap_at, rows = live_probe._ps_snap_cache[0], live_probe._ps_snap_cache[1]
    # ⚠`_ps_snap` writes rows before res: a differing stamp means rows and res are from two snapshots
    if not rows or not res or snap_at != at or now - at >= live_probe.LIVE_STALE_S:
        return at, None      # unknown, never «idle»
    own, cwds = _owners(rows), live_probe._live_pid_cwd[1]
    sess, rest = {}, [0.0, 0, 0]
    for pid, _pp, cmd in rows:
        o = own.get(pid)
        if o is None:
            continue
        pc, rs = res.get(pid, (None, None))
        cpu, rss = _num(pc, float) or 0.0, _num(rs, int) or 0
        if o == "":
            rest[0] += cpu
            rest[1] += rss
            rest[2] += 1
            continue
        s = sess.setdefault(o, [0.0, 0, 0, {}])
        s[0] += cpu
        s[1] += rss
        s[2] += 1
        e = _exe(cmd)
        if e:
            s[3][e] = s[3].get(e, 0) + 1
    best = None
    for o, s in sess.items():
        cwd = cwds.get(o) or ""
        if not cwd:
            continue          # unknown cwd = no repo to name; skipped
        if best is None or (s[0], s[1]) > (best[1][0], best[1][1]):
            best = (cwd, s)
    if best is None:
        return at, None
    cwd, s = best
    exe = sorted(s[3].items(), key=lambda kv: (-kv[1], kv[0]))[:PL_EXE_MAX]
    return at, {"repo": os.path.basename(_proj_root(cwd).rstrip("/"))[:PL_REPO_LEN],
                "cpu": round(s[0], 1), "rssMb": int(round(s[1] / 1024.0)), "n": s[2],
                "exe": [[k, n] for k, n in exe],
                "unowned": {"cpu": round(rest[0], 1), "rssMb": int(round(rest[1] / 1024.0))} if rest[2] else None}


def top():
    """srvLoad.top or None. ⚠On the request path only the last value is served (no `_proj_root` stat there)."""
    if on_request_path():
        return serve_last("procload", top, lambda: (_top_cache[0], _top_cache[1]),
                          live_probe.LIVE_STALE_S, _now, warn_once)
    now = _now()
    if _top_cache[0] == live_probe._ps_res[0] and now - _top_cache[2] < PL_TOP_TTL:
        return _top_cache[1]
    at, val = _calc(now)
    _top_cache[0], _top_cache[1], _top_cache[2] = at, val, now
    return val
