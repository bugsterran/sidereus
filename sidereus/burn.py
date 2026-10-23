"""Quota burndown (`/api/quota/burn`); public face for the usage names split into `sidereus.burn_usage`."""
import json
import os
import threading
import time
from sidereus.config import DATA_DIR
from sidereus.warn import warn_once
from sidereus.bus import _atomic_write
from sidereus.transcript import _tail_incr, iso_epoch
from sidereus.usage import _anchors
from sidereus.timeline import _tok_events
from sidereus.usage_index import acct_tokens
from sidereus.quota import QUOTA_LOG, _cc_account, quota, quota_calibrating
from sidereus.quota_roots import _conf_path, quota_accounts, ring_last, row_usable
from sidereus import boot_queue, claude_roots, ui_prefs
# Pure math owned by burn_calc; the ones only tests read are re-exported too.
from sidereus.burn_calc import (  # noqa: F401
    QB_UNC_N, QBURN_BAND_N, QBURN_TOL, QBURN_WIN, _qb_baseline, _qb_forecast, _qb_interp, _qb_q, _qb_slope,
    _qb_unc_ests, _qburn_cycles, qb_unc, QB_WK_DPCT, QB_WK_DPCT_TARGET, _qwk_span, _qwk_steps, _qb_step_at)
# Re-exported for chat_server (`from sidereus.burn import ...`); owned by burn_usage.
from sidereus.burn_usage import (  # noqa: F401
    WK_DAYS, _WK_RANGES, _live_buckets, _today_loop, _wk_slot, _wkuse_busy, _wkuse_loop, wk_stale, wkuse,
    wkuse_refresh)
from sidereus.burn_hist import burn_est, est_fill, plan_check, plan_cut, plan_past
# 7d side (account runs, weekly rate, `head.wk`) owned by burn_week; ⚠patch `_qwk_pts`/`_tok_events`/`_cc_account`/`quota` on both modules.
from sidereus.burn_week import (
    QB_DROP_MIN, QB_HEAD_MIN_PCT, QBURN_NB, _acct_seg, _qb_week, _qburn_lock, _qwk_pts)


# ───── quota burndown ─────────────────────────────────────────────────────────
# ★Why (2026-09-21): the screen only showed «current %» and «minutes to reset», so **"at this pace will
#   it run out before reset"** was mental math every time. The screen does that math now.
#   `quota-log.jsonl` had only been written, never read — the raw material already existed.
# ⚠**This is an estimate.** The UI text also says "at this pace" — on a monitoring screen an estimate must not look measured.
# ⚠Never parse the whole file per request. It is append-only, so `_tail_incr` accumulates **only the new tail**
#   (per `_tail_incr`'s ★rationale above — putting size in the cache key means one byte misses everything).
#   One more TTL cache layer on top (polling is 2.5s; no reason to recompute every time).
# ⚠Cycle boundaries split on `reset5` but with **±120s tolerance**. Within one cycle the value jitters by seconds
#   (measured 09-21: same cycle was 23:29:59.7 ↔ 23:30:00.2 — splitting by string would cut one cycle in two).
# ⚠No conversation content in the response — `quota-log.jsonl` itself is just %·time, and only those move here.
QBURN_TTL = 30          # response cache (s)
QB_CALIB_DPCT = 5       # own 5h span below this (or no own per-%) = calibrating -> 60 s usage polling
# `QB_HEAD_MIN_PCT` (burn_week) is computed from live values at once — the old 30-min wait
#   (QB_HEAD_WARM) is gone: the error comes from the integer % (+-0.5/pct), not elapsed time, so the % floor alone gates it.
#   The wait hid a 22% window behind the anchor after an account switch discarded the saved denominator.
QB_LIM_TTL = 12 * 3600  # how long the last successful back-computed value may be reused (s)
# ★The back-computed denominator is also persisted to a file (approved 2026-09-22) — memory-only meant a restart
#   fell back to the anchor (3.2x overestimate) until the window hit 30 min again. ⚠Do not touch `usage-anchor.json` — the user maintains it by hand.
QB_LIM_CACHE = os.path.join(DATA_DIR, "qb-lim-cache.json")
# ★2026-09-28 stamp: `acct` (accountUuid) · `reset` (5h cycle end) · `seg` (segment start) — `_qb_lim_stale` drops another account's value.
_qb_lim = {"lim": 0.0, "at": 0.0, "loaded": False, "acct": None, "reset": 0.0, "seg": 0.0}


def _qb_lim_load():
    """Reload the previous back-computed denominator from the file **once**. Discard if outside TTL or for another account."""
    if _qb_lim["loaded"]:
        return
    _qb_lim["loaded"] = True
    try:
        with open(QB_LIM_CACHE, encoding="utf-8") as f:
            c = json.load(f)
        lim, at, ac = float(c.get("lim") or 0), float(c.get("at") or 0), c.get("acct")
        cur = _cc_account()
        # ⚠Do not load another account's denominator — if either is unknown (None), do not discard (unknown is not a mismatch).
        if lim > 0 and (time.time() - at) <= QB_LIM_TTL and not (ac and cur and ac != cur):
            _qb_lim["lim"], _qb_lim["at"], _qb_lim["acct"] = lim, at, ac
            _qb_lim["reset"], _qb_lim["seg"] = float(c.get("reset") or 0), float(c.get("seg") or 0)
    except Exception:
        pass                    # missing or corrupt cache: back-compute from scratch


def _qb_lim_set(lim, at, reset=None, seg=None):
    ac = _cc_account()
    _qb_lim.update({"lim": float(lim), "at": float(at), "loaded": True, "acct": ac,
                    "reset": float(reset or 0), "seg": float(seg or 0)})
    try:
        # ⚠a partial write would make the next startup fall back to the anchor
        _atomic_write(QB_LIM_CACHE,
                      json.dumps({"lim": float(lim), "at": float(at), "acct": ac,
                                  "reset": float(reset or 0), "seg": float(seg or 0)}).encode("utf-8"),
                      prefix=".qb-lim.")  # ⚠no fixed tmp — a pid name is shared by concurrent request threads
    except OSError as e:
        warn_once("qb-lim-save", "limit estimate cache save failed ({err}) — re-estimated on restart",
                  vars={"err": f"{type(e).__name__}: {e}"}, soft=True)
_qburn ={"pos": None, "pts": [], "at": 0, "out": None, "plan": {}}   # plan: {t: plan code} of tagged rows


def _qb_epoch(s):
    """`reset5` (ISO) → epoch seconds. None if unreadable (old-format lines are skipped)."""
    return iso_epoch(s, None)


def _qburn_pts():
    """Accumulated `(t, h5, reset_epoch)`. Reads and appends only the incremental tail (drops the accumulation on `reset`)."""
    with _qburn_lock:
        lines, _st, _en, rs = _tail_incr(QUOTA_LOG, QBURN_NB, _qburn["pos"])
        if rs:
            _qburn["pts"] = []
        _qburn["pos"] = (_st, _en)
        add, padd = [], {}
        for ln in lines:
            try:
                d = json.loads(ln)
            except Exception:
                continue                       # 30 days of data mixes in broken/old lines — skip them
            t, h = d.get("t"), d.get("h5")
            r = _qb_epoch(d.get("reset5"))
            if r is None or h is None or not isinstance(t, (int, float)):
                continue
            try:
                add.append((int(t), float(h), float(r)))
                padd.update({int(t): d["plan"]} if d.get("plan") else {})
            except (TypeError, ValueError):
                continue
        if add:
            _qburn["pts"] = (_qburn["pts"] + add)[-8000:]
        t0 = _qburn["pts"][0][0] if _qburn["pts"] else float("inf")   # ⚠replaced, never mutated: readers hold no lock
        _qburn["plan"] = {k: v for k, v in list(_qburn.get("plan", {}).items()) + list(padd.items()) if k >= t0}
        return list(_qburn["pts"])


# ★Measured 2026-09-24: the first call after a restart took 9.38 s (cold `_tok_events` -> `sessions()`, 1.05 s alone,
#   stretched by the startup threads) and the saver hook times out at 3 s -> «Pending». Its `rate_pph` was 1.21 vs
#   2.74 five seconds later: it read the quota log before the startup fetch appended the live sample (last line then
#   was the pre-restart 10%, live was 12%), and that partial body was cached as final for QBURN_TTL.
# ⇒ `_qburn_warm` (started from main) computes the full body once a live sample is logged. Until then requests get
#   the log-only body (`head` None, `warm: False`, never cached), after waiting up to QBURN_COLD_WAIT for that sample.
# ⚠Without a live sample the light body is the last persisted value (pre-restart log) — still better for the hook
#   than `ok: False`, which sends it to the 3.7MB `/api/state` fallback.
QBURN_COLD_WAIT = 0.7   # s — must stay well under the hook's 3 s timeout
QBURN_WARM_MAX = 60     # s — the warm thread stops waiting; requests then get the full body, still `warm: False`
_qb_warm = {"on": False, "done": False, "cold": False, "t0": 0}


def _qb_live():
    """True once the quota log holds a row written by this process (`_quota_log` always writes its first one)."""
    # ⚠Read the log itself, not `quota._qlog_last`: that is set before the line is appended, so the warm body
    #   was once computed from the pre-sample log and cached (live 09-24: full 6.13 vs fast 7.0 at the same time).
    pts = _qburn_pts()
    return bool(pts) and pts[-1][0] >= _qb_warm["t0"]


def qburn_warm_start():
    _qb_warm["on"], _qb_warm["t0"] = True, int(time.time())   # before the server listens: no early slow request
    threading.Thread(target=_qburn_warm, name="qburn_warm", daemon=True).start()


def _qburn_warm():
    t0 = time.time()
    try:
        while not _qb_live() and time.time() - t0 < QBURN_WARM_MAX:
            time.sleep(0.2)
        with boot_queue.gate("qburn_warm"):   # ⚠after the live-sample wait: never hold the boot gate across it
            if _qb_live():
                _qb_full(time.time())
                _qb_warm["done"] = True
            else:
                _qb_body(time.time())     # ⚠warms the token caches only — a pre-sample body is never cached as final
    except Exception as e:
        warn_once("qburn-warm", "quota burn warm-up failed ({err})",
                  vars={"err": f"{type(e).__name__}: {e}"}, soft=True)
    finally:
        _qb_warm["cold"] = True       # requests take over; the first one that sees a live row caches and ends warm-up


def quota_burn():
    """Body of `GET /api/quota/burn` — current-cycle curve + linear extrapolation + past-cycle median baseline."""
    now = time.time()
    with _qburn_lock:
        if _qburn["out"] and now - _qburn["at"] < QBURN_TTL:
            return _qburn["out"]
    if _qb_warm["on"] and not _qb_warm["done"]:
        if _qb_warm["cold"]:
            if _qb_live():
                _qb_warm["done"] = True
                return _qb_full(now)
            out = _qb_body(now)[0]
        else:
            t0 = time.time()
            while not _qb_live() and time.time() - t0 < QBURN_COLD_WAIT:
                time.sleep(0.05)
            out = _qb_body(time.time(), light=True)[0]
        out["warm"] = False
        return out
    return _qb_full(now)


_qb_acct = {}           # label -> (at, body): per-account burn cache, same QBURN_TTL


def _qb_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def quota_burn_acct(label):
    """Burn body for a non-primary account `label` from its `quota_accounts()` row (label + percentages only)."""
    now = time.time()
    c = _qb_acct.get(label)
    if c and now - c[0] < QBURN_TTL:
        return c[1]
    out = _qb_acct_body(label, now)
    _qb_acct[label] = (now, out)
    return out


def _qb_acct_body(label, now):
    row = next((r for r in quota_accounts() if r.get("label") == label), None)
    fh = (row or {}).get("five_hour") or {}
    pct, left = fh.get("pct"), fh.get("leftSec")
    if not row_usable(row) or not _qb_num(pct) or not _qb_num(left) or left <= 0:
        return {"ok": False, "why": "not measured"}
    pct = float(pct)
    pts = [(float(p[0]), float(p[1])) for p in fh.get("pts") or []]
    rate, over_at, ppct, praw = None, None, None, None
    if len(pts) >= 2:   # same 45-min slope as the primary (`_qb_forecast`); the ring holds only % steps
        r, raw, oa, n_obs = _qb_forecast(now, pts, pct, float(left))
        rate = round(r, 2)
        over_at = int(oa) if oa else None   # same as primary: at 100% it is the last row's time, even at rate 0
        ppct = None if n_obs < 2 else round(min(100.0, max(0.0, raw)), 1)   # ⚠same rule as `_qb_current` proj.pct
        praw = None if n_obs < 2 else round(raw, 1)
    elif pct >= 100:    # already full is a fact, not a forecast: no slope needed
        over_at = int(pts[-1][0] if pts else now)
    out ={"ok": True, "at": int(now), "acct": label,
           # pts/age/raw feed the modal curve; ⚠no start/reset/elapsed here (svLive would start using them)
           "cur": {"now_pct": round(pct, 1), "left": int(left), "rate_pph": rate,
                   "rate_src": "pts" if rate is not None else "not measured",
                   "age": row.get("age"), "pts": [[int(t), round(h, 1)] for t, h in pts]},
           "proj": {"pct": ppct, "raw": praw, "over_at": over_at,
                    "over_in": int(max(0, over_at - now)) if over_at else None}}
    wk = (row.get("seven_day") or {})
    if _qb_num(wk.get("pct")) and _qb_num(wk.get("leftSec")) and wk["leftSec"] > 0:
        out["wk"] = {"now_pct": round(float(wk["pct"]), 1), "left": int(wk["leftSec"])}
    # ⚠`used_acct` = acct_tokens hour-bucket sum (first hour pro rata): approximate, never `used_local` (exact sum)
    n5 = acct_tokens(label, now + int(left) - QBURN_WIN, now)
    n7 = acct_tokens(label, now + out["wk"]["left"] - 7 * 86400, now) if "wk" in out else 0
    if n5 > 0:
        out["cur"]["used_acct"] = int(n5)
    if n7 > 0:
        out["wk"]["used_acct"] = int(n7)
    key = _qb_acct_key(label)
    out["est"] = burn_est(out, key)   # same history est as the primary body; None when the key is unknown
    if out["est"] is None or plan_cut(key)[1]:
        # No history yet: this account's own window per-1% (plan_est, low). ⚠`head` stays on a copy — on the body it
        #   would flip saver_cap to conf high; never the primary's per-1% (plans sit 5-9x apart).
        tmp = dict(out, head=_qb_acct_win(out, n5, n7))
        est_fill(tmp, key)
        out["est"] = tmp["est"]
        if "est_why" in tmp:
            out["est_why"] = tmp["est_why"]
    return out


def _qb_acct_win(out, n5, n7):
    """`plan_est` inputs from this account's own tokens `n5`/`n7` since its 5h/7d window start (usage index), else None."""
    c, w = out["cur"], out.get("wk") or {}
    if n5 <= 0 or c["now_pct"] <= 0:
        return None
    hd = {"per_pct": int(n5 / c["now_pct"]), "src": "win", "wk": None}
    if w.get("now_pct", 0) >= 1:
        if n7 > 0:
            hd["wk"] = {"lim": int(n7 / w["now_pct"] * 100), "used": n7}
    return hd


def _qb_acct_key(label):
    """History key `uuid|plan` of a non-primary account from its own .claude.json; None when unknown.
    ⚠Always `uuid|plan`: `burn_hist._row` would otherwise resolve the plan from the primary's config or fall back
      to a plan-less legacy row."""
    d = next((r.get("dir") for r in claude_roots.accounts() if r.get("label") == label and not r.get("primary")), None)
    if not d:
        return None
    try:
        with open(_conf_path(d), encoding="utf-8") as f:
            oa = json.load(f).get("oauthAccount") or {}
        uid, plan = oa.get("accountUuid"), oa.get("userRateLimitTier") or oa.get("organizationType")   # = quota._plan_code
    except (OSError, ValueError, AttributeError):
        return None
    return "%s|%s" % (uid, plan) if isinstance(uid, str) and uid and isinstance(plan, str) and plan else None


def burn_use(now=None):
    """`{label, primary, src}` = the account the modal burndown and the saver cap follow (one decision for both).
    src "main": an explicit non-primary «Main account» (ui-prefs `mbMainAcct`) · "live": the account whose 5h log has
    the newest step inside a live window · "primary": tie / none live / single account. Metadata only."""
    now = time.time() if now is None else now
    acc = claude_roots.accounts()
    prim = next((r.get("label") for r in acc if r.get("primary")), "")
    others = {r.get("label") for r in acc if not r.get("primary") and r.get("label")}
    if others:
        try:
            m = (ui_prefs.load() or {}).get("mbMainAcct")
        except Exception:
            m = None
        if isinstance(m, str) and m in others:
            return {"label": m, "primary": False, "src": "main"}
        best, bt = None, max((t for t, _h, r in _qburn_pts() if r > now), default=None)
        for lab, (r5, t) in ring_last().items():
            # ⚠strictly newer: a tie keeps the primary (single-account output unchanged)
            if lab in others and _qb_num(r5) and r5 > now and _qb_num(t) and (bt is None or t > bt):
                best, bt = lab, t
        if best:
            return {"label": best, "primary": False, "src": "live"}
    return {"label": prim, "primary": True, "src": "primary"}


def quota_burn_peek(now=None):
    """Cached primary body if younger than USED5_MAX_AGE, else None — never scans (`?dir=` callers are the 3 s hook)."""
    now = time.time() if now is None else now
    with _qburn_lock:
        out, at = _qburn["out"], _qburn["at"]
    return out if out and now - at <= USED5_MAX_AGE else None


USED5_MAX_AGE = 120     # s — older cached body: callers keep their own figure


def used5_peek(now=None):
    """`(start, reset, used)` = the status bar's 5h used tokens (`cur.used_local`) from the cached body, else None.
    ⚠The one source for every other 5h «used» figure (usage.block, quotaWho) — they diverged by 3.1M (220.3M vs 223.4M)
      reading OTel/ccusage instead. Cache only: `/api/state` must not pay the `_tok_events` scan."""
    now = time.time() if now is None else now
    with _qburn_lock:
        out, at = _qburn["out"], _qburn["at"]
    c = (out or {}).get("cur") or {}
    if c.get("used_local") is None or now - at > USED5_MAX_AGE:
        return None
    return c.get("start"), c.get("reset"), c["used_local"]


def _qb_full(now):
    out, keep = _qb_body(now)
    if keep:
        with _qburn_lock:
            _qburn["at"], _qburn["out"] = now, out
    return out


def _qb_body(now, light=False):
    """`(body, cacheable)` — a log read error is not cached."""
    try:
        cyc = _qburn_cycles(_qburn_pts())
    except Exception as e:
        return {"ok": False, "why": "%s: %s" % (type(e).__name__, e)}, False
    _ac = _cc_account(); burn_est({}, _ac)   # ⚠loads persisted plan cuts before `_qb_current` reads them (restart)
    out = {"ok": False, "why": "no-data", "at": int(now)}
    if cyc:
        reset, rows = cyc[-1][0], sorted(cyc[-1][1])
        if now > reset:
            # the cycle already ended — extrapolating «the past cycle» as current before the next line arrives would be false.
            out = {"ok": False, "why": "stale", "at": int(now), "reset": int(reset)}
        else:
            out = _qb_current(now, cyc, reset, rows, light)
    _qb_add_wk(out)
    if not light and out.get("wk"):
        # The measured 7d sum also rides on top-level `wk`, so a body without `cur` (5h cycle just ended, no new
        # row yet: «stale») still carries it — otherwise the status bar flips to the estimate for that minute.
        _c = out.get("cur")
        _wu = _c["wk_used_local"] if _c else _qb_wk_used(_qb_week(now))
        if _wu is not None:
            out["wk"]["used_local"] = _wu
    out["est"] = burn_est(out, _ac)   # history per-1% (sidereus/burn_hist.py)
    est_fill(out, _ac)   # no usable history (plan cut / too new): this window's own per-1%, flagged low
    return out, True


def _qb_drop(rows):
    """Index of the last row whose h5 fell >= QB_DROP_MIN below the previous row's (0 when none)."""
    return max((i for i in range(1, len(rows)) if rows[i - 1][1] - rows[i][1] >= QB_DROP_MIN), default=0)


def _qb_seg(start, rows):
    """`(t0, p0)` — where this window's own usage starts: the window start, or a later account switch / mid-window drop.

    ★2026-09-27: a one-time manual 5h reset may keep `reset5` (unknown) — h5 drops (40 -> 0) inside one cycle, and
      tokens/rows before the drop were already charged. Same treatment as a switch: count from the first row after it."""
    t0, p0 = start, 0.0
    _sw = _acct_seg(_qwk_pts())[1]
    if _sw and _sw > start:
        t0, p0 = next(((t, h) for t, h in rows if t >= _sw), (_sw, rows[-1][1] if rows else 0.0))
    i = _qb_drop(rows)
    if i and rows[i][0] > t0:
        t0, p0 = rows[i]
    return t0, p0


def _qb_current(now, cyc, reset, rows, light=False):
    """`ok: True` body for a live cycle: curve, forecast, past-cycle baseline and token headroom (`light`: no headroom)."""
    start = reset - QBURN_WIN
    now_pct = rows[-1][1]
    left = max(0.0, reset - now)
    seg = _qb_seg(start, rows)
    # ⚠the slope uses only rows since the segment start — a pre-drop/other-account row would bend it
    rate, raw, over_at, n_obs = _qb_forecast(now, [r for r in rows if r[0] >= seg[0]], now_pct, left)
    # current-cycle points — thin evenly if too many (drawing width is ~200px)
    pts = rows if len(rows) <= 300 else [rows[i] for i in
                                         range(0, len(rows), len(rows) // 300 + 1)] + [rows[-1]]
    # ★2026-09-27 account switch: past cycles logged before the switch are the old account's pace — not a baseline.
    _sw = _acct_seg(_qwk_pts())[1]
    _ac = _cc_account()
    elapsed = max(0.0, min(float(QBURN_WIN), now - start))
    head, used_local, wk_used_local = None, None, None
    if not light:              # headroom needs `_tok_events` — the cold-start cost
        # Used tokens = measured sum since the window start; seg[0] only after a switch.
        u0 = seg[0] if _sw and _sw > start else start
        try: used_local = int(sum(n for _t, n in _tok_events(u0) if u0 <= _t <= now))
        except Exception as e: warn_once("qb-used", "5h used-token sum failed ({err})",
                                         vars={"err": type(e).__name__}, soft=True)
        t_obs = _qb_step_at(rows, seg[0])
        lim, lsrc, unc = _qb_limit(now, start, now_pct, rows, seg, t_obs)
        if lsrc == "win": plan_check(_ac, lim / 100.0, now_pct - seg[1], start, now)   # plan code lags an upgrade
        # ⚠only after an account switch — a fresh window / idle h5=0 also lacks a per-% but needs no fast polling
        quota_calibrating(_sw is not None and lsrc not in ("win", "recent") and
                          not (lsrc == "step" and now_pct - seg[1] >= QB_CALIB_DPCT))
        after = 0
        if lim > 0:
            try:                   # same key as `_qb_limit`'s call -> the cached events, no second scan
                after = sum(n for _t, n in _tok_events(seg[0]) if t_obs < _t <= now)
            except Exception:
                after = 0
        # ★2026-09-29 subtracting `after` made headroom fall 1:1 through a step, then the
        #   next step re-divided W/p and jumped back up (live 18%: 253.1M -> 248.8M in 150 s; replay of 13 past cycles:
        #   upward moves 13~231M per cycle). ⇒ Headroom is as of the % reading and moves only on a new step; `since`
        #   carries the not-yet-counted spend. ⚠Do not subtract `after` again — that re-creates the sawtooth.
        hwk = _qb_week(now)
        head = _qb_head(now, start, now_pct, left, rate, lim, lsrc, hwk=hwk)
        # 7d `cyc` = the real token sum since a seen reset (measured); `step`/`week` are estimates -> None.
        # ⚠Not gated on `head`: a 5h window without a denominator (h5 0% right after its reset) dropped the
        #   measured 7d sum and the status bar fell back to the per-1% estimate (483M -> «≈ 506M»).
        wk_used_local = _qb_wk_used(hwk)
        if head is not None:
            head["since"] = int(after)
            head["unc"] = None if unc[0] is None else round(unc[0], 3)
            head["unc_n"] = unc[1]
    # ★2026-09-27 manual reset: a past cycle holding an h5 drop is two paces spliced together — not a baseline.
    past = [c for c in cyc[:-1] if not _qb_drop(sorted(c[1])) and
            (not _sw or (c[1] and min(t for t, _h in c[1]) >= _sw))]
    kept = plan_past(_ac, past, _qburn.get("plan"))
    bases, bpts, band, bwm, bwhy = _qb_baseline(kept + cyc[-1:])
    bwhy = "plan" if not bases and len(kept) < len(past) else bwhy
    bnow = _qb_interp([(p[0], p[1]) for p in bpts], elapsed) if len(bpts) >= 2 else None
    return {
        "ok": True, "at": int(now),
        "cur": {"start": int(start), "reset": int(reset), "now": int(now),
                "now_pct": round(now_pct, 1), "left": int(left), "elapsed": int(elapsed),
                "age": int(max(0, now - rows[-1][0])), "rate_pph": round(rate, 2),
                "used_local": used_local, "wk_used_local": wk_used_local,
                "pts": [[int(t), round(h, 1)] for t, h in pts]},
        # ⚠if `n_obs < 2` no forecast is emitted (★rationale in `_qb_forecast`) — the frontend handles null.
        "proj": {"pct": None if n_obs < 2 else round(min(100.0, max(0.0, raw)), 1),
                 "raw": None if n_obs < 2 else round(raw, 1),
                 "over_at": int(over_at) if over_at else None,
                 "over_in": int(max(0, over_at - now)) if over_at else None},
        "base": {"n": len(bases), "pts": bpts, "band": band, "bw": bwm,
                 "band_n": QBURN_BAND_N, "why": bwhy},
        "head": head,
        "delta": None if bnow is None else round(now_pct - bnow, 1),
    }


def _qb_lim_stale(start, t0):
    """True when the held denominator belongs to another account: uuid mismatch, or (uuid unknown) it was
    stamped before this window's account-switch/drop cut `t0`. ⚠A plain 5h reset is not stale — same account, same cap."""
    ac = _qb_lim.get("acct")
    cur = _cc_account() if ac else None
    if _qb_lim["at"] < (plan_cut(cur or _cc_account())[0] or 0):
        return True                     # held before a detected plan change: the old plan's cap
    if ac and cur:
        return ac != cur
    return bool(t0 and t0 > start and _qb_lim["at"] < t0)


def _qb_limit(now, start, now_pct, rows=(), seg=None, t_obs=None):
    """5h token denominator `(lim, src, (unc, n))`: this window's back-computation, else last success, else the anchor.

    `(unc, n)` is only measured for `win`; `(None, 0)` otherwise (no samples of this window behind the number)."""
    unc = (None, 0)
    # ★Also express "% to empty" as **tokens** (2026-09-21: remaining tokens to empty).
    # ⚠Request count is not emitted — `_burn` measures **context size** per request, not consumption
    #   (cache reads are 0.1x). Dividing by it yields a baseless number.
    # ★The denominator is **back-computed within this block** (2026-09-22) — not stored.
    #   It used to divide by the fixed `blockLimitTokens` in `usage-anchor.json` (09-04 calibration, 519,164,200),
    #   a 3.4x overestimate (measured: official 35.0% · local 47,096,985 tokens ⇒ actual cap ≈135M).
    #   ⚠**A fixed denominator is impossible in principle** — the limit is charged by model weighting, not raw tokens.
    #     A cache-read-heavy block barely consumes the limit even with many tokens; Opus-heavy is the opposite.
    #     Observed max 617,242,503 vs today's back-computed 135M = **4.5x** spread. ⇒ Do not revert to the anchor.
    #   ⚠It is still an **estimate** (cache weights are not published) ⇒ do not remove the `≈` in the UI text.
    # ★Do not require identical windows (2026-09-22) — ccusage blocks and the official cycle have different anchors and are
    #   always offset (measured 90 min). ⇒ Sum local tokens from the official cycle start only; if that fails, hold on the last success (`_qb_lim`).
    lim, lsrc, t0, step = 0.0, None, None, None
    # ★First priority is **the local sum aligned to the official cycle** (2026-09-22; user flagged a 462M
    #   figure as wrong — the ccusage block (05:00) opened before the official cycle (08:30);
    #   measured 13% · local 23.4M ⇒ real denominator ≈180M).
    # ⚠The anchor fallback is a 3.2x overestimate (519,164,200) — do not reverse this order.
    try:
        # ★2026-09-27: after an account switch or a mid-window drop (manual reset) inside this window, tokens before
        #   it are not this usage. ⇒ Count from the segment start (`_qb_seg`) and divide by the % gained since then.
        t0, p0 = seg if seg else _qb_seg(start, rows)
        if now_pct - p0 >= QB_HEAD_MIN_PCT:
            # ★2026-09-23: do not call `agents_timeline()`. It is a rendering function that
            #   put tokens into `max(30, span/240)` buckets, and when the reset boundary fell inside
            #   a bucket that span was dropped entirely (measured 4.95h elapsed · 75s buckets · 48s lost
            #   after reset · 237,189,564 vs 237,043,400). ⇒ Sum raw events directly.
            # ⚠Do not tie quota numbers to screen resolution again.
            _ev = _tok_events(t0)
            # ★2026-09-28 tokens ran to `now` but the % was logged up to
            #   5 min earlier, so with parallel agents lim (and headroom) climbed between polls and fell at each step.
            #   ⇒ Pair the % with tokens up to the moment it was logged (`t_obs`).
            _te = now if t_obs is None else t_obs
            _wt = sum(n for _t, n in _ev if t0 <= _t <= _te)
            if _wt > 0:
                lim, lsrc = _wt / ((now_pct - p0) / 100.0), "win"
                _qb_lim_set(lim, now, start + QBURN_WIN, t0)
                try:
                    if t0 == start:
                        unc = qb_unc(_qb_unc_ests(rows, start, _ev) + [lim / 100.0], now_pct)
                    else:
                        # After a mid-window switch/drop: samples are measured from (t0, p0), and the divisor is a
                        # difference of two integer % (+-0.5 each), so rounding is 1/span, not 0.5/pct.
                        _sp = now_pct - p0
                        u, n = qb_unc(_qb_unc_ests([(t, h - p0) for t, h in rows if t >= t0], t0, _ev)
                                      + [lim / 100.0], _sp)
                        unc = (max(u, 1.0 / _sp), n)
                except Exception:
                    unc = (None, 0)       # ⚠never let the uncertainty drop the denominator itself
        elif now_pct - p0 >= 1:
            # ★2026-10-01 an account switch resets the estimate (Max 5x -> Pro kept the old
            #   5.19M/%): nothing crosses a switch; this own first step (±1/span) is used when no `recent`, else «Measuring».
            #   ⚠No plan-ratio prior — the user refused borrowing another account's value.
            _sp = now_pct - p0
            _te = now if t_obs is None else t_obs
            _wt = sum(n for _t, n in _tok_events(t0) if t0 <= _t <= _te)
            if _wt > 0:
                step = (_wt / (_sp / 100.0), 1.0 / _sp)
    except Exception as e:            # ⚠do not reset lim to 0 here — the fallback below runs
        warn_once("qbwin", "5h denominator calculation failed ({err}) — using the saved value",
                  vars={"err": type(e).__name__}, soft=True)
    # ⚠No ccusage-block fallback: its block opens on the hour, before the official cycle, so a
    #   `block start >= cycle start` guard never passed; if passed it would equal `win` (removed 2026-09-23).
    if lim <= 0:
        _qb_lim_load()            # right after restart the previous value left in the file is the only measurement
        if _qb_lim["lim"] > 0 and _qb_lim_stale(start, t0):
            _qb_lim.update({"lim": 0.0, "at": 0.0})    # account changed in-process: never divide by the old cap
    if lim <= 0 and _qb_lim["lim"] > 0 and (now - _qb_lim["at"]) <= QB_LIM_TTL:
        lim, lsrc = float(_qb_lim["lim"]), "recent"      # hit a guard — hold on the last success
    if lim <= 0 and step:
        lim, lsrc, unc = step[0], "step", (step[1], 0)
    if lim <= 0 and _acct_seg(_qwk_pts())[1] is None:   # ⚠never the hand-kept anchor once accounts have switched
        # none either — hold on the old anchor (without it `head` does not exist)
        lim = float((_anchors() or {}).get("blockLimitTokens") or 0)
        lsrc = "anchor" if lim > 0 else None
    return lim, lsrc, unc


def _qb_wk_used(hwk):
    """Measured 7d used tokens — only a `cyc` sum (tokens since an observed reset); estimates give None."""
    return hwk.get("used") if hwk and hwk.get("src") == "cyc" else None


def _qb_head(now, start, now_pct, left, rate, lim, lsrc, after=0, hwk=False):
    """Token headroom block (`head`), None without a denominator. `after`: tokens spent since the % was logged.
    `hwk`: the caller's `_qb_week(now)` result (False = compute it here)."""
    # ⚠`_qb_week` runs even when `lim <= 0` (same call order as before the split: quota()/usage() side effects).
    if hwk is False:
        hwk = _qb_week(now)
    head = None if lim <= 0 else {
        "tok": int(max(0.0, max(0.0, 100.0 - now_pct) / 100.0 * lim - after)),
        # Back-solved here so the page never derives a 5h figure of its own: its timeline sum
        # follows the **display range**, not the cycle (4h51m in: range 1h 90.0M vs 6h 226.1M,
        # gauge 225.3M). ⚠Keep used/left on this side.
        "used": int(min(lim, max(0.0, now_pct) / 100.0 * lim + after)),
        "per_pct": int(lim / 100.0), "lim": int(lim), "src": lsrc,
        "tph": int(max(0.0, rate) / 100.0 * lim),   # current rate (tokens/hour)
        # ★Headroom **multiple** — same formula as the saver hook (`room_of` in `saver.py`).
        #   ⚠Token counts alone cannot compare the two axes (window lengths differ 33.6x).
        "room": (round((100.0 - now_pct) / (left / 60.0 * 100.0 / 300.0), 2)
                 if left > 0 else None),
        "wk": hwk,
    }
    # The usable headroom is the tighter of the two caps (seen: 5h 420M vs 7d 238M).
    # ⚠`wk.left` is seconds to reset, not tokens - 7d token headroom is lim - used.
    if head is not None:
        head["eff"], head["cap"] = head["tok"], "5h"
        if hwk and hwk.get("lim", 0) > 0:
            _wroom = max(0, hwk["lim"] - hwk["used"])
            if _wroom < head["tok"]:
                head["eff"], head["cap"] = _wroom, "7d"
    return head


def _qb_add_wk(out):
    """Top-level `wk`: the official 7d snapshot as-is (no extrapolation), added to every response shape."""
    # ★Also carry the weekly axis (2026-09-22) — the saver hook judged on 5h only, so late in the week while 7d
    #   was filling it still said "launch 4". The hook calls only this endpoint (`/api/state` is
    #   3.7MB, unusable · this one is 1.4KB) ⇒ adding one line here is the only cheap place.
    # ⚠Unlike the 5h curve (`cur`) this is **the official snapshot as-is** — no extrapolation·baseline (there is no weekly log).
    try:
        _wk = (quota() or {}).get("seven_day") or {}
        _wp, _wl = _wk.get("pct"), _wk.get("leftSec")
        if isinstance(_wp, (int, float)) and not isinstance(_wp, bool) \
           and isinstance(_wl, (int, float)) and not isinstance(_wl, bool) and _wl > 0:
            out["wk"] = {"now_pct": round(float(_wp), 1), "left": int(_wl)}
    except Exception as e:
        warn_once("qb-wk", "weekly quota attach failed ({err}) — responding without wk",
                  vars={"err": f"{type(e).__name__}: {e}"}, soft=True)
