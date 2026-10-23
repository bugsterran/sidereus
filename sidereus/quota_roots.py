"""Per-account 5h/7d quota for extra signed-in Claude config roots (display only; the primary stays in `quota`).

`tick()` runs once at the top of each primary poll (`quota_loop._quota_tick`), never sleeps, and fetches only the
roots that are due. Each root keeps its own fail count and Retry-After, so one root's 429 never touches another
root or the primary `_quota`/`_quota_retry_after`.
⚠Do not call `quota_fetch._qf_request`/`_qf_parse` here — they write the primary `_quota["err"]`/`_quota_retry_after`.
⚠Tokens stay in locals: never logged, stored, put in an error string or sent anywhere but api.anthropic.com.
Output is metadata only: label + percentages + reset times (no email, uuid or dir).
"""
import hashlib
import json
import os
import subprocess
import threading
import time

from sidereus.config import DATA_DIR, IS_MAC, claude_home
from sidereus.bus import _atomic_write
from sidereus import claude_roots
from sidereus.transcript import _iso_ts
from sidereus.warn import exc_name, warn_once
from sidereus.quota import (OMC_FRESH_S, QUOTA_MAX_BACKOFF, QUOTA_URL, _cc_account, _min_iso, _quota_interval,
                         _quota_lookup_on)

USER_HOME = os.path.expanduser("~")    # ⚠tests patch this to a tmp dir
SVC = "Claude Code-credentials"
OMC_REL = os.path.join("plugins", "oh-my-claudecode", ".usage-cache-anthropic.json")
ERR_NO_TOKEN = "no token"

_acc = {}               # label -> {data, at, err, next, fail, acct}
_acc_lock = threading.Lock()
_uuid_cache = {}        # .claude.json path -> (mtime, accountUuid)
PTS_FILE = os.path.join(DATA_DIR, "quota-roots-pts.json")   # ⚠never quota-log: that log is the primary's alone
PTS_CAP = 300
RESET_TOL = 120         # s — resets_at jitter within this is the same 5h window (burn_calc.QBURN_TOL)
# ⚠A failed refetch (429) keeps the last data with `err` set; readers must still use it, or the account's numbers vanish
#   while the backoff runs. Past this age (the screen's own «very old» mark, 55a qhot) kept data counts as unmeasured.
ROW_KEEP_S = 1800
_pts = {}               # label -> {acct: sha1(uid)[:12], reset5: epoch, pts: [[t, pct]]}, under _acc_lock
_pts_loaded = False


def _is_default_root(d):
    return os.path.realpath(d) == os.path.realpath(os.path.join(USER_HOME, ".claude"))


def _conf_path(d):
    # ~/.claude keeps its account file next to it (~/.claude.json); any CLAUDE_CONFIG_DIR root keeps it inside.
    return os.path.join(USER_HOME, ".claude.json") if _is_default_root(d) else os.path.join(d, ".claude.json")


def _root_uuid(d):
    """accountUuid of the root's signed-in account (uuid only, mtime-cached); None when signed out or unreadable."""
    p = _conf_path(d)
    try:
        mt = os.path.getmtime(p)
    except OSError:
        return None
    hit = _uuid_cache.get(p)
    if hit and hit[0] == mt:
        return hit[1]
    try:
        with open(p, encoding="utf-8") as f:
            j = json.load(f)
        uid = ((j.get("oauthAccount") or {}).get("accountUuid") or None) if isinstance(j, dict) else None
    except (OSError, ValueError, AttributeError):
        return None
    _uuid_cache[p] = (mt, uid)
    return uid


def _targets():
    """[(root, uuid)] — non-primary accounts (incl. shared-history profiles) signed in to an account other than the primary's."""
    prim = _cc_account()
    out = []
    for r in claude_roots.accounts():
        if r.get("primary"):
            continue
        uid = _root_uuid(r["dir"])
        if uid and uid != prim:
            out.append((r, uid))
    return out


def _svc_names(d):
    """Keychain service names Claude Code may have used for root `d`.

    ⚠Claude Code hashes the **raw** CLAUDE_CONFIG_DIR string (sha256, first 8 hex), so `~/x`, `/abs/x` and
    `/abs/x/` give different services — try each spelling. ~/.claude itself uses the plain service name."""
    if _is_default_root(d):
        return [SVC]
    ab = os.path.abspath(d)
    raws = [ab, ab + "/"]
    rel = os.path.relpath(ab, USER_HOME)
    if not rel.startswith(".."):
        raws.append("~/" + rel)
    out = []
    for s in raws:
        n = SVC + "-" + hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]
        if n not in out:
            out.append(n)
    return out


def _sec(args):
    return subprocess.run(["security", "find-generic-password"] + args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=10)


def _kc_token(d):
    # Existence check first (exit code only, no -w): the secret is read only for the one service that exists.
    for svc in _svc_names(d):
        try:
            if _sec(["-s", svc]).returncode != 0:
                continue
            r = _sec(["-s", svc, "-w"])
            if r.returncode != 0:
                return None
            j = json.loads(r.stdout.strip())
            return (j.get("claudeAiOauth") or {}).get("accessToken") or j.get("accessToken")
        except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
            return None
    return None


def _file_token(d):
    try:
        with open(os.path.join(d, ".credentials.json"), encoding="utf-8") as f:
            j = json.load(f)
        return (j.get("claudeAiOauth") or {}).get("accessToken") or None
    except (OSError, ValueError, AttributeError):
        return None


def _token(d):
    if not _quota_lookup_on():
        return None
    return (_kc_token(d) if IS_MAC else None) or _file_token(d)


def _retry_after(e):
    try:
        h = getattr(e, "headers", None)
        v = (h.get("Retry-After") or h.get("retry-after")) if h is not None else None
        return max(0, min(int(float(str(v).strip())), 3600)) if v else 0
    except (ValueError, TypeError, AttributeError):
        return 0


def _request(tok):
    """-> (body, err, retry_after). `err` is an error class name + HTTP code only (never the token)."""
    import urllib.request
    req = urllib.request.Request(QUOTA_URL, headers={
        "Authorization": "Bearer " + tok, "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": "claude-cli/2.1.232 (external, cli)", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:  # nosec B310 -- constant https URL
            return json.loads(resp.read().decode("utf-8")), None, 0
    except Exception as e:
        code = getattr(e, "code", None)
        return None, exc_name(e) + (" %s" % code if code else ""), _retry_after(e)


def _parse(body):
    """Response -> {five_hour, seven_day} slots; None when the shape is not usable."""
    if not isinstance(body, dict):
        return None
    out = {}
    for k in ("five_hour", "seven_day"):
        v = body.get(k)
        if v is None and k in body:
            out[k] = {"pct": 0, "resets_at": None}      # null in a successful response = nothing used yet
        elif isinstance(v, dict) and v.get("utilization") is not None:
            out[k] = {"pct": v.get("utilization"), "resets_at": v.get("resets_at")}
    return out or None


def _omc_path(d):
    """This root's own OMC cache, or None. ⚠Never when `plugins` is a symlink or the primary's plugins dir —
    writing there would overwrite the primary account's HUD value with another account's numbers."""
    pl = os.path.join(d, "plugins")
    try:
        if os.path.islink(pl) or not os.path.isdir(pl):
            return None
        if os.path.realpath(pl) == os.path.realpath(os.path.join(claude_home(), "plugins")):
            return None
        p = os.path.join(d, OMC_REL)
        od = os.path.dirname(p)
        # ⚠A symlinked oh-my-claudecode subdir can still land in the primary's cache dir.
        if not os.path.isdir(od) or os.path.realpath(od) == os.path.realpath(os.path.join(claude_home(), os.path.dirname(OMC_REL))):
            return None
    except (OSError, ValueError):
        return None
    return p


def _omc_read(d):
    p = _omc_path(d)
    if not p:
        return None
    try:
        if time.time() - os.path.getmtime(p) > OMC_FRESH_S:
            return None
        with open(p, encoding="utf-8") as f:
            c = json.load(f)
        x = c.get("data") if isinstance(c, dict) else None
        if (not isinstance(x, dict) or c.get("sidereus") or c.get("error") or c.get("rateLimited")
                or c.get("source") not in (None, "anthropic") or x.get("fiveHourPercent") is None):
            return None     # ours (sidereus marker), a failure entry or another provider
        out = {"five_hour": {"pct": x.get("fiveHourPercent"), "resets_at": x.get("fiveHourResetsAt")}}
        if x.get("weeklyPercent") is not None:
            out["seven_day"] = {"pct": x.get("weeklyPercent"), "resets_at": x.get("weeklyResetsAt")}
        return {"data": out, "at": float(c.get("timestamp") or 0) / 1000}
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _omc_write(d, data, at):
    """Same payload shape as `quota._omc_cache_write` (sidereus marker, so our own reader skips it)."""
    p = _omc_path(d)
    fh, sd = (data or {}).get("five_hour") or {}, (data or {}).get("seven_day") or {}
    if not p or fh.get("pct") is None:
        return
    body = {"timestamp": int(time.time() * 1000), "error": False, "source": "anthropic",
            "data": {"fiveHourPercent": fh.get("pct"), "weeklyPercent": sd.get("pct") or 0,
                     "fiveHourResetsAt": fh.get("resets_at"), "weeklyResetsAt": sd.get("resets_at")},
            "lastSuccessAt": int(at) * 1000, "sidereus": True, "sidereusAt": int(at), "sidereusHold": False}
    try:
        _atomic_write(p, json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8"), tmp=p + ".sidereus.tmp")
    except OSError:
        return      # the HUD keeps its own value; our row is unaffected


def _reset_ep(v):
    t = _iso_ts(v.get("resets_at")) if isinstance(v, dict) and v.get("resets_at") else None
    return int(round(t / 60.0) * 60) if t else None


def _same_reset(a, b):
    return a == b or (a is not None and b is not None and abs(a - b) <= RESET_TOL)


def _pts_save():
    """Caller holds _acc_lock. Metadata only: hashed account, epochs and percentages."""
    try:
        _atomic_write(PTS_FILE, json.dumps(_pts, separators=(",", ":")).encode("utf-8"), mkdir=True)
    except OSError as x:      # the ring stays in memory; next change retries
        warn_once("quota-roots-pts", "quota_roots pts save failed ({err})", vars={"err": exc_name(x)}, soft=True)


def _pts_load():
    """Caller holds _acc_lock. Once per process; a bad file is an empty ring."""
    global _pts, _pts_loaded
    _pts_loaded = True
    try:
        with open(PTS_FILE, encoding="utf-8") as f:
            j = json.load(f)
    except (OSError, ValueError):
        return
    if not isinstance(j, dict):
        return
    num = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool)
    # Keep only [epoch, pct] points: a malformed one would raise later and blank the accounts popover.
    for k, v in j.items():
        if isinstance(v, dict) and isinstance(v.get("pts"), list):
            v["pts"] = [p for p in v["pts"] if isinstance(p, list) and len(p) == 2 and num(p[0]) and num(p[1])]
            _pts[k] = v


def _pts_add(label, uid, out, now):
    """Record the 5h used-% step for `label`: a new account or window clears the ring; same % adds nothing."""
    fh = out.get("five_hour") or {}
    pct = fh.get("pct")
    if not isinstance(pct, (int, float)) or isinstance(pct, bool):
        return
    # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1 -- persisted account tag, not security
    ah, r5 = hashlib.sha1(uid.encode("utf-8"), usedforsecurity=False).hexdigest()[:12], _reset_ep(fh)
    with _acc_lock:
        g = _pts.get(label)
        if not g or g.get("acct") != ah or not _same_reset(g.get("reset5"), r5):
            g = {"acct": ah, "reset5": r5, "pts": []}
        elif g["pts"] and g["pts"][-1][1] == pct:
            return
        g["pts"] = (g["pts"] + [[int(now), pct]])[-PTS_CAP:]
        _pts[label] = g
        _pts_save()


def ring_last():
    """{label: (reset5, last step time)} of each extra root's 5h ring; metadata only (`burn.burn_use`)."""
    with _acc_lock:
        if not _pts_loaded:
            _pts_load()
        return {k: (g.get("reset5"), g["pts"][-1][0]) for k, g in _pts.items()
                if isinstance(g, dict) and g.get("pts")}


def _fetch_one(r, uid, e, now):
    """Refresh one due root in place (`e` is a private copy; the caller stores it under the lock)."""
    if e.get("acct") != uid:
        e.update(data=None, at=0, fail=0, acct=uid)     # another account signed in to this root: drop its numbers
    tok = _token(r["dir"])
    if not tok:
        e.update(err=ERR_NO_TOKEN, next=now + _quota_interval())
        return
    body, err, ra = _request(tok)
    tok = None
    out = _parse(body) if err is None else None
    if out is not None:
        e.update(data=out, at=now, err=None, fail=0, next=now + _quota_interval())
        _omc_write(r["dir"], out, now)
        _pts_add(r["label"], uid, out, now)
        return
    o = _omc_read(r["dir"])
    if o and o["at"] > (e.get("at") or 0):
        e.update(data=o["data"], at=o["at"])
    e["fail"] = (e.get("fail") or 0) + 1
    wait = min(QUOTA_MAX_BACKOFF, 15 * (2 ** min(e["fail"], 6)))
    e.update(err=err or "shape", next=now + max(wait, ra))


def tick():
    """Fetch every due extra root once; no sleep. Roots that left (or signed out) are dropped."""
    if not _quota_lookup_on():
        return
    now = time.time()
    tg = _targets()
    with _acc_lock:
        if not _pts_loaded:
            _pts_load()
        keep = {r["label"] for r, _u in tg}
        for lab in [k for k in _acc if k not in keep]:
            del _acc[lab]
        gone = [k for k in _pts if k not in keep]
        for lab in gone:
            del _pts[lab]
        if gone:
            _pts_save()
    for r, uid in tg:
        with _acc_lock:
            e = dict(_acc.get(r["label"]) or {"data": None, "at": 0, "err": None, "next": 0, "fail": 0})
        if now < (e.get("next") or 0) and e.get("acct") == uid:
            continue
        try:
            _fetch_one(r, uid, e, now)
        except Exception as x:      # one root's odd state must not stop the others or the primary poll
            e.update(err=type(x).__name__, next=now + _quota_interval())
        with _acc_lock:
            _acc[r["label"]] = e


def row_usable(row):
    """True when an account row's numbers may be shown: no fetch error, or an error with kept data younger than ROW_KEEP_S."""
    if not row:
        return False
    age = row.get("age")
    return not row.get("err") or (isinstance(age, (int, float)) and not isinstance(age, bool) and age <= ROW_KEEP_S)


def _slot(v, now):
    t = _iso_ts(v.get("resets_at")) if v.get("resets_at") else 0
    r_at = v.get("resets_at")
    if t:
        t = round(t / 60.0) * 60      # same minute rounding as `quota.quota()`
        r_at = _min_iso(t)
    return {"pct": v.get("pct"), "resets_at": r_at, "leftSec": int(t - now) if t else None}


def quota_accounts():
    """[{label, five_hour, seven_day, age, err}] for each extra signed-in root; [] when none or lookup is off."""
    if not _quota_lookup_on():
        return []
    now = time.time()
    with _acc_lock:
        rows = [(k, dict(v)) for k, v in _acc.items()]
        rings = {k: (g.get("reset5"), [list(p) for p in g.get("pts") or []]) for k, g in _pts.items()}
    out = []
    for lab, e in rows:
        d = e.get("data") or {}
        if not d and e.get("err") in (None, ERR_NO_TOKEN):
            continue
        row = {"label": lab, "age": int(now - e["at"]) if e.get("at") else None, "err": e.get("err")}
        for k in ("five_hour", "seven_day"):
            if isinstance(d.get(k), dict):
                row[k] = _slot(d[k], now)
        g = rings.get(lab)
        # pts only for the window the row shows: an older window's steps would bend the forecast
        if g and len(g[1]) >= 2 and "five_hour" in row and _same_reset(g[0], _reset_ep(d["five_hour"])):
            row["five_hour"]["pts"] = g[1]
        out.append(row)
    return out
