"""Quota calibration and the periodic usage/quota loops."""
import json
import random
import time
from sidereus.warn import _LOOP_ERR, warn_once
from sidereus.bus import _atomic_write
from sidereus.transcript import _iso_ts
from sidereus.usage import (ANCHOR_FILE, USAGE_BACKFILL_S, _anchors, _usage_backfill, _usage_load,
    _usage_save, usage)
from sidereus.quota import (OMC_FRESH_S, QUOTA_HDR_EVERY_S, QUOTA_HOLD_EVERY_S, _hdr_at,
    _cc_account, _omc_cache_write, _quota, _quota_from_omc, _quota_interval, _quota_load,
    _quota_lock, _quota_probe_hdr, _quota_retry_after, _quota_save, _wait_hint, quota)
from sidereus.quota_fetch import _quota_fetch
from sidereus.quota_roots import tick as _acc_tick

# ⚠Log a 429 only once the last success is this old. Routine 429 retries recover within minutes and
#   printed one line per 15-min window (147 windows in 500 lines of viewer.err, 2026-09-25) — noise.
#   The screen state (`_quota["err"]`, `_LOOP_ERR`) is untouched; only the log line is gated.
QUOTA_429_LOG_AFTER_S = 600
_cal_logged = [None]    # last calibration result printed — print again only when it changes


def _usage_loop():
    _usage_load()               # show the last result first (the backfill refreshes after)
    while True:                 # ⚠`_usage_load()` above is outside the loop — keep it out of the try
        try:
            _usage_backfill()
            _usage_save()
            # ★Denominator calibration runs **here** (2026-09-02; the weekly figure did not match).
            #   It used to sit right after `_quota_loop`'s success, but once the 429 backoff went to 900 s that spot
            #   rarely ran and calibration effectively stopped (measured: anchor stuck at 8/20).
            #   The token totals live here, and the function checks freshness itself, so it is safe.
            _quota_calibrate()
            _LOOP_ERR.pop("usage", None)
            time.sleep(USAGE_BACKFILL_S)
        except Exception as e:
            warn_once("loop:usage", "Token usage backfill stopped refreshing — {err}",
                      vars={"err": f"{type(e).__name__}: {e}"[:118]})   # 160 chars in all, as before
            _LOOP_ERR["usage"] = {"at": time.time(), "err": f"{type(e).__name__}: {e}"[:160]}
            time.sleep(60)          # ⚠the exception path must sleep too — otherwise it becomes a tight infinite loop
            continue


def _quota_calibrate():
    """**Back-compute the denominator** from official % and local token totals, and store it.

    ★Why automatic (measured 2026-09-02): the denominator was a hand-entered value (that route was deleted 2026-09-21),
      and the last calibration was **8/20** (13 days earlier). The limit had changed meanwhile, leaving the 5h denominator at 479M;
      where the official figure said 31%, local showed 81% — off by 2.6x.
      When an official fetch succeeds both numbers are in hand **at the same moment**, so calibrating then never rots.
    ⚠When the official % is very low the back-computation error is large, so it is left alone (dividing at 1% jumps 100x).

    ⛔**Disabled 2026-09-04** (user decision: show only officially provided values, no local computation).
      The denominator uses the /usage ground truth in `usage-anchor.json` as-is.
      — Why disabled: back-computing the denominator from local totals kept producing different numbers at the same spot.
        · 09-04 06:15 right after block reset, local tokens near 0 but official % was pre-reset → denominator 207M (truth 519M)
        · 09-04 07:57 denominator dropped to 432,467,607 → local 56% · official 46% (10%p apart)
        Even with three guards (same window · 30+ min after window start · change-ratio limit) it drifted again.
        Narrowing the rules failed twice, so **the feature itself is off** (same judgment as external messenger notifications).
      — If the denominator actually changes, the user checks `/usage` and edits `usage-anchor.json`.
      — The implementation below is kept — so the rationale need not be rediscovered on revival. To revive, just delete this `return`."""
    return
    try:
        q = quota()
        # ★Do not gate on `err` — that field may hold **a past failure** while the value itself is fresh
        #   (the case when it came from the OMC cache. Measured 2026-09-02: age 49s yet err had a 429 attached,
        #   and that condition kept calibration from ever running). Check freshness only — that is all calibration needs.
        # ⚠Writing `(q.get("age") or 999)` **jumps to 999 when age is 0** (0 is falsy in Python).
        #   The freshest just-fetched value was exactly what got blocked — the real reason calibration never ran
        #   (measured 2026-09-02: age=0 · pct 35% · back-computed 7.5B all computed, then dropped at this line).
        _age = q.get("age") if q else None
        if _age is None or _age > 120:
            return
        cur = usage()
        a2 = _anchors()
        hit = {}
        for key, field, src in (("five_hour", "blockLimitTokens", "block"),
                                ("seven_day", "weekLimitTokens", "week")):
            o = q.get(key) or {}
            pct = o.get("pct") or 0
            tok = ((cur.get(src) or {}).get("tokens")) or 0
            if pct < 8 or tok <= 0:
                continue                # do not back-compute from too low a %
            # ★**Never calibrate right after a reset** (measured 2026-09-04, the user caught it via /usage):
            #   when the 5-hour block resets at 05:00 local tokens restart from 0, but the official cache still holds
            #   **the pre-reset %**. Back-computing from that pair gives `small tokens / large %` = an absurdly
            #   small denominator — the 5h denominator actually broke from 519M → 207M (0.40x) and
            #   the screen said 24% was 60%. Weekly avoided this pitfall because its % moves slowly.
            #   ⇒ The reset time the official value states and **the end of the window local sees** must point to the same window.
            try:
                r_at = _iso_ts(o.get("resets_at")) if o.get("resets_at") else 0
                l_end = _iso_ts((cur.get(src) or {}).get("end") or "")
            except Exception:
                r_at = l_end = 0
            if r_at and l_end and abs(r_at - l_end) > 3600:
                continue                # looking at different windows — not a basis for back-computation
            # if the window just started, the sample is thin and the error grows (this user burns 4M/min)
            l_start = 0
            try:
                l_start = _iso_ts((cur.get(src) or {}).get("start") or "")
            except Exception:
                l_start = 0
            if l_start and (time.time() - l_start) < 1800:
                continue                # no calibration in the first 30 min of a window
            lim = int(tok / (float(pct) / 100))
            old = int(a2.get(field) or 0)
            # ★**Reject abrupt changes.** A limit does not double overnight (even promotions are 50%).
            #   Block once more here any outlier that slipped through the two gates above.
            if old and not (0.55 <= lim / max(1, old) <= 1.8):
                warn_once("calrej:%s:%d" % (field, lim // 10**7),
                          "Rejected auto-calibration of the quota denominator ({field}: {old} → {new} · change too large)",
                          vars={"field": field, "old": f"{old:,}", "new": f"{lim:,}"})
                continue
            if old and abs(lim - old) / max(1, old) < 0.05:
                continue                # within 5% leave it as-is (no reason for the value to wobble)
            a2[field] = lim
            hit[field] = lim
        if not hit:
            return
        # ⚠atomic — a half-written anchor file would reset every calibrated denominator on the next load
        _atomic_write(ANCHOR_FILE, json.dumps(a2, ensure_ascii=False, indent=1).encode("utf-8"), prefix=".anchor.")
        _hit = sorted(hit.items())
        if _hit == _cal_logged[0]:
            return              # ⚠same values as last print — reprinted every window (34 in viewer.err, 2026-09-25)
        _cal_logged[0] = _hit
        warn_once("cal:" + str(sorted(hit.items())), "Auto-calibrated the quota denominator to the official %: {vals}",
                  vars={"vals": ", ".join("%s=%s" % (k, f"{v:,}") for k, v in hit.items())})
    except OSError:
        pass                    # anchor write failed; retried next cycle
    except Exception as e:
        warn_once("calfail", "Quota denominator auto-calibration failed ({err})", vars={"err": type(e).__name__}, soft=True)


def _quota_loop():
    """Quota poller — **Sidereus is the only poller** (reversed 2026-09-04).

    The order flipped: it used to be `OMC cache → API on failure`, now it is `API → OMC cache on failure`.
    Reason and measurements are in the `_omc_cache_write` comment above — in short, **OMC also got 429s yet
    knocked more often with its 15s failure TTL**, so the two split the limit and both starved.
    Now we call every 60s, and in between write the last success to the cache in OMC format every 10s —
    OMC passes its 30s TTL and skips its own call. Only on failure do we pick up a value OMC fetched itself."""
    _quota_load()
    st = [0]    # fail count; a list so a tick that raises keeps what it already changed
    while True:
        try:
            _quota_tick(st)
        except Exception as e:
            _quota_tick_err(e)


def _quota_tick(st):
    """One poll: API → header credits → OMC cache → backoff. Every sleep happens inside."""
    try:
        _acc_tick()     # extra signed-in roots (display only); never sleeps, never touches `_quota`
        if "quota_acc" in _LOOP_ERR:
            _LOOP_ERR.pop("quota_acc", None)
    except Exception as e:
        _LOOP_ERR["quota_acc"] = {"at": time.time(), "err": type(e).__name__}
    ok = _quota_fetch()
    # ★Every path in this tick returns early, so **it never reaches the end of the body** —
    #   clear the reason at the spot that means "the poller is alive and got here".
    _LOOP_ERR.pop("quota", None)
    if ok:
        _quota_on_ok(st)
        return
    _quota_probe_credits()
    if _quota_try_omc(st):
        return
    _quota_backoff(st)


def _quota_tick_err(e):
    warn_once("loop:quota", "Quota poller stopped — {err}", vars={"err": f"{type(e).__name__}: {e}"[:137]})   # 160 in all
    _LOOP_ERR["quota"] = {"at": time.time(), "err": f"{type(e).__name__}: {e}"[:160]}
    time.sleep(60)      # ⚠the exception path must sleep too — otherwise it becomes a tight infinite loop


def _quota_on_ok(st):
    _quota_retry_after[0] = 0
    _quota_save()
    with _quota_lock:
        _out = _quota["data"]
    _omc_cache_write(_out)    # ★makes the statusline skip its own API call
    _quota_calibrate()        # (currently disabled — the function returns on its first line)
    st[0] = 0
    # ★Even on success, **re-press the cache every 10s.** Otherwise the API interval (60s) exceeds OMC's
    #   TTL (30s), OMC wakes up and starts its own fetch — that was the cause of the 429s.
    _hold_until = time.time() + _quota_interval()
    while True:
        _rest = _hold_until - time.time()
        if _rest <= 0:
            break
        time.sleep(min(QUOTA_HOLD_EVERY_S, max(0.5, _rest)))
        _omc_cache_write(_out)


def _quota_probe_credits():
    # ★While blocked, keep **credits alone** alive via the header path (2026-09-11 · Claude settings showed 21%
    #   while the screen showed 19%). Credits are not in the OMC cache (OMC cannot see credit info),
    #   so without this path they freeze for the whole 429.
    #   ⚠It is a paid call, so it is bounded by `QUOTA_HDR_EVERY_S` and used **only when the limit is known**.
    _n = time.time()
    if _n - _hdr_at[0] >= QUOTA_HDR_EVERY_S:
        _hdr_at[0] = _n
        _h = _quota_probe_hdr()
        if _h:
            with _quota_lock:
                _d = _quota.get("data") or {}
                _e = dict(_d.get("extra") or {})
                _e["pct"] = _h["pct"]
                if _e.get("limit") is not None:
                    # the amount is not in the header — it is an **approximation** reconstructed from the ratio (`approx` adds ≈ on screen)
                    _e["used"] = round(_e["limit"] * _h["pct"] / 100.0)
                _e["at"], _e["approx"] = int(_n), True
                _d["extra"] = _e
                _quota["data"] = _d
                if not _quota["at"]:
                    _quota["at"] = int(_n)
            _quota_save()


def _quota_try_omc(st):
    """True when OMC's cache was used (and the interval slept)."""
    # We are blocked — if OMC got through, we get it for free. Take it only if newer than our value.
    # ★★Widen the trust age during backoff (2026-09-09, paired with the `_wait_hint` raise). Our retries
    #   can spread up to 15 min, so if OMC (or Claude Code itself) gets through even once in between,
    #   that value must not be missed — `fresh_s` grows with `fail` up to 30 min.
    #   Why safe: adoption still requires passing the `o["at"] > our last value` gate below, so
    #   widening never goes back to an older value (see `_quota_from_omc` comment above).
    o = _quota_from_omc(fresh_s=min(1800, OMC_FRESH_S + st[0] * 180))
    if o:
        with _quota_lock:
            if o["at"] > (_quota["at"] or 0):
                # ⚠OMC data has no credit slot — carry ours over, or adoption wipes the credit row (2026-09-25).
                #   Keep its own `at` (fallback: our previous payload time) so the row still shows its age.
                #   ⚠Same account guard as `_qf_store` — after an account switch the old credits are someone else's.
                #   Checked only when there is something to carry, so the config file is not read otherwise.
                _ex = (_quota.get("data") or {}).get("extra")
                if _ex and _quota.get("acct"):
                    _ac = _cc_account()
                    if _ac and _quota["acct"] != _ac:
                        _ex = None
                _new = dict(o["data"] or {})
                if _ex and "extra" not in _new:
                    _new["extra"] = dict(_ex, at=_ex.get("at") or int(_quota["at"] or 0) or None)
                _quota["data"], _quota["at"], _quota["err"] = _new, o["at"], None
                _quota["src"] = "omc"
        _quota_save()
        _quota_calibrate()
        st[0] = 0                 # OMC getting through means the limit window opened
        time.sleep(_quota_interval())
        return True
    return False


def _quota_backoff(st):
    # ★Nothing received — both we and OMC are blocked. **Reduce knockers to one** inside this window:
    #   if the last success is still usable, pin the OMC cache with it to stop OMC's 15s retries.
    with _quota_lock:
        _last, _lat = _quota["data"], (_quota["at"] or 0)
    # ★The age limit was **removed** (measured 2026-09-04). Pinning stopped after `OMC_HOLD_S` (10 min), and
    #   at that moment OMC resumed its own polling (failure TTL 15s = 4/min) and **made the 429 worse** —
    #   the recovery aid backfired. At measurement time quota was frozen 21 min + OMC cache
    #   `error:true,data:null`. Staleness is already stated on screen as "N min old",
    #   so pinning even when stale is better — reducing knockers to one is the only recovery path.
    if _last:
        _omc_cache_write(_last, hold=True)
    st[0] += 1
    fail = st[0]
    # ★Log the 429. It used to be swallowed silently, leaving no trace in the log, and reconstructing why the
    #   screen froze took time (the screen had stopped updating 19 min earlier).
    # ★But this too is **tier 1** (2026-09-07) — "using the last success" means the screen was right, and
    #   there is nothing for the user to do about one 429 (other than wait). Hence `soft=True`.
    #   Backoff is 30·60·120·240s (effective cap 240), so the 6th 429 comes at ~740s (< `SOFT_WIN_S`=900)
    #   ⇒ promoted at ~12.5 min **only if blocked continuously**. The case that actually hurt was
    #   «last success 1510s ago», so that stretch is still caught.
    with _quota_lock:
        _e = _quota.get("err") or ""
    if "429" in str(_e):
        _wh, _ago = _wait_hint(fail), int(time.time() - _lat)
        # ⚠Always call: each call counts toward soft promotion. Gating the call itself (536dccf) left
        #   ~4 calls per 900s window at the 300s cap, so a long 429 block never reached the strip.
        warn_once("quota-429", "Quota lookup blocked by 429 — retrying in {wait}s · showing the last good value ({ago}s ago)",
                  soft=True, vars={"wait": _wh, "ago": _ago}, log=_ago >= QUOTA_429_LOG_AFTER_S)
    # 30·60·120·240s (effective cap 240 — see `_wait_hint` comment) + jitter (0~20%)
    # ★Removed `fail >= 6 → 900s`. That rule was "we back off and give OMC room", but
    #   OMC is now behind us — if we back off 15 min, **nobody calls** (the screen freezes).
    # ★**Keep re-pressing the OMC cache every 10s** even while waiting in backoff (re-fixed after measurement 2026-09-04).
    #   Removing the age limit alone was not enough: on failure our retries spread to 30~300s, while
    #   OMC keeps knocking at its own TTL (15s on failure) and overwrites the cache with `error:true,data:null`.
    #   We actually saw OMC overwrite it 3s after we wrote hold.
    #   ⇒ **Separate API retries (expensive·backoff) from cache pinning (free·file write).**
    #     OMC always sees a cache fresher than 30s and skips its own call, so the only one knocking on the
    #     API is us — and that is what lets the 429 clear.
    #   ⚠Cost: the OMC statusline shows a stale value as current. The Sidereus screen states the real age.
    _wait = _wait_hint(fail)
    _until = time.time() + _wait * (1.0 + random.random() * 0.2)
    while True:
        _rest = _until - time.time()
        if _rest <= 0:
            break
        if _last:
            _omc_cache_write(_last, hold=True)
        time.sleep(min(10.0, max(0.5, _rest)))
