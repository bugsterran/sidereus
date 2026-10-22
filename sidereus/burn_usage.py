"""Weekly per-project usage and the live buckets behind `/api/wkuse` (split from burn.py 2026-09-24).

`sidereus.burn` re-exports the names chat_server imports; the functions and their globals live here.
Today/burn buckets, compaction window and `_slug_name` moved to `sidereus.burn_scan` (2026-09-25); `_today_loop` is re-exported.
⚠Patch `_wkuse_by`/`WK_*`/`USAGE_LOCAL`/... on this module; `CLAUDE_SETTINGS`/`COMPACT_STATE`/`_slug_name` on `sidereus.burn_scan`."""
import json
import os
import subprocess
import threading
import time
from sidereus.warn import _LOOP_ERR, warn_once
from sidereus import boot_queue
from sidereus.ident import _sid8, _slug, bin_path, rich_env
from sidereus.usage import (LIVE_SEC, LIVE_STEP, USAGE_LOCAL, _ccusage_lock, _sid_proj,
    _uidx_projects, _usage, _usage_lock)
from sidereus.agentcost import agentcost
from sidereus.burn_scan import _burn, _burn_lock, _slug_group, _slug_name, _today, _today_lock
from sidereus.burn_scan import _today_loop  # noqa: F401  (re-exported for sidereus.burn)



# ★Weekly per-project tokens (2026-08-27) — `ccusage daily --instances --since` gives per-project daily
#   rows (measured: projects{slug: [daily rows…]}). `session --since` only **selects sessions** by the period and
#   gives those sessions' **full totals**, so it is not weekly — hence daily.
#   Scratchpad sessions fold into one row (`_slug_group`, see `sidereus.burn_scan`).


# ★Cache **separately per period** so the period is selectable (2026-09-04, token report needed a
#   selectable period). Previously there was only 7 days, so the report was always weekly.
#   ⚠Do not overwrite one dict per period — requesting 30 days would erase the sidebar's 7 days.
#     The period is the key. The default (7 days) is filled by the loop every 15 min; others are measured only on request.
_wkuse_by = {}
_WK_RANGES = (1, 7, 30)        # day · week · month
# Per-account slots {(days, label): slot}; ⚠kept apart from `_wkuse_by` so `_wkuse_loop` never refreshes them.
_wkuse_acct = {}
WK_ACCT_ERR = "Per-account totals need the local usage index"


def _wk_slot(days, acct=""):
    if acct:
        return _wkuse_acct.setdefault((int(days), acct), {"at": 0.0, "rows": [], "total": 0,
                                                          "days": int(days), "err": ""})
    return _wkuse_by.setdefault(int(days), {"at": 0.0, "rows": [], "total": 0,
                                            "days": int(days), "err": ""})


_wkuse_lock = threading.Lock()
WK_DAYS = 7


def _live_buckets():
    """Fold the last LIVE_SEC seconds into LIVE_STEP-second buckets — counts only what OTel has accumulated, so cost is 0.

    ★It was inline in `wkuse()` and was **pulled out** (2026-09-04 — it had to move truly in real time).
      `/api/wkuse` runs every 30s (it also carries the daily aggregate·donut), but the live part needs
      to be checked more often — hence a separate `/api/live` that calls only this function."""
    nb = LIVE_SEC // LIVE_STEP
    buck = [0] * nb
    try:
        nw = time.time()
        with _usage_lock:
            # ★`spark`, not `live` — `live` is emptied by the backfill every 15 min (see `_usage` comment above)
            rows = list(_usage.get("spark") or [])
        for ts, tk in rows:
            age = int((nw - ts) // LIVE_STEP)
            if 0 <= age < nb:
                buck[nb - 1 - age] += int(tk or 0)
    except Exception:
        buck = [0] * nb
    return buck


def _wk_load(nd, since, slot, acct=""):
    """Raw `projects` for the period; None after recording a ccusage failure in `slot`."""
    if acct:
        # ccusage has no per-file account, so a pick works only on the local index.
        if not USAGE_LOCAL:
            with _wkuse_lock:
                slot["err"] = WK_ACCT_ERR
            return None
        return _uidx_projects(nd, acct)
    if USAGE_LOCAL:
        # ★Built from the local index — **same shape** as `ccusage daily --instances`, so the rest is unchanged.
        #   Measured 2026-09-11 side by side (7 days): ccusage 32.13s ↔ local 0.05s, and
        #   tokens·cost·mix·11 projects·per-model **all matched to the digit** (0.0000% error).
        return _uidx_projects(nd)
    with _ccusage_lock:  # 34s alone · over 90s when overlapping → serialize + generous cap
        r = subprocess.run([bin_path("ccusage"), "daily", "--json", "--instances", "--since", since],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=180, env=rich_env())
    if r.returncode != 0 or not (r.stdout or "").strip():
        with _wkuse_lock:
            slot["err"] = f"ccusage rc={r.returncode}: {(r.stderr or '')[:120]}"
        return None
    return (json.loads(r.stdout) or {}).get("projects") or {}


def _wk_fold(P):
    """★Fold once here — rows·daily·trend·mix all re-scan this P,
    so folding each separately later would make four places disagree."""
    _g = {}
    for _sl, _v in P.items():
        _m = _g.setdefault(_slug_group(_sl), {})
        for _d in (_v if isinstance(_v, list) else (_v.get("daily") or [])):
            _k = _d.get("date")
            if not _k:
                continue
            _a = _m.get(_k)
            if _a is None:
                _a = _m[_k] = {"date": _k, "inputTokens": 0, "outputTokens": 0,
                               "cacheCreationTokens": 0, "cacheReadTokens": 0,
                               "totalTokens": 0, "totalCost": 0.0, "modelBreakdowns": []}
            for _f in ("inputTokens", "outputTokens", "cacheCreationTokens",
                       "cacheReadTokens", "totalTokens"):
                _a[_f] += _d.get(_f) or 0
            _a["totalCost"] += _d.get("totalCost") or 0
            _a["modelBreakdowns"].extend(_d.get("modelBreakdowns") or [])
    return {_k: sorted(_m.values(), key=lambda x: x["date"]) for _k, _m in _g.items()}


# ⚠`_slug_name` matches a slug against cwds in the live session snapshot, which is empty at startup and holds only
#   current sessions — so periods fetched at different moments named one project two ways (".mailbox-mcp" vs the
#   path fallback "mailbox-mcp"). A session-matched name is kept here, beats a later fallback and is re-applied on serve.
_WK_NAMES = {}
WK_NAMES_MAX = 1024


def _wk_is_fallback(slug, name):
    """True when `name` is `_slug_name`'s no-session path fallback (⚠mirrors its tail in `sidereus.burn_scan`)."""
    if name == slug:
        return True
    home = _slug(os.path.expanduser("~"))
    return slug.startswith(home) and slug[len(home):].lstrip("-") in (name, "")


def _wk_namer():
    """One resolver per fetch: each slug through `_slug_name` once (it walks sessions_rows()), learned name over fallback."""
    memo = {}

    def nm(sl):
        n = memo.get(sl)
        if n is None:
            n = _slug_name(sl)
            if _wk_is_fallback(sl, n):
                n = _WK_NAMES.get(sl, n)
            else:
                if len(_WK_NAMES) >= WK_NAMES_MAX:
                    _WK_NAMES.clear()
                _WK_NAMES[sl] = n
            memo[sl] = n
        return n
    return nm


def _wk_rename(out):
    """Re-apply learned names to a served slot copy — a slot fetched before the name was learned keeps the fallback otherwise."""
    nm = dict(_WK_NAMES)
    if not nm:
        return out
    if "rows" in out:
        out["rows"] = [dict(r, name=nm.get(r.get("slug"), r.get("name"))) for r in out["rows"] or []]
    if "trend" in out:
        out["trend"] = [dict(t, name=nm.get(t.get("slug"), t.get("name"))) for t in out["trend"] or []]
    if "daily" in out:
        out["daily"] = [dict(x, top=[dict(p, name=nm.get(p.get("slug"), p.get("name"))) for p in x.get("top") or []])
                        for x in out["daily"] or []]
    return out


def _wk_rows(P, nm=None):
    nm = nm or _wk_namer()
    rows = []
    for slug, v in P.items():
        days = v if isinstance(v, list) else (v.get("daily") or [])
        tok = sum((d.get("totalTokens") or 0) for d in days)
        cost = sum((d.get("totalCost") or 0) for d in days)
        if tok <= 0:
            continue
        rows.append({"slug": slug, "name": nm(slug),
                     "tok": tok, "cost": round(cost, 2), "days": len(days)})
    rows.sort(key=lambda x: -x["tok"])
    return rows


def _wk_daily(P, nd, nm=None):
    """★Daily totals — ccusage already gives per-date data but only project totals were used and the rest **thrown away**
    (2026-09-03, daily token graph). Missing days are filled with 0 rather than left blank
    — a missing bar reads as "unknown that day" when the fact is "nothing used that day"."""
    agg = {}
    byday = {}      # date -> {slug: tok}; P is already folded, so slugs match the donut/project table
    for slug, v in P.items():
        days = v if isinstance(v, list) else (v.get("daily") or [])
        for d in days:
            k = d.get("date")
            if not k:
                continue
            a = agg.setdefault(k, [0, 0.0])
            a[0] += d.get("totalTokens") or 0
            a[1] += d.get("totalCost") or 0
            pm = byday.setdefault(k, {})
            pm[slug] = pm.get(slug, 0) + (d.get("totalTokens") or 0)
    nm = nm or _wk_namer()
    daily = []
    keys = []
    for i in range(nd - 1, -1, -1):
        k = time.strftime("%Y-%m-%d", time.localtime(time.time() - i * 86400))
        keys.append(k)
        t, c = agg.get(k, (0, 0.0))
        # Top 2 projects of the day for the «Daily» table; zero-token projects are noise, empty day -> [].
        top = sorted(((sl, tk) for sl, tk in (byday.get(k) or {}).items() if tk > 0),
                     key=lambda x: (-x[1], x[0]))[:2]
        daily.append({"d": k, "tok": int(t), "cost": round(c, 2),
                      "top": [{"name": nm(sl), "slug": sl, "tok": int(tk)} for sl, tk in top]})
    return daily, keys


def _wk_trend(P, rows, keys, nm=None):
    """★**Per-project daily trend** (2026-09-04). The total alone does not show
    who burned it — measured 09-04: 156.9M went out in 40 min and 36% of that was 4 parallel
    subagents, which the total bar alone did not reveal.
    Only the top 3 are emitted (below that is a tail that just adds rows) + the rest folded into 'Other'."""
    byproj = {}
    for slug, v in P.items():
        days = v if isinstance(v, list) else (v.get("daily") or [])
        m = {}
        for d in days:
            if d.get("date"):
                m[d["date"]] = int(d.get("totalTokens") or 0)
        byproj[slug] = m
    nm = nm or _wk_namer()
    top = [r["slug"] for r in rows[:3]]
    trend = [{"name": nm(sl), "slug": sl,
              "tok": sum(byproj.get(sl, {}).get(k, 0) for k in keys),
              "series": [byproj.get(sl, {}).get(k, 0) for k in keys]} for sl in top]
    rest = [sl for sl in byproj if sl not in top]
    if rest:
        ser = [sum(byproj.get(sl, {}).get(k, 0) for sl in rest) for k in keys]
        if sum(ser) > 0:
            trend.append({"name": "기타 %d개" % len(rest), "slug": "",
                          "tok": sum(ser), "series": ser})
    return trend


def _wk_mix(P):
    """★**Token mix** (2026-09-04, extra stats). ccusage already gives it per date, but
    only `totalTokens` was used and in/out/cache-create/cache-read were thrown away entirely.
    CLAUDE.md's cost rules came straight from these numbers, yet the screen lacked them —
    30-day measurement: cache read 98.2% · cache create 1.7% · output 0.15% · input 0.00%.
    i.e. only 0.15% can be saved by "talking less"; what to cut is context per request.
    `ratio` is how many times a created cache was reused (58x over 30 days). If it drops,
    it signals sporadic use causing TTL-expiry rewrites."""
    mix = {"in": 0, "out": 0, "cc": 0, "cr": 0}
    mdl = {}
    for slug, v in P.items():
        for d in (v if isinstance(v, list) else (v.get("daily") or [])):
            mix["in"] += d.get("inputTokens") or 0
            mix["out"] += d.get("outputTokens") or 0
            mix["cc"] += d.get("cacheCreationTokens") or 0
            mix["cr"] += d.get("cacheReadTokens") or 0
            # ★Per-model is emitted **only when two or more are mixed** (only opus is in use now; may need the split
            #   after updates). With a single kind it is one 100% row that just takes space.
            for m in d.get("modelBreakdowns") or []:
                a = mdl.setdefault(m.get("modelName") or "?", [0, 0.0])
                a[0] += ((m.get("inputTokens") or 0) + (m.get("outputTokens") or 0)
                         + (m.get("cacheCreationTokens") or 0) + (m.get("cacheReadTokens") or 0))
                a[1] += m.get("cost") or 0
    mix["tot"] = sum(mix[k] for k in ("in", "out", "cc", "cr"))
    mix["ratio"] = round(mix["cr"] / mix["cc"], 1) if mix["cc"] else 0
    models = sorted(({"name": k, "tok": v[0], "cost": round(v[1], 2)}
                     for k, v in mdl.items()), key=lambda x: -x["tok"])
    return mix, models


def _wkuse_fetch(days=None, acct=""):
    # ⚠The period is taken as `nd` — the phase helpers use a local `days` to hold per-project daily lists.
    #   Using the argument name directly gets overwritten by that assignment and `range(days-1,...)` blows up as a list op (measured 2026-09-04).
    nd = int(days or WK_DAYS)
    slot = _wk_slot(nd, acct) if acct else _wk_slot(nd)   # ⚠one-arg call kept: the golden trace stubs it
    since = time.strftime("%Y%m%d", time.localtime(time.time() - (nd - 1) * 86400))
    try:
        P = _wk_load(nd, since, slot, acct)
        if P is None:
            return
        P = _wk_fold(P)
    except Exception as e:
        with _wkuse_lock:
            slot["err"] = f"{type(e).__name__}"
        return
    nm = _wk_namer()
    rows = _wk_rows(P, nm)
    daily, keys = _wk_daily(P, nd, nm)
    trend = _wk_trend(P, rows, keys, nm)
    mix, models = _wk_mix(P)
    with _wkuse_lock:
        slot.update({"at": time.time(), "rows": rows, "daily": daily, "trend": trend,
                     "mix": mix, "models": models,
                     "cost": round(sum(x["cost"] for x in rows), 2),
                     "total": sum(x["tok"] for x in rows), "days": nd, "err": ""})


_wkuse_busy = [False]
_wkuse_busy_days = set()      # periods currently being measured — do not dispatch the same period twice


def wkuse_refresh(days=None, acct=""):
    """Manual forced refresh. ★**Not measured directly in the HTTP handler** — ccusage takes 26s, so that request
    blocks meanwhile and polling backs up too. Dispatch to the background; the screen watches for `at` to change.
    If already measuring, do not dispatch again (a duplicate run just runs ccusage twice)."""
    d = int(days or WK_DAYS)
    key = (d, acct)
    if key in _wkuse_busy_days:
        return False
    _wkuse_busy_days.add(key)
    _wkuse_busy[0] = True

    def run():
        try:
            _wkuse_fetch(d, acct)
        except Exception as e:
            # ★if it dies silently `at` stays 0 forever and the screen freezes at 'measuring' — record the reason
            with _wkuse_lock:
                _wk_slot(d, acct)["err"] = f"{type(e).__name__}: {e}"[:160]
        finally:
            _wkuse_busy_days.discard(key)
            _wkuse_busy[0] = bool(_wkuse_busy_days)
    threading.Thread(target=run, daemon=True).start()
    return True


# ★Refresh intervals differ per period. One day is still accumulating and changes often; 30-day totals barely change
#   (measured: one hour is under 0.3% of 30 days' 18.3B). ccusage takes 30~60s per period, so running all at
#   the same interval just queues behind the lock.
# ★Intervals were narrowed (2026-09-11). These values assumed **ccusage takes 30~60s per period**, but
#   aggregation moved to local incremental and the premise is gone — measured first scan 7.7~8.9s · **incremental 0.05s**.
#   ⚠Still not 0: each call `stat`s 2,273 transcripts (cheap but not free).
WK_EVERY = {1: 120, 7: 180, 30: 600}
WK_RETRY_S = 120     # minimum retry interval for a period whose `at` is 0 due to failure


def _wkuse_loop():
    """★Refresh **every period that has ever been measured**. Previously `_wkuse_fetch()` was called with no
    argument, so only the default 7 days ran (measured 2026-09-04), and with month selected the screen froze on a 33-min-old value.
    ⚠Periods never measured are not measured here — not worth burning ccusage every minute for a period
      nobody looks at. The screen measures on demand when first opened; after that it is picked up here.

    ★But **a period opened once and failed is retried** (2026-09-07). Checking only `at == 0` skipped
      everything except the default period, so a 30-day run that failed once held only `err` and stayed 0 forever,
      freezing the screen at "measuring". `at==0` **with** `err` means someone opened it and it failed, so
      re-measure. Periods with no `err` either (= nobody looked) keep being skipped per the rule above."""
    while True:
        try:
            now = time.time()
            with boot_queue.gate("wkuse_loop"):   # ⚠first pass waits its boot turn; no-op after drain (traps/server.md)
                for d in _WK_RANGES:
                    sl = _wk_slot(d)
                    at = sl.get("at") or 0
                    if not at:
                        if d == WK_DAYS:
                            _wkuse_fetch(d)  # the default period used by the sidebar is measured even if nobody opens it
                        elif sl.get("err") and now - (sl.get("tryAt") or 0) >= WK_RETRY_S:
                            # ⚠Knocking tightly keeps burning ccusage (30~60s per period) → enforce a minimum interval.
                            #   Record the attempt time first — even if it fails again, the next retry is pushed 10 min out.
                            with _wkuse_lock:
                                sl["tryAt"] = now
                            _wkuse_fetch(d)
                        continue
                    if now - at >= WK_EVERY.get(d, 900):
                        _wkuse_fetch(d)
            _LOOP_ERR.pop("wkuse", None)
            time.sleep(60)
        except Exception as e:
            warn_once("loop:wkuse", "Period token totals stopped refreshing — {err}",
                      vars={"err": f"{type(e).__name__}: {e}"[:140]})
            _LOOP_ERR["wkuse"] = {"at": time.time(), "err": f"{type(e).__name__}: {e}"[:160]}
            time.sleep(60)          # ⚠the exception path must sleep too — otherwise it becomes a tight infinite loop
            continue


def wk_stale(days, acct=""):
    """True when the slot was never measured or is older than its period's WK_EVERY (per-account slots refresh only here)."""
    d = int(days or WK_DAYS)
    with _wkuse_lock:
        at = _wk_slot(d, acct).get("at") or 0
    return not at or time.time() - at >= WK_EVERY.get(d, 900)


def wkuse(days=None, acct=""):
    """Period aggregate + **what today added since the last fetch**.

    ★Why split it (2026-09-03, only today's tokens needed periodic refresh): ccusage takes 20+ s and
      runs only every 5 min. If today's bar freezes meanwhile, current usage is invisible.
      Adding only what OTel accumulated live in `live` **since the last fetch time** moves today's
      cell without double counting. The screen shows this share separately to flag it as an estimate."""
    d = int(days or WK_DAYS)
    with _wkuse_lock:
        out = dict(_wk_slot(d, acct))
    _wk_rename(out)
    out["range"] = d
    out["ranges"] = list(_WK_RANGES)
    out["acct"] = acct
    at = out.get("at") or 0
    add = 0
    if at and not acct:     # OTel live share carries no account, so a pick adds none
        try:
            with _usage_lock:
                add = sum(t for ts, t, _c in _usage["live"] if ts > at)
        except Exception:
            add = 0
    out["liveAdd"] = int(add)
    out["today"] = time.strftime("%Y-%m-%d")
    # ★Live — the last 30 min **per minute** (2026-09-03, for liveliness).
    #   No ccusage: `live` here is what OTel accumulates in place per request, so
    #   cost is 0 and there is no lag (daily bars come from ccusage, once every 5 min).
    #   ⚠Usage from sessions that do not send OTel is not included — the screen tooltip says so.
    out["live"] = _live_buckets()
    # ★Live per-project top 3 (2026-09-04 — usage was moving too fast to tell who was burning it).
    #   The graph only said **how fast**, not who was burning.
    #   OTel `api_request` carries session.id, so fold that into projects (no extra cost).
    #   ⚠Subagent requests also come with that session id — i.e. per-session totals (which suits root-cause tracing).
    try:
        with _usage_lock:
            lb = list(_usage.get("liveby") or [])
        cut = time.time() - LIVE_SEC
        agg2 = {}
        for ts, tk, sid in lb:
            if ts < cut:
                continue
            nm = _sid_proj.get(sid) or (_sid8(sid) if sid else "?")
            agg2[nm] = agg2.get(nm, 0) + int(tk or 0)
        tops = sorted(agg2.items(), key=lambda x: -x[1])[:3]
        mins = max(1.0, LIVE_SEC / 60.0)
        out["liveTop"] = [{"name": n, "tok": v, "per": int(v / mins)} for n, v in tops]
    except Exception as e:
        warn_once("livetop", "Live top-sessions tally failed ({err})", vars={"err": type(e).__name__}, soft=True)
        out["liveTop"] = []
    with _today_lock:
        out["intraday"] = dict(_today)
    with _burn_lock:
        out["burn"] = dict(_burn)
    # agent cost table — TTL 120s cache, so logs are not re-read here (warm 6ms measured)
    out["agc"] = agentcost()
    out["liveSec"] = LIVE_SEC
    out["liveStep"] = LIVE_STEP
    return out
