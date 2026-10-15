"""OAuth usage fetch (split out of sidereus/quota.py for the size cap): `_quota_fetch` and its `_qf_*` phases.
State stays owned by `quota` (`_quota`/`_quota_lock`/`_quota_retry_after`, mutated in place here). ⚠Tests patch these names on this module."""
import json
import time
from sidereus.warn import exc_name, warn_once
from sidereus.transcript import _iso_ts
from sidereus.quota import QUOTA_URL, _cc_account, _oauth_token, _quota, _quota_lock, _quota_lookup_on, _quota_retry_after


QF_ERR_KEYS = ("Quota lookup is turned off in settings (quota_lookup)",
               "Could not read the token from the keychain (access may need to be allowed)")   # ⚠fixed I18N keys (page does T(q.err)); keep in sync with 06-i18n-x.js


def _qf_err(msg):
    with _quota_lock:
        _quota["err"] = msg


def _qf_retry_after(e):
    # ★A 429 tells us **how long to wait** (`Retry-After`). We used to drop it and keep knocking on our own
    #   backoff (max 300s) — measured 2026-09-04: a 429 did not clear for 9+ minutes, and knocking every
    #   300s meanwhile may have extended the window. If the server gave a wait time, follow it.
    _ra = 0
    try:
        _h = getattr(e, "headers", None)
        if _h is not None:
            _rv = _h.get("Retry-After") or _h.get("retry-after")
            if _rv:
                _ra = int(float(str(_rv).strip()))
    except Exception:
        _ra = 0
    return max(0, min(_ra, 3600))


def _qf_request(tok):
    """GET the usage endpoint -> (True, body), or (False, None) after recording the error."""
    import urllib.request
    req = urllib.request.Request(QUOTA_URL, headers={
        "Authorization": "Bearer " + tok, "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": "claude-cli/2.1.232 (external, cli)", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        code = getattr(e, "code", None)
        _quota_retry_after[0] = _qf_retry_after(e)
        _qf_err(f"{exc_name(e)}{' ' + str(code) if code else ''}")
        return False, None
    return True, body


def _qf_parse(body):
    """Response body -> slot dict, or None after recording a shape error."""
    # ⚠The response shape is not ours to define (external API) — a non-dict blows up at `.get` below.
    #   This spot used to be **outside** the try, so it escaped to the loop; even when the guard caught it,
    #   it blew up at the same spot next cycle and quota stopped forever. The reason goes to `_quota["err"]` — the screen reads it.
    out = {}
    try:
        if not isinstance(body, dict):
            raise TypeError("top-level " + type(body).__name__)
        for key in ("five_hour", "seven_day"):
            v = body.get(key)
            if not isinstance(v, dict):
                if v is not None:     # neither an object nor null — the shape is broken
                    warn_once("quota-member-" + key,
                              "Quota response field {key} is not an object ({err}) — that slot stays unknown",
                              vars={"key": key, "err": type(v).__name__})
                    continue      # leave just that slot as «unknown»
                # ★**`null` in a successful response means «0», not «unknown»** (2026-09-11; shown as a 0% gauge,
                #   not a notice). The call succeeded but that window is absent = **nothing used in this window yet** —
                #   exactly what a freshly attached account looks like.
                #   ⚠Before, this was skipped and the screen fell to "no quota % · HTTPError 429".
                #     Fetch failure (no value) and zero usage (value received, and it is 0) are **different facts** but were lumped together.
                #   ⚠0 is filled in here **only for a successful response**. Failures (429 etc.) already returned above —
                #     that path never gets a 0 (that would be fabrication).
                out[key] = {"pct": 0, "resets_at": None, "zero": True}
                continue
            if v.get("utilization") is not None:
                out[key] = {"pct": v.get("utilization"), "resets_at": v.get("resets_at")}
        # ★Credits (extra usage) are in the **same response** (measured 2026-09-09 · schema from the CLI binary
        #   `extra_usage{is_enabled, monthly_limit, used_credits, utilization, currency, disabled_reason}`).
        #   We used to drop this slot ⇒ while 5h was at 100% and usage continued on credits, the screen only said
        #   "used up" and nowhere showed how much was actually being spent (2026-09-09).
        #   ⚠Amounts are in **cents (minor unit)** — the CLI puts `spendLimitCents`·`usedCents` into these fields as-is.
        ex = body.get("extra_usage")
        if isinstance(ex, dict) and ex.get("is_enabled"):
            # ★`at` is **the time this credit value was actually received** (2026-09-11). The payload `at` is
            #   refreshed whenever OMC refreshes 5h, but credits do not come through that path (OMC's cache has
            #   no credit slot), so **the amount looked "just now" while hours stale** — for the screen to state
            #   age, the slot needs its own timestamp (same reason as `keptAt` for 5h·7d).
            out["extra"] = {"pct": ex.get("utilization"), "used": ex.get("used_credits"),
                            "limit": ex.get("monthly_limit"), "cur": ex.get("currency") or "USD",
                            "at": int(time.time())}
    except Exception as e:
        warn_once("quota-shape",
                  "Could not parse the quota response ({err}) — usage is empty", vars={"err": type(e).__name__})
        _qf_err("shape " + type(e).__name__)
        return None
    return out


def _qf_carry(out, prev, prev_at, _now):
    """Revive previous 5h/7d values into `out` where the response had none (caller holds `_quota_lock`)."""
    for k in ("five_hour", "seven_day"):
        # ⚠Within the **same account**, `zero` loses to the previous value. Usage cannot drop back to 0 while
        #   the window is still open — that is a transient empty API response. On account change the guard
        #   in `_qf_store` already cleared `prev`, so this does not trigger and 0 stays.
        #   ⚠Why this matters: `pct` sets the saver-mode stage. Misreading 100% as 0% releases
        #     saver mode entirely.
        if k in out and not (out[k] or {}).get("zero"):
            continue
        if not prev.get(k) or not prev[k].get("pct"):
            continue
        # ⚠`at` is bumped to now, so the screen's `age` cannot tell this slot is stale.
        #   Hence a last-measured time **per slot** (`one()` uses it to print "value from N min ago").
        #   ⚠Once set, `keptAt` is carried forward — `prev_at` is refreshed on every success, so
        #     measuring age with it makes a stale value **never age**.
        _kept = int((prev[k] or {}).get("keptAt") or prev_at)
        _t = _iso_ts((prev[k] or {}).get("resets_at"))
        if _t:
            if _t <= _now:
                continue           # window already ended — showing the past % would be false
        elif _now - _kept > 6 * 3600:
            continue               # reset time unknown — carry forward for at most 6 hours
        out[k] = dict(prev[k], keptAt=_kept)


def _qf_store(out):
    with _quota_lock:
        if out:
            # ★Merge per slot (2026-09-10). We used to replace `out` wholesale, so the moment a response lacked
            #   `five_hour`, **the old value was wiped and the gauge vanished from the screen**.
            #   ★Measured 09-10: 14:10 h5=100·d7=58 → 14:15 response had both slots null → only extra left in cache.
            #   ⚠Only values whose **reset time has not passed** are revived — showing an old 100% after the window
            #     rolled over is a lie. Past values are simply dropped.
            # ⚠If the account changed, **there is no previous value to carry.** Showing the old account's 5h on the
            #   new account's screen is someone else's number (measured 2026-09-11 — hence this guard precedes the merge).
            _ac = _cc_account()
            if _ac and _quota.get("acct") and _quota["acct"] != _ac:
                _quota["data"] = None
            if _ac:
                _quota["acct"] = _ac
            _qf_carry(out, _quota.get("data") or {}, _quota.get("at") or 0, time.time())
            for k in ("five_hour", "seven_day"):
                if isinstance(out.get(k), dict):
                    out[k].pop("zero", None)          # decision-only marker — not stored or shown
            _quota["data"], _quota["at"], _quota["err"] = out, time.time(), None
            _quota["src"] = "api"


def _quota_fetch():
    if not _quota_lookup_on():
        _qf_err(QF_ERR_KEYS[0])
        return False
    tok = _oauth_token()
    if not tok:
        _qf_err(QF_ERR_KEYS[1])
        return False
    ok, body = _qf_request(tok)
    if not ok:
        return False
    out = _qf_parse(body)
    if out is None:
        return False
    _qf_store(out)
    return bool(out)
