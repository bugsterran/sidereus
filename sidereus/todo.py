"""Per-project to-do list (feature `todo`): a Sidereus-owned store DATA_DIR/todo/<sha1(git root)[:16]>.json (v2)
keyed by project and session id, written by sessions through the sidereus MCP tool (POST /api/todo/agent) and by the
person (POST /api/todo/add · /api/todo/set). Item state: " " open · "~" in progress · "x" done, with add / start / done times.
⚠Item text is a one-line request label (like the Agent tool description), never a message body.
⚠Nothing is written in the repo: an existing `<git root>/.claude/todo.md` is imported once, read-only, then never read again.
⚠In progress comes only from a session's `start`; it is never inferred from session state.
"""
import hashlib
import json
import os
import re
import threading
import time

from sidereus import config
from sidereus.bus import _atomic_write
from sidereus.gitinfo import _git_root
from sidereus.ident import _real_home
from sidereus.warn import warn_once
from sidereus.work import _allowed_cwds

TODO_MAX = 64 * 1024        # bytes — a bigger file is not a to-do list; no data rather than a slow poll
TEXT_MAX = 200              # chars per item label
LEDGER_MAX = 1000           # items kept per repo store
LEDGER_DONE_S = 90 * 86400  # done items older than this leave the store
DAY_ITEMS_MAX = 50          # texts per day and kind in GET /api/todo `days`
DAYS_MAX = 60
MEMO_MAX = 256
LEDGER_DIR = None           # None = DATA_DIR/todo; ⚠tests set a tmp dir
LINE_RE = re.compile(r"^\s*- \[( |~|x|X)\] (.+)$")
_LOCK = threading.Lock()    # serialises import and store read-modify-write
_MEMO = {}                  # repo -> ((mtime_ns, size, ino) of the store file, counts) for the state piece
_NOIMPORT = set()           # repos with no store and nothing to import (todo.md not re-read in this process)
_now = time.time


def _ledger_path(repo):
    # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1 -- file-name key, not security
    k = hashlib.sha1(repo.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
    return os.path.join(LEDGER_DIR or os.path.join(config.DATA_DIR, "todo"), k + ".json")


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
    """True when `.claude` or todo.md is a symlink (lstat) — ⚠import read guard: a link could aim the read anywhere."""
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
    """[{i, s, t}] of a legacy todo.md (import only) — i = line index, s = " " | "~" | "x", t = text."""
    out = []
    for i, ln in enumerate(_lines(raw)):
        m = LINE_RE.match(_body(ln).decode("utf-8", "replace"))
        if m and m.group(2).strip():
            out.append({"i": i, "s": m.group(1).lower(), "t": m.group(2).strip()})
    return out


def _counts(items):
    c = {"o": 0, "w": 0, "d": 0}
    for it in items:
        c[{" ": "o", "~": "w", "x": "d"}[it["s"]]] += 1
    return c


def _key(t):
    return " ".join(t.split()).casefold()


# ── store (DATA_DIR/todo/<sha1(repo)[:16]>.json, v2) ──

def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x == x and x > 0


def _label(t):
    """One-line label of at most TEXT_MAX chars (imported file text may hold tabs or be long)."""
    t = "".join(" " if ord(c) < 32 or 0x7f <= ord(c) < 0xa0 or c in "  " else c for c in str(t or ""))
    return " ".join(t.split())[:TEXT_MAX]


def _clean_item(v):
    """⚠Hand-edited store: a non-numeric time or a bad state would raise inside the /api/state poll — drop or skip it."""
    if not isinstance(v, dict) or not isinstance(v.get("id"), int) or isinstance(v.get("id"), bool) \
            or v.get("s") not in (" ", "~", "x") or not isinstance(v.get("t"), str) or not v["t"].strip():
        return None
    out = {"id": v["id"], "s": v["s"], "t": _label(v["t"]), "sid": v.get("sid") if isinstance(v.get("sid"), str) else ""}
    for k in ("add", "start", "done"):
        if _num(v.get(k)):
            out[k] = float(v[k])
    return out


def _read_store(repo):
    """Parsed JSON of the store file, or None (missing · unreadable · not JSON)."""
    try:
        with open(_ledger_path(repo), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _v2(d):
    items = [x for x in map(_clean_item, d.get("items") or [] if isinstance(d.get("items"), list) else []) if x]
    seq = d.get("seq") if isinstance(d.get("seq"), int) and not isinstance(d.get("seq"), bool) else 0
    return {"v": 2, "repo": d.get("repo") or "", "imported": d.get("imported") or 0,
            "seq": max([seq] + [x["id"] for x in items]), "items": items}


def _import_locked(repo, v1):
    """Store built once from `<repo>/.claude/todo.md` (read-only, never written or deleted) + the v1 ledger.
    Times come from the matching v1 key (`text#occ`), else the file mtime; v1 entries no longer in the file are kept
    only when done (they still belong on «By day»). Returns (store, has_items)."""
    raw, st = _read(repo)
    led = v1.get("items") if isinstance(v1, dict) and v1.get("v") != 2 and isinstance(v1.get("items"), dict) else {}
    at = st[0] / 1e9 if st else _now()
    items, used, occ = [], set(), {}
    for it in (parse(raw) if raw is not None else []):
        base = _key(it["t"])
        n = occ[base] = occ.get(base, -1) + 1
        k = "%s#%d" % (base, n)
        old = led.get(k) if isinstance(led.get(k), dict) else {}
        used.add(k)
        row = {"id": len(items) + 1, "s": it["s"], "t": _label(it["t"]), "sid": ""}
        row["add"] = float(old["add"]) if _num(old.get("add")) else at
        if _num(old.get("start")) or it["s"] == "~":
            row["start"] = float(old["start"]) if _num(old.get("start")) else at
        if it["s"] == "x":
            row["done"] = float(old["done"]) if _num(old.get("done")) else at
        items.append(row)
    for k, old in led.items():
        if k in used or not isinstance(old, dict) or not _num(old.get("done")) or not _label(old.get("t")):
            continue
        row = {"id": len(items) + 1, "s": "x", "t": _label(old.get("t")), "sid": "", "done": float(old["done"])}
        for f in ("add", "start"):
            if _num(old.get(f)):
                row[f] = float(old[f])
        items.append(row)
    store = {"v": 2, "repo": repo, "imported": _now(), "seq": len(items), "items": items}
    return store, bool(items)


def _save_locked(repo, store):
    data = json.dumps(store, ensure_ascii=False, sort_keys=True).encode("utf-8")
    _atomic_write(_ledger_path(repo), data, mkdir=True)
    _MEMO.pop(repo, None)


def _load_locked(repo):
    """The repo's v2 store. Caller holds _LOCK. ⚠todo.md is read only while no v2 file exists (import once);
    nothing to import = no file written, remembered in-process so the poll does not re-read the file."""
    d = _read_store(repo)
    if d is not None and d.get("v") == 2:
        return _v2(d)
    if repo in _NOIMPORT:
        return {"v": 2, "repo": repo, "imported": 0, "seq": 0, "items": []}
    store, has = _import_locked(repo, d)
    if not has:
        if len(_NOIMPORT) >= MEMO_MAX:
            _NOIMPORT.clear()
        _NOIMPORT.add(repo)
        return store
    try:
        _save_locked(repo, store)
    except OSError as e:   # ⚠shown from memory; the next read imports again (todo.md stays read-only either way)
        warn_once("todo-ledger", "To-do ledger write failed ({err})", vars={"err": type(e).__name__}, soft=True)
    return store


def _prune(items, now):
    """Done items older than LEDGER_DONE_S leave; over LEDGER_MAX the oldest done go first, then the oldest open."""
    items[:] = [v for v in items if not (v["s"] == "x" and v.get("done") and now - v["done"] > LEDGER_DONE_S)]
    if len(items) > LEDGER_MAX:
        last = lambda v: max(v.get(x) or 0 for x in ("add", "start", "done"))
        drop = set(id(v) for v in sorted(items, key=lambda v: (v["s"] != "x", last(v)))[:len(items) - LEDGER_MAX])
        items[:] = [v for v in items if id(v) not in drop]


def _h(it):
    # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1 -- stale-item check, not security
    return hashlib.sha1(("%d:%s:%s" % (it["id"], it["s"], it["t"])).encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def _ui(items):
    """[{i, s, t, h}] in store order — the shape web/js/40c-sessions-todo.js reads (i = item id)."""
    return [{"i": v["id"], "s": v["s"], "t": v["t"], "h": _h(v)} for v in items]


def _day(ts):
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def _days(items):
    by = {}
    for v in items:
        for f, name in (("add", "added"), ("start", "started"), ("done", "done")):
            ts = v.get(f)
            if _num(ts):
                by.setdefault(_day(ts), {"added": [], "started": [], "done": []})[name].append((ts, v["t"]))
    out = []
    for d in sorted(by, reverse=True)[:DAYS_MAX]:
        row = {"day": d}
        for name, xs in by[d].items():
            row[name] = [t for _ts, t in sorted(xs, reverse=True)[:DAY_ITEMS_MAX]]
        out.append(row)
    return out


def days(repo):
    """[{day, added, started, done}] newest day first; each list holds item texts (≤ DAY_ITEMS_MAX)."""
    with _LOCK:
        return _days(_load_locked(repo)["items"])


# ── state piece and GET ──

def state_counts(rows):
    """/api/state `todo` = {cwd: {o, w, d}} for session rows whose repo has a non-empty list; counts only.
    Recounted only when the store file's (mtime_ns, size, ino) moved."""
    out, seen = {}, {}
    for r in rows or []:
        cwd = r.get("cwd") if isinstance(r, dict) else None
        repo = repo_of(cwd)
        if not repo:
            continue
        if repo not in seen:   # several sessions of one repo: one stat per poll
            seen[repo] = _counts_cached(repo)
        c = seen[repo]
        if c and (c["o"] or c["w"] or c["d"]):
            out[cwd] = c
    return out


def _stat_key(repo):
    try:
        st = os.stat(_ledger_path(repo))
        return (st.st_mtime_ns, st.st_size, st.st_ino)
    except OSError:
        return None


def _counts_cached(repo):
    key = _stat_key(repo)
    if key is None and repo in _NOIMPORT:
        return None
    hit = _MEMO.get(repo)
    if key is not None and hit and hit[0] == key:
        return hit[1]
    with _LOCK:
        c = _counts(_load_locked(repo)["items"])
        key = _stat_key(repo)
        if key is not None:
            if len(_MEMO) >= MEMO_MAX:
                _MEMO.clear()
            _MEMO[repo] = (key, c)
    return c


def _allowed_repo(cwd):
    """(repo, None) for a cwd of an on-screen session, else (None, (code, body))."""
    if not (isinstance(cwd, str) and cwd in (_allowed_cwds() or {})):
        return None, (403, {"ok": False, "err": "only sessions shown on screen"})
    return _repo_dir(cwd)


def _repo_dir(cwd):
    repo = repo_of(cwd)
    if not repo or not os.path.isdir(repo) or os.path.islink(repo):
        return None, (404, {"ok": False, "err": "no git repo"})
    return repo, None


def todo_get(cwd):
    """GET /api/todo?cwd= -> (code, {ok, repo, items, days, max})."""
    repo, err = _allowed_repo(cwd)
    if err:
        return err
    with _LOCK:
        items = _load_locked(repo)["items"]
    return 200, {"ok": True, "repo": repo, "items": _ui(items), "days": _days(items), "max": TEXT_MAX}   # max = add limit for the UI


# ── writes (POST) — only the store under DATA_DIR; ⚠nothing is written in the repo ──

def _clean_text(t):
    if not isinstance(t, str):
        return None
    t = t.strip()
    if not t or len(t) > TEXT_MAX or any(ord(c) < 32 or 0x7f <= ord(c) < 0xa0 or c in "  " for c in t):
        return None
    return t


def _commit_locked(repo, store):
    """Prune + save -> None or (500, body)."""
    _prune(store["items"], _now())
    store["repo"] = repo
    try:
        _save_locked(repo, store)
    except OSError as e:
        return 500, {"ok": False, "err": "write failed (%s)" % type(e).__name__}
    _NOIMPORT.discard(repo)
    return None


def _new_item(store, text, sid):
    store["seq"] += 1
    it = {"id": store["seq"], "s": " ", "t": text, "sid": sid, "add": _now()}
    store["items"].append(it)
    return it


def add(req):
    """POST /api/todo/add {cwd, text} -> append one open item typed by the person."""
    text = _clean_text(req.get("text") if isinstance(req, dict) else None)
    if text is None:
        return 400, {"ok": False, "err": "one line, 1-%d characters" % TEXT_MAX}
    repo, err = _allowed_repo(req.get("cwd"))
    if err:
        return err
    with _LOCK:
        store = _load_locked(repo)
        _new_item(store, text, "")
        err = _commit_locked(repo, store)
        return err or (200, {"ok": True, "items": _ui(store["items"])})


def _mark(it, s, sid=None):
    """Move one item to state s with its times: start once, done set on x and dropped on reopen."""
    it["s"] = s
    if s == "~":
        it.setdefault("start", _now())
        if sid:
            it["sid"] = sid
    if s == "x":
        it["done"] = _now()
    else:
        it.pop("done", None)


def set_state(req):
    """POST /api/todo/set {cwd, i, h, s: " "|"x"} -> toggle item i (409 when h is stale)."""
    if not isinstance(req, dict) or req.get("s") not in (" ", "x") or not isinstance(req.get("i"), int) \
            or isinstance(req.get("i"), bool) or not isinstance(req.get("h"), str):
        return 400, {"ok": False, "err": "need i, h and s ' ' or 'x'"}
    repo, err = _allowed_repo(req.get("cwd"))
    if err:
        return err
    with _LOCK:
        store = _load_locked(repo)
        it = next((v for v in store["items"] if v["id"] == req["i"]), None)
        if it is None or _h(it) != req["h"]:
            return 409, {"ok": False, "err": "list changed — reload"}
        if it["s"] == req["s"]:
            return 200, {"ok": True, "items": _ui(store["items"])}
        _mark(it, req["s"])
        err = _commit_locked(repo, store)
        return err or (200, {"ok": True, "items": _ui(store["items"])})


SID_RE = re.compile(r"^[A-Za-z0-9._:-]{0,128}$")
AGENT_DONE_MAX = 20   # newest done items in an agent reply (open and in-progress are always all listed)


def _agent_items(items):
    done = [v for v in items if v["s"] == "x"][-AGENT_DONE_MAX:]
    keep = set(id(v) for v in done)
    return [{"id": v["id"], "s": v["s"], "t": v["t"]} for v in items if v["s"] != "x" or id(v) in keep]


def _target(items, req, action):
    """Item by `id`, else by exact normalized text: the newest not-done one; for `open` the newest "~" (paused), else the newest done."""
    i = req.get("id")
    if isinstance(i, int) and not isinstance(i, bool):
        return next((v for v in items if v["id"] == i), None)
    k = _key(_clean_text(req.get("text")))
    for want in (("~",), ("x",)) if action == "open" else ((" ", "~"),):
        hit = next((v for v in reversed(items) if v["s"] in want and _key(v["t"]) == k), None)
        if hit:
            return hit
    return None


def agent(req):
    """POST /api/todo/agent {cwd, sid, action: add|start|done|open|list, text?, id?} -> {ok, repo, items:[{id, s, t}]}.
    Called by the sidereus MCP tool for the session's own repo (any git root, not only on-screen cwds).
    ⚠Labels only (one line ≤ TEXT_MAX); `start` leaves one in-progress item per session (the sid's other `~` go back to open)."""
    if not isinstance(req, dict) or req.get("action") not in ("add", "start", "done", "open", "list"):
        return 400, {"ok": False, "err": "action must be add, start, done, open or list"}
    sid = req.get("sid") if req.get("sid") is not None else ""
    if not isinstance(sid, str) or not SID_RE.match(sid):
        return 400, {"ok": False, "err": "bad sid"}
    action = req["action"]
    has_id = isinstance(req.get("id"), int) and not isinstance(req.get("id"), bool)
    if action in ("start", "done", "open") and not has_id and req.get("text") is None:
        return 400, {"ok": False, "err": "text or id required"}
    if action == "add" or (req.get("text") is not None and not has_id and action != "list"):
        if _clean_text(req.get("text")) is None:
            return 400, {"ok": False, "err": "one line, 1-%d characters" % TEXT_MAX}
    repo, err = _repo_dir(req.get("cwd"))
    if err:
        return err
    with _LOCK:
        store = _load_locked(repo)
        items = store["items"]
        if action != "list":
            if action == "add":
                it = _new_item(store, _clean_text(req["text"]), sid)
            else:
                it = _target(items, req, action)
                if it is None:
                    return 404, {"ok": False, "err": "no such item"}
            if action == "start":
                for v in items:
                    if v is not it and v["s"] == "~" and sid and v.get("sid") == sid:
                        v["s"] = " "
            if action in ("start", "done", "open"):
                _mark(it, {"start": "~", "done": "x", "open": " "}[action], sid)
            err = _commit_locked(repo, store)
            if err:
                return err
        return 200, {"ok": True, "repo": repo, "items": _agent_items(store["items"])}
