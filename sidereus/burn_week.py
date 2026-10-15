"""7d quota side of the burndown: per-account runs of the quota log, the weekly rate and `head.wk` (split from `sidereus.burn`)."""
import json
import threading
from sidereus.warn import warn_once
from sidereus.transcript import _tail_incr
from sidereus.usage import usage
from sidereus.timeline import _tok_events
from sidereus.quota import QUOTA_LOG, _cc_account, quota
from sidereus.burn_calc import _qwk_span, qb_unc

QBURN_NB = 400_000      # first-read tail cap — same as `_quota_log`'s trim cap (= effectively everything)
QB_HEAD_MIN_PCT = 8     # do not back-compute below this % (dividing at 1% right after reset jumps 100x)
_qburn_lock = threading.Lock()   # shared with `burn._qburn_pts`: one lock for both quota-log tails
# ⚠A 1%p dip is source jitter, not a reset (live log 09-04 15:23: 66 -> 67 -> 66 -> 67 within one cycle).
QB_DROP_MIN = 2         # %p fall between consecutive rows that counts as a mid-window reset


# 7d step constants and `_qwk_steps`/`_qwk_span` live in burn_calc (pure); their ★rationale moved with them.
_qwk = {"pos": None, "pts": []}
QB_STALE_DPCT = 30     # a 7d % jump this large between two polls of one account is implausible (see `_acct_runs`)


def _acct_runs(pts):
    """`(runs, switch time or None)` — contiguous runs of the current account's rows (another account's rows split them).

    ★2026-09-27 account switch (7e768e53 -> 5817baff): d7 went 4 -> 12 with no drop, so `cyc` kept the OLD account's
      03:03 reset and divided 87.0M tokens (78M of them the old account's) by the new 14% -> head.wk lim 617M.
    ★2026-10-01 cutting at the LAST foreign row let a 5817baff stint (11:53-13:21) erase
      7e768e53's history since 09-28, leaving a 26-min 96 -> 98 span (19.5M/%, ±50%) vs ≈29M/% from its own 4 -> 96.
      ⇒ Filter foreign rows out instead; a span must stay inside one run (local tokens are not per account).
    ⚠Rows without `acct` (logged before 2026-09-27) are unknown, not a mismatch — they never split.
    `sw` = start of the current run (the last switch back), so callers never mix in the calendar week."""
    if not any(len(p) > 2 and p[2] for p in pts):
        return ([list(pts)] if pts else []), None          # no tagged rows: skip reading ~/.claude.json
    cur = _cc_account()
    if not cur:
        return ([list(pts)] if pts else []), None
    # ★2026-10-02 quota-log `t 1790828464 h5 15 d7 96 acct 5817baff`: at the switch the new account's value got the
    #   old label (5817baff 21 -> 96 -> 96 7e768e53). ⇒ A row equal to the next row's pct, where that row has another
    #   non-empty acct, AND which jumps >= QB_STALE_DPCT from its own label's previous row, reads as the next row's acct.
    #   ⚠Without the jump test it fired on real switches that just happen to share a pct (tests/test_quota AcctSwitch).
    lab = [p[2] if len(p) > 2 else None for p in pts]
    acc = list(lab)
    for i in range(len(pts) - 2, 0, -1):
        if (acc[i + 1] and acc[i + 1] != lab[i] and pts[i][1] == pts[i + 1][1] and lab[i - 1] == lab[i]
                and abs(pts[i][1] - pts[i - 1][1]) >= QB_STALE_DPCT):
            acc[i] = acc[i + 1]
    runs, run, last_foreign = [], [], None
    for p, a in zip(pts, acc):
        if a and a != cur:
            last_foreign = p[0]
            if run:
                runs.append(run)
            run = []
        else:
            run.append(p)
    if run:
        runs.append(run)
    if last_foreign is None:
        return runs, None
    sw = run[0][0] if run else last_foreign
    return runs, sw


def _acct_seg(pts):
    """`(the current account's rows, switch time or None)` — `_acct_runs` flattened."""
    runs, sw = _acct_runs(pts)
    return [p for r in runs for p in r], sw


def _qwk_pts():
    """Accumulated `(t, d7, acct)` from the quota log (incremental tail, same as `_qburn_pts`)."""
    with _qburn_lock:
        lines, _st, _en, rs = _tail_incr(QUOTA_LOG, QBURN_NB, _qwk["pos"])
        if rs:
            _qwk["pts"] = []
        _qwk["pos"] = (_st, _en)
        for ln in lines:
            try:
                d = json.loads(ln)
                t, p = d.get("at") or d.get("t"), d.get("d7")
                if isinstance(t, (int, float)) and isinstance(p, (int, float)) and not isinstance(p, bool):
                    _qwk["pts"].append((float(t), float(p), d.get("acct")))
            except Exception:
                continue
        _qwk["pts"] = _qwk["pts"][-8000:]
        return list(_qwk["pts"])


def _qwk_rate(now, wp):
    """7d `(used tokens, tokens per %, source, reset time or None)` for the current weekly cycle at `wp` %.

    `cyc`: a reset was observed — plain back-computation like 5h: tokens since the reset / wp (wp >= 1).
    `step`: no reset seen — tokens between the latest observed 7d steps spanning >= QB_WK_DPCT, / that span.
    `used` includes the tokens spent since the current % was first logged (see `since` below).
    `(0, 0, None, start)` when neither applies (caller falls back to the calendar week only if start is None)."""
    # ⚠After an account switch only the current account's rows count; `sw` is returned as the start so the caller never
    #   falls back to the calendar week (it holds the other account's tokens too) — unknown beats a mixed number.
    runs, sw = _acct_runs([p for p in _qwk_pts() if p[0] >= now - 7 * 86400])
    own = [p for r in runs for p in r]
    if not own:
        return 0, 0.0, None, sw
    # ★2026-10-01 a 30 -> 22 drop across another account's stint read as a reset: `cyc` gave 9.08M / 22% = lim 41.3M ±2%.
    #   ⇒ `cyc` only for a drop between two rows of one run; across a foreign stint it still cuts the steps (`step` only).
    heads = {sum(len(r) for r in runs[:j]) for j in range(len(runs))}
    i0 = 0
    for i in range(1, len(own)):
        if own[i - 1][1] - own[i][1] >= QB_DROP_MIN:
            i0 = i                                # a drop is a reset, whatever `resets_at` says (1%p = jitter)
    st = own[i0][0] if i0 > 0 else None
    seen = i0 > 0 and i0 not in heads             # the reset happened between two of this account's own rows
    if st is not None:
        runs = [r for r in ([p for p in r if p[0] >= st] for r in runs) if r]
    # ★2026-10-01 left was (100 - pct) x per only, so it froze at 40M while
    #   d7 sat at 98 (25.3M spent since 13:52). ⇒ Tokens since the current % was first logged (this run) count as used.
    cur = runs[-1]
    t_s = None
    if cur[-1][1] == wp and not (sw is not None and sw > cur[-1][0]):   # ⚠last row foreign: no own row since the switch back
        t_s = cur[-1][0]
        for p in reversed(cur):
            if p[1] != wp:
                break
            t_s = p[0]
    # A detected reset wins over `step`: the whole cycle is then post-change, so its own sum is exact, not an estimate.
    # ⚠Only while no other account logged after the reset — its tokens would land in the sum.
    if st is not None and seen and len(runs) == 1:
        if wp >= 1:
            ev = [(t, n) for t, n in _tok_events(st) if t >= st]
            tok = sum(n for _t, n in ev)
            if tok > 0:
                # per pairs the % with tokens up to its first sighting (same as 5h `_qb_step_at`)
                tok_s = sum(n for _t, n in ev if t_s is None or _t < t_s)
                return int(tok), (tok_s if tok_s > 0 else tok) / wp, "cyc", st
        return 0, 0.0, None, st
    sp = _qwk_span(runs)
    if sp is not None:
        (t0, p0), (t1, p1) = sp
        ev = _tok_events(t0)
        tok = sum(n for _t, n in ev if t0 <= _t < t1)
        if tok > 0:
            per = tok / (p1 - p0)
            _qwk["span"] = p1 - p0            # read by `_qb_week` for the rounding term (1 / span)
            since = 0
            if t_s is not None:
                since = sum(n for _t, n in ev if t_s <= _t <= now)   # t_s >= t1 > t0: `ev` already covers it
            return int(wp * per + since), per, "step", None
    return 0, 0.0, None, (st if st is not None else sw)



def _qb_week(now):
    """`head.wk` — 7d used/limit from this weekly cycle's own data, else the calendar week; None when unknown."""
    # ★Weekly is **not drawn on screen** (2026-09-22 — seeing weekly interfered with pacing within the 5h window).
    #   The value stays in the API only as `head.wk` — if separate tracking is needed the user will ask then.
    # ⚠Do not revive it on the default screen. To revive it, it must know workdays (some weeks have only 2~3 workdays).
    hwk = None
    try:
        _uw = (usage() or {}).get("week") or {}
        _wtok = _uw.get("tokens")
        _wq = (quota() or {}).get("seven_day") or {}
        _wp, _wl = _wq.get("pct"), _wq.get("leftSec")
        _wok = (isinstance(_wp, (int, float)) and not isinstance(_wp, bool)
                and isinstance(_wl, (int, float)) and not isinstance(_wl, bool) and _wl > 0)
        # This cycle's own data first (★ at QB_WK_DPCT). After a detected reset it is a plain back-computation
        # (`cyc`, used = tokens since reset, pct >= 1 only); the 8% guard applies to the calendar-week fallback.
        _wu, _wr, _wsrc, _wst = _qwk_rate(now, float(_wp)) if _wok else (0, 0.0, None, None)
        if _wok and _wr > 0:
            hwk = {"used": min(int(_wu), int(100 * _wr)), "lim": int(100 * _wr),   # since can overshoot: left >= 0
                   "pct": round(float(_wp), 1), "left": int(_wl), "src": _wsrc}
            if _wsrc == "cyc":
                # Rounding band of the official % (tooltip only): lim at pct +- 0.5.
                hwk["lo"] = int(_wr * _wp / (_wp + 0.5) * 100)
                hwk["hi"] = int(_wr * _wp / (_wp - 0.5) * 100) if _wp > 0.5 else None
        elif (_wok and _wst is None and _wp >= QB_HEAD_MIN_PCT
                and isinstance(_wtok, (int, float)) and not isinstance(_wtok, bool) and _wtok > 0):
            # ⚠Calendar-week total — only valid when no mid-week reset was observed.
            # ⚠`used` is the amount used — the opposite of 5h's `head.tok` (remaining headroom).
            hwk = {"used": int(_wtok), "lim": int(_wtok / (_wp / 100.0)),
                   "pct": round(float(_wp), 1), "left": int(_wl), "src": "week"}
        if hwk:
            # 7d uncertainty = rounding term only (no per-step token samples kept for 7d): `cyc`/`week` divide by
            # one integer % (0.5/pct); `step` divides by a difference of two (+-0.5 each -> 1/span).
            _sp = _qwk.get("span") or 0
            _u = (1.0 / _sp if _sp > 0 else None) if hwk["src"] == "step" else qb_unc(None, float(_wp))[0]
            # The official % is whole, so headroom is only known to ±1% x per — at 98% (≈33M left, ≈29M/%) that
            # dominates the per-% rounding term; never show the smaller one.
            _wleft = hwk["lim"] - hwk["used"]
            if _wleft > 0:
                _u = max(_u or 0.0, hwk["lim"] / 100.0 / _wleft)
            hwk["unc"] = None if _u is None else round(_u, 3)
    except Exception as e:
        warn_once("qbweek", "Weekly headroom calculation failed ({err})", vars={"err": type(e).__name__}, soft=True)
        hwk = None
    return hwk
