"""Per-account tokens per 1% from our own history (`est` in `/api/quota/burn`): 5h and 7d «Remaining ≈» / «Used ≈».

«Remaining ≈» uses our collected tokens per 1% per account, not this window's average.
  Backtest (quota-log + local transcripts) — remaining-token error, median, predicted at 30/50/70% used:
    window-avg (used ÷ % × left %): 27/22/19% (Pro 5817, 13 windows) · 38/25/16% (team 7e76, 4 windows)
    history median (this module):   12/17/15% · 11/12/9%
  Full 5h: Pro ≈59M (31–90M), team ≈472M · 7d per 1%: Pro 3.19M, team 29.6M (~9x between plans -> per account).
⚠Never computed on the request path: a background pass (≈2 s for 5 days of transcripts) every HIST_TTL,
  persisted to HIST_CACHE; until the first pass lands `burn_est` returns None and the page keeps its fallback.
⚠Metadata only — the pass reads `message.usage` numbers, ids and timestamps, nothing else."""
import bisect
import glob
import json
import os
import statistics
import threading
import time
from sidereus.config import DATA_DIR
from sidereus.warn import warn_once
from sidereus.bus import _atomic_write
from sidereus.transcript import CLAUDE_PROJECTS, iso_epoch
from sidereus.quota import QUOTA_LOG, _plan_code
from sidereus.burn_calc import QBURN_WIN, _qburn_cycles

HIST_TTL = 1800          # s between background passes (brief: >= 10 min)
HIST_CACHE = os.path.join(DATA_DIR, "burn-hist-cache.json")
HIST_GAP = 1800          # s — a longer gap between two log rows is not one interval (poller was off)
HIST_MIN_WIN = 3         # fewer full (>= 99%) windows -> pooled intervals instead of the median
HIST_FULL = 99.0         # a window «reached the limit» at this h5
HIST_MIN_ROWS = 4        # a full window needs this many rows (cmp.py)
HIST_MIN_WK = 3          # 7d needs this many d7 points of rise in total
_TOK_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
# ★Plan change detector: a model-mix shift moves per-1% by CV 0.29-0.49, plans sit 5-7x apart -> 2x is a plan, not a mix.
PLAN_RATIO = 2.0
# ⚠Do not lower: the official % is an integer, so below 5% gained rounding alone moves per-1% by >= ±10%.
PLAN_MIN_DPCT = 5
_hist = {"at": 0.0, "acct": {}, "busy": False, "loaded": False}
_hist_lock = threading.Lock()
# `{acct: {"t": cut, "set": when}}` — history before `t` is another plan (persisted in HIST_CACHE; never cleared).
_plan_cut = {}


def tok_counter(ev):
    """`tok(a, b)` = tokens with a < t <= b over sorted `(t, n)` events (prefix sums + bisect)."""
    ts, cum = [e[0] for e in ev], [0]
    for e in ev:
        cum.append(cum[-1] + e[1])
    return lambda a, b: cum[bisect.bisect_right(ts, b)] - cum[bisect.bisect_right(ts, a)]


def h5_per_pct(rows, tok, now):
    """`(per_pct, n, src)` for one account's `(t, h5, reset_epoch)` rows sorted by t; `(None, 0, None)` when unknown.

    `med`: median over closed windows that reached HIST_FULL of tokens(window start -> first >= 99 row) / max h5.
    `pool`: fewer than HIST_MIN_WIN such windows -> sum tokens / sum Δh5 over rising intervals (gap <= HIST_GAP)."""
    closed = [(r, ps) for r, ps in _qburn_cycles(rows) if r <= now]   # ⚠the open window is the thing being predicted
    per, prev = [], None
    for r, ps in closed:
        top, r0, prev = max(h for _t, h in ps), prev, r
        if top < HIST_FULL or len(ps) < HIST_MIN_ROWS:
            continue
        end = next(t for t, h in ps if h >= HIST_FULL)
        # ⚠a manual reset ends a window early (09-27: resets 15:00 then 16:39) — never count the overlap twice
        n = tok(max(r - QBURN_WIN, r0 or 0), end)
        if n > 0:
            per.append(n / top)
    if len(per) >= HIST_MIN_WIN:
        return statistics.median(per), len(per), "med"
    num = den = 0.0
    wins = 0
    for _r, ps in closed:
        used = False
        for (ta, ha), (tb, hb) in zip(ps, ps[1:]):
            if tb - ta <= HIST_GAP and hb > ha:
                num, den, used = num + tok(ta, tb), den + (hb - ha), True
        wins += used
    return (num / den, wins, "pool") if den > 0 and num > 0 else (None, 0, None)


def wk_per_pct(rows, acct, tok):
    """`(per_pct, d7 points)` from consecutive log rows `(t, d7, acct)` (sorted by t) that both belong to `acct`."""
    num = den = 0.0
    for (ta, da, aa), (tb, db, ab) in zip(rows, rows[1:]):
        if aa != acct or ab != acct or da is None or db is None or tb - ta > HIST_GAP or db < da:
            continue
        num, den = num + tok(ta, tb), den + (db - da)
    return (num / den, int(den)) if den >= HIST_MIN_WK and num > 0 else (None, int(den))


def _gkey(r):
    """Group key: `acct|plan` for plan-tagged rows; untagged (older) rows stay under `acct`."""
    a, pl = r.get("acct"), r.get("plan")
    return "%s|%s" % (a, pl) if a and pl else a


def plan_shift(cur_pp, cur_dpct, hist_pp, hist_n):
    """True when this window's per-1% is a different plan from history (ratio >= PLAN_RATIO either way)."""
    if not cur_pp or not hist_pp or cur_dpct < PLAN_MIN_DPCT or hist_n < HIST_MIN_WIN:
        return False
    k = cur_pp / float(hist_pp)
    return k >= PLAN_RATIO or k <= 1.0 / PLAN_RATIO


def hist_compute(log_rows, ev, now, cuts=None):
    """`{acct[|plan]: {h5_per_pct, h5_n, h5_src, wk_per_pct, wk_n}}` from parsed quota-log dicts and `(t, n)` events.

    `cuts` `{acct: t}` drops that account's rows logged before t (a detected plan change)."""
    tok = tok_counter(sorted(ev))
    cuts = cuts or {}
    rows = sorted((r for r in log_rows if isinstance(r.get("t"), (int, float))
                   and r["t"] >= cuts.get(r.get("acct"), r["t"])), key=lambda r: r["t"])
    wk_rows = [(r["t"], r.get("d7"), _gkey(r)) for r in rows]
    out = {}
    for a in sorted({_gkey(r) for r in rows if r.get("acct")}):
        h5 = []
        for r in rows:
            rs = iso_epoch(r.get("reset5"), None)
            if _gkey(r) == a and r.get("h5") is not None and rs is not None:
                h5.append((r["t"], float(r["h5"]), rs))
        hp, hn, hs = h5_per_pct(h5, tok, now)
        wp, wn = wk_per_pct(wk_rows, a, tok)
        out[a] = {"h5_per_pct": None if hp is None else int(hp), "h5_n": hn, "h5_src": hs,
                  "wk_per_pct": None if wp is None else int(wp), "wk_n": wn}
    return out


def _log_rows():
    rows = []
    with open(QUOTA_LOG, encoding="utf-8", errors="ignore") as f:
        for ln in f:
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            if isinstance(d, dict) and d.get("acct"):    # untagged rows (before 2026-09-27) belong to nobody
                rows.append(d)
    return rows


# ★Full rescan of ~1256 transcripts cost ~4.8 s CPU per pass even with nothing changed -> per-file tail cache.
# `{path: {"ino", "off" (byte after last full line), "t0" (events below it pruned), "ev": [(t, key, tok)]}}`; memory only.
_tok_files = {}


def _tok_parse(buf, ev):
    """Append `(t, key, tokens)` for each usage line in `buf` (complete lines only)."""
    for raw in buf.split(b"\n"):
        if b'"usage"' not in raw:
            continue
        try:
            e = json.loads(raw.decode("utf-8", "ignore"))
            m = e.get("message") or {}
            u = m.get("usage") or {}
            t = iso_epoch(e.get("timestamp"), None)
            if t is None or not isinstance(u, dict):
                continue
            ev.append((t, (m.get("id"), e.get("requestId")), sum(int(u.get(x) or 0) for x in _TOK_KEYS)))
        except (ValueError, AttributeError, TypeError):
            continue


def _tok_file(fp, st, t0):
    """Cached events of one file, reading only bytes appended since the last pass."""
    c = _tok_files.get(fp)
    # ⚠a replaced file (new inode), a truncation or an earlier t0 (pruned events needed again) restarts at byte 0
    if c is None or c["ino"] != st.st_ino or st.st_size < c["off"] or t0 < c["t0"]:
        c = _tok_files[fp] = {"ino": st.st_ino, "off": 0, "t0": t0, "ev": []}
    if st.st_size > c["off"]:
        with open(fp, "rb") as f:
            f.seek(c["off"])
            buf = f.read()
        cut = buf.rfind(b"\n")
        if cut >= 0:                          # ⚠a half-written last line waits for the next pass
            _tok_parse(buf[:cut], c["ev"])
            c["off"] += cut + 1
    if t0 > c["t0"]:
        c["ev"] = [x for x in c["ev"] if x[0] >= t0]
        c["t0"] = t0
    return c["ev"]


def _tok_scan(t0):
    """`(t, tokens)` from every transcript touched since t0, deduped by (message.id, requestId)."""
    ev, seen, live = [], {}, set()
    # ⚠Primary root only: the quota log it is matched against belongs to the viewer's own account.
    # ⚠glob order is filesystem-defined (APFS name order, ext4 hash order) -> dedup must not depend on it
    for fp in glob.glob(os.path.join(CLAUDE_PROJECTS, "**", "*.jsonl"), recursive=True):
        try:
            st = os.stat(fp)
            if st.st_mtime < t0:
                continue
            fev = _tok_file(fp, st, t0)
        except OSError:
            continue
        live.add(fp)
        for t, k, n in fev:
            if t < t0:
                continue
            if k != (None, None):             # ⚠dedup at aggregate time: the same key can sit in two files
                i = seen.get(k)
                if i is not None:             # keep the earliest copy: the original request time
                    if t < ev[i][0]:
                        ev[i] = (t, n)
                    continue
                seen[k] = len(ev)
            ev.append((t, n))
    for fp in set(_tok_files) - live:
        _tok_files.pop(fp, None)
    return ev


def _hist_pass():
    try:
        now = time.time()
        rows = _log_rows()
        with _hist_lock:
            cuts = {a: c["t"] for a, c in _plan_cut.items()}
        res = hist_compute(rows, _tok_scan(min(r["t"] for r in rows) - QBURN_WIN) if rows else [], now, cuts)
        with _hist_lock:
            _hist["at"], _hist["acct"] = now, res
        _hist_save()
    except Exception as e:
        warn_once("burn-hist", "per-1% token history failed ({err})", vars={"err": f"{type(e).__name__}: {e}"}, soft=True)
    finally:
        with _hist_lock:
            _hist["busy"] = False


def _hist_save():
    with _hist_lock:
        body = {"at": _hist["at"], "acct": _hist["acct"], "plan_cut": dict(_plan_cut)}
    _atomic_write(HIST_CACHE, json.dumps(body).encode("utf-8"))


def _hist_load():
    """Persisted result from the last run, so a restart has numbers before the first pass ends."""
    try:
        with open(HIST_CACHE, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d.get("acct"), dict) and isinstance(d.get("at"), (int, float)):
            _hist["at"], _hist["acct"] = float(d["at"]), d["acct"]
        if isinstance(d.get("plan_cut"), dict):
            _plan_cut.update({a: c for a, c in d["plan_cut"].items()
                              if isinstance(c, dict) and isinstance(c.get("t"), (int, float))})
    except FileNotFoundError:
        return                       # first run: the pass fills it
    except (OSError, ValueError, AttributeError) as e:
        warn_once("burn-hist-load", "per-1% token history cache unreadable ({err})",
                  vars={"err": type(e).__name__}, soft=True)


def _hist_start():
    threading.Thread(target=_hist_pass, name="burn_hist", daemon=True).start()


def _hist_ensure():
    """Load the persisted table + cuts once (caller holds `_hist_lock`) — a restart must honour a saved cut."""
    if not _hist["loaded"]:
        _hist["loaded"] = True
        _hist_load()


def _hist_get(now):
    """The account table as of now (maybe empty); starts a background pass when stale. Never blocks on a scan."""
    with _hist_lock:
        _hist_ensure()
        # a cut newer than the table re-runs the pass now, not after HIST_TTL
        pend = any(c.get("set", 0) > _hist["at"] for c in _plan_cut.values())
        go = (now - _hist["at"] >= HIST_TTL or pend) and not _hist["busy"]
        if go:
            _hist["busy"] = True
        tab = _hist["acct"]
    if go:
        _hist_start()
    return tab


def _row(tab, acct):
    """`acct|plan` row, else the untagged `acct` row. ⚠The plan code (reads ~/.claude.json) only when a tagged row exists."""
    if not acct:
        return None
    if any(k.startswith(acct + "|") for k in tab):
        r = tab.get("%s|%s" % (acct, _plan_code()))
        if r:
            return r
    return tab.get(acct)


def hist_peek(acct):
    """History row from the table already in memory — never loads the cache or starts a pass."""
    with _hist_lock:
        tab = _hist["acct"]
    return _row(tab, acct)


def plan_cut(acct):
    """`(cut t, cut newer than the history table)` or `(None, False)`.
    ⚠Never cleared: rows before the cut (incl. untagged legacy rows) stay out even after the plan code catches up.
    ⚠Reads memory only — `_qb_body` loads the persisted cuts first via `burn_est` (tests stub that, never the live cache)."""
    with _hist_lock:
        c = _plan_cut.get(acct) if acct else None
        return (c["t"], c.get("set", 0) > _hist["at"]) if c else (None, False)


def plan_check(acct, cur_pp, cur_dpct, start, now):
    """Cut history at this window's `start` when its per-1% (`win`) is another plan than the in-memory history."""
    r = hist_peek(acct) or {}
    if plan_shift(cur_pp, cur_dpct, r.get("h5_per_pct"), r.get("h5_n", 0)):
        plan_cut_set(acct, start, now)


def plan_past(acct, cyc, plans=None):
    """Past `(reset, rows)` cycles at/after the plan cut; with tagged rows (`plans` {t: code}) prefer the current plan's."""
    t = plan_cut(acct)[0]
    keep = [c for c in cyc if not t or (c[1] and min(r[0] for r in c[1]) >= t)]
    cur = _plan_code() if plans else None      # ⚠reads ~/.claude.json only when tagged rows exist
    if not cur:
        return keep
    tags = [[plans.get(int(r[0])) for r in c[1]] for c in keep]
    same = [c for c, g in zip(keep, tags) if cur in g and all(x in (None, cur) for x in g)]
    return same or keep


PLAN_EST_MIN = 2   # % used below which this window's own per-1% is not shown (rounding alone is >= ±25%)


def plan_est(out):
    """Low-confidence `est` from this window's own per-1% (`head` win/step) while history waits out a plan cut."""
    c, hd = out.get("cur") or {}, out.get("head") or {}
    p, pp, w = c.get("now_pct"), hd.get("per_pct"), hd.get("wk") or {}
    if not out.get("ok") or p is None or p < PLAN_EST_MIN or not pp or hd.get("src") not in ("win", "step"):
        return None
    wl, wu = w.get("lim") or 0, w.get("used")
    wk = wl > 0 and wu is not None
    return {"acct": None, "low": True, "h5_per_pct": int(pp), "h5_n": 0, "h5_src": hd["src"],
            "wk_per_pct": int(wl / 100) if wk else None, "wk_n": 0,
            "h5_left": int(pp * max(0.0, 100.0 - p)),
            "wk_left": int(max(0, wl - wu)) if wk else None, "wk_used": int(wu) if wk else None}


def est_fill(out, acct):
    """Fall back to `plan_est` whenever history gives no est; `est_why` = "plan" (cut) or "hist" (none yet).
    ⚠A cut newer than the table nulls the history est first — that table still holds the old plan."""
    cut, pend = plan_cut(acct)
    if pend:
        out["est"] = None
    if out.get("est") is None:
        out["est"] = plan_est(out)
        if out["est"] is not None or pend:
            out["est_why"] = "plan" if cut else "hist"


def plan_cut_set(acct, t, now):
    """Mark history before `t` as another plan (only moves forward); persisted and picked up by the next pass."""
    if not acct:
        return
    with _hist_lock:
        _hist_ensure()                 # ⚠else the save below overwrites the persisted table and cuts
        c = _plan_cut.get(acct)
        if c and c["t"] >= t:
            return
        _plan_cut[acct] = {"t": float(t), "set": float(now)}   # only moves forward (checked above)
    try:
        _hist_save()
    except OSError as e:
        warn_once("burn-hist-cut", "plan cut save failed ({err})", vars={"err": type(e).__name__}, soft=True)


def burn_est(out, acct, now=None):
    """`est` for the burn body: history per-1% × remaining/used %; None when the account or its history is unknown."""
    if not acct:
        return None
    h = _row(_hist_get(time.time() if now is None else now), acct)
    if not h or (h.get("h5_per_pct") is None and h.get("wk_per_pct") is None):
        return None
    hp, wp = h.get("h5_per_pct"), h.get("wk_per_pct")
    p5 = (out.get("cur") or {}).get("now_pct") if out.get("ok") else None
    p7 = (out.get("wk") or {}).get("now_pct")
    return {"acct": acct[:8], "h5_per_pct": hp, "h5_n": h.get("h5_n", 0), "h5_src": h.get("h5_src"),
            "wk_per_pct": wp, "wk_n": h.get("wk_n", 0),
            "h5_left": None if hp is None or p5 is None else int(hp * max(0.0, 100.0 - p5)),
            "wk_left": None if wp is None or p7 is None else int(wp * max(0.0, 100.0 - p7)),
            "wk_used": None if wp is None or p7 is None else int(wp * min(100.0, max(0.0, p7)))}
