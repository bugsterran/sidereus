"""«Review» queue: finished sessions' uncommitted files with per-file / per-session «reviewed» marks (metadata only).

A (root, sid) item lists files the session (or its subagents) edited (file_owner.index) that still differ from HEAD.
Marks are stored as signatures; any change to a file (or HEAD) changes its signature and reopens the item.
⛔Metadata only: paths, status letter, line counts, sizes. No diff text leaves this module.
⚠Read-only git (`diff`/`rev-parse`, wait=0). Sidereus never runs git write commands.
"""
import hashlib
import json
import os
import subprocess
import threading
import time

from sidereus.config import DATA_DIR
from sidereus.memo import BoundedMemo
from sidereus.warn import warn_once
from sidereus.bus import _atomic_write
from sidereus.gitinfo import _git_root, _git_run
from sidereus.steps import _edit_target
from sidereus.sessions import sessions_snapshot
from sidereus import work as _wk
from sidereus import file_owner as _fo

RV_FILE = os.path.join(DATA_DIR, "review-state.json")
RV_KEEP_S = 7 * 86400        # marks older than 7 days are dropped on write
RV_MAX_ITEMS = 300
RV_TTL = 20                  # per-root git answer reused this long
RV_FILES_MAX = 200           # pathspec cap per root (one git call)
RV_BODY_MAX = 4096
_RV_LOCK = threading.RLock()  # guards the store read-modify-write and _RV_MEM
_RV_MEM = {"key": None, "items": {}}   # parsed store keyed by (path, mtime_ns, size)
_RV_CACHE = BoundedMemo(128)           # (root, rels) -> {"at", "head", "files": {rel: (st, add, del)}}
_RV_OWN = [(None, {})]                 # [(index() result, {sid: {root: set(rel)}})] (see _owned_by_sid)


def _finished(r):
    """Same «done» criterion as attention._row_sigs: turn over, nothing still running under it."""
    if not isinstance(r, dict) or r.get("state") not in ("wait", "done") or r.get("blocked"):
        return False
    wf_run = any(isinstance(w, dict) and w.get("run") for w in (r.get("wf") or []))
    return not r.get("sub") and not r.get("bgs") and not wf_run


def _roots(r):
    """Git roots a row may review: its cwd's root plus the repos it touched (raw and realpath)."""
    out = set()
    for p in [r.get("cwd") or ""] + list(r.get("repos") or []):
        if not isinstance(p, str) or not p:
            continue
        root = _git_root(p) or p
        out.add(root)
        out.add(os.path.realpath(root))
    return out


def _owned_by_sid(idx):
    """{sid: {root: set(rel)}} for one index() result, built once and reused while index() returns the same object.
    ★Folding per file x per session was ~45% of /api/state poll CPU; ⚠keyed by identity (`is`), and the memo keeps
    `idx` alive so its id cannot be reused by another dict."""
    hit = _RV_OWN[0]                   # one read of one tuple: no torn (idx, by) pair across threads
    if hit[0] is idx:
        return hit[1]
    by = {}
    for p, units in idx.items():
        t = _edit_target(p)
        if not t:
            continue
        for sid in {s for s, _aid in units}:
            by.setdefault(sid, {}).setdefault(t["cwd"], set()).add(t["path"])
    _RV_OWN[0] = (idx, by)
    return by


def _owned(sid, now):
    """{root: sorted [rel]} of files `sid` (main or its subagents) edited in the last 24 h."""
    out = _owned_by_sid(_fo.index(now)).get(sid) or {}
    return {k: sorted(v)[:RV_FILES_MAX] for k, v in out.items()}


def _parse(out):
    """`diff --raw --numstat -z --no-renames` -> {rel: (st, add, del)} (binary counts as 0/0)."""
    toks, st, res, i = out.split("\0"), {}, {}, 0
    while i < len(toks):
        t = toks[i]
        if t.startswith(":") and i + 1 < len(toks):
            st[toks[i + 1]] = (t.split() or ["M"])[-1][:1]
            i += 2
            continue
        parts = t.split("\t")
        if len(parts) == 3:
            a, d, rel = parts
            res[rel] = (int(a) if a.isdigit() else 0, int(d) if d.isdigit() else 0)
        i += 1
    return {rel: (st.get(rel, "M"), a, d) for rel, (a, d) in res.items()}


def _root_stat(root, rels, now):
    """HEAD + uncommitted numstat of `rels` in `root` (20 s cache). No git slot / git error -> last value or None."""
    ck = (root, tuple(rels))
    hit = _RV_CACHE.get(ck)
    if hit and now - hit["at"] < RV_TTL:
        return hit
    try:
        h = _git_run(root, ["rev-parse", "--verify", "-q", "HEAD"], 2, wait=0)
        if h.returncode != 0:
            return hit
        r = _git_run(root, ["diff", "HEAD", "--raw", "--numstat", "-z", "--no-renames", "--"]
                     + [":(literal)" + x for x in rels], 3, wait=0)
        if r.returncode != 0:
            return hit
    except subprocess.TimeoutExpired:
        return hit                            # no slot now (poll path never waits) — keep the last answer
    except Exception as e:
        warn_once("review-git", "review git read failed ({err})", vars={"err": type(e).__name__}, soft=True)
        return hit
    val = {"at": now, "head": h.stdout.strip(), "files": _parse(r.stdout)}
    _RV_CACHE.put(ck, val)
    return val


def _fsig(root, rel, st, add, dl):
    try:
        s = os.stat(os.path.join(root, rel))
        size, mt = s.st_size, s.st_mtime_ns
    except OSError:
        size, mt = -1, 0                      # deleted in the worktree
    return hashlib.sha1(("%d\t%d\t%d\t%d" % (add, dl, size, mt)).encode(), usedforsecurity=False).hexdigest()[:16]


def _files(root, rels, now):
    """(head, {rel: {st, add, del, fsig}}) for the session's uncommitted files in root, or None when unknown."""
    if not rels:
        return None
    got = _root_stat(root, rels, now)
    if not got:
        return None
    fs = {}
    for rel in rels:
        v = got["files"].get(rel)
        if v:
            fs[rel] = {"st": v[0], "add": v[1], "del": v[2], "fsig": _fsig(root, rel, *v)}
    return got["head"], fs


def _ssig(head, fs):
    body = head + "\n" + "\n".join("%s\t%s" % (rel, fs[rel]["fsig"]) for rel in sorted(fs))
    return hashlib.sha1(body.encode("utf-8", "replace"), usedforsecurity=False).hexdigest()[:16]


def _key(root, sid):
    return root + "\t" + sid


def _load_items():
    """Stored items (read-only view; callers copy before mutating). Missing/corrupt file -> {}."""
    path = RV_FILE
    try:
        s = os.stat(path)
    except OSError:
        return {}
    key = (path, s.st_mtime_ns, s.st_size)
    with _RV_LOCK:
        if _RV_MEM["key"] == key:
            return _RV_MEM["items"]
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        items = d.get("items") if isinstance(d, dict) and d.get("v") == 1 else None
        items = {k: v for k, v in (items or {}).items() if isinstance(v, dict)} if isinstance(items, dict) else {}
    except (OSError, ValueError) as e:
        warn_once("review-load", "review-state.json unreadable ({err})", vars={"err": type(e).__name__}, soft=True)
        items = {}
    with _RV_LOCK:
        _RV_MEM["key"], _RV_MEM["items"] = key, items
    return items


def _prune(items, now):
    keep = [(k, v) for k, v in items.items() if now - float(v.get("at") or 0) <= RV_KEEP_S]
    keep.sort(key=lambda kv: -float(kv[1].get("at") or 0))
    return dict(keep[:RV_MAX_ITEMS])


def _save(items, now):
    items = _prune(items, now)
    data = json.dumps({"v": 1, "items": items}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    _atomic_write(RV_FILE, data, prefix=".tmp-review-")
    with _RV_LOCK:
        try:
            s = os.stat(RV_FILE)
            _RV_MEM["key"], _RV_MEM["items"] = (RV_FILE, s.st_mtime_ns, s.st_size), items
        except OSError:
            _RV_MEM["key"] = None
    return items


def _state_of(item, head, fs):
    """(done, {rel: reviewed}) — done only while the stored session signature equals the current one."""
    item = item or {}
    marks = item.get("files") if isinstance(item.get("files"), dict) else {}
    rv = {rel: marks.get(rel) == f["fsig"] for rel, f in fs.items()}
    return bool(fs) and item.get("sig") == _ssig(head, fs), rv


def review(rows, now=None):
    """state().review -> {n (pending rows), rows:[{sid, cwd, root, branch, nf, add, del, done, since}]}."""
    now = time.time() if now is None else now
    items, out = None, []                     # loaded lazily: no finished row -> no file read
    for r in rows or ():
        sid = r.get("sid") if isinstance(r, dict) else ""
        if not sid or not _wk._SID_SAFE.match(sid) or not _finished(r):
            continue
        allowed = _roots(r)
        for root, rels in sorted(_owned(sid, now).items()):
            if root not in allowed:
                continue
            got = _files(root, rels, now)
            if not got or not got[1]:
                continue
            head, fs = got
            items = _load_items() if items is None else items
            done, _rv = _state_of(items.get(_key(root, sid)), head, fs)
            out.append({"sid": sid, "cwd": r.get("cwd") or "", "root": root, "branch": r.get("branch") or "",
                        "nf": len(fs), "add": sum(f["add"] for f in fs.values()),
                        "del": sum(f["del"] for f in fs.values()), "done": done,
                        "since": int(now - (r.get("ageSec") or 0))})
    out.sort(key=lambda x: (x["done"], -x["since"]))
    return {"n": sum(1 for x in out if not x["done"]), "rows": out}


def _row_of(sid):
    """The visible session row with this sid (allow list first, then the last sessions() snapshot)."""
    for r in list((_wk._allowed_cwds() or {}).values()) + list(sessions_snapshot(60) or []):
        if isinstance(r, dict) and r.get("sid") == sid:
            return r
    return None


def _resolve(cwd, sid, now):
    """Validate (cwd, sid) -> (root, head, fs) or an error string. ⚠Both are request input."""
    if not isinstance(sid, str) or not _wk._SID_SAFE.match(sid):
        return "bad sid"
    if not isinstance(cwd, str) or not cwd or "\0" in cwd:
        return "bad cwd"
    r = _row_of(sid)
    if r is None:
        return "unknown session"
    allowed = _roots(r)
    if cwd in allowed:
        root = cwd
    elif cwd == r.get("cwd"):
        root = _git_root(cwd) or cwd
    else:
        return "cwd not allowed"
    got = _files(root, _owned(sid, now).get(root) or [], now)
    if got is None:
        return root, "", {}
    return root, got[0], got[1]


def review_files(cwd, sid, now=None):
    """GET /api/review -> (code, {ok, files:[{path, st, add, del, rv}], sig, done})."""
    now = time.time() if now is None else now
    res = _resolve(cwd, sid, now)
    if isinstance(res, str):
        return 400, {"ok": False, "err": res}
    root, head, fs = res
    done, rv = _state_of(_load_items().get(_key(root, sid)), head, fs)
    files = [{"path": rel, "st": f["st"], "add": f["add"], "del": f["del"], "rv": rv[rel]}
             for rel, f in sorted(fs.items())]
    return 200, {"ok": True, "files": files, "sig": _ssig(head, fs) if fs else "", "done": done}


def review_mark(req, now=None):
    """POST /api/review/mark {cwd, sid, path | all, on} -> (code, {ok, done, n}). The file list and every
    signature are recomputed here — ⚠a client-sent sig is never read."""
    now = time.time() if now is None else now
    if not isinstance(req, dict):
        return 400, {"ok": False, "err": "bad body"}
    path, all_, on = req.get("path"), req.get("all"), req.get("on")
    if not isinstance(on, bool) or (not all_ and not isinstance(path, str)) or (all_ and path):
        return 400, {"ok": False, "err": "bad args"}
    res = _resolve(req.get("cwd"), req.get("sid"), now)
    if isinstance(res, str):
        return 400, {"ok": False, "err": res}
    root, head, fs = res
    if not fs or (not all_ and path not in fs):
        return 400, {"ok": False, "err": "unknown path"}
    key = _key(root, req["sid"])
    with _RV_LOCK:                            # one read-modify-write at a time (RLock: _load_items/_save re-enter)
        items = {k: dict(v) for k, v in _load_items().items()}
        it = items.get(key) or {}
        marks = {rel: s for rel, s in (it.get("files") or {}).items() if rel in fs}
        if all_:
            marks = {rel: f["fsig"] for rel, f in fs.items()} if on else {}
        elif on:
            marks[path] = fs[path]["fsig"]
        else:
            marks.pop(path, None)
        full = all(marks.get(rel) == f["fsig"] for rel, f in fs.items())
        items[key] = {"at": now, "sig": _ssig(head, fs) if full else "", "files": marks}
        _save(items, now)
    return 200, {"ok": True, "done": full, "n": sum(1 for rel, f in fs.items() if marks.get(rel) == f["fsig"])}
