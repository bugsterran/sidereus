"""«Tools» usage index — how often each skill / agent / slash command / MCP server was used (GET /api/tools).

⚠Counts only: keys `tool:<Name>` · `mcp:<server>` · `skill:<name>` · `agent:<type>` · `cmd:<name>` · `hook:<hookName>` with a count and last-use epoch.
  Hook runs read only attachment `type`/`hookName` (+ a hash of `command`, `hookc:` keys) — never content/stdout/stderr
  or the command text (nor stop_hook_summary).
  Tool inputs other than the skill name / agent type are never kept; message text is never read into the payload.
  MCP failures: `deferred_tools_delta` attachments' `failedMcpServers` — server name + errorCode only, never `error` text;
  the same attachments' `addedNames`/`readdedNames` (`mcp__<server>__<tool>`) are the connect evidence that clears one.
Incremental: per-file byte offsets, so a refresh reads only appended tails (same idea as usage_index).
Offsets + events persist to `toolidx-cache.json` so a restart resumes instead of rescanning.
"""
import glob
import hashlib
import json
import os
import re
import threading
import time
from array import array
from bisect import bisect_left
from itertools import chain, islice
from sidereus.config import DATA_DIR
from sidereus.bus import _atomic_write
from sidereus.warn import warn_once
from sidereus import boot_queue
from sidereus.transcript import CLAUDE_PROJECTS, iso_epoch
from sidereus.agents import sub_globs
from sidereus.claude_roots import projects_dirs
from sidereus.toolidx_fmt import _arr, _b64, _canon, _num, hook_hash   # hook_hash re-exported for harness

TI_MAX_DAYS = 90             # widest window the screen can ask for; older files are not read
TI_TTL_S = 30                # result cache per `days`
TI_STALE_MAX_S = 10 * TI_TTL_S   # ⚠past this a stale result is recomputed synchronously, so a failing revalidate surfaces
TI_NAME_MAX = 120            # keys are names, not text — cap anything odd
TI_BUDGET = 32 << 20         # bytes read per request / per background slice (first full scan is ~GBs)
TI_CHUNK_MIN = 1 << 20
TI_BG = True                 # tests turn the background warm thread off
# ★10-03: cold scan of 90 days = 4.64 GB / 3,970 files / 22 s, so «Loading» showed for that long after every restart.
#   The cache (36.8 MB JSON, 0.23 s to load) brings a restart down to reading only the tails appended since the last save.
TI_CACHE = os.path.join(DATA_DIR, "toolidx-cache.json")
# 5: header line + one JSON line per file `[path, sz, off, [keys], ids, ts, ki, fail, conn]`, the three arrays
#   base64 little-endian (int64 id hash · float64 ts · uint32 index into that row's keys); loaded line by line.
#   4: "ev" grouped by key ({key: [[id strings], [ts]]}) · 3: `tool:` events deduped by id · 2: per-file "tools".
#   ★10-13: v3 (one 80 MB JSON, 894k events, 80% hook runs) peaked at 489 MB in json.load; v4 see `_load_disk`.
TI_CACHE_V = 5
TI_SAVE_S = 120              # at most one save per this many seconds (★10-05: a dump is 0.31 s under the lock)
_TI_ROOT = CLAUDE_PROJECTS   # ⚠disk cache only for the real projects dir — tests patch CLAUDE_PROJECTS and get no disk I/O
_TI_HINT = (b"mcp__", b'"Skill"', b'"Task"', b'"Agent"', b"<command-name>", b'"hook_success"', b'"hook_additional_context"', b'"failedMcpServers"')
_HOOK_TYPES = {"hook_success": "hook:", "hook_additional_context": "hookctx:"}   # ⚠one run writes both records: kept apart, not summed
_CMD_RE = re.compile(r"<command-name>/?([^<\s]{1,120})</command-name>")
_ERR_RE = re.compile(r"[A-Z_]{1,24}")
# Tool names for hook-matcher checks, read off the raw line (no JSON parse: most tool lines carry no _TI_HINT).
_TOOL_RE = re.compile(rb'"type":\s?"tool_use",\s?"id":\s?"([^"]{1,80})",\s?"name":\s?"([A-Za-z0-9_.:-]{1,120})"')
_TS_RE = re.compile(rb'"timestamp":\s?"([^"]{1,40})"')
_SRV_RE = re.compile(r"[^A-Za-z0-9_-]")   # config name -> tool-name prefix form (`claude.ai X` -> `claude_ai_X`)
_HDR_RE = re.compile(rb'\{\s*"v"\s*:\s*(\d{1,4})\s*[,}]')
# path -> {"sz", "off", "ids"/"ts"/"ki": parallel arrays (id hash, epoch, key index), "lo"/"hi": ts range,
#          "mc": {mcp key: newest call ts}, "fail": {mcp key: (ts, code)}, "conn": {mcp key: ts}}
# ★10-22 (5,335 files / 1.53M events, 1,845 ids in 2+ files): per-event dicts of id strings + tuples -> arrays of
#   id hashes: index traced 328 -> 55 MB · 4-window recompute peak 454 -> 56 MB, 1.68 -> 0.66 s (no full `_merged`
#   copy) · maxrss after cache load + recompute 539 -> 166 MB · cold 90-day scan maxrss 711 -> 464 MB · cache 96 -> 47 MB.
# ⚠Events older than TI_MAX_DAYS are dropped: a copy with no timestamp (ts 0) no longer hides the timestamped copy
#   of the same id, which now counts. ★10-22, 47 of 1.53M: 31 in another file, 16 in the same file (an
#   `api-request-blob` line carries the tool_use with no timestamp a few lines before the real assistant line).
_TI_FILES = {}
_TI_KEYS = []                # key index -> key (~1k distinct keys over all events)
_TI_KIDX = {}                # key -> index
_TI_SEEN = array("q")        # sorted id hashes at the last `_reindex`; with _TI_NEW a superset of every indexed id
_TI_NEW = set()              # id hashes added since the last `_reindex`
_TI_DUP = set()              # id hashes that may sit in more than one file (only these go through `_merged`)
TI_REINDEX_MIN = 1 << 17
_INF = float("inf")
_TI_RES = {}                 # days -> (computed at, result); only complete results are cached
_TI_MCP = {}                 # days -> (computed at, mcp_status result)
_TI_STATE = {"pending": False, "bg": None, "loaded": False, "dirty": False, "saved": 0.0, "rv": False}
_TI_LOCK = threading.Lock()


def _paths():
    out = []
    for root in projects_dirs(CLAUDE_PROJECTS):
        out += glob.glob(os.path.join(root, "*", "*.jsonl"))
        for pat in sub_globs(root):
            out += glob.glob(pat)
    return list(dict.fromkeys(out))


def _key_of(block):
    """tool_use block -> usage key, or "" when it is not a tracked tool."""
    nm = str(block.get("name") or "")
    inp = block.get("input") if isinstance(block.get("input"), dict) else {}
    if nm.startswith("mcp__"):
        srv = nm[5:].split("__", 1)[0]
        return "mcp:" + srv if srv else ""
    if nm == "Skill":
        sk = inp.get("skill") or inp.get("command")
        return "skill:" + str(sk).lstrip("/") if isinstance(sk, str) and sk.strip() else ""
    if nm in ("Task", "Agent"):
        st = inp.get("subagent_type")
        return "agent:" + (st if isinstance(st, str) and st.strip() else "general-purpose")
    return ""


def _line_events(d):
    """[(event id, key)] of one transcript record — tool_use ids for tools, the record uuid for slash commands."""
    msg = d.get("message") if isinstance(d.get("message"), dict) else {}
    c = msg.get("content")
    out = []
    a = d.get("attachment")
    if d.get("type") == "attachment" and isinstance(a, dict):
        pre, hn = _HOOK_TYPES.get(a.get("type")), a.get("hookName")
        if pre and isinstance(hn, str) and hn.strip() and d.get("uuid"):
            out.append(("hook#" + str(d["uuid"]), (pre + hn.strip())[:TI_NAME_MAX]))
            # Per-hook runs: the configured command string, kept only as a one-way hash (`hook_hash`).
            if pre == "hook:" and isinstance(a.get("command"), str) and a["command"]:
                out.append(("hookc#" + str(d["uuid"]), "hookc:%s#%s" % (hn.strip()[:TI_NAME_MAX - 20], hook_hash(a["command"]))))
        return out
    if d.get("type") == "assistant" and isinstance(c, list):
        for b in c:
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id"):
                k = _key_of(b)
                if k:
                    out.append((str(b["id"]), k[:TI_NAME_MAX]))
    elif d.get("type") == "user" and isinstance(c, str) and "<command-name>" in c and d.get("uuid"):
        m = _CMD_RE.search(c)
        if m:
            out.append(("cmd#" + str(d["uuid"]), "cmd:" + m.group(1)))
    return out


def _fails_of(d):
    """[(mcp key, errorCode)] reported failed by one record. ⚠Only `name`/`errorCode` are read — `error` is free text."""
    a = d.get("attachment")
    if d.get("type") != "attachment" or not isinstance(a, dict) or not isinstance(a.get("failedMcpServers"), list):
        return []
    out = []
    for s in a["failedMcpServers"]:
        nm = s.get("name") if isinstance(s, dict) else None
        if isinstance(nm, str) and nm.strip():
            code = str(s.get("errorCode") or "")[:24]
            out.append(("mcp:" + _SRV_RE.sub("_", nm.strip())[:TI_NAME_MAX - 4], code if _ERR_RE.fullmatch(code) else ""))
    return out


def _conns_of(d):
    """[mcp key] whose tools a `deferred_tools_delta` record adds — the server connected at that time."""
    a = d.get("attachment")
    if d.get("type") != "attachment" or not isinstance(a, dict) or a.get("type") != "deferred_tools_delta":
        return []
    out = set()
    for k in ("addedNames", "readdedNames"):
        for nm in a.get(k) if isinstance(a.get(k), list) else ():
            if isinstance(nm, str) and nm.startswith("mcp__") and nm[5:].split("__", 1)[0]:
                out.add("mcp:" + nm[5:].split("__", 1)[0][:TI_NAME_MAX - 4])
    return sorted(out)


def _new_ent(sz=-1, off=0):
    return {"sz": sz, "off": off, "ids": array("q"), "ts": array("d"), "ki": array("I"),
            "lo": _INF, "hi": -_INF, "mc": {}, "fail": {}, "conn": {}}


def _hid(eid):
    """Event id -> signed 64-bit hash (★1.5M ids: collision odds ~1e-7; a str id cost ~105 B, this 8 B in an array)."""
    return int.from_bytes(hashlib.blake2b(eid.encode("utf-8", "replace"), digest_size=8).digest(), "little", signed=True)


def _kid(key):
    i = _TI_KIDX.setdefault(key, len(_TI_KEYS))
    if i == len(_TI_KEYS):
        _TI_KEYS.append(key)
    return i


def _reindex():
    """Rebuild `_TI_SEEN`/`_TI_DUP` exactly from the files (drops ids of removed or trimmed files; call under the lock).
    ⚠The sort makes a transient list of every id (★10-22: load peak 122 MB traced at 1.5M) — runs at load and
      when _TI_NEW passes a quarter of _TI_SEEN, never per request."""
    global _TI_SEEN
    s = sorted(chain.from_iterable(ent["ids"] for ent in _TI_FILES.values()))
    _TI_DUP.clear()
    _TI_DUP.update(a for a, b in zip(s, islice(s, 1, None)) if a == b)
    _TI_SEEN = array("q", s)
    _TI_NEW.clear()


def _forget(gone):
    """Remove the ids of dropped entries (`gone` = their id arrays) from `_TI_SEEN`/`_TI_NEW` (call under the lock).
    ⚠Without it a rescan of a dropped file finds its own ids «seen» and marks every one a duplicate
      (★#17: 1,545,890 dups vs 1,845, maxrss 719 vs 288 MB). Ids already in `_TI_DUP` stay: another file may hold them."""
    global _TI_SEEN
    n = sum(map(len, gone))
    if n and n > (len(_TI_SEEN) + len(_TI_NEW)) >> 2:
        _reindex()          # bulk drop: one exact rebuild from the remaining files beats a huge filter set
        return
    rm = set(chain.from_iterable(gone))
    rm -= _TI_DUP           # not a dup => exactly one copy indexed, so it is safe to drop
    if rm:
        _TI_NEW.difference_update(rm)
        _TI_SEEN = array("q", (x for x in _TI_SEEN if x not in rm))


def _add(ent, eid, key, ts, cut, own):
    """Index one event unless it is older than `cut` or already in this file (first copy in a file wins, as before).
    Returns the file's id set once a lookup needed it (built lazily: most ids are new everywhere)."""
    if ts < cut:
        return own
    x = _hid(eid)
    i = bisect_left(_TI_SEEN, x)
    if x in _TI_NEW or (i < len(_TI_SEEN) and _TI_SEEN[i] == x):
        if own is None:
            own = set(ent["ids"])
        if x in own:
            return own
        _TI_DUP.add(x)      # also in another file (or was): `_merged` picks the earliest copy
    else:
        _TI_NEW.add(x)
    if own is not None:
        own.add(x)
    ent["ids"].append(x)
    ent["ts"].append(ts)
    ent["ki"].append(_kid(key))
    ent["lo"], ent["hi"] = min(ent["lo"], ts), max(ent["hi"], ts)
    if key.startswith("mcp:"):
        ent["mc"][key] = max(ent["mc"].get(key, 0.0), ts)
    return own


def _trim(ent, cut):
    """Drop events older than `cut` (they count in no window). True when something was dropped."""
    if ent["lo"] >= cut:
        return False
    keep = [i for i, t in enumerate(ent["ts"]) if t >= cut]
    for f, code in (("ids", "q"), ("ts", "d"), ("ki", "I")):
        ent[f] = array(code, map(ent[f].__getitem__, keep))
    ent["lo"], ent["hi"] = (min(ent["ts"]), ent["hi"]) if keep else (_INF, -_INF)
    return True


def _scan_file(fp, ent, limit, cut=-_INF):
    """Read up to `limit` bytes of `fp` from `ent["off"]` (complete lines only). True when EOF was reached."""
    with open(fp, "rb") as f:
        f.seek(ent["off"])
        raw = f.read(limit)
        eof = len(raw) < limit
        while not eof and b"\n" not in raw:          # one line longer than the chunk: finish that line
            more = f.read(limit)
            raw += more
            eof = len(more) < limit
    end = raw.rfind(b"\n") + 1
    own = None
    for ln in raw[:end].split(b"\n"):
        names = _TOOL_RE.findall(ln) if b'"tool_use"' in ln else ()
        if names:
            m = _TS_RE.search(ln)
            t = iso_epoch(m.group(1).decode("ascii", "replace"), 0.0) if m else 0.0
            for tid, nm in names:   # ⚠"t#" id: resumed/forked transcripts copy the same tool_use lines into another file
                own = _add(ent, "t#" + tid.decode("ascii", "replace"), "tool:" + nm.decode("ascii"), t, cut, own)
        if not any(h in ln for h in _TI_HINT):
            continue
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        ts = iso_epoch(d.get("timestamp"), 0.0)
        for eid, k in _line_events(d):
            own = _add(ent, eid, k, ts, cut, own)
        for k, code in _fails_of(d):
            if ts >= ent["fail"].get(k, (0.0, ""))[0]:
                ent["fail"][k] = (ts, code)
        conn = ent.setdefault("conn", {})
        for k in _conns_of(d):
            conn[k] = max(conn.get(k, 0.0), ts)
    ent["off"] += end
    if len(_TI_NEW) > max(TI_REINDEX_MIN, len(_TI_SEEN) >> 2):
        _reindex()          # keeps the unsorted set small; geometric, so a cold scan sorts only a few times
    return eof, end


def _disk_ok():
    return bool(TI_CACHE) and CLAUDE_PROJECTS == _TI_ROOT


def _load_disk(cut=-_INF):
    """Seed `_TI_FILES` from the last save (once). A missing, foreign or malformed file just means a full scan."""
    _TI_STATE["loaded"] = True
    if not _disk_ok():
        return
    # ⚠Line by line, never json.load: the peak stays near the in-memory index, not text + whole tree.
    bad = 0
    pre = CLAUDE_PROJECTS.rstrip(os.sep) + os.sep
    rpre = os.path.realpath(CLAUDE_PROJECTS).rstrip(os.sep) + os.sep
    try:
        with open(TI_CACHE, "rb") as f:
            m = _HDR_RE.match(f.readline(64))   # ⚠bounded: a v3 file is one 80 MB line
            if m is None:
                raise ValueError("no version header")
            if int(m.group(1)) != TI_CACHE_V:
                return                          # older format: full rescan, the next save replaces it
            for ln in f:
                try:
                    fp, ent = _ent_from(json.loads(ln), cut)
                except (ValueError, TypeError):
                    bad += 1
                    continue
                _TI_FILES.setdefault(_canon(fp, pre, rpre), ent)   # ⚠a save under the other spelling must still match the scan
    except FileNotFoundError:
        return
    except (OSError, ValueError) as e:
        warn_once("toolidx-cache", "Tool usage cache unreadable, rescanning ({err})", vars={"err": e}, soft=True)
        return
    if bad:
        warn_once("toolidx-cache-ent", "Dropped {n} malformed tool usage cache entries; rescanning those files",
                  vars={"n": bad}, soft=True)


def _ent_from(row, cut=-_INF):
    """One cache line `[path, sz, off, [keys], ids, ts, ki, fail, conn]` -> (path, entry); ValueError when malformed.
    Events older than `cut` are dropped. ⚠Full type check — a wrong inner type would crash every count and the warm thread."""
    if not (isinstance(row, list) and len(row) == 9 and isinstance(row[0], str)):
        raise ValueError("row")
    fp, sz, off, keys, ids, ts, lk, fail, conn = row
    if not (type(sz) is int and type(off) is int and off >= 0 and isinstance(keys, list)
            and all(type(k) is str for k in keys) and isinstance(fail, dict) and isinstance(conn, dict)):
        raise ValueError("entry")
    ids, ts, lk = _arr("q", ids), _arr("d", ts), _arr("I", lk)
    if not (len(ids) == len(ts) == len(lk) and (not lk or max(lk) < len(keys))):
        raise ValueError("ev")
    if not (all(isinstance(v, list) and len(v) == 2 and _num(v[0]) and isinstance(v[1], str) for v in fail.values())
            and all(_num(v) for v in conn.values())):
        raise ValueError("fail/conn")
    ent = _new_ent(sz, off)
    ent["fail"], ent["conn"] = dict((k, tuple(v)) for k, v in fail.items()), conn
    gk = [_kid(k) for k in keys]
    ent["ids"], ent["ts"], ent["ki"] = ids, ts, array("I", map(gk.__getitem__, lk))
    if ts:
        ent["lo"], ent["hi"] = min(ts), max(ts)
    _trim(ent, cut)
    mcp, mc = dict((g, k) for g, k in zip(gk, keys) if k.startswith("mcp:")), ent["mc"]
    for t, g in zip(ent["ts"], ent["ki"]) if mcp else ():
        if g in mcp and t > mc.get(mcp[g], 0.0):
            mc[mcp[g]] = t
    return fp, ent


def _ent_row(fp, ent):
    """Inverse of `_ent_from`: one compact JSON line (keys written once per file, events as packed arrays)."""
    loc = {}
    lk = array("I", [loc.setdefault(g, len(loc)) for g in ent["ki"]])
    keys = [_TI_KEYS[g] for g in sorted(loc, key=loc.get)]
    return json.dumps([fp, ent["sz"], ent["off"], keys, _b64(ent["ids"]), _b64(ent["ts"]), _b64(lk),
                       ent["fail"], ent.get("conn", {})], separators=(",", ":"))


def _snapshot(now):
    """Bytes to persist (call under the lock, only when caught up), or None when unchanged / saved recently."""
    if not (_disk_ok() and _TI_STATE["dirty"]) or 0 <= now - _TI_STATE["saved"] < TI_SAVE_S:
        return None
    _TI_STATE["dirty"], _TI_STATE["saved"] = False, now
    # ⚠Only the primary root is persisted: extra account roots are rescanned cold after every restart.
    pre = CLAUDE_PROJECTS.rstrip(os.sep) + os.sep
    lines = ['{"v":%d}' % TI_CACHE_V] + [_ent_row(k, v) for k, v in _TI_FILES.items() if k.startswith(pre)]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _save(data):
    """Write outside the lock. A failed save only costs a rescan next start."""
    if data is None:
        return
    try:
        _atomic_write(TI_CACHE, data, prefix=".toolidx-")
    except OSError as e:
        warn_once("toolidx-save", "Could not save the tool usage cache ({err})", vars={"err": e}, soft=True)


def _refresh(now, budget):
    """Advance the per-file cache by at most `budget` bytes (newest files first). True when fully caught up."""
    cut = now - TI_MAX_DAYS * 86400
    if not _TI_STATE["loaded"]:
        _load_disk(cut)
        _reindex()          # rows are loaded without `_add`: dedup sets come from one sort
    todo = []
    for fp in _paths():
        try:
            st = os.stat(fp)
        except OSError:
            continue
        if st.st_mtime >= cut:
            todo.append((st.st_mtime, st.st_size, fp))
    seen = set(t[2] for t in todo)
    gone = [_TI_FILES.pop(p)["ids"] for p in [p for p in _TI_FILES if p not in seen]]
    if gone:
        _TI_STATE["dirty"] = True
        _forget(gone)
    for _mt, size, fp in sorted(todo, reverse=True):
        ent = _TI_FILES.get(fp)
        if ent is None or size < ent["off"]:
            if ent is not None:
                del _TI_FILES[fp]
                _forget([ent["ids"]])     # truncated file: rescanned from 0, its old ids must not count as seen
            ent = _TI_FILES[fp] = _new_ent()
        if _trim(ent, cut):     # ⚠an active file keeps events past the window; dropped here, not by file mtime
            _TI_STATE["dirty"] = True
        if size == ent["sz"]:
            continue
        if budget <= 0:
            return False
        try:
            eof, used = _scan_file(fp, ent, max(TI_CHUNK_MIN, budget), cut)
        except OSError as e:
            warn_once("toolidx", "Tool usage: could not read a transcript ({err})", vars={"err": e}, soft=True)
            continue
        budget -= max(used, 1)
        _TI_STATE["dirty"] = True
        if eof:
            ent["sz"] = size
        else:
            return False
    return True


def _bg_warm(at=None):
    """Finish the first (large) scan off the request thread, one budget slice per lock hold."""
    while True:
        with _TI_LOCK:
            now = time.time() if at is None else at
            done = _refresh(now, TI_BUDGET)
            _TI_STATE["pending"] = not done
            data = _snapshot(now) if done else None
        if done:
            _save(data)
            return


def warm(now=None):
    """Startup pre-warm (viewer thread): finish the scan, then fill the 30-day `tool_uses`/`mcp_status` caches.
    ⚠Without it the first Harness/Tools request paid the cold load + merge under `_TI_LOCK` (see traps/server.md «showed «Loading…» for seconds after a restart»)."""
    if not TI_BG:
        return boot_queue.done("toolidx_warm")    # nothing to warm: do not hold up the boot drain
    with boot_queue.gate("toolidx_warm"):          # ⚠boot warms run one at a time (traps/server.md)
        with _TI_LOCK:   # ⚠register "bg" only inside the gate: set while queued, _kick() saw a live thread and no scan ran
            t = _TI_STATE.get("bg")
            t = _TI_STATE["bg"] = t if t and t.is_alive() else threading.current_thread()
        _bg_warm(now) if t is threading.current_thread() else t.join()   # a kicked scan runs: wait for it, never a second one
        tool_uses(30, now)
        mcp_status(30, now)


def _kick():
    with _TI_LOCK:                                 # same lock as warm()'s check-and-register: one scan thread at a time
        t = _TI_STATE.get("bg")
        if TI_BG and not (t and t.is_alive()):
            t = _TI_STATE["bg"] = threading.Thread(target=_bg_warm, name="toolidx-warm", daemon=True)
            t.start()


def scanning():
    """True while the index is still catching up (the counts are partial)."""
    return bool(_TI_STATE["pending"])


def _merged():
    """id hash -> (ts, key index) for the ids in `_TI_DUP` only, earliest copy wins (call under the lock).
    ⚠Not a copy of every event: ids in one file are counted straight from the file arrays by `_count`."""
    win = {}
    if not _TI_DUP:
        return win
    for ent in _TI_FILES.values():
        if _TI_DUP.isdisjoint(ent["ids"]):
            continue
        for x, t, k in zip(ent["ids"], ent["ts"], ent["ki"]):
            if x in _TI_DUP:
                w = win.get(x)
                if w is None or t < w[0]:
                    win[x] = (t, k)
    return win


def _count(merged, days, now):
    """{key: {"n", "last"}} for events at/after the window start; ids in `_TI_DUP` come from `merged` only."""
    cut = now - days * 86400
    n, hi = {}, {}

    def add(rows):
        for t, k in rows:
            if t >= cut:
                n[k] = n.get(k, 0) + 1
                if t > hi.get(k, -_INF):
                    hi[k] = t
    for ent in _TI_FILES.values():
        if ent["hi"] < cut:
            continue
        if _TI_DUP and not _TI_DUP.isdisjoint(ent["ids"]):
            add((t, k) for x, t, k in zip(ent["ids"], ent["ts"], ent["ki"]) if x not in _TI_DUP)
        else:
            add(zip(ent["ts"], ent["ki"]))
    add(merged.values())
    return dict((_TI_KEYS[k], {"n": c, "last": max(0, int(hi[k]))}) for k, c in n.items())


def _spawn(target, args):
    threading.Thread(target=target, args=args, name="toolidx-reval", daemon=True).start()


def _revalidate(days, now):
    """Catch up, then recompute `days` and every other expired window (one merge) off the request thread."""
    try:
        while True:
            with _TI_LOCK:
                done = _refresh(now, TI_BUDGET)
                _TI_STATE["pending"] = not done
                data = None
                if done:
                    merged = _merged()
                    for d in set(k for k, v in _TI_RES.items() if not 0 <= now - v[0] < TI_TTL_S) | {days}:
                        _TI_RES[d] = (now, _count(merged, d, now))
                    data = _snapshot(now)
            if done:
                _save(data)
                return
    finally:
        with _TI_LOCK:
            _TI_STATE["rv"] = False


def tool_uses(days=30, now=None):
    """{key: {"n": count, "last": epoch}} over the last `days` (1..90). Deduped by event id across files.
    ⚠Reads at most TI_BUDGET bytes per call; the rest continues in a background thread (`scanning()`).
    ⚠Stale-while-revalidate: an expired complete result is returned as is and one background pass refreshes it.
      ★10-12: the synchronous refresh (stat 3,547 files + merge 764k events) held the request 0.8-1.8 s after each expiry."""
    days = max(1, min(TI_MAX_DAYS, int(days)))
    now = time.time() if now is None else now
    with _TI_LOCK:
        hit = _TI_RES.get(days)
        if hit and not _TI_STATE["pending"]:
            if 0 <= now - hit[0] < TI_TTL_S:
                return hit[1]
            if TI_BG and now - hit[0] <= TI_STALE_MAX_S:
                if not _TI_STATE.get("rv"):
                    _TI_STATE["rv"] = True   # set under the lock so concurrent callers spawn only one pass
                    try:
                        _spawn(_revalidate, (days, now))
                    except RuntimeError:     # ⚠a failed start must not leave the guard set forever
                        _TI_STATE["rv"] = False
                return hit[1]
        done = _refresh(now, TI_BUDGET)
        _TI_STATE["pending"] = not done
        out = _count(_merged(), days, now)
        data = None
        if done:
            _TI_RES[days] = (now, out)
            data = _snapshot(now)
    _save(data)
    if not done:
        _kick()
    return out


def mcp_status(days=30, now=None):
    """{mcp key: {"status": 'ok'|'fail', "err", "fail_at", "ok_at"}} over the last `days`, from the files `tool_uses` indexed.
    fail = a failure newer than the last call/connect, or the newest session mentioning the server ended on a failure.
    ⚠A call (tool_use) or a connect (tools added in a delta) is the success evidence: an unused but connected server
      would otherwise keep its old failure forever. Keys with neither are absent ('none' to the caller)."""
    days = max(1, min(TI_MAX_DAYS, int(days)))
    now = time.time() if now is None else now
    hit = _TI_MCP.get(days)
    if hit and 0 <= now - hit[0] < TI_TTL_S:
        return hit[1]
    # ⚠With a previous result, never wait on the lock: `_revalidate` holds it ~0.35 s and this sits on the same request.
    if not _TI_LOCK.acquire(not hit):
        return hit[1]
    try:
        out = _mcp_compute(now - days * 86400)
    finally:
        _TI_LOCK.release()
    _TI_MCP[days] = (now, out)
    return out


def _mcp_compute(cut):
    """mcp_status body (call under the lock)."""
    agg = {}
    for ent in _TI_FILES.values():
        calls = dict((k, ts) for k, ts in ent["mc"].items() if ts >= cut)   # newest call per file: same max as all calls >= cut
        for k, ts in ent.get("conn", {}).items():
            if ts >= cut:
                calls[k] = max(calls.get(k, 0.0), ts)
        fails = dict((k, v) for k, v in ent.get("fail", {}).items() if v[0] >= cut)
        for k in set(calls) | set(fails):
            c, f = calls.get(k, 0.0), fails.get(k, (0.0, ""))
            r = agg.setdefault(k, {"ok_at": 0.0, "fail_at": 0.0, "err": "", "sess": 0.0, "sfail": False})
            r["ok_at"] = max(r["ok_at"], c)
            if f[0] > r["fail_at"]:
                r["fail_at"], r["err"] = f[0], f[1]
            if max(c, f[0]) > r["sess"]:
                r["sess"], r["sfail"] = max(c, f[0]), f[0] > c
    out = {}
    for k, r in agg.items():
        bad = r["fail_at"] > r["ok_at"] or r["sfail"]
        out[k] = {"status": "fail" if bad else "ok", "err": r["err"], "fail_at": int(r["fail_at"]), "ok_at": int(r["ok_at"])}
    return out


def reset():
    """Drop every cache (tests)."""
    global _TI_SEEN
    with _TI_LOCK:
        _TI_FILES.clear()
        _TI_KEYS[:] = []
        _TI_KIDX.clear()
        _TI_SEEN = array("q")
        _TI_NEW.clear()
        _TI_DUP.clear()
        _TI_RES.clear()
        _TI_MCP.clear()
        _TI_STATE.update(pending=False, loaded=False, dirty=False, saved=0.0, rv=False)
