"""Pure quota-burndown math (split from burn.py 2026-09-25): cycle split, interpolation, quantiles, slope,
forecast, past-cycle baseline and the denominator's uncertainty. No I/O, no module state."""


QBURN_TOL = 120         # tolerance for same-cycle check (s)
QBURN_WIN = 5 * 3600    # 5-hour window
QBURN_GRID = 300        # baseline grid (s)
QBURN_RATE_W = 2700     # recent span for slope measurement (s · 45 min)
QBURN_BASE_N = 6        # number of past cycles used for the baseline
# ★Quantile band (2026-09-21). A single median line only says «what past cycles were at this point» and hides
#   **how much they varied**. Laying p25~p75 as a band shows at a glance whether the current curve is inside the usual range.
# ⚠With a thin sample the band is noise, not information — measured 09-21: 4 of 6 cycles were nearly idle, so
#   p25~p75 spread by tens of %p. ⇒ **Do not draw it if fewer than 5 cycles or the band's median width exceeds 40%p**
#   (then keep just the median line and write `N-cycle sample` in the legend to explain why there is no band).
QBURN_BAND_N = 5        # minimum sample cycles needed to draw the band (per grid point)
QBURN_BAND_W = 40.0     # cap on band median width (%p) — above it the band is dropped
# ⚠The opposite pitfall was also hit (as of 09-21 16:00): 4 of the past 6 cycles were **0% throughout**, so
#   p25~p75 had width 0.0%p everywhere — invisible when drawn but taking a legend slot.
#   ⇒ If no grid point exceeds 1%p, drop the band and keep only the median.
QBURN_BAND_MIN = 1.0    # floor for the band's max width (%p)


def _qburn_cycles(pts):
    """Split cycles where `reset5` changes (±QBURN_TOL) → `[(reset_epoch, [(t, pct), …]), …]`."""
    out = []
    for t, h, r in pts:
        if out and abs(r - out[-1][0]) <= QBURN_TOL:
            out[-1][1].append((t, h))
        else:
            out.append([r, [(t, h)]])
    return out


def _qb_interp(series, e):
    """Linearly interpolate the % at elapsed `e` seconds. series is `[(elapsed, %)]` ascending. None if out of range."""
    if not series or e < series[0][0] or e > series[-1][0]:
        return None
    lo = 0
    for i in range(1, len(series)):
        if series[i][0] >= e:
            lo = i - 1
            break
    else:
        return series[-1][1]
    x0, y0 = series[lo]
    x1, y1 = series[lo + 1]
    if x1 == x0:
        return y1
    return y0 + (y1 - y0) * (e - x0) / (x1 - x0)


def _qb_q(vals, q):
    """Quantile of ascending `vals` (linear interpolation). Interpolates so small samples (2~6) do not skew to one side."""
    n = len(vals)
    if n == 1:
        return vals[0]
    pos = (n - 1) * q
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)


def _qb_slope(seg):
    """Least-squares slope (%/hour). 0 if too few points or no time spread."""
    n = len(seg)
    if n < 2:
        return 0.0
    mx = sum(p[0] for p in seg) / n
    my = sum(p[1] for p in seg) / n
    var = sum((p[0] - mx) ** 2 for p in seg)
    if var <= 0:
        return 0.0
    cov = sum((p[0] - mx) * (p[1] - my) for p in seg)
    return cov / var * 3600.0


def _qb_forecast(now, rows, now_pct, left):
    """`(rate %/h, raw % at reset, over_at or None, n_obs)` from the last QBURN_RATE_W seconds."""
    # Slope — last 45 min. The value at the window's left edge is «the last value before the window» (% is a step
    # function, recorded only on change). Append (now, now_pct) at the right edge to **count idle time too** —
    # without it, after 45 idle minutes the old slope remains and falsely says "empty soon".
    w0 = now - QBURN_RATE_W
    seg = [(float(t), h) for t, h in rows if t >= w0]
    # ★Count the sample **here** (2026-09-22) — the anchor and `(now, now_pct)` are appended below,
    #   so `len(seg)` cannot distinguish «points actually recorded».
    #   Right after reset the window has 1 point ⇒ `_qb_slope` is 0.0 ⇒ `raw = now_pct + 0*left = now_pct`.
    #   i.e. **a number produced by having no sample was shown as a forecast**
    #   (2026-09-22: a "2% at reset at this pace" figure).
    # ⚠Do not revert — with fewer than 2 points `proj.pct`/`proj.raw` are `None`.
    #   (`over_at`·`over_in`·`cur.rate_pph` stay as-is — 0.0 is a fact.)
    n_obs = len(seg)
    anc = [(t, h) for t, h in rows if t < w0]
    if anc:
        seg = [(max(w0, float(anc[-1][0])), anc[-1][1])] + seg
    # ⚠Keep only change points and always append the right edge. A repeated same-% row (the first sample after
    #   every restart, a d7 or reset5 jitter) and a 1 s gate on the edge each added weight: live 09-24 the same log
    #   gave 11.27 at +1 s and 11.94 at +3 s after a restart, and the saver verdict flipped with it.
    seg = [p for i, p in enumerate(seg) if i == 0 or p[1] != seg[i - 1][1]]
    seg = seg + [(now, now_pct)]
    rate = _qb_slope(seg)
    raw = now_pct + rate * (left / 3600.0)
    over_at = None
    if now_pct >= 100:
        over_at = rows[-1][0]
    elif rate > 0 and raw > 100:
        over_at = now + (100.0 - now_pct) / rate * 3600.0
    return rate, raw, over_at, n_obs


def _qb_baseline(cyc):
    """`(bases, median pts, p25~p75 band, band median width, why dropped)` from past cycles."""
    # baseline — up to 6 cycles going back from the immediately previous one. Cycles with <2 points cannot be interpolated.
    bases = []
    for r0, rw in reversed(cyc[:-1]):
        s0 = r0 - QBURN_WIN
        ser = sorted(set((max(0.0, min(float(QBURN_WIN), t - s0)), h) for t, h in rw))
        if len(ser) >= 2:
            bases.append(ser)
        if len(bases) >= QBURN_BASE_N:
            break
    bpts, band = [], []
    for e in range(0, QBURN_WIN + 1, QBURN_GRID):
        vals = sorted(v for v in (_qb_interp(s, e) for s in bases) if v is not None)
        if len(vals) < 2:                        # a single cycle is not a «median»
            continue
        bpts.append([e, round(_qb_q(vals, 0.5), 1)])
        if len(vals) >= QBURN_BAND_N:
            band.append([e, round(_qb_q(vals, 0.25), 1), round(_qb_q(vals, 0.75), 1)])
    # ⚠Keep the band «only when it is information» (★rationale at QBURN_BAND_* above). The width (`bw`) is
    #   computed and emitted anyway so the screen can state why it was dropped — whether dropped is read from `band` being empty.
    bw = sorted(p[2] - p[1] for p in band)
    bwm = round(bw[len(bw) // 2], 1) if bw else None
    bwhy = None
    if len(band) < 2 or bwm is None:
        bwhy = "n"          # some grid point did not reach QBURN_BAND_N samples
    elif bwm > QBURN_BAND_W:
        bwhy = "wide"       # spread too wide — noise, not information
    elif bw[-1] < QBURN_BAND_MIN:
        bwhy = "flat"       # width ~0 across the span — invisible even if drawn
    if bwhy:
        band = []
    return bases, bpts, band, bwm, bwhy


# ★Uncertainty of the back-computed denominator (shown as «≈ 186M ±12%»). Two terms, the larger wins:
#   rounding - the official % is an integer, so pct +-0.5 moves lim by 0.5/pct (4% -> 12.5%, 60% -> 0.8%);
#   spread - per-sample estimates (tokens up to each logged % step / that %) disagree when the model mix shifts.
# ⚠Shown, never used as a guard (early error is shown and converges, not hidden): the headroom number does not depend on it.
QB_UNC_MIN_PCT = 4      # samples below this % are skipped as spread input (rounding alone is >12% there)
QB_UNC_N = 8            # most recent per-sample estimates that form the spread
# Two-sided 95% Student t for df 1..10 — inflates the spread when there are few samples.
_QB_T95 = (12.71, 4.30, 3.18, 2.78, 2.57, 2.45, 2.36, 2.31, 2.26, 2.23)


def qb_unc(ests, pct):
    """Relative uncertainty `(unc, n)` of a tokens-per-% denominator at official `pct`.

    `ests`: per-sample tokens-per-% estimates, oldest first; None = rounding term only (no samples to compare).
    Fewer than 2 samples with `ests` given -> 1.0 (spread unmeasurable). `(None, 0)` without a usable pct."""
    if not isinstance(pct, (int, float)) or isinstance(pct, bool) or pct <= 0:
        return None, 0
    rnd = 0.5 / pct
    if ests is None:
        return rnd, 0
    xs = [float(e) for e in ests if e and e > 0][-QB_UNC_N:]
    n = len(xs)
    if n < 2:
        return max(rnd, 1.0), n
    m = sum(xs) / n
    sd = (sum((x - m) ** 2 for x in xs) / (n - 1)) ** 0.5
    t = _QB_T95[n - 2] if n - 1 <= len(_QB_T95) else 2.0
    return max(rnd, t * sd / m), n


def _qb_step_at(rows, t_min):
    """Time the current % was first logged. ★2026-09-28 the official % is whole, so pairing
    tokens with the latest log inflated the denominator while the % sat still (sawtooth). ⇒ Pair with the step's first log."""
    t = rows[-1][0]
    for _t, _h in reversed(rows):
        if _h != rows[-1][1] or _t < t_min:
            break
        t = _t
    return t


def _qb_unc_ests(rows, start, events):
    """Per-sample tokens-per-% at each logged % change point >= QB_UNC_MIN_PCT since `start`."""
    ev = sorted((t, n) for t, n in events if t >= start)
    out, i, acc, prev = [], 0, 0, None
    for t, h in rows:
        chg = h != prev
        prev = h
        if t < start or h < QB_UNC_MIN_PCT or not chg:
            continue
        while i < len(ev) and ev[i][0] <= t:
            acc += ev[i][1]
            i += 1
        if acc > 0:
            out.append(acc / h)
    return out


# ★7d tokens-per-% comes from this cycle's own recent 7d % steps (2026-09-23). Cumulative «week tokens / week %»
#   mixed a cheap stretch with a 2x-costlier one (11.8~15.4 -> 24.7~26.1M/%: 15% left shown 224M vs ~375M), and
#   the local week total is a calendar week, so an early server reset (09-23 16:02, d7 87 -> 0) left it counting pre-reset tokens.
# ⚠Back-computed from this cycle only — never fixed or blended with past cycles.
# After the account switch d7 went 12 -> 15 and the old 5%p minimum
#   hid a computable number (same flaw as the removed 5h 30-min wait). The error is shown instead: `unc` = 1/span
#   (a difference of two integer %, +-0.5 each), so 2%p reads ±50% and 3%p ±33%.
# ⚠Keep 2, not 1: at 1%p the rounding term is ±100% and a lone 1%p flap (66 -> 67) would pass as a step.
QB_WK_DPCT = 2          # minimum 7d %-span for the step-based rate
# ★2026-09-27: picking the latest span >= 2 was greedy — live 14 -> 16 gave 674M ±50% while 12 -> 15 gave 449M ±33%.
#   ⇒ Walk back to the first span >= QB_WK_DPCT_TARGET (keeps the 09-23 «latest steps» intent); a segment that never
#   reaches it uses its widest span >= QB_WK_DPCT.
# ★2026-09-28 single 1%p steps ran 12M..48M/% on one day (rounding + mix), so a 5%p
#   window swung the 7d cap 3.8B -> 2.87B within hours (headroom 3.1B -> 2.2B) while the official % rose smoothly.
#   ⇒ 10%p: rounding ±10%, still this cycle's recent steps (09-23 intent). ⚠Do not go back to 5.
QB_WK_DPCT_TARGET = 10


def _qwk_steps(run):
    """`(t, pct)` at each first sighting of a higher 7d % within one run."""
    return [p[:2] for p in [run[0]] + [run[k] for k in range(1, len(run)) if run[k][1] > run[k - 1][1]]]


def _qwk_span(runs):
    """`((t0, p0), (t1, p1))` for the step rate, or None — never spans two runs."""
    for r in reversed(runs):                  # latest run first: walk back to the first span >= target
        steps = _qwk_steps(r)
        p1 = steps[-1][1]
        s0 = next((s for s in reversed(steps[:-1]) if p1 - s[1] >= QB_WK_DPCT_TARGET), None)
        if s0 is not None:
            return s0, steps[-1]
    for r in reversed(runs):                  # none reaches it: widest span >= QB_WK_DPCT, latest run first
        steps = _qwk_steps(r)
        p1 = steps[-1][1]
        s0 = max(steps[:-1], key=lambda s: (p1 - s[1], -s[0]), default=None)   # widest; earliest on a tie
        if s0 is not None and p1 - s0[1] >= QB_WK_DPCT:
            return s0, steps[-1]
    return None
