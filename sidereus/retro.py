"""Retrospect view (GET /api/retro?days=N) — failure trend, weekly summary, tokens per commit."""
import os
import subprocess
import threading
import time
from sidereus.gitinfo import DIFF_TIMEOUT, _git_root, _git_run
from sidereus.otel import _otel_src_heat, _otel_src_models, _otel_tools_summary, _otel_tool_rank
from sidereus.otel_cache import _oc_view
from sidereus.otel_hooks import _oh_view
from sidereus.otel_acct import _oa_snap
from sidereus.failures import _fail_events, _pub_sig
from sidereus.history import history
from sidereus.timefmt import ymd as _rt_day


# ── Retrospect (GET /api/retro) ───────────────────────────────────────────────
# ★No new scanner: tokens/sessions come from `history()` (usage index, metadata only) and failures from
#   `_fail_events()` (grade/kind already assigned there) — this module only folds them by day/week/project.
# ⚠Fetched only when the tab opens; never attached to `state()`. Cached per range for RETRO_TTL_S.
RETRO_DAYS = (7, 30)
RETRO_TTL_S = 120
RETRO_GIT_MAX = 40          # cap on repos asked for commits (one `git log` each)
_retro_lock = threading.Lock()
_retro_cache = {}           # (days, account label) -> (measured at, result, history body)


def _rt_week(d):
    """Monday (local) of the week containing date string `d`."""
    t = time.mktime(time.strptime(d + " 12", "%Y-%m-%d %H"))
    return _rt_day(t - time.localtime(t).tm_wday * 86400)


def _retro_git(cwd, since):
    """[(sha, unix time)] on local branches since `since`, limited to `cwd` (a subdir project counts only its own files)."""
    try:
        r = _git_run(cwd, ["log", "--branches", "--no-merges",
                           "--since=@%d" % int(since), "--format=%H %ct", "--", "."], DIFF_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    out = []
    for ln in r.stdout.splitlines():
        p = ln.split()
        if len(p) == 2 and p[1].isdigit():
            out.append((p[0], int(p[1])))
    return out


RETRO_WHERE_MAX = 8        # sessions listed under one failure row


def _rt_where_add(w, ev):
    """Count one event under its owning session. ⚠Metadata only (sid · cwd · project · count · time) — never ev text/sig."""
    sid = ev.get("sid") or ""
    if not sid:
        return
    x = w.get(sid)
    if x is None:
        x = w[sid] = {"sid": sid, "cwd": ev.get("cwd") or "", "project": ev.get("proj") or "", "n": 0, "last": 0}
    x["n"] += 1
    x["last"] = max(x["last"], int(ev.get("at") or 0))


def _rt_sigs_out(sigs):
    """Top 8 by count, plus any sig holding «to check» events so the grade summary can point at them."""
    order = sorted(sigs.values(), key=lambda s: (-s["n"], -s["last"]))
    pick = order[:8] + [s for s in order[8:] if s["chk"]][:8]
    out = []
    for s in pick:
        ws = sorted(s["_w"].values(), key=lambda x: (-x["n"], -x["last"]))
        o = {k: v for k, v in s.items() if k != "_w"}
        o["where"], o["wn"] = ws[:RETRO_WHERE_MAX], len(ws)
        out.append(o)
    return out


def _rt_cache_join(cache, hist):
    """Attach path/project from the history rows to each cache session; unmatched => 8-char sid only (metadata only)."""
    who = {}
    for dd in (hist.get("list") or []):
        for r in (dd.get("rows") or []):
            if r.get("sid") and r["sid"] not in who:
                who[r["sid"]] = (r.get("cwd") or "", r.get("project") or "")
    ss = []
    for x in ((cache or {}).get("sessions") or []):
        sid = str(x.get("sid") or "")
        o = {"sid": sid, "read": x.get("read") or 0, "create": x.get("create") or 0, "pct": x.get("pct") or 0}
        if sid in who:
            o["path"], o["project"] = who[sid]
        else:
            o["sid"] = sid[:8]
        ss.append(o)
    return {"days": list((cache or {}).get("days") or []), "sessions": ss}


def _retro_build(days, now, hist, evs, commits, tools, rank=None, cache=None, heat=None, models=None, hooks=None):
    """Pure fold. hist = history() body · evs = _fail_events() list · commits = {project: [(sha, ts)]} or None per project."""
    dates = [_rt_day(now - (days - 1 - i) * 86400) for i in range(days)]
    first = dates[0]
    dmap = {d: {"d": d, "tok": 0, "cost": 0.0, "sess": set(), "commits": 0, "fails": 0, "kinds": {}}
            for d in dates}
    projs = {}
    for dd in (hist.get("list") or []):
        for r in (dd.get("rows") or []):
            d = dmap.get(r.get("date"))
            if d is None:
                continue
            d["tok"] += r.get("tok") or 0
            d["cost"] += r.get("cost") or 0.0
            d["sess"].add(r.get("sid"))
            name = r.get("project") or "?"
            p = projs.setdefault(name, {"project": name, "tok": 0, "cost": 0.0, "sess": set(),
                                        "commits": None, "byw": {}})
            p["tok"] += r.get("tok") or 0
            p["cost"] += r.get("cost") or 0.0
            p["sess"].add(r.get("sid"))
            w = _rt_week(r["date"])
            p["byw"][w] = p["byw"].get(w, 0) + (r.get("tok") or 0)
    kinds, grades, sigs = {}, {}, {}
    for ev in evs:
        d = dmap.get(_rt_day(ev.get("at") or 0))
        if d is None:
            continue
        k = ev.get("kind") or "?"
        d["fails"] += 1
        d["kinds"][k] = d["kinds"].get(k, 0) + 1
        kinds[k] = kinds.get(k, 0) + 1
        g = ev.get("grade") or "check"
        grades[g] = grades.get(g, 0) + 1
        # ⚠`_pub_sig`: tool/hook sigs are raw-output derived — send the fixed label + tool name only (rule 1, 2026-09-25).
        sg = _pub_sig(ev) if ev.get("sig") else ""
        s = sigs.get(sg)
        if s is None:
            s = sigs[sg] = {"sig": sg, "kind": k, "grade": g, "n": 0, "last": 0, "chk": 0, "_w": {}}
        s["n"] += 1
        s["last"] = max(s["last"], ev.get("at") or 0)
        s["chk"] += 1 if g == "check" else 0
        _rt_where_add(s["_w"], ev)
    seen = set()
    for name, cs in (commits or {}).items():
        p = projs.get(name)
        if p is None or cs is None:
            continue
        p["commits"] = 0
        for sha, ts in cs:
            dd = _rt_day(ts)
            if dd < first or dd not in dmap:
                continue
            p["commits"] += 1
            if sha not in seen:      # a sha reached from two projects counts once in day/week totals
                seen.add(sha)
                dmap[dd]["commits"] += 1
    weeks = {}
    for d in dates:
        x = dmap[d]
        w = weeks.setdefault(_rt_week(d), {"week": _rt_week(d), "from": d, "to": d, "days": 0, "tok": 0,
                                           "cost": 0.0, "sess": set(), "commits": 0, "fails": 0})
        w["to"] = d
        w["days"] += 1
        w["tok"] += x["tok"]
        w["cost"] += x["cost"]
        w["sess"] |= x["sess"]
        w["commits"] += x["commits"]
        w["fails"] += x["fails"]
    wk = []
    for w in sorted(weeks.values(), key=lambda v: v["week"], reverse=True):
        top = sorted(((p["byw"].get(w["week"], 0), n) for n, p in projs.items()), reverse=True)
        wk.append({"week": w["week"], "from": w["from"], "to": w["to"], "days": w["days"], "tok": w["tok"],
                   "cost": round(w["cost"], 4), "sessions": len(w["sess"]), "commits": w["commits"],
                   "fails": w["fails"], "top": [{"project": n, "tok": t} for t, n in top[:3] if t > 0]})
    pr = []
    for p in sorted(projs.values(), key=lambda v: -v["tok"])[:30]:
        c = p["commits"]
        pr.append({"project": p["project"], "tok": p["tok"], "cost": round(p["cost"], 4),
                   "sessions": len(p["sess"]), "commits": c,
                   "tpc": (int(p["tok"] / c) if c else None)})
    trows = [r for r in ((tools or {}).get("rows") or []) if len(r) >= 3 and r[2] > 0][:8]
    return {"ok": True, "days": days, "at": int(now),
            "daily": [{"d": x["d"], "tok": x["tok"], "cost": round(x["cost"], 4), "sessions": len(x["sess"]),
                       "commits": x["commits"], "fails": x["fails"], "kinds": x["kinds"]} for x in dmap.values()],
            "kinds": kinds, "grades": grades, "fails": sum(kinds.values()),
            "sigs": _rt_sigs_out(sigs),
            "weeks": wk, "projects": pr,
            "tools": {"rows": trows, "since": (tools or {}).get("since") or 0},
            "rank": rank, "time": (rank or {}).get("time"),
            "cache": _rt_cache_join(cache, hist), "heat": heat, "models": models, "hooks": hooks}


def _retro_commits(hist, since):
    """{project: [(sha, ts)] | None} — one `git log` per project, from its shortest existing cwd (main checkout over worktrees)."""
    cw = {}
    for dd in (hist.get("list") or []):
        for r in (dd.get("rows") or []):
            c, name = r.get("cwd") or "", r.get("project") or "?"
            if c and (name not in cw or len(c) < len(cw[name])) and os.path.isdir(c):
                cw[name] = c
    out = {}
    for name, c in sorted(cw.items(), key=lambda kv: kv[0])[:RETRO_GIT_MAX]:
        out[name] = _retro_git(c, since) if _git_root(c) else None
    return out


def _retro_acct(base, days, now, acct, key):
    """All body with the six OTel cards redrawn from one account's buckets; «Tools failing most» stays All."""
    since = time.mktime(time.strptime(_rt_day(now - (days - 1) * 86400), "%Y-%m-%d"))
    sd = _rt_day(since)
    snap, first = _oa_snap(key)
    rank = _otel_tool_rank(sd, src=snap["t"])
    out = dict(base[1])
    out.update(rank=rank, time=(rank or {}).get("time"), cache=_rt_cache_join(_oc_view(sd, src=snap["c"]), base[2]),
               heat=_otel_src_heat(since, now, src=snap["s"]), models=_otel_src_models(since, now, src=snap["s"]),
               hooks=_oh_view(sd, src=snap["h"]), acct=acct, acctSince=_rt_day(first or now))
    return out


def retro(days=7, acct="", key=None):
    """Body of `GET /api/retro?days=N[&acct=label]`. acct = account label ("" = All); key = its otel_acct key
    ("" for the primary, defaults to the label). ⚠The route validates the label against claude_roots.accounts()."""
    try:
        days = int(days or 7)
    except (TypeError, ValueError):
        days = 7
    if days not in RETRO_DAYS:
        days = RETRO_DAYS[0]
    acct = acct if isinstance(acct, str) else ""
    # ⚠One lock across the build: a second tab/request waits for the first result instead of rescanning.
    with _retro_lock:
        now = time.time()
        c = _retro_cache.get((days, acct))
        if c and now - c[0] < RETRO_TTL_S:
            return c[1]
        base = _retro_cache.get((days, ""))
        if not (base and now - base[0] < RETRO_TTL_S):
            base = _retro_all(days, now)
        if not acct:
            return base[1]
        out = _retro_acct(base, days, now, acct, acct if key is None else key)
        _retro_cache[(days, acct)] = (time.time(), out, base[2])
        return out


def _retro_all(days, now):
    """Build and cache the All body. ⚠Caller holds `_retro_lock`."""
    t0 = time.time()
    hist = history(days)
    since = time.mktime(time.strptime(_rt_day(now - (days - 1) * 86400), "%Y-%m-%d"))
    # ⚠capped=False: the tab's file caps (60 main · 400 sub) dropped most of 30 days (measured 453 of 1,030 files).
    evs, _n, _h = _fail_events(max(24, (now - since) / 3600 + 1), capped=False)
    out = _retro_build(days, now, hist, evs, _retro_commits(hist, since), _otel_tools_summary(),
                       _otel_tool_rank(_rt_day(since)), _oc_view(_rt_day(since)), _otel_src_heat(since, now),
                       _otel_src_models(since, now), _oh_view(_rt_day(since)))
    out["ms"] = int((time.time() - t0) * 1000)
    c = _retro_cache[(days, "")] = (time.time(), out, hist)
    return c
