"""Recent-window transcript scans (split from burn_usage.py 2026-09-25): project display names, today's hourly buckets
(`_today`), the consumption report (`_burn`), the compaction window per session, and `_today_loop` that refreshes them.

`sidereus.burn_usage` imports `_today`/`_burn` (+ locks) and `_slug_name`/`_slug_group` for `wkuse()` and re-exports `_today_loop`.
⚠Patch `CLAUDE_SETTINGS`/`COMPACT_STATE`/`_slug_name`/... on this module, not on `sidereus.burn_usage` (a re-export is a copy of the binding)."""
import glob
import json
import os
import threading
import time
from sidereus.redact import redact
from sidereus.config import DATA_DIR, claude_home
from sidereus.ctxsrc import read_text
from sidereus.warn import _LOOP_ERR, warn_once
from sidereus import boot_queue
from sidereus.bus import _atomic_write
from sidereus.transcript import CLAUDE_PROJECTS, _line_ts
from sidereus.agents import sub_globs, sub_sess_dir
from sidereus.ident import _proj_name, _sid8, _slug
from sidereus.usage import _usage_save
from sidereus.sessions import sessions_rows
from sidereus.timeline import _resp_key
from sidereus.otel import _otel_src_save


# ★Sessions run in scratchpads are **folded into one row** (2026-09-04).
#   Each session lands under `/private/tmp/claude-501/<project>/<session-uuid>/scratchpad[...]`, and in the
#   30-day aggregate 6 of 17 projects were these — together only 4M (0.02% of total), yet they took
#   half the table and its width. They are temp-file locations, not real work locations.
TMP_GROUP = "__scratchpad__"


def _slug_group(slug):
    return TMP_GROUP if "scratchpad" in slug else slug


def _slug_name(slug):
    if slug == TMP_GROUP:
        return "임시(스크래치패드)"
    """Project slug -> display name. ★A path cannot be recovered from a slug (`/` and `-` collapse into the same character).
    So **first try to match against the cwd of sessions on screen**; if none matches, strip only the home prefix and show it as-is —
    never invent a path that does not exist."""
    try:
        for r in sessions_rows(wait=0, max_age=float("inf")):   # ⚠called per row, maybe on a request: never wait
            c = r.get("cwd") or ""
            if c and _slug(c) == slug:
                return _proj_name(c) or os.path.basename(c) or slug
    except Exception as e:
        warn_once("slug-name", "session list failed ({err}) — project names fall back to paths",
                  vars={"err": f"{type(e).__name__}: {e}"}, soft=True)
    # ⚠`HOME` in this file is **the data dir (`DATA_DIR`, default `~/.mailbox-mcp`)**, not the user's home — measured
    #   2026-08-27: stripping the prefix with it failed and `-Users-me-repo-F` showed up on screen as-is.
    home = _slug(os.path.expanduser("~"))
    return (slug[len(home):].lstrip("-") or "홈") if slug.startswith(home) else slug



# ★**Today's hourly** per-project aggregate (2026-09-04, today-trend view).
#   ccusage has no hourly (only daily·weekly·monthly·session·blocks, and blocks are 5-hour units and
#   not per-project). So count directly from transcripts — measured **0.75s / 192MB / 19 files**,
#   far cheaper than ccusage (34s). Only files touched today, capped at the last 60MB per file.
#   ⚠Because of the tail cap, early hours of very large files may be missing — the screen states that.
TODAY_CAP = 60_000_000
TODAY_CHUNK = 4_000_000
_today = {"at": 0, "by": [], "h0": 0, "h1": 23, "cut": False}
_today_lock = threading.Lock()
# ★Incremental per-file cache (measured: 182 files / 220MB re-read every 30s, one pass +379MB peak,
#   viewer maxrss 127 -> 566MB). Each file keeps its read offset and first-seen responses; a pass reads only
#   appended bytes. ⚠Responses are stored per file (key -> (hour, tok)) and deduplicated across files at
#   aggregation in glob order, so the result equals the old full scan. ⚠Reset on inode change or shrink only.
_today_files = {}
_today_day = [0]
_today_scan_lock = threading.Lock()


def _today_lines(buf, mid, ent):
    """Count the complete lines in `buf` (bytes) into the file entry."""
    keyed, loose = ent["keyed"], ent["loose"]
    for ln in buf.split(b"\n"):
        if b'"usage"' not in ln:          # filter on bytes — most lines are never decoded
            continue
        try:
            e = json.loads(ln.decode("utf-8", "replace"))
        except Exception:
            continue
        t = _line_ts(e, 0)
        if not t or t < mid:
            continue
        u = (e.get("message") or {}).get("usage") or {}
        # ★The definition is `_TOKRE` alone (includes output = ccusage `totalTokens`).
        tok = (int(u.get("input_tokens") or 0) + int(u.get("output_tokens") or 0)
               + int(u.get("cache_read_input_tokens") or 0) + int(u.get("cache_creation_input_tokens") or 0))
        h = time.localtime(t).tm_hour
        k = _resp_key(e)
        if k is None:
            loose[h] += tok
        elif k not in keyed:
            keyed[k] = (h, tok)


def _today_read(fp, st, mid, ent):
    """Read bytes after the entry's offset in chunks; a partial last line stays unread (offset = last newline)."""
    with open(fp, "rb") as f:
        if ent["off"] == 0 and st.st_size > TODAY_CAP:
            f.seek(st.st_size - TODAY_CAP); f.readline(); ent["cut"] = True
        else:
            f.seek(ent["off"])
        off, rest = f.tell(), b""
        while True:
            buf = f.read(TODAY_CHUNK)
            if not buf:
                break
            buf = rest + buf
            nl = buf.rfind(b"\n")
            if nl < 0:
                rest = buf
                continue
            _today_lines(buf[:nl + 1], mid, ent)
            off += nl + 1
            rest = buf[nl + 1:]
            ent["off"] = off
    ent["ino"] = st.st_ino


def _today_fetch(now=None):
    with _today_scan_lock:
        _today_fetch_locked(now)


def _today_fetch_locked(now):
    t0 = now or time.time()
    mid = time.mktime(time.localtime(t0)[:3] + (0, 0, 0, 0, 0, -1))
    if _today_day[0] != mid:
        _today_files.clear()
        _today_day[0] = mid
    live = []
    try:
        pats = (os.path.join(CLAUDE_PROJECTS, "*", "*.jsonl"),) + sub_globs(CLAUDE_PROJECTS)
        for pat in pats:
            for fp in glob.glob(pat):
                try:
                    st = os.stat(fp)
                except OSError:
                    continue
                if st.st_mtime < mid:
                    continue
                ent = _today_files.get(fp)
                if ent is not None and (ent["ino"] != st.st_ino or st.st_size < ent["off"]):
                    ent = None                # replaced or truncated: start this file over
                if ent is None:
                    d = os.path.dirname(fp)
                    # The path is `<project>/<session>/subagents/agent-*.jsonl` — go up **three levels** to reach
                    # the project. Going up only two grouped by session id and inflated 'other' (measured: 215M).
                    # ⚠Workflow-tool agents sit one level deeper — take the session dir's parent, not a fixed depth.
                    base = os.path.dirname(sub_sess_dir(fp)) if sub_sess_dir(fp) else d
                    ent = {"ino": st.st_ino, "off": 0, "slug": os.path.basename(base), "keyed": {},
                           "loose": [0] * 24, "cut": False}
                if st.st_size > ent["off"]:
                    try:
                        _today_read(fp, st, mid, ent)
                    except OSError:
                        _today_files.pop(fp, None)   # vanished after stat — skip this file, not the pass
                        continue
                    except Exception:
                        _today_files.pop(fp, None)   # ⚠half-counted entry must not survive with an old offset
                        raise
                _today_files[fp] = ent
                live.append(fp)
    except Exception as e:
        # ⚠A transcript vanishing between stat and open also lands here and aborts the whole pass.
        warn_once("today-scan", "Today-by-hour scan failed ({err}) — keeping the previous value",
                  vars={"err": type(e).__name__}, soft=True)
        return
    keep = set(live)
    for fp in [p for p in _today_files if p not in keep]:
        del _today_files[fp]
    # ★Deduplicate responses — one response arrives as multiple lines (see ★ above `_resp_key_line`).
    #   Summing per line used to give **×1.97** (measured 2026-09-09 today: 413.3M ↔ real 210.0M).
    agg, seen_resp, cut_hit = {}, set(), False
    for fp in live:
        ent = _today_files[fp]
        cut_hit = cut_hit or ent["cut"]
        row = agg.setdefault(ent["slug"], [0] * 24)
        for h, v in enumerate(ent["loose"]):
            row[h] += v
        for k, (h, v) in ent["keyed"].items():
            if k not in seen_resp:
                seen_resp.add(k)
                row[h] += v
    tot = {k: sum(v) for k, v in agg.items() if sum(v) > 0}
    order = sorted(tot, key=lambda k: -tot[k])
    hrs = [h for h in range(24) if any(agg[k][h] for k in tot)]
    h0 = hrs[0] if hrs else 0
    h1 = max(hrs[-1], time.localtime(t0).tm_hour) if hrs else 23
    by = [{"name": _slug_name(k), "tok": tot[k], "series": agg[k][h0:h1 + 1]} for k in order[:3]]
    rest = order[3:]
    if rest:
        ser = [sum(agg[k][h] for k in rest) for h in range(h0, h1 + 1)]
        if sum(ser) > 0:
            by.append({"name": "기타 %d개" % len(rest), "tok": sum(ser), "series": ser})
    with _today_lock:
        _today.update({"at": time.time(), "by": by, "h0": h0, "h1": h1, "cut": cut_hit})


# ★**Consumption report** (2026-09-04 — split into its own report). Until then each question was answered
#   by typing a table in chat, which is visible only when asked and long. On screen it can be seen anytime.
#   Measures: in the recent window, **per-project context·request count·median per request**, running subagents,
#   and **which compaction window** each session runs with (the setting is read only at session start — see `_compact_win`).
BURN_MIN = 60
_burn = {"at": 0, "min": BURN_MIN, "rows": [], "subs": [], "sess": [], "tot": 0}
_burn_lock = threading.Lock()

# ★Compaction window per session (2026-09-24). Labels used to be hard-coded («300k»/«1M») and keyed on
#   settings.json **mtime** — any edit (e.g. a new Stop hook) flipped every live session to «1M».
#   ⇒ Read `autoCompactWindow` itself and remember when *its value* last changed (COMPACT_STATE).
#   ⚠The first `since` is seeded from the file mtime — approximate (`approx: true`).
#   ⚠Never write settings.json — read only.
CLAUDE_SETTINGS = os.path.join(claude_home(), "settings.json")
COMPACT_STATE = os.path.join(DATA_DIR, "compact-win.json")
COMPACT_DEFAULT = 1_000_000


def _compact_setting():
    """(window, mtime) from settings.json; window None when the file is unreadable (mid-write)."""
    try:
        mt = os.path.getmtime(CLAUDE_SETTINGS)
    except OSError:
        return COMPACT_DEFAULT, 0
    try:
        d = json.loads(read_text(CLAUDE_SETTINGS))
    except (OSError, ValueError):
        return None, mt                  # mid-write settings.json: caller keeps the previous window
    d = d if isinstance(d, dict) else {}   # ⚠a non-object top level / `env` falls back to the default, not a crash
    win = d.get("autoCompactWindow")
    env = d.get("env")
    # An env override in the settings file wins (only window-sized keys, not the *_PCT_* percentage).
    for k, v in (env if isinstance(env, dict) else {}).items():
        ku = k.upper()
        # ⚠Only *WINDOW keys — a DISABLE_AUTOCOMPACT=1 flag must not become a 1-token window.
        if "AUTOCOMPACT" in ku.replace("_", "") and ku.endswith("WINDOW") and "PCT" not in ku:
            win = v
    try:
        win = int(win) if win is not None else COMPACT_DEFAULT
    except (TypeError, ValueError):
        win = COMPACT_DEFAULT
    return (win if win >= 10000 else COMPACT_DEFAULT), mt


def _compact_win(now=None):
    """{value, since, prev, approx} — `since` moves only when the value changes, not on unrelated edits."""
    now = now or time.time()
    try:
        with open(COMPACT_STATE, encoding="utf-8") as f:
            st = json.load(f)
        if not isinstance(st, dict) or "value" not in st:
            st = None
    except Exception:
        st = None
    val, mt = _compact_setting()
    if val is None:
        return st or {"value": None, "since": 0, "prev": None, "approx": True}
    if st is None:
        st = {"value": val, "since": int(mt), "prev": None, "approx": True}
    elif st.get("value") != val:
        st = {"value": val, "since": int(now), "prev": st.get("value"), "approx": False}
    else:
        return st
    try:
        _atomic_write(COMPACT_STATE, json.dumps(st).encode("utf-8"))
    except Exception as e:
        warn_once("compact-win", "compact-win state write failed ({err})", vars={"err": repr(e)}, soft=True)
    return st


def _sess_win(born, cw):
    """Window a session born at `born` runs with, or None when unknown (born before a change we did not record)."""
    if cw.get("value") is None:
        return None
    return cw["value"] if born > (cw.get("since") or 0) else cw.get("prev")


BURN_CAP = 12_000_000
# ★Incremental per-file cache, like `_today_files` (measured: 13 files / 9.7MB re-read every 30s, 110ms CPU,
#   23MB peak, unchanged between passes). Each file keeps its offset and in-window events (t, resp_key, ctx);
#   ⚠dedup across files happens at aggregation in glob order so the result equals the old full scan.
_burn_files = {}
_burn_scan_lock = threading.Lock()


def _burn_read(fp, st, cut, ent):
    """Read bytes after the entry's offset (first read: last BURN_CAP bytes); a partial last line stays unread."""
    with open(fp, "rb") as f:
        if ent["off"] == 0 and st.st_size > BURN_CAP:
            f.seek(st.st_size - BURN_CAP); f.readline()
        else:
            f.seek(ent["off"])
        off = f.tell()
        data = f.read()
    ent["ino"] = st.st_ino
    nl = data.rfind(b"\n")
    if nl < 0:
        return
    ent["off"] = off + nl + 1
    ev = ent["ev"]
    for ln in data[:nl + 1].split(b"\n"):
        if b'"usage"' not in ln:
            continue
        try:
            e = json.loads(ln.decode("utf-8", "replace"))
        except Exception:
            continue
        t = _line_ts(e, 0)
        if not t or t < cut:
            continue
        u = (e.get("message") or {}).get("usage") or {}
        # ⚠This is **context size** — not consumption but "how much that request read", so
        #   output tokens are excluded (deliberately different from `_TOKRE`).
        c = (int(u.get("input_tokens") or 0) + int(u.get("cache_read_input_tokens") or 0)
             + int(u.get("cache_creation_input_tokens") or 0))
        ev.append((t, _resp_key(e), c))


def _burn_fetch(now=None):
    with _burn_scan_lock:
        _burn_fetch_locked(now)


def _burn_fetch_locked(now):
    now = now or time.time()
    cut = now - BURN_MIN * 60
    cw = _compact_win(now)
    stg = cw.get("since") or 0
    agg = {}       # slug -> [ctx sum, request count, [ctx…]]
    subs = []
    sess = []
    # ★Deduplicate responses (★ above `_resp_key_line`). Here even **the request count** was wrong — one response is 2 lines,
    #   so "request count" was doubled while "median per request" was right (copies have the same value). So when the screen
    #   said "400 requests of 170K" there were really 200 (measured 2026-09-09).
    seen_resp = set()
    live = []
    try:
        for pat, is_sub in ((os.path.join(CLAUDE_PROJECTS, "*", "*.jsonl"), False),) + \
                tuple((p, True) for p in sub_globs(CLAUDE_PROJECTS)):
            for fp in glob.glob(pat):
                try:
                    st = os.stat(fp)
                except OSError:
                    continue
                if st.st_mtime < cut:
                    continue
                ent = _burn_files.get(fp)
                if ent is not None and (ent["ino"] != st.st_ino or st.st_size < ent["off"]):
                    ent = None                # replaced or truncated: start this file over
                if ent is None:
                    base = os.path.dirname(fp) if not is_sub else os.path.dirname(sub_sess_dir(fp))
                    ent = {"ino": st.st_ino, "off": 0, "slug": os.path.basename(base), "is_sub": is_sub, "ev": []}
                if st.st_size > ent["off"]:
                    try:
                        _burn_read(fp, st, cut, ent)
                    except OSError:
                        _burn_files.pop(fp, None)   # vanished after stat — skip this file, not the pass
                        continue
                    except Exception:
                        _burn_files.pop(fp, None)   # ⚠half-read entry must not survive with an old offset
                        raise
                ent["ev"] = [x for x in ent["ev"] if x[0] >= cut]
                _burn_files[fp] = ent
                live.append((fp, st))
        keep = set(fp for fp, _st in live)
        for fp in [p for p in _burn_files if p not in keep]:
            del _burn_files[fp]
        for fp, st in live:
            ent = _burn_files[fp]
            slug, is_sub = ent["slug"], ent["is_sub"]
            key = slug + ("\u0000sub" if is_sub else "")
            a = agg.setdefault(key, [0, 0, []])
            n0 = a[1]
            for _t, k, c in ent["ev"]:
                if k is not None:
                    if k in seen_resp:
                        continue
                    seen_resp.add(k)
                a[0] += c; a[1] += 1; a[2].append(c)
            if is_sub and a[1] > n0:
                mp = fp[:-len(".jsonl")] + ".meta.json"
                try:
                    mm = json.load(open(mp, encoding="utf-8"))
                except Exception:
                    mm = {}
                subs.append({"proj": _slug_name(slug), "type": mm.get("agentType") or "?",
                             "desc": redact(mm.get("description") or "")[:44],
                             "depth": int(mm.get("spawnDepth") or 1),
                             "req": a[1] - n0, "run": (now - st.st_mtime) < 120})
            if not is_sub:
                born = getattr(st, "st_birthtime", st.st_ctime)
                sess.append({"proj": _slug_name(slug), "id": _sid8(os.path.basename(fp)),
                             "born": int(born), "new": bool(stg and born > stg),
                             "win": _sess_win(born, cw)})
    except Exception as e:
        warn_once("burn-scan", "Context burn scan failed ({err}) — keeping the previous value",
                  vars={"err": type(e).__name__}, soft=True)
        return
    rows = []
    for key, (c, n, lst) in agg.items():
        if not n:
            continue
        slug, _, sub = key.partition("\u0000")
        lst.sort()
        rows.append({"name": _slug_name(slug) + (" (서브에이전트)" if sub else ""), "ctx": c, "req": n,
                     "med": lst[len(lst) // 2], "per": int(c / max(1, BURN_MIN))})
    rows.sort(key=lambda x: -x["ctx"])
    subs.sort(key=lambda x: -x["req"])
    sess = [x for x in sess if x["proj"]]
    with _burn_lock:
        _burn.update({"at": now, "min": BURN_MIN, "rows": rows[:10], "subs": subs[:10],
                      "sess": sess[:12], "tot": sum(r["ctx"] for r in rows),
                      # ★2026-09-27 cross-tab audit: no "limit" here — it was the abandoned 519M anchor (~8x real).
                      #   ⚠The page divides by BURN.head.lim (burnLim()), the only 5h-limit source.
                      "settingsAt": int(stg), "win": cw.get("value"), "winPrev": cw.get("prev"),
                      "winApprox": bool(cw.get("approx"))})


def _today_loop():
    while True:
        try:
            with boot_queue.gate("today_loop"):   # ⚠first pass waits its boot turn; no-op after drain (traps/server.md)
                _today_fetch()
                _burn_fetch()
            # ★Piggyback the spark snapshot save here (2026-09-09) — `_usage_loop` runs every 900s, so
            #   dying in between loses the whole 10-min window (LIVE_SEC). Instead of a new thread/timer,
            #   ride on this loop that already runs every 30s (disk write is one small JSON, not a new cycle).
            _usage_save()
            _otel_src_save()    # OTel bySrc buckets — self-throttled to 60s; first call loads the file
            _LOOP_ERR.pop("today", None)
            time.sleep(30)  # ★2026-09-04: today-only refreshed every 30s — measured 0.75s, no burden
        except Exception as e:
            warn_once("loop:today", "Today's hourly totals stopped refreshing — {err}",
                      vars={"err": f"{type(e).__name__}: {e}"[:140]})
            _LOOP_ERR["today"] = {"at": time.time(), "err": f"{type(e).__name__}: {e}"[:160]}
            time.sleep(60)          # ⚠the exception path must sleep too — otherwise it becomes a tight infinite loop
            continue
