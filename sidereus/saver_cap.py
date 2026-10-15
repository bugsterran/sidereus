"""Calculated subagent concurrency cap (`cap` block of `/api/quota/burn`) for the saver hook.

n = clamp(floor(avail_tpm / per_tpm) - running, 0, CAP_MAX). Metadata only: counts and token numbers.
⚠avail_tpm and per_tpm are RAW tokens per minute — the hook divides by 1e6 for its «M/min» line.
⚠Both use one counter: input + output + cache_read + cache_creation, unweighted (ccusage `totalTokens`).
  `head.eff` is back-computed from `_tok_events` (timeline_scan `_line_tokens`, that sum) and the usage index
  buckets `[in, out, cc, cr]` are summed the same way here — weighting only one side skews n by the cache-read share.
"""
import math
import os
import time
from sidereus.bgtasks import SUB_LIVE_S
from sidereus.sessions import sessions_snapshot
from sidereus.usage_index import _uidx, _uidx_lock

SAFETY = 0.8              # share of the per-minute headroom handed out
CAP_MAX = 6
CAP_LOW_MAX = 2           # headroom from a stale/estimated denominator (head.src not win/recent)
PER_WIN_S = 2 * 3600      # subagents that ended within this window feed the median
PER_MIN_N = 5             # fewer samples => PER_TPM_EST
PER_TPM_EST = 1_000_000   # fallback tokens/min per subagent (raw total incl. cache reads)
PER_MIN_DUR = 60          # ⚠a 5 s run would read as a huge rate — floor the duration
_SUB_SEP = os.sep + "subagents" + os.sep
_WORKING = ("tool", "think")


def _ended_runs(now):
    """[(start, end, tok)] of subagent transcripts that ended within PER_WIN_S (usage index; no refresh here)."""
    with _uidx_lock:
        items = [(fp, e.get("mt") or 0, e.get("h")) for fp, e in _uidx["files"].items() if _SUB_SEP in fp]
    out = []
    for fp, mt, h in items:
        try:
            end = float(mt)
        except (TypeError, ValueError):
            continue
        if not (now - PER_WIN_S <= end <= now - SUB_LIVE_S) or not isinstance(h, dict):
            continue                     # still live (or too old): not an ended sample
        tok = 0
        for mm in list(h.values()):
            if not isinstance(mm, dict):
                continue
            for v in list(mm.values()):
                try:
                    tok += int(v[0]) + int(v[1]) + int(v[2]) + int(v[3])
                except (TypeError, ValueError, IndexError, KeyError):
                    continue
        try:
            st = os.stat(fp)
            start = float(getattr(st, "st_birthtime", st.st_ctime))
        except OSError:
            continue
        out.append((start, end, tok))
    return out


def _per_tpm(now):
    """(median tokens/min of ended subagents, "meas") or (PER_TPM_EST, "est")."""
    rates = sorted(tok / (max(PER_MIN_DUR, e - s) / 60.0) for s, e, tok in _ended_runs(now) if tok > 0)
    if len(rates) < PER_MIN_N:
        return float(PER_TPM_EST), "est"
    m = len(rates) // 2
    return (rates[m] if len(rates) % 2 else (rates[m - 1] + rates[m]) / 2.0), "meas"


def _running(rows):
    """Live subagents + working main sessions across all sessions, minus the asking session (>= 0)."""
    k = 0
    for r in rows or []:
        if r.get("state") in _WORKING:
            k += 1
        k += len(r.get("sub") or [])
        for w in r.get("wf") or []:
            if w.get("run"):
                k += sum(1 for a in w.get("agents") or [] if a.get("st") == "run")
    return max(0, k - 1)


def cap(now=None, body=None):
    """`{n, avail_tpm, per_tpm, per_src, running, conf}` from a quota_burn body."""
    now = time.time() if now is None else now
    b = body or {}
    head, cur = b.get("head") or {}, b.get("cur") or {}
    eff, left = head.get("eff"), cur.get("left")
    if not head and b.get("acct"):   # non-primary body has no back-solve: tighter of the history 5h/7d left (conf low)
        e = b.get("est") or {}
        ls = [v for v in (e.get("h5_left"), e.get("wk_left")) if isinstance(v, (int, float)) and not isinstance(v, bool)]
        eff = min(ls) if ls else None
    per, src = _per_tpm(now)
    rows = sessions_snapshot()
    run = _running(rows)
    conf = "high" if head.get("src") in ("win", "recent") and rows is not None else "low"
    # ⚠avail None = not measured (no head/cur, e.g. a «stale» body after the reset); 0 = measured empty.
    #   Printing None as «0.0M/min» read as a real zero headroom.
    avail = None
    if isinstance(eff, (int, float)) and isinstance(left, (int, float)) and left > 0:
        avail = max(0.0, eff) / (left / 60.0) * SAFETY
    n = 0
    if avail and per > 0:
        n = max(0, min(CAP_MAX, int(math.floor(avail / per)) - run))
    if conf == "low":
        n = min(n, CAP_LOW_MAX)
    return {"n": n, "avail_tpm": (None if avail is None else int(avail)), "per_tpm": int(per), "per_src": src,
            "running": run, "conf": conf}
