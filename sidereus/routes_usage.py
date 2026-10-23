"""Usage GET route handlers (otel · live · quota burn · weekly usage; split out of routes_get.py) — a mixin `_GetRoutes` inherits.
Also owns `_acct_of_dir`/`_agent_quota` (routes_get imports `_agent_quota` back for the agent brief)."""
import json
import os
import time
from urllib.parse import parse_qs

from sidereus.usage import LIVE_SEC, LIVE_STEP
from sidereus.otel import _otel, _otel_lock, _otel_sample, _otel_stat, _otel_src_cmp, _otel_src_win
from sidereus.burn import WK_DAYS, _WK_RANGES, _live_buckets, _wk_slot, _wkuse_busy, burn_use, quota_burn, quota_burn_acct, quota_burn_peek, wk_stale, wkuse, wkuse_refresh
from sidereus.claude_roots import accounts as claude_accounts
from sidereus.saver_cap import cap as saver_cap
from sidereus.warn import warn_once
from sidereus.agent_brief import brief_quota
from sidereus.routes_struct import _q1


def _acct_of_dir(d):
    """Account row whose config dir realpath-matches `d`, else None. The path itself is never opened."""
    try:   # ⚠a NUL byte makes realpath raise ValueError on 3.9
        rp = os.path.realpath(os.path.expanduser(d))
        return next((r for r in claude_accounts() if r.get("dir") and os.path.realpath(r["dir"]) == rp), None)
    except ValueError:
        return None


def _agent_quota(d):
    """`/api/agent/quota[?dir=]` — the calling session's account; an unknown dir never gets the primary's numbers."""
    if not d:
        return brief_quota()
    hit = _acct_of_dir(d)
    if not hit:
        return {"ok": False, "err": "unknown account"}
    return brief_quota(acct=hit.get("label"))


class _UsageRoutes:
    def _g_otel(self, u):
        # Diagnostic — which sessions are sending telemetry (if absent, that session started without the env)
        q = parse_qs(u.query)
        try:
            h = min(192, max(1, int((q.get("h") or ["5"])[0])))
        except ValueError:
            h = 5
        if _q1(q, "cmp") == "1":
            return self._send(200, json.dumps(_otel_src_cmp(h), ensure_ascii=False, indent=1),
                              "application/json; charset=utf-8")
        with _otel_lock:
            snap = {k: {"ev": v.get("ev"), "tool": v.get("tool"), "tokens": v.get("tokens"),
                        "ago": int(time.time() - (v.get("at") or 0)), "seq": v.get("seq")}
                    for k, v in _otel.items()}
        snap["_sample_api_request"] = dict(_otel_sample)
        with _otel_lock:
            # ⚠Copy nested dicts under the lock — ingest mutates bySrc/names while json.dumps runs outside it.
            st = {k: (dict(v) if isinstance(v, dict) else v) for k, v in _otel_stat.items()}
        now2 = time.time()
        st["postAgo"] = int(now2 - st["lastPost"]) if st["lastPost"] else None
        st["keptAgo"] = int(now2 - st["lastKept"]) if st["lastKept"] else None
        st["bySrcWin"] = _otel_src_win(h)     # persisted 5-min buckets — survives restarts (bySrc does not)
        snap["_stat"] = st
        return self._send(200, json.dumps(snap, ensure_ascii=False, indent=1),
                          "application/json; charset=utf-8")

    def _g_live(self, u):
        # ★Live-only lightweight endpoint (2026-09-04: live must move in real time).
        #   `/api/wkuse` carries today's per-project totals, donut and burn, tied to a 30s cycle.
        #   This is served separately so only the live sparkline can be fetched every 3s — the computation is a single bucket fold.
        body = json.dumps({"live": _live_buckets(), "liveSec": LIVE_SEC,
                           "liveStep": LIVE_STEP, "at": int(time.time())},
                          ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _g_quota_burn(self, u):
        # ★Limit burndown — current 5h cycle consumption curve + extrapolation to reset + past-cycle baseline.
        #   Light (TTL 30s cache + incremental tail read) — the screen calls it piggybacked on token-area polling.
        # `?dir=` picks the account by config dir (realpath match only); the path itself is never opened.
        _d = (parse_qs(u.query).get("dir") or [""])[0]
        lab = None
        if _d:
            hit = _acct_of_dir(_d)
            if not hit:
                self._raw_json(400, {"ok": False})
                return
            lab = None if hit.get("primary") else hit["label"]
        try:
            out = quota_burn() if lab is None else quota_burn_acct(lab)
        except Exception as e:
            out = {"ok": False, "why": f"{type(e).__name__}: {e}"}
        try:   # `use` = account in use (burn_use); the cap reads that account's body whichever was asked
            use = burn_use()
            out = dict(out, use=use)   # ⚠copy — `out` may be the cached body
            ub = out if lab == (None if use["primary"] else use["label"]) else None
        except Exception as e:
            use, ub = None, out
            warn_once("burn-use", "account-in-use pick failed ({err}) — cap from the asked account", soft=True,
                      vars={"err": type(e).__name__})
        try:   # concurrency cap for the saver hook
            if ub is None:
                # ⚠cache only for the primary: a cold quota_burn() scan (636 ms warm disk, 6-20 s after reboot) vs the hook's 3 s timeout
                ub = (quota_burn_peek() or out) if use["primary"] else quota_burn_acct(use["label"])
            out = dict(out, cap=saver_cap(time.time(), ub))
        except Exception as e:
            warn_once("saver-cap", "concurrency cap failed ({err}) — responding without cap", soft=True,
                      vars={"err": type(e).__name__})
        self._raw_json(200, out)

    def _g_wkuse(self, u):
        _q = parse_qs(u.query)
        # ★Period (days). Unknown values fall back to default — accepting arbitrary large values makes ccusage run for minutes.
        try:
            _rg = int((_q.get("range") or [WK_DAYS])[0])
        except ValueError:
            _rg = WK_DAYS
        if _rg not in _WK_RANGES:
            _rg = WK_DAYS
        # Account pick: only a known label (it keys a slot); anything else = all accounts.
        _ac = _q1(_q, "acct") or ""
        if _ac not in {a.get("label") for a in claude_accounts()}:
            _ac = ""
        # If that period was never measured, fire now (do not await — ccusage takes over 30s)
        if _ac:
            if _q1(_q, "force") == "1" or wk_stale(_rg, _ac):   # ⚠per-account slots are not in _wkuse_loop
                wkuse_refresh(_rg, _ac)
        elif _q1(_q, "force") == "1" or not (_wk_slot(_rg).get("at") or 0):
            wkuse_refresh(_rg)                    # Fire in background and return the current value right away
        out = wkuse(_rg, _ac) if _ac else wkuse(_rg)
        out["busy"] = _wkuse_busy[0]
        self._raw_json(200, out)
