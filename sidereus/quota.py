"""Official quota (OAuth usage API, OMC cache), quota persistence and quota()."""
import json
import os
import stat
import subprocess
import threading
import time
from sidereus.config import CFG, DATA_DIR, IS_MAC, claude_home
from sidereus.warn import warn_once
from sidereus.bus import _atomic_write, _open_append
from sidereus.transcript import _iso_ts, _tail_lines
from sidereus.quota_local import (_cc_account, _cc_plan, _cc_scope, _cc_seat, _plan_code, _quota_from_omc,
                                  _scope_moved)


# ── Official quota (GET /api/oauth/usage) ─────────────────────────────────
#   ★This is the very API `/usage` uses. The first conclusion "no official API" was wrong —
#     search showed only the feature request (#43149), but digging **the executable's strings** revealed the endpoint as is
#     (`fetchUtilization: GET /api/oauth/usage` · fields `five_hour`·`seven_day`·`utilization`·`resets_at`).
#     Measured 2026-08-20: the response's 5h 88% · reset 11:10 KST exactly matched what the user read on screen.
#   ⇒ The user need not hand-enter % and reset (no calibration needed either).
#   ⚠**429s are common** (that endpoint's own limit · measured 200 on the 3rd try). So call rarely and back off.
#   ⚠The token is read from **the user's own keychain** (off macOS: `.credentials.json`) and used **only for api.anthropic.com**. Never logged or written to files.
QUOTA_URL = "https://api.anthropic.com/api/oauth/usage"
# ★★**The only real-time path during 429** (measured 2026-09-11; the screen lagged the Claude settings page, 19% vs 21%).
#   The CLI **almost never calls** this endpoint — it reads the `anthropic-ratelimit-unified-*` headers attached to
#   ordinary model-call responses (header names found 28 times in the CLI binary).
#   So the CLI screen was real-time while ours froze. ⇒ We too get the same headers with **one call to the
#   cheapest model**. Measured response: `overage-utilization 0.24` (=24% · **a 0~1 ratio**) ·
#   `overage-reset 1790812800` (start of month) · `status allowed`.
#   ⚠Cost: this is **a real API call and costs money** — haiku · 8 input tokens · `max_tokens 1` ⇒ about
#     $0.00002 per call ($0.02/month at 2-min intervals). It burns a tiny bit of the very credit being watched.
#   ⚠When `/api/oauth/usage` **works, its value is authoritative** — headers are used only while it 429s (poller below).
#   ⚠Amounts are not in the headers. They are **an approximation** reconstructed as ratio × monthly limit, shown with `≈`.
QUOTA_HDR_URL = "https://api.anthropic.com/v1/messages"
QUOTA_HDR_MODEL = "claude-haiku-4-5-20251001"
QUOTA_HDR_EVERY_S = 120        # never call more often than this (it costs money)
# ⚠Paid call ⇒ OFF unless opted in: env SIDEREUS_QUOTA_PROBE (1/0) beats config `quota_probe` (default false).
QUOTA_PROBE_ENV = "SIDEREUS_QUOTA_PROBE"


def _quota_probe_on():
    v = os.environ.get(QUOTA_PROBE_ENV)
    if v is not None and v.strip() != "":
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(CFG.get("quota_probe", False))
# ★25 → 20. Even at 25, OMC made its own call twice (13:57:33 · 13:59:35) — our success interval, with jitter and
#   response time added, drifted to 31~39 s and exceeded the 30 s TTL. At 20, even a 5 s response lands the next
#   write within 30 s.
QUOTA_HOLD_EVERY_S = 10        # success or failure alike — press the OMC cache at this interval to stop its own lookups

# ★★**Adaptive interval** (2026-09-04). Previously a fixed 20 s = 180/hour · 4,320/day, a value derived from the
#   constraint "shorter than the OMC cache TTL (30 s)". But cache holding (file write, free) and API calls (expensive)
#   are now **separated** by `QUOTA_HOLD_EVERY_S`, so that constraint is gone.
#   And this endpoint's limit appears to be on **request count**, not usage — measured 2026-09-04:
#   at 11% of the 5-hour limit, 429 persisted over 13 min with only `Retry-After: 0` (no information).
#   ⇒ Our own polling burned the window. At 11% there is no value in checking every 20 s —
#     freshness matters near the saver-mode threshold (85%). So **check as often as usage warrants.**
#     11% → 300 s (12/hour) · 60% → 120 s · 88% → 60 s. Normal call volume drops to 1/15.
# ★80 → 90 (2026-09-09). The last 300 lines of `viewer.err` had 41 429s, nearly all in the 80s% — the old boundary put the
#   most common range (80~90%) on tight 60 s polling, which itself burned the request-count cap (per the measurement above,
#   this endpoint limits requests, not usage). ⇒ Narrow tight 60 s polling to 90%+ only (past the 85% saver threshold ·
#   right before entering the credit zone), and lower 70~90% to 120 s (still under 5 min).
QUOTA_STEPS = ((90, 60), (70, 120))     # (above this %, this interval)
QUOTA_SLOW_S = 300                       # below that — when there is headroom
# ★2026-10-01 after an account switch the log gains a row only per poll, so the first own % step took
#   up to 5 min. ⇒ While burn has no own per-% (`burn.quota_calibrating`), poll every 60 s; the flag lapses unless renewed.
QUOTA_CALIB_S = 60
QUOTA_CALIB_TTL = 600                    # s — burn renews it every recompute (QBURN_TTL 30 s) while calibrating
_calib = {"until": 0.0}


def quota_calibrating(on):
    """Set by `sidereus.burn` each recompute: True while the current account has no own tokens-per-% yet."""
    _calib["until"] = time.time() + QUOTA_CALIB_TTL if on else 0.0


def _quota_interval():
    base = _quota_interval_base()
    return min(base, QUOTA_CALIB_S) if time.time() < _calib["until"] else base


def _quota_interval_base():
    try:
        with _quota_lock:
            d = _quota["data"] or {}
        # ★**A seat running on credits must not set the interval by 5h** (2026-09-11; screen lagged settings, 26% vs 27%).
        #   `enterprise_usage_based` has 5h **at 0% forever**, so the steps below always fell to
        #   `QUOTA_SLOW_S` (300 s), while what actually moves is credit —
        #   measured at that moment: screen 26.435% (300 s old) · API at the same time 27.145%. $1.42 went out in 5 min.
        #   ⇒ On that seat check every 60 s. In 1 min drift is under 0.2%, so the integer % does not diverge.
        # ⚠Disabled credits (`on` False) are kept for display but do not move — no fast poll for them.
        _ex = d.get("extra") or {}
        if _ex.get("pct") is not None and _ex.get("on") is not False and "usage_based" in (_cc_seat() or ""):
            return 60
        pct = ((d.get("five_hour") or {}).get("pct")) or 0
        for lim, sec in QUOTA_STEPS:
            if pct >= lim:
                return sec
    except Exception as e:
        warn_once("quota-interval", "quota poll interval failed ({err}) — using the slow interval",
                  soft=True, vars={"err": f"{type(e).__name__}: {e}"})
    return QUOTA_SLOW_S
# ★It was 240 s. The comment said "max 900 s" but the constant was 240, so **during 429 it kept knocking every
#   4 min** (measured 2026-09-02: 429 for 35 min straight, age 2100 s). Knocking itself keeps the limit in place, and when
#   one call finally passes the % **jumps** 31 → 80 (the value bounced back and forth).
#   ⇒ Raise the cap as the comment said, and while stale let the screen below use **a local estimate** (values stay continuous).
# ★900 → 300. 900 cut the knocking, but **the screen went up to 15 min stale** (2026-09-04; a 13-min-old value was shown).
#   The gauge's reset countdown keeps moving, so staleness is hard to notice — 5 min is the compromise.
#   Jitter is added so multiple sessions' retries do not overlap (overlap is what sustains 429).
# ★300 → 900 (2026-09-09). This constant had been **dead code** — `_wait_hint`'s exponent was bounded by
#   `min(fail, 4)`, stopping at 15*2**4=240, never reaching the 300 of `min(own, 300)`.
#   So however many 429s in a row, the retry interval was **240 s forever** (measured: last success
#   1510 s ago — knocked 6 more times at 240 s and still not released). Left alone we keep burning the request-count limit.
#   `_wait_hint` below raises the exponent cap so it really grows.
# ★900 → 300 (measured 2026-09-11). 900 is **so rare it misses the open window.** That day's measurement:
#   a single call after the poller had not knocked for 6.5 min got **200** (extra_usage 19.02%),
#   then knocking 10 times at 15 s intervals got **all 10 as 429** (the whole 135 s). ⇒ The window "opens when rested,
#   closes when knocked". What is needed is neither "more often" nor "less often" but **one shot after a rest**,
#   and a 5-min rest was enough. 900 s rests two and a half times that, leaving credit values 15 min stale.
# ⚠Credit (amount) has **no source other than this API** — the OMC cache has only 5h and weekly (2026-09-11:
#   OMC cannot see credit info). So while 5h becomes fresh via OMC, however late, credit stays old forever unless
#   we manage to get a 200 — this constant is the age cap of the credit line.
QUOTA_MAX_BACKOFF = 300
_quota = {"data": None, "at": 0, "err": None, "next": 0}
_quota_lock = threading.Lock()


QUOTA_LOOKUP_ENV = "SIDEREUS_QUOTA_LOOKUP"


def _quota_lookup_on():
    """Reading the Claude Code OAuth token (keychain; `.credentials.json` off macOS) is opt-out: env SIDEREUS_QUOTA_LOOKUP (1/0) beats config
    `quota_lookup` (default true). Off = no token read, no call to api.anthropic.com (SECURITY.md)."""
    v = os.environ.get(QUOTA_LOOKUP_ENV)
    if v is not None and v.strip() != "":
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(CFG.get("quota_lookup", True))


CREDS_MAX_BYTES = 64 * 1024


def _creds_file_token(d):
    """Off macOS Claude Code keeps the login in `<config dir>/.credentials.json`; None on any doubt (never logged)."""
    p = os.path.join(d, ".credentials.json")
    try:
        st = os.lstat(p)
        if not stat.S_ISREG(st.st_mode) or st.st_size > CREDS_MAX_BYTES:
            return None     # ⚠symlink / dir / oversize refused: only the CLI's own regular file is trusted
        with open(p, "rb") as f:
            j = json.loads(f.read(CREDS_MAX_BYTES + 1).decode("utf-8"))
        tok = (j.get("claudeAiOauth") or {}).get("accessToken") or j.get("accessToken")
        return tok if isinstance(tok, str) and tok else None
    except (OSError, ValueError, AttributeError):
        return None


_KEYCHAIN_NOT_FOUND_RC = 44    # `security find-generic-password` exit code when the item does not exist
_oauth_miss = {"no_login": False}    # why the last macOS read gave no token; read by quota_fetch for the status text


def _oauth_token():
    _oauth_miss["no_login"] = False
    if not _quota_lookup_on():
        return None
    if not IS_MAC:
        return _creds_file_token(claude_home())     # primary root = the account this viewer follows (CLAUDE_CONFIG_DIR)
    try:
        r = subprocess.run(["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],  # nosec B607 -- PATH lookup on purpose: the tool's location differs per OS
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=10)
        if r.returncode != 0:
            _oauth_miss["no_login"] = r.returncode == _KEYCHAIN_NOT_FOUND_RC     # ⚠other codes (denied, locked) keep the keychain message
            return None
        j = json.loads(r.stdout.strip())
        return (j.get("claudeAiOauth") or {}).get("accessToken") or j.get("accessToken")
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        return None     # keychain denied/odd entry: _quota_fetch reports the missing token


_hdr_at = [0]


def _quota_probe_hdr():
    """With one model call, get the `anthropic-ratelimit-unified-*` headers and read **the credit ratio**.

    Used in one place only — while `/api/oauth/usage` is blocked by 429 (rationale in the `QUOTA_HDR_URL` comment above).
    ⚠5h and weekly are **not read here.** The headers carry only one "representative-claim", and when credit
      is the representative, as now, there is no 5h field at all. Saver mode keys on 5h `pct`, so
      reading the blank as 0 would misread 100%→0% — that risk is not taken (OMC backs 5h).
    Returns `{"pct": 0~100}` or None on failure. **The body is discarded** (the value lives only in headers)."""
    import urllib.request
    if not _quota_probe_on():
        return None
    tok = _oauth_token()
    if not tok:
        return None
    body = json.dumps({"model": QUOTA_HDR_MODEL, "max_tokens": 1,
                       "messages": [{"role": "user", "content": "."}]}).encode()
    req = urllib.request.Request(QUOTA_HDR_URL, data=body, headers={
        "Authorization": "Bearer " + tok, "anthropic-beta": "oauth-2025-04-20",
        "anthropic-version": "2023-06-01", "Content-Type": "application/json",
        "User-Agent": "claude-cli/2.1.232 (external, cli)"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:  # nosec B310 -- constant https URL
            h, _ = resp.headers, resp.read()
    except Exception as e:
        h = getattr(e, "headers", None)      # headers come even on a 429 response — that is enough
        if h is None:
            # soft: a single startup network blip (2026-09-25 12:48:27, first tick after restart) stays off the strip
            warn_once("quota-hdr", "Header-path lookup is blocked too ({err}) — credit stays at the old value",
                      soft=True, vars={"err": type(e).__name__})
            return None
    try:
        v = h.get("anthropic-ratelimit-unified-overage-utilization")
        if v is None:
            return None
        p = float(v) * 100.0                 # ⚠the header is **a ratio** (0.24 = 24%)
    except (AttributeError, TypeError, ValueError):
        return None                          # absent/garbled header: credit keeps its old value
    if not (0 <= p <= 1000):
        return None
    return {"pct": round(p, 2)}


QUOTA_CACHE = os.path.join(DATA_DIR, "quota-cache.json")
_quota_retry_after = [0]      # seconds the server gave via `Retry-After` (0 if none)


def _wait_hint(fail):
    # 30·60·120·240·300 (cap) — if the server's value is longer, **follow it**.
    # ★The cap is `QUOTA_MAX_BACKOFF` (900→300 on 2026-09-11; rationale in that constant's comment).
    # ★★Exponent cap raised from `min(fail, 4)` (fixed 240) to `min(fail, 6)` (grows to 900)
    #   (2026-09-09). It was pinned at 240 because the 6th 429 would cross the 900s `SOFT_WIN_S` window
    #   and **soft promotion would never happen** — but that was **already solved** by `warn_once`'s `_alive`
    #   carry-over (this file's "tier 1/tier 2" section, added the same day): even if the window breaks and `_n`
    #   resets to 1, an unexpired banner entry only refreshes its age without re-requiring the count. ⇒ The
    #   underlying constraint is gone, so no reason to pin it.
    # ⇒ Why grow it: this endpoint is limited by **request count**, not usage (measured above) — knocking forever
    #   at a fixed 240s keeps burning the limit window with our own requests. The case (last success 1510s ago)
    #   knocked 6 more times at 240s intervals without clearing — the window needs rarer knocks to rest.
    # ⚠Cost: if blocked for really long, our retry interval widens up to 15 min — during that,
    #   `_quota_from_omc()` (a value OMC got on its own) is the only refresh path. The "screen age within 5 min"
    #   goal **cannot be met in this stretch** — the call site of that function widens OMC trust instead.
    own = min(QUOTA_MAX_BACKOFF, 15 * (2 ** min(fail, 6)))
    ra = _quota_retry_after[0]
    return max(own, ra) if ra else own


QUOTA_LOG = os.path.join(DATA_DIR, "quota-log.jsonl")
_qlog_last = [None]
_qlog_lock = threading.Lock()


def _quota_log(d, at, src):
    """Log one line **whenever** the quota % changes.

    ★Why (2026-09-03, a jump back to the 30% range needed verifying): the cache file holds
      **only the last value**, so a past jump could not be checked afterwards at all.
      A jump has two causes that look identical —
        (a) the 5-hour block reset (normal · % climbs again from 0)
        (b) a stale value was frozen for long, then one call got through and it leapt (must be fixed)
      With a log, it can be **laid side by side with the reset time** to tell which."""
    try:
        fh = (d or {}).get("five_hour") or {}
        sd = (d or {}).get("seven_day") or {}
        # ★2026-09-27 account switch: rows carry the account uuid so burn readers can split them into runs (`_acct_runs`).
        _ac = _cc_account()
        _pl = _plan_code()               # history per-1% must not mix plans (burn_hist groups by acct|plan)
        key = (fh.get("pct"), sd.get("pct"), fh.get("resets_at"), _ac, _pl)
        # ⚠sole writer of QUOTA_LOG; the lock keeps an append from landing between trim-read and replace
        with _qlog_lock:
            if key == _qlog_last[0]:
                return                      # unchanged value is not logged (the file would grow every second)
            _qlog_last[0] = key
            with _open_append(QUOTA_LOG) as f:
                f.write(json.dumps({"t": int(time.time()), "at": int(at or 0), "src": src,
                                    "h5": fh.get("pct"), "d7": sd.get("pct"),
                                    "reset5": fh.get("resets_at"), "acct": _ac, "plan": _pl}, ensure_ascii=False) + "\n")
            # drop old lines (hundreds per day · 30 days is enough)
            if os.path.getsize(QUOTA_LOG) > 400_000:
                keep = _tail_lines(QUOTA_LOG, nbytes=200_000, limit=4000)
                # ⚠atomic replace — an in-place "w" let `_qburn_pts` read an empty/half file
                _atomic_write(QUOTA_LOG, ("\n".join(keep) + "\n").encode("utf-8"), prefix=".quota-log.")
    except Exception as e:            # ⚠OSError included — a failing append silently thinned the burn chart
        warn_once("qlog", "Could not append the quota log ({err})", vars={"err": type(e).__name__}, soft=True)


def _quota_save():
    try:
        with _quota_lock:
            d, at, sr = _quota["data"], _quota["at"], _quota.get("src") or ""
        if d:
            # ⚠atomic — an in-place "w" let `_quota_load` (another thread/restart) read a half file
            _atomic_write(QUOTA_CACHE, json.dumps({"data": d, "at": at, "acct": _cc_scope()},
                                                  ensure_ascii=False).encode("utf-8"), prefix=".quota-cache.")
            _quota_log(d, at, sr)
    except OSError as e:
        warn_once("quota-save", "quota cache save failed ({err}) — fetched afresh on restart",
                  soft=True, vars={"err": f"{type(e).__name__}: {e}"})


def _quota_load():
    try:
        with open(QUOTA_CACHE, encoding="utf-8") as f:
            c = json.load(f)
        ac = _cc_scope()
        # ⚠**Do not load another account's cache.** Revived on restart, the screen would show someone else's numbers again.
        #   If either is unknown (None), do not discard — unknown is not a mismatch.
        if _scope_moved(c.get("acct"), ac):
            return
        if c.get("data"):
            with _quota_lock:
                _quota["data"], _quota["at"] = c["data"], c.get("at") or 0
                _quota["acct"] = c.get("acct") or ac
    except Exception:
        pass                    # missing or corrupt cache: start empty and fetch live


def _min_iso(t):
    """Epoch seconds -> UTC ISO-8601 string (whole minute, as `quota()` publishes resets_at)."""
    from datetime import datetime, timezone
    return datetime.fromtimestamp(t, timezone.utc).isoformat()


def quota():
    omc = _quota_from_omc()          # a fresh OMC cache is the fastest and costs nothing
    with _quota_lock:
        d, at, err = _quota["data"], _quota["at"], _quota["err"]
    src = "api"
    # ★The OMC cache has no credit slot (it holds only 5h·weekly). Even when OMC wins, **keep our credit value** —
    #   otherwise the credit row flickered away whenever OMC was fresh.
    _ex = (d or {}).get("extra")
    if omc and omc["at"] >= at:
        d, at, src = omc["data"], omc["at"], "omc"
        err = None
    if not d:
        return {"err": err}
    now = time.time()
    out = {"at": int(at), "age": int(now - at), "err": err, "src": src}
    for k in ("five_hour", "seven_day"):
        v = d.get(k)
        if not v:
            continue
        t = _iso_ts(v.get("resets_at"))
        r_at = v.get("resets_at")
        if t:
            # ⚠The API's resets_at jitters by under a second around the minute (…01:59:59.6Z / …02:00:00.008Z);
            #   views truncate to HH:MM, so unrounded it flipped 10:59 <-> 11:00 between polls and views.
            t = round(t / 60.0) * 60
            r_at = _min_iso(t)
        left = int(t - now) if t else None
        out[k] = {"pct": v["pct"], "resets_at": r_at, "leftSec": left}
        if v.get("keptAt"):
            out[k]["keptAt"] = v["keptAt"]     # only this slot is stale (per-slot preservation in quota_fetch._qf_carry)
    _pl = _cc_plan()
    if _pl:
        out["plan"] = _pl     # KPI popover «Team · Max 5x limit» — tier codes only
    if _ex or d.get("extra"):
        out["extra"] = dict(d.get("extra") or _ex)
        out["extra"]["seat"] = _cc_seat()     # the badge condition reads it (`buildCredit`) — seat is not in the response
        # ★Age of the credit «slot». Measured by `extra.at`, not `at` (payload) — see quota_fetch._qf_parse.
        out["extra"]["age"] = int(now - (out["extra"].get("at") or at))
    return out
