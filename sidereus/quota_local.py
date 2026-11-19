"""Account metadata from ~/.claude.json (uuid/tier only) and the OMC usage-cache read/write."""
import json
import os
import time
from sidereus.config import claude_home, claude_json
from sidereus.warn import warn_once
from sidereus.bus import _atomic_write


# ★OMC (oh-my-claudecode)'s statusline file-caches the **same endpoint** with a 30s TTL.
#   The statusline runs on every render, so that file is always fresh (measured 2026-08-20: 9s old).
#   ⇒ **Read that file first.** (a) fast (file read) (b) we do not hit the API again and add 429s.
#     Only call directly when it is stale.
OMC_CACHE = os.path.join(claude_home(), "plugins", "oh-my-claudecode", ".usage-cache.json")
# OMC 5.x keeps one file per provider; it only migrates the legacy file when this one is missing.
OMC_CACHE5 = os.path.join(claude_home(), "plugins", "oh-my-claudecode", ".usage-cache-anthropic.json")
OMC_FRESH_S = 600          # age at which the OMC cache is still usable — better than nothing (age is shown on screen)
# ★**The quota cache is bound to the account** (2026-09-11). After switching accounts the screen kept
#   showing the previous account's `5h 100%` — the cache had no account marker, so **there was no way to tell**.
#   ★Measured 09-11: `quota-log.jsonl` rose unbroken from 11:12 `h5=5%` to 13:50 `h5=100%`, then at
#     13:55 `h5=null d7=null` (successful response · `extra` included). Both windows `null` is not a fetch
#     failure but the normal form for **no usage in this window**, and that moment is the account switch.
#   ⚠The keychain (`Claude Code-credentials`) has **no** account identifier (token·tier·scopes only).
#     The identifier exists only at `oauthAccount.accountUuid` in `~/.claude.json`.
#   ⚠Use only the uuid — email·name are not values to put on a shared screen (this file's «metadata only» rule).
CLAUDE_CONF = claude_json()
ACCT_TTL_S = 60                  # this file is read often and is hundreds of KB — do not parse on every poll
_acct = {"at": 0, "mt": 0, "id": None, "ouid": None, "seat": None, "tier": None, "org": None}


def _cc_plan():
    """Plan metadata `{tier, seat, org}` (rate-limit tier codes only — never email/name/org name); None when unknown."""
    _cc_account()
    p = {k: _acct[k] for k in ("tier", "seat", "org") if isinstance(_acct.get(k), str) and _acct[k]}
    return p or None


def _plan_code():
    """Rate-limit plan code for splitting quota history by plan (`tier`, else `org`); None when unknown."""
    _cc_account()
    return _acct["tier"] or _acct["org"]


def _cc_seat():
    """Seat type (`seatTier`). ★`enterprise_usage_based` is a seat **billed immediately per use**, so
    "credits only start after 5h is used up" does not hold (2026-09-11 — when the 5h slot went empty the
    credit badge went off with it). The badge condition checks this."""
    _cc_account()
    return _acct["seat"]


def _cc_account():
    """uuid of the currently logged-in account. None if unknown — then **discard nothing** (unknown is not a mismatch)."""
    now = time.time()
    try:
        mt = os.path.getmtime(CLAUDE_CONF)
    except OSError:
        return _acct["id"]
    if _acct["id"] and _acct["mt"] == mt:
        return _acct["id"]
    if now - _acct["at"] < ACCT_TTL_S:
        return _acct["id"]
    _acct["at"] = now
    try:
        with open(CLAUDE_CONF, encoding="utf-8") as f:
            j = json.load(f)
        _oa = j.get("oauthAccount") or {}
        aid = _oa.get("accountUuid") or None
        _acct["seat"] = _oa.get("seatTier") or None
        _acct["tier"] = _oa.get("userRateLimitTier") or None
        _acct["org"] = _oa.get("organizationType") or None
        _acct["ouid"] = _oa.get("organizationUuid") or None
    except (OSError, ValueError, AttributeError):
        return _acct["id"]              # config mid-write/odd: keep the known account until the next TTL
    if aid and _acct["id"] and aid != _acct["id"]:
        warn_once("acct-switch-" + aid[:8], "The signed-in account changed — dropping the previous account's quota cache")
    _acct["mt"], _acct["id"] = mt, aid
    return aid


def _cc_scope():
    """Quota cache scope `accountUuid@organizationUuid` (or the bare uuid); None if unknown.

    ⚠Switching organization keeps the same `accountUuid`, so a uuid-only guard kept the old org's 7d 100%
      until its reset while the new seat (enterprise usage-based) reported both windows null."""
    aid = _cc_account()
    return aid + "@" + _acct["ouid"] if aid and _acct.get("ouid") else aid


def _scope_moved(stored, cur):
    """True only when both scopes are known and differ.

    ⚠A stored bare uuid (older cache) is a mismatch once an org is known: it cannot say which org it was measured
      under, and treating it as a match carried exactly the old org's 7d 100% this guard exists to drop."""
    return bool(stored and cur and stored != cur)
# ★The OMC cache **is sometimes empty** (measured 2026-08-20: `data: null, error: true` — OMC also gets 429s).
#   So trusting OMC and not keeping our own value blanks the screen. Keep the last success **in a file** so it survives restarts.


def _quota_from_omc(fresh_s=None):
    """If `fresh_s` is given, use it as the age cap instead of `OMC_FRESH_S`.

    ★Widened only while we are in 429 backoff (`_quota_loop` below) — the screen states the real age
      as "value from N s ago" anyway, and `_quota_loop` only adopts it when `o["at"] > our last value`,
      so widening never **goes back** to an older value (2026-09-09, paired with the `_wait_hint` backoff raise).
    """
    cap = fresh_s if fresh_s is not None else OMC_FRESH_S
    if _omc_shared_foreign():
        return None
    found = []
    for path in (OMC_CACHE5, OMC_CACHE):
        try:
            st = os.stat(path)
        except OSError:
            continue
        if time.time() - st.st_mtime <= cap:
            found.append((st.st_mtime, path, st))
    # 3.x and 5.x may both be installed or left over: freshest usable file wins.
    for _mt, path, st in sorted(found, key=lambda x: x[0], reverse=True):
        r = _omc_read(path, st)
        if r is not None:
            return r
    return None


# ⚠OMC derives its cache path from CLAUDE_CONFIG_DIR/plugins and does not key keychain logins by account, so
#   another root whose `plugins` resolves to ours writes its own account's numbers into the primary's cache file.
OMC_TRUST_TTL_S = 30
_omc_trust = {"at": 0.0, "foreign": None}


def _omc_shared_foreign():
    """Label of a non-primary root sharing our plugins dir while signed in to another account; None = cache trusted."""
    now = time.time()
    if now - _omc_trust["at"] < OMC_TRUST_TTL_S:
        return _omc_trust["foreign"]
    from sidereus import claude_roots, quota_roots     # quota_roots imports this module (same check as quota_roots._targets)
    prim = _cc_account()
    mine = os.path.realpath(os.path.dirname(os.path.dirname(OMC_CACHE5)))
    hit = None
    for r in claude_roots.accounts():
        if r.get("primary"):
            continue
        try:
            if os.path.realpath(os.path.join(r["dir"], "plugins")) != mine:
                continue
        except (OSError, ValueError, KeyError):
            continue
        uid = quota_roots._root_uuid(r["dir"])
        if uid and prim and uid != prim:      # unknown on either side is not a mismatch (same rule as `_cc_account`)
            hit = r.get("label") or "?"
            break
    prev = _omc_trust["foreign"]
    _omc_trust["at"], _omc_trust["foreign"] = now, hit
    # A shared plugins dir is a steady layout, not a fault: note it once per change, not on every TTL recheck
    # (each recheck re-counted the soft warning until it reached the strip as "still slow").
    if hit and hit != prev:
        warn_once("omc-shared-foreign", "OMC cache not read or written — its plugins dir is shared with account {acct}, "
                  "so it would mix the two accounts' quota", soft=True, vars={"acct": hit})
    return hit


def _omc_read(path, st):
    """Parse one OMC cache file into our quota shape; None when unusable."""
    # ⚠**This file is written by the OMC plugin — outside our control.** So the top level may not be an object
    #   (`null`·array·number) and `json.load` lets it through. The `.get`s below used to sit **outside** this
    #   try, raising `AttributeError`; even when the loop guard caught it, it blew up at the same spot every 25s
    #   and quota refresh effectively stopped forever. If it does not parse, return «unknown» (None), not 0.
    try:
        with open(path, encoding="utf-8") as f:
            c = json.load(f)
        if not isinstance(c, dict):
            warn_once("omc-top-shape",
                      "OMC cache top level is not an object ({err}) — quota comes from the API only",
                      vars={"err": type(c).__name__})
            return None
        d = c.get("data")
        if not isinstance(d, dict):
            d = {}          # `data: null` is OMC's normal failure form after its own 429 (see comment above)
        if c.get("error") or d.get("fiveHourPercent") is None:
            return None
        if c.get("sidereus"):
            return None      # ★this is a value we wrote — re-reading it would falsely revive its age (see comment above)
        # 5.x backoff entries and non-Anthropic providers (e.g. zai) are not our account's quota.
        if c.get("rateLimited") or c.get("source") not in (None, "anthropic"):
            return None
        out = {"five_hour": {"pct": d.get("fiveHourPercent"), "resets_at": d.get("fiveHourResetsAt")}}
        if d.get("weeklyPercent") is not None:
            out["seven_day"] = {"pct": d.get("weeklyPercent"), "resets_at": d.get("weeklyResetsAt")}
        return {"data": out, "at": (c.get("timestamp") or st.st_mtime * 1000) / 1000, "src": "omc"}
    except Exception as e:
        warn_once("omc-parse",
                  "Could not parse the OMC cache ({err}) — quota comes from the API only", vars={"err": type(e).__name__})
        return None


# ★★**We write the OMC cache for OMC** (2026-09-04, refresh kept failing).
#   It used to be the reverse — read the OMC file first, call the API only when stale. Why that broke:
#     measured 13:49 — OMC cache was `{"data": null, "error": true}`, i.e. **OMC was getting 429s too.**
#     And OMC's failure TTL is 15s, so **it knocks more often (4/min) while failing.**
#     With us knocking too it was 4.5/min, both got 429 → screen showed "8 min old" (official 84% · screen 79%).
#   ⇒ Root cause: two pollers sharing the same endpoint's limit with the same token.
#     **Reduce to one.** Sidereus calls every 25s and on success writes the value to the cache file in OMC format.
#     OMC passes `isCacheValid` (30s on success) and **skips its own API call** (`getUsage()` in
#     dist/hud/usage-api.js returns the cache as-is when valid — verified in code).
#   Result: 4.5 req/min → 2.4 req/min (one client) · staleness cap 25s + backoff · statusline and
#     Sidereus show **the same value** (previously two different values were displayed).
#   ⚠When we fail we do not touch the file — if OMC's own attempt succeeds we pick up that value (free).
def _omc_cache_write(out, hold=False):
    """Write our value to the OMC cache file in OMC format.

    `hold=True` is a call **while our fetch is failing**. The timestamp is still written as now so
    OMC passes its 30s TTL — that keeps **a single knocking client** inside the 429 window
    (measured 2026-09-04: without it OMC knocks every 15s, overwrites the file with `error:true`,
    and our screen and the statusline each hold a different stale value).
    ⚠The age limit was **removed** (2026-09-04). The rule that released the file after 10 min released OMC's
      15s retries at that moment and made the 429 worse — the recovery aid backfired.
      Instead an `sidereus` marker in the file keeps **our fallback from re-reading this value** (breaks the cycle).
      If Sidereus dies the file stops updating, so OMC sees the TTL expire and resumes its own fetches.
      (OMC uses timestamp only for the TTL check and does not print age — verified in usage-api.js.)
    """
    # ⚠A shared plugins dir is also the other account's HUD cache — our numbers there would be shown as theirs.
    if _omc_shared_foreign():
        return
    try:
        # ⚠Write only into an OMC install that exists — never create the plugin's dir on a machine without it.
        paths = [p for p in (OMC_CACHE, OMC_CACHE5) if os.path.isdir(os.path.dirname(p))]
        if not paths:
            return
        fh = (out or {}).get("five_hour") or {}
        sd = (out or {}).get("seven_day") or {}
        if fh.get("pct") is None:
            return
        d = {"fiveHourPercent": fh.get("pct"), "weeklyPercent": sd.get("pct") or 0,
             "fiveHourResetsAt": fh.get("resets_at"), "weeklyResetsAt": sd.get("resets_at")}
        # ★★Leave both **a marker that we wrote it and the real measurement time** (found by measurement 2026-09-04).
        #   Without it there is a cycle: we stamp `timestamp=now` in hold → our fallback reads that file and adopts
        #   it as "just now" → screen age revives to 22s. The value is 20 min old but the screen
        #   says fresh — the same symptom the user got angry about in the morning, in a new form.
        #   With the `sidereus` marker, `_quota_from_omc()` **treats the file as our own and ignores it**.
        #   OMC ignores unknown keys, so its TTL check is unaffected.
        # swap atomically — OMC must never read a half-written file
        # ⚠5.x drops data older than 15 min by `lastSuccessAt` and never matches a file carrying
        #   rateLimited/backoff/credentialIdentity keys — so write exactly these keys, one payload for both files.
        at = int((out or {}).get("at") or 0)
        body = json.dumps(
            {"timestamp": int(time.time() * 1000), "data": d, "error": False, "source": "anthropic",
             "lastSuccessAt": at * 1000, "sidereus": True, "sidereusAt": at,
             "sidereusHold": bool(hold)}, ensure_ascii=False, indent=2).encode("utf-8")
        for p in paths:
            _atomic_write(p, body, tmp=p + ".sidereus.tmp")
    except OSError as e:
        warn_once("omc-write", "OMC cache write failed ({err}) — the OMC HUD shows old values",
                  soft=True, vars={"err": f"{type(e).__name__}: {e}"})
    except Exception as e:
        warn_once("omc-write", "Could not write the OMC cache ({err})", vars={"err": type(e).__name__}, soft=True)
