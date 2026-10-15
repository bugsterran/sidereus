"""Usage (5-hour block, weekly): OTel accumulation, backfill, persistence, 5h attribution (quota_who).
The local usage index (scan, prices, blocks) lives in sidereus/usage_index.py (split 2026-09-24); re-exported here."""
import json
import os
import shutil
import subprocess
import threading
import time
from sidereus.config import DATA_DIR, IS_MAC
from sidereus.warn import warn_once
from sidereus.bus import _atomic_write
from sidereus.memo import BoundedMemo
from sidereus.ident import _sid8, node_dir
from sidereus.transcript import _iso_ts, iso_epoch
from sidereus.usage_index import (_blocks_local, _cost4, _uidx, _uidx_hours, _uidx_lock,  # noqa: F401
    _uidx_projects, _uidx_refresh, _uidx_week)


# ── Usage (5-hour block · weekly) ─────────────────────────────────────────
#   ★No official API (as of 2026-08 · feature request anthropics/claude-code#43149 open). It appears only in the `/usage`
#     slash command and limit-exceeded error messages, and is not stored locally (checked: `~/.claude.json` has only the plan tier
#     `default_claude_max_5x` and bar names `five_hour`·`seven_day`).
#   ⇒ **The limit (%) cannot be shown.** What can be shown is **amount used and reset time**. Never invent what is missing.
#   Two sources:
#     ① OTel `api_request` events we already receive — real-time, free (each request carries tokens and cost)
#     ② `ccusage` (installed) — history. **Slow** (full scan 18 s · statusline cold 40 s) ⇒ background only.
#   5-hour block boundaries follow ccusage's rule: **first activity time floored to the hour**, then 5 hours.
USAGE_BACKFILL_S = 900          # interval for refilling history via ccusage (rare, since slow)
# ★Reset time — ccusage's windows are **not the account's real resets** (5h floors the first activity, weekly is calendar weeks).
#   The real values appear only in `/usage`, so once the user writes down **one anchor**, the rest is computed by period.
#   File: usage-anchor.json  {"block":"2026-08-20T11:00:00+09:00","week":"2026-08-22T09:00:00+09:00"}
#         block = next 5-hour reset · week = next weekly reset (both as seen in /usage)
ANCHOR_FILE = os.path.join(DATA_DIR, "usage-anchor.json")
# ★Backfill results are persisted — otherwise **the screen goes blank on every restart** (ccusage cold takes 40~100 s,
#   and the usage slot vanished entirely meanwhile · 2026-08-20).
USAGE_CACHE = os.path.join(DATA_DIR, "usage-cache.json")


def _next_reset(iso, period_s):
    """Add periods to the anchor to get **the next reset**. None without an anchor (no guessing)."""
    if not iso:
        return None
    t = _iso_ts(iso)
    if not t:
        return None
    now = time.time()
    if period_s <= 0:
        return t if t > now else None
    while t <= now:
        t += period_s
    return t


def _anchors():
    try:
        with open(ANCHOR_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}               # no anchors yet or mid-write: windows fall back to their defaults
_usage = {"blocks": None, "week": None, "blockMax": 0, "weekMax": 0, "at": 0, "live": [],
          # ★Per-project real-time attribution (2026-09-04; top-3 projects by real-time tokens).
          #   `live`'s tuple shape is read in four places, so it is untouched and this is stacked **alongside**.
          # ★★**The sparkline uses its own buffer** (2026-09-08; real-time occasionally reset to zero).
          #   `live` means "**since the last backfill**", so a successful backfill empties it wholesale (`:3511`).
          #   The real-time graph was folding the last 10 min out of that list ⇒ every `USAGE_BACKFILL_S`
          #   (900 s) the graph regrew from 0. ★Measured: oldest non-zero bucket 330 s ·
          #   last backfill 334 s ago — a 10 min window filled only since the backfill.
          #   ⚠The accounting path (`live` and its reset) is **not touched** — "since backfill" must keep its meaning,
          #     and touching it shakes the block and weekly numbers.
          #   ⚠Simply removing `live`'s reset is wrong — the list would sit at its 20000 cap and every event
          #     (1~2 per second) would rebuild a 20k list in cleanup. The 15-min reset currently hides that cost.
          "spark": [],    # spark = [(ts, tokens)] — never emptied by anyone; trimmed by age only
          "liveby": []}   # live = [(ts, tokens, cost)] · liveby = [(ts, tokens, sid)]
_sid_proj = BoundedMemo(300)   # session id -> project name (sessions() fills it every poll)
WHO_STEP = 300            # 5h attribution bucket (s)
WHO_KEEP = 5 * 3600 + 2 * WHO_STEP   # buckets kept: one 5h cycle plus slack for a straddling bucket
_usage_lock = threading.Lock()


def _usage_add(ts, tokens, cost, sid=""):
    """Accumulate one OTel `api_request`. Anything older than 7 days is dropped."""
    with _usage_lock:
        _usage["live"].append((ts, tokens, cost))
        cut = time.time() - 7 * 86400
        if len(_usage["live"]) > 20000:
            _usage["live"] = [x for x in _usage["live"] if x[0] >= cut][-20000:]
        # sparkline buffer — holds only twice the window (10 min). Same approach as `liveby`
        sp = _usage.setdefault("spark", [])
        sp.append((ts, tokens))
        if len(sp) > 4000:
            cut3 = time.time() - LIVE_SEC * 2
            _usage["spark"] = [x for x in sp if x[0] >= cut3][-4000:]
        # attribution uses only **the real-time window (10 min)**, so keep it short — no reason to hold more
        lb = _usage.setdefault("liveby", [])
        lb.append((ts, tokens, sid or ""))
        if len(lb) > 4000:
            cut2 = time.time() - max(LIVE_SEC * 3, 1800)
            _usage["liveby"] = [x for x in lb if x[0] >= cut2][-4000:]
        # 5h attribution: `liveby` keeps only ~30 min, so fold per-sid tokens into 5-min buckets
        #   (bounded: ~62 buckets x active sids) for the quota modal's «who is using the 5h».
        bk = _usage.setdefault("byc", {})
        b0 = int(ts // WHO_STEP) * WHO_STEP
        if b0 not in bk:          # prune only when a new bucket opens (once per WHO_STEP)
            for k in [k for k in bk if k < b0 - WHO_KEEP]:
                del bk[k]
        row = bk.setdefault(b0, {})
        row[sid or ""] = row.get(sid or "", 0) + int(tokens or 0)
        _usage.setdefault("bycSince", ts)


# ★ccusage runs **one at a time** (2026-09-04; weekly tokens failed to load).
#   Measured cause: three threads (_usage_loop · _projcost_loop · _wkuse_loop) and the forced-refresh thread
#   could each launch ccusage. Each run scans GBs of transcripts, so they crowded each other past the
#   90 s timeout — the screen showed `err=TimeoutExpired · rows=0 · daily=0`.
#   Alone it measured **34 s** (rc=0, 4 projects). So the problem was overlap, not slowness.
#   ⚠The lock wraps only the run. Waiters are background threads and never block the screen.
_ccusage_lock = threading.Lock()


def _shape_list(doc, field, wkey, what="that view"):
    """Take one list field from an external tool's (ccusage) response **after checking its shape**.
    ★Why: we do not control these responses' shape (it changes on upgrades). If unexpected, `.get` raises
      `AttributeError`; even caught by the loop guard, it **blows up in the same spot** next cycle and that refresh
      stops forever. ⇒ If odd, return "unknown" (None) and log the reason.
    ⚠"Unknown" (None) and "none" ([]) are distinct — on None the caller keeps the old value and does not
      refresh `at` (silently overwriting with 0 makes the screen lie)."""
    if not doc:
        return None                     # the run itself failed (run already logged the reason)
    if not isinstance(doc, dict):
        # `what` is a fixed phrase per call site, so it is part of the i18n key (not a var)
        warn_once(wkey + "-top", "ccusage {field} top level is not an object ({err}) — %s is empty" % what,
                  vars={"field": field, "err": type(doc).__name__})
        return None
    v = doc.get(field)
    if isinstance(v, list):
        return v
    warn_once(wkey + "-list", "ccusage response has no {field} list ({err}) — %s is empty" % what,
              vars={"field": field, "err": type(v).__name__})
    return None


# ── Local usage index — ccusage replacement (2026-09-11) ───────────────────
# The index itself (scan, hour buckets, prices, blocks, per-project dailies) lives in sidereus/usage_index.py.
# ⚠With `USAGE_LOCAL = False` the old ccusage path runs as before (for comparison · do not delete).
USAGE_LOCAL = True


def _usage_backfill_local():
    """Local version of `_usage_backfill()`. **Return shape (keys, units) matches the ccusage version** — the names
    `totalTokens`·`costUSD`·`startTime`… are kept as is so the UI JS stays untouched."""
    _uidx_refresh()
    hours = _uidx_hours()
    now = time.time()
    bl = _blocks_local(hours, now)
    act = next((b for b in bl if b["isActive"]), None)
    wk = {}
    for k, mm in hours.items():
        a = wk.setdefault(_uidx_week(k), [0, 0.0])
        for mdl, v in mm.items():
            a[0] += sum(v)
            a[1] += _cost4(mdl, v)
    keys = sorted(wk)
    cw = keys[-1] if keys else None
    with _usage_lock:
        _usage["blocks"] = act or (bl[-1] if bl else None)
        _usage["blockMax"] = max([b["totalTokens"] for b in bl if not b["isActive"]], default=0)
        _usage["week"] = ({"week": cw, "totalTokens": wk[cw][0],
                           "totalCost": round(wk[cw][1], 2)} if cw else None)
        _usage["weekMax"] = max([wk[k][0] for k in keys[:-1]], default=0)
        _usage["at"] = time.time()
        _usage["live"] = []      # the backfill covers up to now, so reset the real-time part


def _ccusage_exe():
    """Known absolute paths first, then PATH (`shutil.which` also finds Windows npm's `ccusage.cmd`)."""
    return next((x for x in ("/opt/homebrew/bin/ccusage", "/usr/local/bin/ccusage",
                             os.path.expanduser("~/.bun/bin/ccusage")) if os.path.exists(x)),
                None) or shutil.which("ccusage")


def _usage_backfill():
    """5-hour block and weekly totals. Default is **the local index** (`_usage_backfill_local` above);
    the ccusage path below runs only with `USAGE_LOCAL = False`, **for comparison**."""
    if USAGE_LOCAL:
        return _usage_backfill_local()
    # ★Find it by absolute path — launchd's minimal PATH does not know `/opt/homebrew/bin` (measured 2026-08-20:
    #   the call failed silently and usage came out empty).
    exe = _ccusage_exe()
    if not exe:
        warn_once("ccusage-missing", "ccusage not found — usage counts live data only")
        return

    # ★Fill PATH — `ccusage` is **a shim that calls node**, and launchd's PATH is only
    #   `/usr/bin:/bin:/usr/sbin:/sbin`, so node is not found (measured 2026-08-20: failed silently).
    env = dict(os.environ)
    mac = ["/opt/homebrew/bin", "/usr/local/bin"] if IS_MAC else []
    env["PATH"] = os.pathsep.join(mac + [os.path.dirname(exe), node_dir()]     # ⚠os.pathsep, not ":"
                                  + ([env["PATH"]] if env.get("PATH") else []))

    def run(args, timeout=240):
        try:
            with _ccusage_lock:
                r = subprocess.run([exe] + args, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=timeout, env=env)
            if r.returncode != 0 or not r.stdout.strip():
                # ★Failures are **not swallowed**. rc used to be ignored, so a blank screen had no known reason.
                warn_once("ccusage-rc", "ccusage {cmd} failed (rc={rc}): {err}",
                          vars={"cmd": args[0], "rc": r.returncode, "err": (r.stderr or "")[:160]})
                return None
            return json.loads(r.stdout)
        except Exception as e:
            warn_once("ccusage", "Could not run ccusage ({err}) — counting live data only",
                      vars={"err": f"{type(e).__name__}: {e}"})
            return None
    allb = run(["blocks", "--json"])          # all blocks — **the denominator (observed max)** comes from here
    week = run(["weekly", "--json"])
    # ⚠What follows is **outside** `run()`'s try — run wraps only execution and JSON parsing. If a ccusage upgrade
    #   changes the shape it blows up here, and even caught by the loop guard it blows up in the same spot every 60 s,
    #   stopping the backfill effectively forever. ⇒ Check the shell with `_shape_list` and **elements** with
    #   `isinstance` below, skipping only odd elements (never discard everything for one element).
    bls = _shape_list(allb, "blocks", "ccusage-blocks", "the 5-hour blocks view")
    ws = _shape_list(week, "weekly", "ccusage-weekly", "the weekly totals view")
    with _usage_lock:
        if bls is not None:
            bl = [b for b in bls if isinstance(b, dict) and not b.get("isGap")]
            act = next((b for b in bl if b.get("isActive")), None)
            _usage["blocks"] = act or (bl[-1] if bl else None)
            # ★The limit is not published, so **the largest block observed so far** is the denominator (same as ccusage's
            #   `--token-limit max`). If the limit was never hit, max < real limit and **% is inflated** — the screen says so.
            done = [b for b in bl if not b.get("isActive")]
            _usage["blockMax"] = max([b["totalTokens"] for b in done
                                      if isinstance(b.get("totalTokens"), (int, float))], default=0)
        if ws is not None:
            ws = [w for w in ws if isinstance(w, dict)]
            _usage["week"] = ws[-1] if ws else None
            _usage["weekMax"] = max([w["totalTokens"] for w in ws[:-1]
                                     if isinstance(w.get("totalTokens"), (int, float))], default=0)
        if bls is not None or ws is not None:
            _usage["at"] = time.time()
            _usage["live"] = []      # the backfill covers up to now, so reset the real-time part
        # ★On failure `at` is not refreshed — an old value must not pose as fresh (the screen shows "N min ago")


def _usage_save():
    # ★spark (real-time sparkline) is saved too (2026-09-09) — only blocks/week used to be saved, so
    #   the last-10-min strip was empty after every restart (the backfill is an aggregate, not a time series, and cannot refill it).
    #   ⇒ Inside the lock take only a shallow copy (snapshot); actual file IO happens outside — so other threads
    #   (`_usage_add` etc.) are not blocked on the lock while writing.
    with _usage_lock:
        snap = {k: _usage.get(k) for k in ("blocks", "week", "blockMax", "weekMax", "at")}
        snap["spark"] = list(_usage.get("spark") or [])
    try:
        # ⚠two threads (today_loop · usage_loop) save here — open("w") interleaved into trailing garbage
        _atomic_write(USAGE_CACHE, json.dumps(snap, ensure_ascii=False).encode("utf-8"), prefix=".usage-cache.")
    except OSError as e:
        warn_once("usage-save", "usage cache save failed ({err}) — charts start empty on restart",
                  soft=True, vars={"err": f"{type(e).__name__}: {e}"})


def _usage_load():
    try:
        with open(USAGE_CACHE, encoding="utf-8") as f:
            d = json.load(f)
        with _usage_lock:
            for k in ("blocks", "week", "blockMax", "weekMax", "at"):
                if d.get(k) is not None:
                    _usage[k] = d[k]
            # ★spark restore (2026-09-09) — drop points older than LIVE_SEC (600 s) relative to restart
            #   (otherwise dead values stick to the head of the fresh window). The `isinstance` checks quietly
            #   skip old-version caches without a spark key — loading must never break.
            sp = d.get("spark")
            if isinstance(sp, list):
                cut = time.time() - LIVE_SEC
                _usage["spark"] = [tuple(x) for x in sp
                                    if isinstance(x, (list, tuple)) and len(x) == 2
                                    and isinstance(x[0], (int, float)) and x[0] >= cut]
    except Exception:
        pass                    # missing or corrupt cache: start empty (loading must never break)


def usage():
    """Usage for the screen. Backfill (history) + real-time since then."""
    with _usage_lock:
        b, w, at, live = _usage["blocks"], _usage["week"], _usage["at"], list(_usage["live"])
        wmax = _usage.get("weekMax") or 0
    now = time.time()
    add_tok = sum(x[1] for x in live if x[0] >= at)
    add_cost = sum(x[2] for x in live if x[0] >= at)
    out = {"at": int(at), "live": len(live), "stale": int(now - at) if at else None}
    a = _anchors()
    rb = _next_reset(a.get("block"), 5 * 3600)      # 5-hour period
    rw = _next_reset(a.get("week"), 7 * 86400)      # 7-day period
    out["reset"] = {"block": rb, "week": rw, "src": "anchor" if (rb or rw) else None}
    if b:
        end = iso_epoch(b.get("endTime"), 0)
        out["block"] = {
            "tokens": (b.get("totalTokens") or 0) + add_tok,
            "cost": round((b.get("costUSD") or 0) + add_cost, 2),
            "start": b.get("startTime"), "end": b.get("endTime"),
            "leftMin": max(0, int((end - now) / 60)) if end else None,
        }
        # ★2026-09-27 cross-tab audit: no 5h max/pct here. The anchor (519M) read 8% vs official 55%;
        #   ⚠the 5h limit's only source is the burn back-solve (`quota_burn` head.lim), the % is official quota.
    if w:
        out["week"] = {"tokens": (w.get("totalTokens") or 0) + add_tok,
                       "cost": round((w.get("totalCost") or 0) + add_cost, 2),
                       "week": w.get("week"), "max": wmax}
        limw = a.get("weekLimitTokens") or wmax
        if limw:
            out["week"]["max"] = limw
            out["week"]["pct"] = round(out["week"]["tokens"] / limw * 100)
            out["week"]["src"] = "calibrated" if a.get("weekLimitTokens") else "observed max"
    return out
_who_seed_lock = threading.Lock()


def _who_scan(start):
    """Transcript tokens since `start` as `[(ts, tokens, sid)]` + the oldest time reliably covered.
    Mirrors `_tok_events` (same picks, same nb/lim so `_SEG_RAW` is shared) but keeps the owning
    session id: `<sid>.jsonl`, and its subagent files fold into that sid (same as OTel)."""
    from sidereus.timeline import _tl_pick, _sess_segments, _SEG_WIN, SEG_CAP_BYTES   # lazy: timeline imports usage
    from sidereus.agents import _agent_meta, wf_agent_files
    ev, seen, cov = [], set(), start

    def one(f, sid, **kw):
        nonlocal cov
        if f in seen:
            return
        try:
            if os.stat(f).st_mtime < start:
                return
        except OSError:
            return
        seen.add(f)
        got = []
        _segs, reach = _sess_segments(f, start, tok_out=got, **kw)
        ev.extend((t, n, sid) for t, n in got)
        # ⚠A file hit the 80MB read cap before reaching `start` — the cycle's head is genuinely unknown.
        try:
            if reach and reach > start and (_SEG_WIN.get(f) or (0,))[0] >= SEG_CAP_BYTES \
                    and os.path.getsize(f) > SEG_CAP_BYTES:
                cov = max(cov, reach)
        except OSError:
            pass                # transcript deleted since the scan: no cap evidence from it

    for _cwd, _proj, pick, _newest in _tl_pick(start):
        for fp in pick:
            sid = os.path.basename(fp)[:-len(".jsonl")]
            for mm in _agent_meta(fp[:-len(".jsonl")], ttl=10).values():
                if mm.get("_file"):
                    one(mm["_file"], sid, nb=2_000_000, lim=4000)
            for f2 in wf_agent_files(fp[:-len(".jsonl")]):   # Workflow-tool agents fold into the same sid
                one(f2, sid, nb=2_000_000, lim=4000)
            one(fp, sid)
    return ev, cov


def _who_seed(start, now=None, floor=0):
    """Backfill `byc` from transcripts once per 5h cycle, so the modal is not empty after a restart.
    ⚠No double count: only events before the first live OTel add (`bycSince`) or the seed start are added;
    `floor` = the previous seed's `until`, so a re-seed never re-adds what an earlier one already wrote."""
    t0 = time.time() if now is None else now
    try:
        ev, cov = _who_scan(start)
    except Exception as e:
        warn_once("who_seed", "quota_who seed failed: {err}", vars={"err": repr(e)})
        with _usage_lock:
            _usage["bycSeed"] = {"done": True, "start": start, "cov": 0, "n": 0}
        return
    with _usage_lock:
        until = min(t0, _usage.get("bycSince") or t0)
        lo = max(start, floor)
        bk = _usage.setdefault("byc", {})
        n = 0
        for ts, tk, sid in ev:
            if lo <= ts < until:
                row = bk.setdefault(int(ts // WHO_STEP) * WHO_STEP, {})
                row[sid] = row.get(sid, 0) + int(tk or 0)
                n += 1
        _usage["bycSeed"] = {"done": True, "start": start, "cov": cov, "until": until, "n": n,
                             "ms": int((time.time() - t0) * 1000) if now is None else 0}


def _who_seed_kick(start):
    """Start the per-cycle seed in the background — a cold transcript scan must never block `state()`."""
    with _who_seed_lock:
        prev = _usage.get("bycSeed")
        # ⚠Re-seed once per new cycle only; a small resets_at jitter (< WHO_STEP) must not rescan every poll.
        if prev is not None and (not prev.get("done") or start < (prev.get("start") or 0) + WHO_STEP):
            return
        floor = (prev or {}).get("until") or 0
        _usage["bycSeed"] = {"done": False, "start": start}
    threading.Thread(target=_who_seed, args=(start, None, floor), name="who_seed", daemon=True).start()


def quota_who(q, now=None, top=6):
    """Who used the current 5h cycle — per project (metadata only: project name · session ids · tokens).
    Cycle start = official `five_hour.resets_at` - 5h. OTel-only, in-memory since server start:
    `partial` marks a cycle that began before the first recorded request."""
    now = time.time() if now is None else now
    fh = (q or {}).get("five_hour") or {}
    r_at = _iso_ts(fh.get("resets_at")) if fh.get("resets_at") else 0
    start = (r_at - 5 * 3600) if r_at else (now - 5 * 3600)
    if r_at:
        _who_seed_kick(start)     # seed only against the official cycle start
    with _usage_lock:
        bk = {k: dict(v) for k, v in (_usage.get("byc") or {}).items() if k + WHO_STEP > start}
        since = _usage.get("bycSince") or 0
        seed = _usage.get("bycSeed") or {}
    # coverage starts at the seed's reach when the backfill for *this* cycle finished, else at the first live OTel add
    if seed.get("done") and seed.get("cov") and abs((seed.get("start") or 0) - start) < WHO_STEP:
        since = seed["cov"]
    by = {}
    for row in bk.values():
        for sid, tk in row.items():
            nm = _sid_proj.get(sid) or (_sid8(sid) if sid else "?")
            e = by.setdefault(nm, {"tok": 0, "sids": {}})
            e["tok"] += tk
            e["sids"][sid] = e["sids"].get(sid, 0) + tk
    total = sum(e["tok"] for e in by.values())
    rows = []
    for nm, e in sorted(by.items(), key=lambda x: -x[1]["tok"])[:top]:
        ss = sorted(e["sids"].items(), key=lambda x: -x[1])
        rows.append({"name": nm, "tok": e["tok"], "share": round(e["tok"] * 100.0 / total, 1) if total else 0,
                     "n": len(ss), "sids": [{"sid": _sid8(s), "tok": t} for s, t in ss[:5]]})
    return {"start": int(start), "exact": bool(r_at), "total": total, "rows": rows,
            "others": max(0, len(by) - top), "othersTok": total - sum(r["tok"] for r in rows),
            "partial": bool(not since or since > start),
            "since": int(since) if since else None}


# ★Live sparkline: the **last 10 minutes in 10-second buckets** (2026-09-03, choosing minute vs second granularity).
#   Picked from measured inflow (3 sessions · 2.17M tokens/min · an event every 1~2s):
#     10 minute buckets   → too coarse, moves only once a minute
#     600 second buckets  → a mostly-zero sawtooth; polling is 10s so 599 cells would not move anyway
#     60 ten-second buckets → **matches the poll period**, advancing one cell per refresh (that is the 'liveliness')
LIVE_SEC = 600             # span shown (s)
LIVE_STEP = 10             # bucket size (s)
