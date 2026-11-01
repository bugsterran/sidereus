"""Per-project to-do list (feature `todo`): `<git root>/.claude/todo.md` written by sessions (SessionStart brief) and by
the person (POST /api/todo/add · /api/todo/set), plus a Sidereus-owned ledger of add / start / done times.

Line form: `- [ ] text` open · `- [~] text` in progress · `- [x] text` done (anything else is ignored).
⚠Item text is a one-line request label (like the Agent tool description) — the file is never echoed beyond parsed items.
⚠In progress comes only from `[~]` in the file; it is never inferred from session state.
"""
import hashlib
import json
import os
import re
import secrets
import shutil
import threading
import time

from sidereus import config
from sidereus.bus import _atomic_write
from sidereus.gitinfo import _git_root
from sidereus.ident import _real_home
from sidereus.warn import warn_once
from sidereus.work import _allowed_cwds

TODO_MAX = 64 * 1024        # bytes — a bigger file is not a to-do list; no data rather than a slow poll
TEXT_MAX = 200              # chars per item added from the viewer
LEDGER_MAX = 1000           # items kept per repo ledger
LEDGER_DONE_S = 90 * 86400  # done items older than this leave the ledger
DAY_ITEMS_MAX = 50          # texts per day and kind in GET /api/todo `days`
DAYS_MAX = 60
MEMO_MAX = 256
TRASH_DIR = None            # None = DATA_DIR/tool-trash; ⚠tests set a tmp dir
LEDGER_DIR = None           # None = DATA_DIR/todo; ⚠tests set a tmp dir
LINE_RE = re.compile(r"^\s*- \[( |~|x|X)\] (.+)$")
_LOCK = threading.Lock()    # serialises todo.md writes and ledger read-modify-write
_MEMO = {}                  # repo -> ((mtime_ns, size, ino), counts) for the state piece
_now = time.time


def _trash_dir():
    return TRASH_DIR or os.path.join(config.DATA_DIR, "tool-trash")


def _ledger_path(repo):
    # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1 -- file-name key, not security
    k = hashlib.sha1(repo.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
    return os.path.join(LEDGER_DIR or os.path.join(config.DATA_DIR, "todo"), k + ".json")


def _h(line):
    # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1 -- stale-line check, not security
    return hashlib.sha1(line, usedforsecurity=False).hexdigest()


def repo_of(cwd):
    """Git root of a session cwd, or "" — ⚠never the home dir or `/` (a dotfiles repo would aim at ~/.claude)."""
    if not (isinstance(cwd, str) and os.path.isabs(cwd)):
        return ""
    r = _git_root(cwd)
    if not r or os.path.dirname(r) == r or os.path.normpath(r) == os.path.normpath(_real_home()):
        return ""
    return r


def todo_path(repo):
    return os.path.join(repo, ".claude", "todo.md")


def _linked(repo):
    """True when `.claude` or todo.md is a symlink (lstat) — ⚠a link could aim a write anywhere."""
    for p in (os.path.join(repo, ".claude"), todo_path(repo)):
        try:
            if os.path.islink(p):
                return True
        except OSError:
            return True
    return False


def _read(repo):
    """(raw bytes, stat key) of todo.md, or (None, None): missing · unreadable · symlinked · not a file · over TODO_MAX."""
    p = todo_path(repo)
    if _linked(repo):
        return None, None
    try:
        st = os.lstat(p)
        if not os.path.isfile(p) or st.st_size > TODO_MAX:
            return None, None
        with open(p, "rb") as f:
            raw = f.read(TODO_MAX + 1)
    except OSError:
        return None, None
    if len(raw) > TODO_MAX:
        return None, None
    return raw, (st.st_mtime_ns, st.st_size, st.st_ino)


def _lines(raw):
    """Lines with their ending kept (split on \\n only, so a CRLF line keeps its \\r\\n)."""
    return raw.splitlines(True) if raw else []


def _body(ln):
    return ln[:-2] if ln.endswith(b"\r\n") else ln[:-1] if ln.endswith(b"\n") else ln


def parse(raw):
    """[{i, s, t, h}] — i = line index, s = " " | "~" | "x", t = text, h = sha1 of the raw line without its ending."""
    out = []
    for i, ln in enumerate(_lines(raw)):
        b = _body(ln)
        m = LINE_RE.match(b.decode("utf-8", "replace"))
        if m and m.group(2).strip():
            out.append({"i": i, "s": m.group(1).lower(), "t": m.group(2).strip(), "h": _h(b)})
    return out


def _counts(items):
    c = {"o": 0, "w": 0, "d": 0}
    for it in items:
        c[{" ": "o", "~": "w", "x": "d"}[it["s"]]] += 1
    return c


def _key(t):
    return " ".join(t.split()).casefold()


# ── ledger (DATA_DIR/todo/<sha1(repo)[:16]>.json) ──

def _ledger_load(repo):
    try:
        with open(_ledger_path(repo), encoding="utf-8") as f:
            d = json.load(f)
        items = d.get("items") if isinstance(d, dict) else None
        return {k: _clean_entry(v) for k, v in items.items() if isinstance(v, dict)} if isinstance(items, dict) else {}
    except (OSError, ValueError):
        return {}


def _clean_entry(v):
    """⚠Drop a non-numeric add/start/done (hand-edited ledger): float() on it would raise inside the /api/state poll."""
    return {k: x for k, x in v.items()
            if k not in ("add", "start", "done") or (isinstance(x, (int, float)) and not isinstance(x, bool) and x == x)}


def _prune(items, now):
    for k in [k for k, v in items.items() if v.get("done") and now - float(v["done"]) > LEDGER_DONE_S]:
        items.pop(k)
    if len(items) > LEDGER_MAX:
        last = lambda v: max(float(v.get(x) or 0) for x in ("add", "start", "done"))
        for k in sorted(items, key=lambda k: last(items[k]))[:len(items) - LEDGER_MAX]:
            items.pop(k)


def _observe_locked(repo, parsed, at=None):
    """Fold the file's items into the ledger. Caller holds _LOCK. Writes only on change.
    Key = normalized text + occurrence number (n-th line with that text), so a repeated request is its own entry.
    add = first seen in any state · start = first seen [~] (absent when never seen [~]) · done = first seen [x],
    dropped only when that same occurrence is seen open again.
    ⚠Times = todo.md mtime (`at`) when the viewer first saw the change: edits made while nothing polled still get
    their file time, and several edits between two reads collapse to one time."""
    now, items = _now(), _ledger_load(repo)
    at = float(at) if isinstance(at, (int, float)) and at > 0 else now
    before = json.dumps(items, sort_keys=True)
    occ = {}
    for it in parsed:
        base = _key(it["t"])
        n = occ[base] = occ.get(base, -1) + 1
        v = items.setdefault("%s#%d" % (base, n), {"t": it["t"][:TEXT_MAX * 2]})
        if not v.get("add"):
            v["add"] = at
        if it["s"] == "~" and not v.get("start"):
            v["start"] = at
        if it["s"] == "x":
            if not v.get("done"):
                v["done"] = at
        elif v.get("done"):
            v.pop("done")   # this occurrence was reopened
    _prune(items, now)
    if json.dumps(items, sort_keys=True) == before:
        return
    data = json.dumps({"v": 1, "repo": repo, "items": items}, ensure_ascii=False, sort_keys=True).encode("utf-8")
    try:
        _atomic_write(_ledger_path(repo), data, mkdir=True)
    except OSError as e:   # ⚠the ledger is a side record; a failed write must not fail the poll or the person's write
        warn_once("todo-ledger", "To-do ledger write failed ({err})", vars={"err": type(e).__name__}, soft=True)


def observe(repo, parsed, at=None):
    with _LOCK:
        _observe_locked(repo, parsed, at)


def _day(ts):
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def days(repo):
    """[{day, added, started, done}] newest day first; each list holds item texts (≤ DAY_ITEMS_MAX)."""
    by = {}
    for v in _ledger_load(repo).values():
        for f, name in (("add", "added"), ("start", "started"), ("done", "done")):
            ts = v.get(f)
            if isinstance(ts, (int, float)) and ts > 0:
                by.setdefault(_day(ts), {"added": [], "started": [], "done": []})[name].append((ts, str(v.get("t") or "")))
    out = []
    for d in sorted(by, reverse=True)[:DAYS_MAX]:
        row = {"day": d}
        for name, xs in by[d].items():
            row[name] = [t for _ts, t in sorted(xs, reverse=True)[:DAY_ITEMS_MAX]]
        out.append(row)
    return out


# ── state piece and GET ──

def state_counts(rows):
    """/api/state `todo` = {cwd: {o, w, d}} for session rows whose repo has a non-empty list; counts only.
    Re-parsed (and the ledger folded) only when todo.md's (mtime_ns, size, ino) moved — direct session edits land here."""
    out, seen = {}, {}
    for r in rows or []:
        cwd = r.get("cwd") if isinstance(r, dict) else None
        repo = repo_of(cwd)
        if not repo:
            continue
        if repo not in seen:   # several sessions of one repo: one lstat per poll
            seen[repo] = _counts_cached(repo)
        c = seen[repo]
        if c and (c["o"] or c["w"] or c["d"]):
            out[cwd] = c
    return out


def _counts_cached(repo):
    try:
        st = os.lstat(todo_path(repo))
        key = (st.st_mtime_ns, st.st_size, st.st_ino)
    except OSError:
        _MEMO.pop(repo, None)
        return None
    hit = _MEMO.get(repo)
    if hit and hit[0] == key:
        return hit[1]
    raw, key = _read(repo)
    if raw is None:
        _MEMO.pop(repo, None)
        return None
    parsed = parse(raw)
    observe(repo, parsed, key[0] / 1e9)
    if len(_MEMO) >= MEMO_MAX:
        _MEMO.clear()
    _MEMO[repo] = (key, _counts(parsed))
    return _MEMO[repo][1]


def _allowed_repo(cwd):
    """(repo, None) for a cwd of an on-screen session, else (None, (code, body))."""
    if not (isinstance(cwd, str) and cwd in (_allowed_cwds() or {})):
        return None, (403, {"ok": False, "err": "only sessions shown on screen"})
    repo = repo_of(cwd)
    if not repo or not os.path.isdir(repo) or os.path.islink(repo):
        return None, (404, {"ok": False, "err": "no git repo"})
    return repo, None


def todo_get(cwd):
    """GET /api/todo?cwd= -> (code, {ok, repo, items, days}); a missing/refused file = items []."""
    repo, err = _allowed_repo(cwd)
    if err:
        return err
    raw, k = _read(repo)
    items = parse(raw) if raw is not None else []
    if raw is not None:
        observe(repo, items, k[0] / 1e9)
    return 200, {"ok": True, "repo": repo, "items": items, "days": days(repo), "max": TEXT_MAX}   # max = add limit for the UI


# ── writes (POST) ──

def _clean_text(t):
    if not isinstance(t, str):
        return None
    t = t.strip()
    if not t or len(t) > TEXT_MAX or any(ord(c) < 32 or 0x7f <= ord(c) < 0xa0 or c in "  " for c in t):
        return None
    return t


def _backup(p):
    base = os.path.join(_trash_dir(), time.strftime("%Y%m%d-%H%M%S", time.localtime(_now())))
    d, n = base, 1
    while os.path.exists(d):
        n += 1
        d = "%s-%d" % (base, n)
    os.makedirs(d)
    dst = os.path.join(d, "todo-" + os.path.basename(os.path.dirname(os.path.dirname(p))) + ".md")
    shutil.copy2(p, dst)
    return dst


def _write_locked(repo, raw, new_raw):
    """Backup, tmp + fsync, re-compare, os.replace -> (200, None) or (code, body). Caller holds _LOCK.
    ⚠raw None = create: `.claude` made only when missing; a symlink appearing meanwhile is refused."""
    p = todo_path(repo)
    cl = os.path.dirname(p)
    try:
        if raw is not None:
            _backup(p)
        elif not os.path.lexists(cl):
            os.mkdir(cl)
        if _linked(repo) or not os.path.isdir(cl):
            return 400, {"ok": False, "err": "symlinked .claude or todo.md — edit by hand"}
        # ⚠random name + O_EXCL|O_NOFOLLOW: a pre-planted file or symlink at a guessable tmp path is never written through
        tmp = "%s.sidereus-tmp.%d.%s" % (p, os.getpid(), secrets.token_hex(6))
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0), 0o644)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(new_raw)
                f.flush()
                os.fsync(f.fileno())
            now, _k = _read(repo)
            if now != raw or (raw is None and os.path.lexists(p)):   # ⚠a session wrote meanwhile — never clobber it
                return 409, {"ok": False, "err": "file changed — reload"}
            if raw is not None:
                shutil.copymode(p, tmp)
            else:
                os.chmod(tmp, 0o644)
            if _linked(repo):   # ⚠re-check right before the rename: `.claude` swapped for a link meanwhile
                return 400, {"ok": False, "err": "symlinked .claude or todo.md — edit by hand"}
            os.replace(tmp, p)
        finally:
            if os.path.lexists(tmp):
                os.remove(tmp)
    except OSError as e:
        return 500, {"ok": False, "err": "write failed (%s)" % type(e).__name__}
    try:
        at = os.lstat(p).st_mtime
    except OSError:
        at = None
    _observe_locked(repo, parse(new_raw), at)
    _MEMO.pop(repo, None)
    return 200, None


def _write_target(req):
    """(repo, raw, None) or (None, None, (code, body)): allowed cwd, readable or missing file, no symlinks."""
    repo, err = _allowed_repo(req.get("cwd") if isinstance(req, dict) else None)
    if err:
        return None, None, err
    if _linked(repo):
        return None, None, (400, {"ok": False, "err": "symlinked .claude or todo.md — edit by hand"})
    raw, _k = _read(repo)
    if raw is None and os.path.lexists(todo_path(repo)):
        return None, None, (400, {"ok": False, "err": "todo.md unreadable or over 64 KB"})
    return repo, raw, None


def add(req):
    """POST /api/todo/add {cwd, text} -> append `- [ ] text` with the file's own newline (others byte-identical)."""
    text = _clean_text(req.get("text") if isinstance(req, dict) else None)
    if text is None:
        return 400, {"ok": False, "err": "one line, 1-%d characters" % TEXT_MAX}
    with _LOCK:
        repo, raw, err = _write_target(req)
        if err:
            return err
        old = raw or b""
        nl = b"\r\n" if b"\r\n" in old.split(b"\n", 1)[0] + b"\n" else b"\n"
        new = old + (nl if old and not old.endswith(b"\n") else b"") + b"- [ ] " + text.encode("utf-8") + nl
        if len(new) > TODO_MAX:
            return 400, {"ok": False, "err": "todo.md would exceed 64 KB"}
        code, body = _write_locked(repo, raw, new)
        if code != 200:
            return code, body
        return 200, {"ok": True, "items": parse(new)}


def set_state(req):
    """POST /api/todo/set {cwd, i, h, s: " "|"x"} -> change only the bracket byte of line i (409 when h is stale)."""
    if not isinstance(req, dict) or req.get("s") not in (" ", "x") or not isinstance(req.get("i"), int) \
            or isinstance(req.get("i"), bool) or not isinstance(req.get("h"), str):
        return 400, {"ok": False, "err": "need i, h and s ' ' or 'x'"}
    with _LOCK:
        repo, raw, err = _write_target(req)
        if err:
            return err
        lines = _lines(raw)
        i = req["i"]
        if raw is None or not 0 <= i < len(lines) or _h(_body(lines[i])) != req["h"]:
            return 409, {"ok": False, "err": "file changed — reload"}
        ln = lines[i]
        if not LINE_RE.match(_body(ln).decode("utf-8", "replace")):
            return 409, {"ok": False, "err": "file changed — reload"}
        at = ln.index(b"- [") + 3
        lines[i] = ln[:at] + req["s"].encode("ascii") + ln[at + 1:]
        new = b"".join(lines)
        if new == raw:
            return 200, {"ok": True, "items": parse(raw)}
        code, body = _write_locked(repo, raw, new)
        if code != 200:
            return code, body
        return 200, {"ok": True, "items": parse(new)}
