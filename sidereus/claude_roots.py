"""Claude config roots (accounts): the primary root plus extra ones whose transcripts are also shown.

Primary = `config.claude_home()`. Extras: `~/.claude` when `$CLAUDE_CONFIG_DIR` points elsewhere,
`~/.claude-*` dirs that have `projects/`, and prefs `claude_roots` `[{dir, label}]`.
Label priority: prefs label > Orbit plugin registry (`~/.claude-accounts` `account <name> <dir>`) > folder basename.
Read-only: nothing here writes. Callers read the roots at call time (never copy them at import).
`accounts()` = roots + shared-history profiles (own dir, projects/ symlinked to a root already scanned);
`acct_of(sid, fp)` reads the SessionStart hook's per-session record (`ACCT_DIR/<sid>`, one line = config dir).
"""
import os
import re
import stat
import threading
import time

from sidereus.config import DATA_DIR, claude_home
from sidereus.memo import BoundedMemo
from sidereus.prefs import dir_too_wide, effective

SCAN_HOME = os.path.expanduser("~")   # ⚠tests patch this to a tmp dir (never the live home)
ROOTS_TTL_S = 30
LABEL_MAX = 24
_LABEL_BAD = re.compile(r"[^A-Za-z0-9._-]+")
_LOCK = threading.Lock()
_CACHE = {"t": 0.0, "v": None}
_REG = {"key": None, "v": {}}   # registry memo keyed on (path, mtime_ns, size)
ACCT_DIR = os.path.join(DATA_DIR, "acct")   # written by hooks/invite_notice.py on SessionStart
ACCT_REC_MAX = 4096
_SID_OK = re.compile(r"^[0-9a-zA-Z-]{8,64}$")
_ACCT_MEMO = BoundedMemo(2000)   # sid -> (mtime_ns, realpath of the recorded config dir)


def _label(raw, d):
    s = raw if isinstance(raw, str) and raw.strip() else os.path.basename(os.path.normpath(d))
    if not (isinstance(raw, str) and raw.strip()):
        s = s[len(".claude-"):] if s.startswith(".claude-") else s.lstrip(".")
    s = _LABEL_BAD.sub("-", s.strip()).strip("-")[:LABEL_MAX]
    return s or "acct"


def _registry_labels():
    """{realpath(dir): name} from the Orbit plugin registry; {} when absent or unreadable."""
    path = os.path.join(SCAN_HOME, ".claude-accounts")
    try:
        st = os.stat(path)
        key = (path, st.st_mtime_ns, st.st_size)
    except (OSError, ValueError):
        return {}
    if _REG["key"] == key:
        return _REG["v"]
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(None, 2)
                if len(parts) == 3 and parts[0] == "account":
                    d = parts[2].strip()
                    if d == "~" or d.startswith("~/"):
                        d = SCAN_HOME + d[1:]
                    out.setdefault(os.path.realpath(d), parts[1])   # first line wins, like the CLI
    except (OSError, ValueError):
        out = {}
    _REG["key"], _REG["v"] = key, out
    return out


def _real_projects(d):
    try:
        return os.path.realpath(os.path.join(d, "projects"))
    except (OSError, ValueError):
        return ""


def _candidates():
    """(dir, label|None, from_registry) extras in priority order: ~/.claude, ~/.claude-*, registry, prefs."""
    out = []
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        out.append((os.path.join(SCAN_HOME, ".claude"), None, False))
    try:
        names = sorted(os.listdir(SCAN_HOME))
    except OSError:
        names = []
    out += [(os.path.join(SCAN_HOME, n), None, False) for n in names if n.startswith(".claude-")]
    out += [(d, None, True) for d in _registry_labels()]   # Orbit `add --dir` folders outside ~/.claude-*
    for ent in effective("claude_roots") or []:
        out.append((os.path.expanduser(ent["dir"]), ent.get("label"), False))
    return out


def _uniq(base, labels):
    name, i = base, 2
    while name in labels:   # labels identify a root on rows, so they stay unique
        suf = "-%d" % i
        name, i = base[:LABEL_MAX - len(suf)] + suf, i + 1
    labels.add(name)
    return name


def _build():
    """(roots, shared) — shared = profiles whose projects/ resolves to a root already listed (accounts only)."""
    prim = claude_home()
    rows = [{"dir": prim, "label": _label(None, prim), "primary": True}]
    seen = {_real_projects(prim)}
    labels = {rows[0]["label"]}
    cands = _candidates()
    # A prefs label wins for its dir even when the ~/.claude-* scan reached that dir first.
    pref_lab = {}
    for d, lab, _r in cands:
        if isinstance(lab, str) and lab.strip():
            pref_lab.setdefault(_real_projects(d), lab)
    reg = _registry_labels()
    rprim = os.path.realpath(prim)
    shared, sdirs = [], {rprim}
    for d, lab, from_reg in cands:
        rp = _real_projects(d)
        rd = os.path.realpath(d)
        # A registry-only folder counts once signed in (.claude.json); projects/ alone is not enough there.
        ok = os.path.isfile(os.path.join(d, ".claude.json")) if from_reg else os.path.isdir(rp)
        # ⚠A projects dir (or registry folder) at /, home or above would widen every caller's path guard.
        if rp and rp in seen and rd not in sdirs and not dir_too_wide(rd, SCAN_HOME) and (
                os.path.isfile(os.path.join(d, ".claude.json")) or os.path.isdir(os.path.join(d, "projects"))):
            sdirs.add(rd)   # ⚠own account, shared history: out of scan roots (double rows) but kept as an account
            shared.append((d, lab if isinstance(lab, str) and lab.strip() else reg.get(rd)))
            continue
        if (not rp or rp in seen or rd == rprim or not ok
                or dir_too_wide(rp, SCAN_HOME) or (from_reg and dir_too_wide(rd, SCAN_HOME))):
            continue
        seen.add(rp)
        sdirs.add(rd)
        name = _uniq(_label(pref_lab.get(rp) or reg.get(os.path.realpath(d)), d), labels)
        rows.append({"dir": d, "label": name, "primary": False})
    # Registry names the primary too (accounts only; roots() keeps its folder label).
    acc = [dict(r) for r in rows]
    alab = {r["label"] for r in rows[1:]}
    acc[0]["label"] = _uniq(_label(reg.get(rprim), prim), alab) if reg.get(rprim) else rows[0]["label"]
    alab.add(acc[0]["label"])
    for d, lab in shared:
        acc.append({"dir": d, "label": _uniq(_label(lab, d), alab), "primary": False})
    by_real = {}
    for a in acc:
        by_real.setdefault(os.path.realpath(a["dir"]), a)   # acct_of lookup without a realpath per row
    return rows, acc, by_real


def roots():
    """[{dir, label, primary}] — primary first; memoized for ROOTS_TTL_S seconds."""
    return [dict(r) for r in _cached()[0]]


def accounts():
    """[{dir, label, primary}] — roots() plus shared-history profiles; labels unique, registry names the primary."""
    return [dict(r) for r in _cached()[1]]


def _cached():
    now = time.monotonic()
    with _LOCK:
        if _CACHE["v"] is not None and now - _CACHE["t"] < ROOTS_TTL_S:
            return _CACHE["v"]
    v = _build()
    with _LOCK:
        _CACHE["t"], _CACHE["v"] = now, v
    return v


def reset():
    """Drop the memo (tests, or after SCAN_HOME / prefs change)."""
    with _LOCK:
        _CACHE["t"], _CACHE["v"] = 0.0, None
        _REG["key"], _REG["v"] = None, {}
    _ACCT_MEMO.clear()


def projects_dirs(primary):
    """[primary] + each extra root's projects dir. `primary` is the caller's own (patchable) CLAUDE_PROJECTS."""
    out, seen = [primary], {os.path.realpath(primary)}
    for r in roots():
        if r["primary"]:
            continue
        p = os.path.join(r["dir"], "projects")
        rp = os.path.realpath(p)
        if rp not in seen and os.path.isdir(p):   # a signed-in registry root may have no projects/ yet
            seen.add(rp)
            out.append(p)
    return out


def root_of(path):
    """(label, dir) of the extra root holding `path`; ("", "") for the primary root or an unknown path."""
    try:
        rp = os.path.realpath(path)
    except (OSError, ValueError, TypeError):
        return "", ""
    best = None
    for r in roots():
        base = os.path.realpath(r["dir"])
        if rp == base or rp.startswith(base.rstrip(os.sep) + os.sep):
            if best is None or len(base) > best[0]:
                best = (len(base), r)
    if best is None or best[1]["primary"]:
        return "", ""
    return best[1]["label"], best[1]["dir"]


def _acct_rec(sid):
    """realpath of the config dir recorded for `sid`; "" when absent, unreadable or oversized."""
    if not isinstance(sid, str) or not _SID_OK.match(sid):
        return ""
    p = os.path.join(ACCT_DIR, sid)
    try:
        st = os.stat(p)
    except (OSError, ValueError):
        return ""
    if not stat.S_ISREG(st.st_mode):   # ⚠a FIFO here would block the poll on open()
        return ""
    hit = _ACCT_MEMO.get(sid, None, stamp=st.st_mtime_ns)
    if hit is not None:
        return hit
    v = ""
    try:
        if st.st_size <= ACCT_REC_MAX:
            with open(p, encoding="utf-8") as f:
                line = f.read(ACCT_REC_MAX).strip().splitlines()
            if line and os.path.isabs(line[0].strip()):
                v = os.path.realpath(line[0].strip())
    except (OSError, ValueError):
        v = ""
    return _ACCT_MEMO.put(sid, v, stamp=st.st_mtime_ns)


def acct_of(sid, fp):
    """(label, dir) of the account that ran `sid`; ("", "") for the primary. No record or no match -> root_of(fp)."""
    rd = _acct_rec(sid)
    a = _cached()[2].get(rd) if rd else None
    if a:
        return ("", "") if a["primary"] else (a["label"], a["dir"])
    return root_of(fp)
