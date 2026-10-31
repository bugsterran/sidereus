"""Copilot CLI presence from its own record folder (no hooks needed): `<root>/session-state/<uuid>/workspace.yaml`.

Read by sidereus/ext_presence.py only — ⚠not an adapter (`ext_store.PLAT_MODS` stays Gemini + Codex).
⚠Metadata only: workspace.yaml is parsed line by line through `_KEYS`; `name` / `summary*` lines are dropped
before anything is kept, and `events.jsonl` is only stat'ed, never opened.
"""
import os
import re
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
