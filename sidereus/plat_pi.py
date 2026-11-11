"""pi coding agent (earendil-works/pi) platform: session-file reader for the session list and timeline.

Records: `<agent dir>/sessions/--<cwd>--/<timestamp>_<id>.jsonl` — line 1 is the `session` header (id, cwd, timestamp),
then tree entries (`message`, `model_change`, `usage`, `compaction`, `branch_summary`, ...).
⚠Metadata only: header id/cwd/timestamp, entry ids and times, provider/model, token counts, cost and tool names.
Message content, tool arguments, tool output, thinking, summaries, session names and system sections are never read.
⚠No hooks yet: rows come from the files alone (ext_presence), so state is always unknown; a running `pi` process
in the same cwd keeps its newest file listed past the window and gives the row its pid (ext_presence._pi_procs).
"""
import glob
import hashlib
import json
import math
import os
import re
import threading

from sidereus import config   # module access: tests patch `config.ASSET_DIR`
from sidereus.ident import _proj_name, _real_home
from sidereus.transcript import iso_epoch

PLAT = "pi"              # hook `platform` value
KEY = "pi"               # row `plat` key (same as the logo `AILG.pi`)
NAME = "Pi"
CHILD_LABEL = "pi -p"    # a run launched from a Claude session's Bash
SCAN_MAX = 64 << 20      # skip session files larger than this
TOOLS_N = 50             # tool names kept per session (timeline label, work panel)
_TOOL = re.compile(r"^[A-Za-z0-9_.:-]{1,40}$")
_lock = threading.Lock()
_cache = {}              # path -> ((size, mtime), parsed | None)
REV_HEX = re.compile(r"[0-9a-f]{12}")   # extension rev, fullmatch only (same shape as ext_hook.build)
_REV_LINE = re.compile(rb'^const REV: string = "([0-9a-f]{12})";', re.M)
REV_READ_MAX = 256 << 10  # bytes read from the installed extension when looking for its rev
_rev_memo = {}           # (kind, path) -> ((mtime, size), rev | None)


def root():
    # pi's own override of its config dir; ⚠only an absolute value (a relative one would follow our cwd).
    d = os.environ.get("PI_CODING_AGENT_DIR") or ""
    return d if os.path.isabs(d) else os.path.join(_real_home(), ".pi", "agent")


def _sid_ok(s):
    # ⚠Same rule as ext_store._sid_ok (that module imports this one, so it cannot be imported here); tested on both.
    return isinstance(s, str) and 0 < len(s) <= 64 and all(c.isalnum() or c in "-_" for c in s)


def path_ok(path):
    """A `.jsonl` file whose real path is under the real sessions folder (a symlink out of it is refused)."""
    if not path or not str(path).endswith(".jsonl"):
        return False
    base = os.path.realpath(os.path.join(root(), "sessions"))
    return os.path.realpath(path).startswith(base + os.sep)


def _n(v):
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v > 0 else 0


def _pm(prov, model):
    p = prov if isinstance(prov, str) else ""
    m = model if isinstance(model, str) else ""
    return (p + "/" + m if p and m else m or p)[:40]


def _tuple(u, ts, model):
    """pi `Usage` -> (uncached in, out, cache, thought, ts, model, cost). `reasoning` is already inside `output`."""
    c = u.get("cost")
    tot = c.get("total") if isinstance(c, dict) else None
    usd = float(tot) if isinstance(tot, (int, float)) and not isinstance(tot, bool) and math.isfinite(tot) else None
    return (_n(u.get("input")), _n(u.get("output")), _n(u.get("cacheRead")) + _n(u.get("cacheWrite")), 0,
            float(ts), model, usd)


def read(path):
    """{head, msgs, acts, tools, model} of one session file, or None when line 1 is not a `session` header."""
    msgs, acts, tools = {}, {}, []
    cur = ""
    head = None
    cut = 0.0
    try:
        with open(path, "rb") as f:
            for ln in f:
                try:
                    o = json.loads(ln)
                except ValueError:
                    o = None
                if head is None:
                    if not isinstance(o, dict) or o.get("type") != "session":
                        return None
                    head = o
                    # ⚠/clone and /fork copy the parent's entries (same ids, usage, times): count only entries after this header.
                    hts = o.get("timestamp")
                    cut = iso_epoch(hts) if o.get("parentSession") and isinstance(hts, str) else 0.0
                    continue
                if not isinstance(o, dict):
                    continue
                typ, eid = o.get("type"), o.get("id")
                eid = eid[:64] if isinstance(eid, str) and eid else ""
                ets = iso_epoch(o.get("timestamp")) if isinstance(o.get("timestamp"), str) else 0.0
                old = bool(cut and ets and ets < cut)      # copied parent entry: model tracking only
                if typ == "model_change":
                    cur = _pm(o.get("provider"), o.get("modelId")) or cur
                elif typ == "message":
                    m = o.get("message")
                    if not isinstance(m, dict):
                        continue
                    role = m.get("role")
                    if role not in ("user", "assistant", "toolResult"):
                        continue
                    mt = m.get("timestamp")
                    ts = mt / 1000.0 if isinstance(mt, (int, float)) and not isinstance(mt, bool) and mt > 0 else ets
                    if eid and ts and not old:
                        acts[eid] = float(ts)
                    if role == "assistant":
                        pm = _pm(m.get("provider"), m.get("model"))
                        cur = pm or cur
                        if eid and not old and isinstance(m.get("usage"), dict):
                            msgs[eid] = _tuple(m["usage"], ts, pm or cur)
                    elif role == "toolResult":
                        nm = m.get("toolName")
                        if not old and isinstance(nm, str) and _TOOL.match(nm):
                            tools.append((float(ts), nm))
                            del tools[:-TOOLS_N]
                elif typ in ("usage", "compaction", "branch_summary"):
                    if eid and not old and isinstance(o.get("usage"), dict):
                        msgs["u:" + eid] = _tuple(o["usage"], ets, _pm(o.get("provider"), o.get("model")) or cur)
    except OSError:
        return None
    if head is None:
        return None
    return {"head": head, "msgs": msgs, "acts": acts, "tools": tools, "model": cur}


def _parsed(path, st):
    key = (st.st_size, st.st_mtime)
    with _lock:
        c = _cache.get(path)
    if c and c[0] == key:
        return c[1]
    r = read(path)
    with _lock:
        _cache[path] = (key, r)
    return r


def _row(path, st, r):
    h = r["head"]
    sid = h.get("id")
    if not _sid_ok(sid):
        sid = os.path.basename(path)[:-6].split("_", 1)[-1]   # file name = <timestamp>_<id>
        if not _sid_ok(sid):
            return None
    # ⚠cwd only from the header: the `--<cwd>--` folder name is lossy (`/`, `\`, `:` all became `-`).
    cwd = h.get("cwd") if isinstance(h.get("cwd"), str) else ""
    ts = h.get("timestamp")
    return {"sid": sid, "path": path, "cwd": cwd, "project": _proj_name(cwd) or "?",
            "start": iso_epoch(ts) if isinstance(ts, str) else 0.0, "kind": "",
            "msgs": r["msgs"], "acts": r["acts"], "model": r["model"], "tools": list(r["tools"]),
            "mtime": st.st_mtime}


def _rows(paths, since):
    out, seen = [], set()
    for p in paths:
        try:
            st = os.stat(p)
        except OSError:
            continue
        if st.st_mtime < since or st.st_size > SCAN_MAX or not path_ok(p):
            continue
        seen.add(p)
        r = _parsed(p, st)
        row = _row(p, st, r) if r else None
        if row:
            out.append(row)
    return out, seen


def scan(since=0.0):
    """Session files modified since `since` -> adapter rows (+ model, tools, mtime), cached by (size, mtime)."""
    out, seen = _rows(glob.glob(os.path.join(root(), "sessions", "*", "*.jsonl")), since)
    with _lock:
        if len(_cache) > 2 * len(seen) + 64:
            for k in [k for k in _cache if k not in seen]:
                _cache.pop(k, None)
    return out


NEWEST_N = 8           # files read per cwd folder when looking for a running session's file


def folder(cwd):
    """pi's session folder name for `cwd` (lossy: leading separator dropped, `/`, `\\`, `:` -> `-`)."""
    return "--" + re.sub(r"[/\\:]", "-", re.sub(r"^[/\\]", "", cwd)) + "--"


def newest(cwd):
    """Row of the newest session file (any age) whose header cwd is `cwd`, or None.
    ⚠The folder name is lossy, so the header cwd is checked; only the newest NEWEST_N files are read."""
    if not isinstance(cwd, str) or not cwd:
        return None
    d = os.path.join(root(), "sessions", folder(cwd))
    paths = []
    for p in glob.glob(os.path.join(glob.escape(d), "*.jsonl")):
        try:
            paths.append((os.stat(p).st_mtime, p))
        except OSError:
            continue
    paths.sort(reverse=True)
    for _mt, p in paths[:NEWEST_N]:
        hit = next((c for c in _rows([p], 0.0)[0] if c["cwd"] == cwd), None)
        if hit:
            return hit
    return None


def one(sid):
    """Row of one session by sid (any age), or None. File name first, then every file (a custom header id)."""
    if not _sid_ok(sid):
        return None
    base = os.path.join(root(), "sessions", "*")
    for paths in (glob.glob(os.path.join(base, "*_" + sid + ".jsonl")), glob.glob(os.path.join(base, "*.jsonl"))):
        hit = next((c for c in _rows(paths, 0.0)[0] if c["sid"] == sid), None)
        if hit:
            return hit
    return None


def session_msgs(path):
    """Per-request tuples of one session file, or None (outside the sessions folder, unreadable, over SCAN_MAX)."""
    if not path_ok(path):
        return None
    try:
        st = os.stat(path)
    except OSError:
        return None
    if st.st_size > SCAN_MAX:
        return None
    r = _parsed(path, st)
    return dict(r["msgs"]) if r else None


def who_5h(start, now):
    """{project: {"tok", "sids": {sid: tok}}} of Anthropic-billed entries with start <= ts <= now (QWHO pi rows).
    ⚠Only provider `anthropic` draws on the Claude 5h window; openai/github-copilot/... are other quotas."""
    out = {}
    for r in scan(since=start):
        n = 0
        for t in r["msgs"].values():
            if start <= t[4] <= now and str(t[5]).startswith("anthropic/"):
                n += t[0] + t[1] + t[2]          # in + out + cacheRead + cacheWrite
        if n:
            e = out.setdefault(r["project"], {"tok": 0, "sids": {}})
            e["tok"] += n
            e["sids"][r["sid"]] = e["sids"].get(r["sid"], 0) + n
    return out


def _rev_of(kind, path, fn):
    """Memoised fn(bytes) for `path` keyed on (mtime, size); None when missing or unreadable."""
    try:
        st = os.stat(path)
        key = (st.st_mtime, st.st_size)
        with _lock:
            c = _rev_memo.get((kind, path))
        if c and c[0] == key:
            return c[1]
        with open(path, "rb") as f:
            r = fn(f.read(REV_READ_MAX + 1) if kind == "inst" else f.read())
    except OSError:
        return None
    with _lock:
        _rev_memo[(kind, path)] = (key, r)
    return r


def ext_rev(tpl=None):
    """Current extension rev: sha256(raw template bytes)[:12], or None when the template is unreadable."""
    p = tpl or os.path.join(config.ASSET_DIR, "ext-hooks", "pi-extension.ts")
    return _rev_of("tpl", p, lambda b: hashlib.sha256(b).hexdigest()[:12])


def installed_rev():
    """REV of the installed `<root>/extensions/sidereus.ts`, or None (missing, unreadable, no rev, outside root)."""
    p = os.path.join(root(), "extensions", "sidereus.ts")
    # ⚠Same rule as path_ok: the real path must stay under the real agent dir; a symlinked root is resolved.
    if not os.path.realpath(p).startswith(os.path.realpath(root()) + os.sep) or not os.path.isfile(p):
        return None

    def _find(b):
        m = _REV_LINE.search(b[:REV_READ_MAX])
        return m.group(1).decode("ascii") if m else None
    return _rev_of("inst", p, _find)
