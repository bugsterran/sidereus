"""Past session history (GET /api/history)."""
import json
import os
import threading
import time
from sidereus import claude_roots
from sidereus.memo import BoundedMemo
from sidereus.redact import redact
from sidereus.transcript import CLAUDE_PROJECTS, _model_label
from sidereus.ident import _cwd_from_slug, _proj_name, _sid8
from sidereus.usage import _cost4, _uidx, _uidx_lock, _uidx_refresh
from sidereus.usage_index import _model_disp, _uidx_snap
from sidereus.live import _sid_transcript, sid_alive
from sidereus.agents import _agent_fin, _agent_meta, _agent_tools, slash, sub_sess_dir
from sidereus.work import _SID_SAFE, _under_projects
from sidereus.ext import PLAT_MODS
from sidereus.warn import warn_once
from sidereus.timefmt import ymd


# ── Past session history (GET /api/history) ─────────────────────────────────
# ★Why no new scanner: `usage-index.json` already holds **hour buckets of every transcript**
#   (incremental 0.05 s). The list (`sessions()`) cuts at `max_age_h=12`, so sessions older than 12 h vanish
#   from the screen entirely; this view picks up from there.
# ⚠Builds **metadata only** — transcripts are never opened, so conversation cannot leak in.
# ⚠Resolution is **the hour bucket**. Minute-level start/end is not in this source ⇒ reported as `hours` (active hour count).
# ⚠External CLI sessions: not from `ext-sessions.json` (purged after 24h). Each platform comes from its own record
#   files (`ext.PLAT_MODS[..].scan`) into a separate per-day block (`gm`, `cx`, ...) — never into the Claude `rows`/totals.
HIST_TTL_S = 60           # same args within this window are not rescanned (runs only when the view is opened)
HIST_MAX_DAYS = 90
_hist_lock = threading.Lock()
_hist_cache = {}          # days -> (measured at, result)
_hist_cwd = {}            # slug -> cwd. `.` also becomes `-` in slugs, so some cannot be reversed


def _cwd_probe(slug):
    """When `_cwd_from_slug` comes back empty (`-home-me--mailbox-mcp` → `/home/me/.mailbox-mcp`),
    pull **just the `cwd` field** from a transcript. ⚠Conversation is not read — stops as soon as found."""
    fns = []
    for p in claude_roots.projects_dirs(CLAUDE_PROJECTS):   # the slug may live in any Claude root
        d = os.path.join(p, slug)
        try:
            fns += [os.path.join(d, fn) for fn in os.listdir(d) if fn.endswith(".jsonl")]
        except OSError:
            continue
    try:
        fns = sorted(fns, key=lambda fp: -os.path.getmtime(fp))[:2]
    except OSError:
        return ""
    for fn in fns:
        read = 0
        try:
            with open(fn, "rb") as f:
                while read < 4000000:           # cap — some files start with a huge snapshot line
                    raw = f.readline()
                    if not raw:
                        break
                    read += len(raw)
                    if b'"cwd"' not in raw:
                        continue
                    try:
                        c = json.loads(raw).get("cwd")
                    except Exception:
                        continue
                    if c and os.path.isdir(c):
                        return c
        except OSError:
            continue
    return ""


def _title_branch(ent):
    """(title, branch) from a usage-index entry — `/rename` beats the auto title; both come from Claude Code records."""
    return ((ent.get("tc") or ent.get("ti") or ""), (ent.get("br") or ""))


def _cross(hs, frm, last):
    """(runFrom, runTo) of a day row whose hours run on across local midnight, else None.
    ⚠Rows are split per local day, so a session active 23:00-01:00 showed «23:00~00:00» and «00:00~01:00»
    with nothing tying them; the run is walked through consecutive hour buckets in `hs` (all days of that sid)."""
    d = ymd(frm)
    rf = rt = None
    k = frm
    if (k - 3600) in hs and ymd(k - 3600) != d:
        while (k - 3600) in hs:
            k -= 3600
        rf = k
    k = last
    if (k + 3600) in hs and ymd(k + 3600) != d:
        while (k + 3600) in hs:
            k += 3600
        rt = k + 3600
    return rf, rt


def _day_order(rs):
    """Rows of one day: newest start first (ties: later end first) — the tab lists days newest first too."""
    return sorted(rs, key=lambda r: (-r["from"], -r["to"]))


def _plat_days(cutday, since, scan, key):
    """{date: {n, tok, cost, costMiss, rows}} from one platform's `scan` (`ext.PLAT_MODS`), bucketed by hour
    like the Claude rows. ⚠Kept apart from the Claude `rows`/totals — `retro()` sums those and must stay Claude-only."""
    agg, hs = {}, {}
    for c in scan(since):
        sk = c.get("parent") or c["sid"]      # a CLI subagent chat folds into its parent session's row
        for _mid, (i, o, ca, t, ts, mdl, usd) in c["msgs"].items():
            if not ts:
                continue
            ki = int(ts // 3600 * 3600)
            hs.setdefault(sk, set()).add(ki)
            d = ymd(ki)
            if d < cutday:
                continue
            a = agg.get((d, sk))
            if a is None:
                a = agg[(d, sk)] = {"c": c, "from": ki, "to": ki, "hrs": set(), "tok": 0,
                                          "cost": None, "miss": 0, "m": {}}
            elif not c.get("parent"):
                a["c"] = c                        # the parent's own chat wins over a subagent seen first
            a["from"], a["to"] = min(a["from"], ki), max(a["to"], ki)
            a["hrs"].add(ki)
            n = i + o + ca + t
            a["tok"] += n
            a["m"][mdl] = a["m"].get(mdl, 0) + n
            if usd is None:
                a["miss"] += 1
            else:
                a["cost"] = (a["cost"] or 0.0) + usd
    byd = {}
    for (d, sid), a in agg.items():
        c = a["c"]
        top = max(a["m"].items(), key=lambda kv: kv[1])[0] if a["m"] else ""
        rf, rt = _cross(hs.get(sid, ()), a["from"], a["to"])
        byd.setdefault(d, []).append({
            "date": d, "sid": sid, "id": _sid8(sid), "slug": "", "cwd": c["cwd"], "project": c["project"],
            "plat": key, "model": top, "models": len(a["m"]),
            "from": a["from"], "to": a["to"] + 3600, "hours": len(a["hrs"]), "tok": a["tok"],
            "cost": 0, "estCost": None if a["cost"] is None else round(a["cost"], 4), "costMiss": a["miss"],
            "sub": 0, "title": "", "branch": "", "runFrom": rf, "runTo": rt})
    out = {}
    for d, rs in byd.items():
        ec = [r["estCost"] for r in rs if r["estCost"] is not None]
        out[d] = {"n": len(rs), "tok": sum(r["tok"] for r in rs),
                  "estCost": round(sum(ec), 4) if ec else None, "costMiss": sum(r["costMiss"] for r in rs),
                  "rows": _day_order(rs)}
    return out


def history(days=7):
    """Body of `GET /api/history?days=N` — folds past sessions into **date × session**."""
    try:
        days = int(days or 7)
    except (TypeError, ValueError):
        days = 7
    days = max(1, min(days, HIST_MAX_DAYS))
    now = time.time()
    with _hist_lock:
        c = _hist_cache.get(days)
        if c and now - c[0] < HIST_TTL_S:
            return c[1]
    t0 = time.time()
    _uidx_refresh()
    with _uidx_lock:
        items = [(fp, e.get("sl") or "?", _uidx_snap(e.get("h"))) for fp, e in _uidx["files"].items()]
        meta = {fp: _title_branch(e) for fp, e in _uidx["files"].items() if "/subagents/" not in slash(fp)}
    cutday = ymd(now - (days - 1) * 86400)
    agg, dc, hs = {}, {}, {}
    for fp, slug, h in items:
        sub = "/subagents/" in slash(fp)
        if sub:
            # `<project>/<session>/subagents/agent-*.jsonl` — subagent share goes onto **the parent session**
            sid = os.path.basename(sub_sess_dir(fp))   # plain or Workflow-tool agent (one level deeper)
        else:
            sid = os.path.basename(fp)
            if sid.endswith(".jsonl"):
                sid = sid[:-6]
        hset = hs.setdefault(sid, set())
        for k, mm in h.items():
            ki = int(k)
            hset.add(ki)
            d = dc.get(ki)
            if d is None:
                d = dc[ki] = ymd(ki)
            if d < cutday:
                continue
            a = agg.get((d, sid))
            if a is None:
                a = agg[(d, sid)] = {"date": d, "sid": sid, "slug": slug, "from": ki, "to": ki,
                                     "hrs": set(), "tok": 0, "cost": 0.0, "m": {}, "subf": set(),
                                     "tb": ("", ""), "fp": fp}
            if not sub:
                a["tb"] = meta.get(fp) or ("", "")
                a["fp"] = fp
            a["from"] = min(a["from"], ki)
            a["to"] = max(a["to"], ki)
            a["hrs"].add(ki)
            if sub:
                a["subf"].add(fp)
            for mdl, v in mm.items():
                t = v[0] + v[1] + v[2] + v[3]
                a["tok"] += t
                a["cost"] += _cost4(mdl, v)
                md = _model_disp(mdl)             # tier/TTL keys merge into one model
                a["m"][md] = a["m"].get(md, 0) + t
    cw = {}                                   # slug -> cwd (isdir once per slug)
    ac = {}                                   # sid -> account label ('' = primary)
    byd = {}
    for a in agg.values():
        slug = a["slug"]
        if slug not in cw:
            try:
                cw[slug] = _cwd_from_slug(slug) or _hist_cwd.get(slug) or _cwd_probe(slug)
            except Exception:
                cw[slug] = ""
            if cw[slug]:
                _hist_cwd[slug] = cw[slug]      # slug->path never changes — dig it once
        cwd = cw[slug]
        top = max(a["m"].items(), key=lambda kv: kv[1])[0] if a["m"] else ""
        rf, rt = _cross(hs.get(a["sid"], ()), a["from"], a["to"])
        byd.setdefault(a["date"], []).append({
            "date": a["date"], "sid": a["sid"], "id": _sid8(a["sid"]), "slug": slug, "cwd": cwd,
            "project": _proj_name(cwd) or slug.lstrip("-"),
            "plat": "cc",                     # this source is Claude transcripts only (see ⚠ above)
            "model": _model_label(top), "models": len(a["m"]),
            "from": a["from"], "to": a["to"] + 3600, "hours": len(a["hrs"]),
            "tok": a["tok"], "cost": round(a["cost"], 4), "sub": len(a["subf"]),
            "title": a["tb"][0], "branch": a["tb"][1], "runFrom": rf, "runTo": rt})
        # Account picker filter key; primary rows get no key so the goldens stay byte-equal (as timeline.py).
        if a["sid"] not in ac:
            ac[a["sid"]] = claude_roots.acct_of(a["sid"], a["fp"])[0]
        if ac[a["sid"]]:
            byd[a["date"]][-1]["acct"] = ac[a["sid"]]
    out = {"ok": True, "days": days, "at": time.time(), "n": len(agg), "list": [
        {"date": d, "n": len(rs), "tok": sum(r["tok"] for r in rs),
         "cost": round(sum(r["cost"] for r in rs), 4),
         "rows": _day_order(rs)}
        for d, rs in sorted(byd.items(), reverse=True)]}
    blocks = []
    for plat, m in PLAT_MODS.items():
        try:
            blocks.append((m.KEY, _plat_days(cutday, time.mktime(time.strptime(cutday, "%Y-%m-%d")), m.scan, m.KEY)))
        except Exception as e:                # a broken record file must not take the Claude history down
            warn_once("hist-" + plat, "Could not read {name} history ({err})",
                      vars={"name": m.NAME, "err": f"{type(e).__name__}: {e}"})
    if any(b for _k, b in blocks):
        have = {x["date"]: x for x in out["list"]}
        for bk, b in blocks:
            for d, g in b.items():
                if d not in have:
                    have[d] = {"date": d, "n": 0, "tok": 0, "cost": 0.0, "rows": []}
                have[d][bk] = g
        out["list"] = [have[d] for d in sorted(have, reverse=True)]
    out["ms"] = int((time.time() - t0) * 1000)
    with _hist_lock:
        _hist_cache[days] = (time.time(), out)
    return out


# ── Work units of one past session (GET /api/history/units?sid=) ────────────
# Clicking a history row lists the main session + each sub-agent, each opening /work.
# ⚠Metadata only — type, the Agent tool `description` (same field the timeline shows), times, tokens, tool count.
#   Tokens come from the usage index; times are file birth/mtime; the tool count reuses `_agent_tools` (cached, incremental).
# ⚠The main transcript is never scanned (it grows to 910MB) ⇒ its tool count is `None`, not an estimate.
UNITS_TTL_S = 30
UNITS_MAX = 200               # cap on listed sub-agents per session
UNITS_LIVE_S = 120            # an unfinished agent written this recently counts as running
_units_cache = BoundedMemo(64)   # sid -> (measured at, result)


def _idx_tok(h):
    return sum(v[0] + v[1] + v[2] + v[3] for mm in (h or {}).values() for v in mm.values())


def _born_end(fp):
    st = os.stat(fp)
    return int(getattr(st, "st_birthtime", st.st_ctime)), int(st.st_mtime)


def history_units(sid):
    """Body of `GET /api/history/units?sid=` — the main session and its sub-agents, sorted by start."""
    sid = str(sid or "")
    if not _SID_SAFE.match(sid):
        return {"ok": False, "msg": "Invalid session id"}
    now = time.time()
    with _hist_lock:
        c = _units_cache.get(sid)
        if c and now - c[0] < UNITS_TTL_S:
            return c[1]
    _uidx_refresh()
    tail = os.sep + sid + ".jsonl"
    with _uidx_lock:
        main = next((fp for fp in _uidx["files"] if fp.endswith(tail) and "/subagents/" not in slash(fp)), "")
        subtok = {fp: _idx_tok(e.get("h")) for fp, e in _uidx["files"].items()
                  if ("/" + sid + "/subagents/") in slash(fp)}
        mh = dict((_uidx["files"].get(main) or {}).get("h") or {}) if main else {}
        mtok = _idx_tok(mh)
    main = main or _sid_transcript(sid)
    if not main or not _under_projects(main) or not os.path.isfile(main):
        return {"ok": False, "msg": "Could not find the transcript for session {sid}.", "vars": {"sid": _sid8(sid)}}
    slug = os.path.basename(os.path.dirname(main))
    cwd = _hist_cwd.get(slug) or _cwd_from_slug(slug) or _cwd_probe(slug)
    if cwd:
        _hist_cwd[slug] = cwd
    units = []
    try:
        b, e = _born_end(main)
        # A resumed session's file is born weeks earlier (measured 42 days) ⇒ span from index hour buckets, clamped to the file.
        hk = sorted(int(k) for k in mh)
        if hk:
            b, e = max(b, hk[0]), min(e, hk[-1] + 3600)
        units.append({"kind": "main", "tid": ("sess:" + cwd + "|" + sid) if cwd else "", "type": "main", "desc": "",
                      "start": b, "end": e, "tok": mtok, "tc": None, "depth": 0, "hours": len(hk) or None,
                      "st": "run" if sid_alive(sid) else "end"})
    except OSError:
        pass
    for tid, m in sorted(_agent_meta(main[:-len(".jsonl")], ttl=10).items())[:UNITS_MAX]:
        f2 = m.get("_file") or ""
        try:
            b, e = _born_end(f2)
        except OSError:
            continue
        fin = _agent_fin(f2)
        units.append({"kind": "agent", "tid": tid + "|" + sid, "aid": m.get("_id") or "",
                      "type": m.get("agentType") or "agent", "desc": redact(m.get("description") or "")[:80],
                      "start": b, "end": e, "tok": subtok.get(f2, 0), "tc": _agent_tools(f2),
                      "depth": int(m.get("spawnDepth") or 1),
                      "st": "done" if fin else ("run" if now - e < UNITS_LIVE_S else "cut")})
    units.sort(key=lambda u: (u["kind"] != "main", u["start"]))
    out = {"ok": True, "sid": sid, "cwd": cwd, "project": _proj_name(cwd) or slug.lstrip("-"),
           "units": units, "at": now}
    with _hist_lock:
        _units_cache.put(sid, (now, out))
    return out
